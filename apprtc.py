#!/usr/bin/python2.4
#
# Copyright 2011 Google Inc. All Rights Reserved.

# pylint: disable-msg=C6310

"""WebRTC Demo

This module demonstrates the WebRTC API by implementing a simple video chat app.
"""

import datetime
import logging
import os
import random
import re
from google.appengine.api import channel
from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app


def generate_random(len):
  word = ''
  for i in range(len):
    word += random.choice('0123456789')
  return word

def sanitize(key):
  return re.sub("[^a-zA-Z0-9\-]", "-", key);

def make_token(room, user):
  return room.key().id_or_name() + '/' + user

def make_pc_config(stun_server):
  if stun_server:
    return "STUN " + stun_server
  else:
    return "STUN stun.l.google.com:19302"

    
            

class Room(db.Model):
  """All the data we store for a room"""
  user1 = db.StringProperty()
  user2 = db.StringProperty()
  user3 = db.StringProperty()
  usercount = db.IntegerProperty(default = 0)

  def __str__(self):
    str = "["
    if self.user1:
      str += self.user1
    if self.user2:
      str += ", " + self.user2
    if self.user3:
      str += ", " + self.user3
    str += "]"
    return str

  def get_occupancy(self):
    occupancy = 0
    if self.user1:
      occupancy += 1
    if self.user2:
      occupancy += 1
    if self.user3:
      occupancy += 1
    return occupancy

  def get_other_users(self, user):
    if user == self.user1:
        return [self.user2, self.user3]
    elif user == self.user2:
        return [self.user3, self.user1]
    elif user == self.user3:
        return [self.user1, self.user2]
    else:
        return None
    
  def has_user(self, user):
    return (user and (user == self.user1 or user == self.user2  or user == self.user3))
    #return (user and (user == self.user1 or user == self.user2))

  def add_user(self, user):
    count = self.usercount
    if not self.user1:
      self.user1 = user
      self.usercount = count + 1
    elif not self.user2:
      self.user2 = user
      self.usercount = count + 1
    elif not self.user3:
      self.user3 = user
      self.usercount = count + 1
    else:
      raise RuntimeError('room is full')
    self.put()

  def remove_user(self, user):
    if user == self.user3:
      self.user3 = None
    if user == self.user2:
      self.user2 = None
    if user == self.user1:
      if self.user2:
        self.user1 = self.user2
        self.user2 = None
      else:
        self.user1 = None
    if self.get_occupancy() > 0:
      self.put()
    else:
      self.delete()


class ConnectPage(webapp.RequestHandler):
  def post(self):
    key = self.request.get('from')
    room_key, user = key.split('/');
    logging.info('User ' + user + ' connected to room ' + room_key)

class OccupantsNumber(webapp.RequestHandler):
  def post(self):
      room_key = self.request.get('r')
      room = Room.get_by_key_name(room_key)
      no_of_occupant = room.usercount 
      #template_values = {
      #                  'no_of_occupant': no_of_occupant,
      #                 }
      #path = os.path.join(os.path.dirname(__file__), 'index.html')
      self.response.out.write(no_of_occupant)
      logging.info('No of occupants in the room: ' + str(no_of_occupant))
          
class DisconnectPage(webapp.RequestHandler):
  def post(self):
    key = self.request.get('from')
    room_key, user = key.split('/');
    logging.info('Removing user ' + user + ' from room ' + room_key)
    room = Room.get_by_key_name(room_key)
    if room and room.has_user(user):
      other_users = room.get_other_users(user)
      logging.info('Other users are ' + str(other_users).strip('[]'))
      for each_user in other_users:
          room.remove_user(user)
          logging.info('Room ' + room_key + ' has state ' + str(room))
          if each_user:
            channel.send_message(make_token(room, each_user), '{"type":"bye"}')
            logging.info('Sent BYE to ' + each_user)
    else:
      logging.warning('Unknown room ' + room_key)


class MessagePage(webapp.RequestHandler):
    def post(self):
        message = self.request.body
        room_key = self.request.get('r')
        room = Room.get_by_key_name(room_key)
        if room:
          user = self.request.get('u')
          other_users = room.get_other_users(user)
          logging.info('Other users are ' + str(other_users).strip('[]'))
          for each_user in other_users:
              if each_user:
                  # special case the loopback scenario
                  if each_user == user:
                      message = message.replace("\"offer\"", "\"answer\"")
                      message = message.replace("a=crypto:0 AES_CM_128_HMAC_SHA1_32",
                                                "a=xrypto:0 AES_CM_128_HMAC_SHA1_32")
                  channel.send_message(make_token(room, each_user), message)
                  logging.info('Delivered message to user ' + each_user);
        else:
          logging.warning('Unknown room ' + room_key)


class MainPage(webapp.RequestHandler):
  """The main UI page, renders the 'index.html' template."""
  
  def get(self):
    """Renders the main page. When this page is shown, we create a new
    channel to push asynchronous updates to the client."""      
    room_key = sanitize(self.request.get('r'));
    debug = self.request.get('debug')
    stun_server = self.request.get('ss');
    if not room_key:
      room_key = generate_random(8)
      redirect = '/?r=' + room_key
      if debug:
        redirect += ('&debug=' + debug)
      if stun_server:
        redirect += ('&ss=' + stun_server)
      self.redirect(redirect)
      logging.info('Redirecting visitor to base URL to ' + redirect)
      return

    user = None
    initiator = 0
        
    room = Room.get_by_key_name(room_key)
    
    if not room and debug != "full":
      # New room.
      user = generate_random(8)
      room = Room(key_name = room_key)
      room.add_user(user)
      
      #mike - autoincrement initiator FOR THIS USER **newly added
      #initiator += 1
            
      if debug != "loopback":
        #mike - change initiator to +=1
        initiator = 0
        
      else:
        room.add_user(user)
        #mike - autoincrement initiator
        initiator = 1
        
        #swap nextline with below
    #elif room and room.get_occupancy() == 1 and debug != "full":
    elif room and room.get_occupancy() <= 3 and debug != "full":
      # 1 occupant.
      user = generate_random(8)
      room.add_user(user)
      #swap next line with below
      initiator += 1
             
    else:
      # 2 occupants (full).
      path = os.path.join(os.path.dirname(__file__), 'full.html')
      self.response.out.write(template.render(path, { 'room_key': room_key }));
      logging.info('Room ' + room_key + ' is full');
      return

    no_of_occupant = room.usercount 
    room_link = 'https://apprtc.appspot.com/?r=' + room_key
    if debug:
      room_link += ('&debug=' + debug)
    if stun_server:
      room_link += ('&ss=' + stun_server)
      
    token = channel.create_channel(room_key + '/' + user)
    other_users = room.get_other_users(user)
    logging.info('Other users are ' + str(other_users).strip('[]'))
    secondtoken = ''
    other_room_no = ''
    #another_room_key = generate_random(8)
    #secondtoken = channel.create_channel(another_room_key + '/' + user)
    #other_room_no = 'SERVER_ADDRESS/?r=' + another_room_key
    for each_user in other_users:
        if each_user:
            secondtoken = channel.create_channel(room_key + '/' + each_user)
            other_room_no = 'SERVER_ADDRESS/?r=' + room_key
    
    pc_config = make_pc_config(stun_server)
    template_values = {'token': token,
                       'second_token': secondtoken,
                       'me': user,
                       'room_key': room_key,
                       'room_link': room_link,
                       'other_room_no': other_room_no,
                       'initiator': initiator,
                       'no_of_occupant': no_of_occupant,
                       'pc_config': pc_config
                      }
    path = os.path.join(os.path.dirname(__file__), 'index.html')
    self.response.out.write(template.render(path, template_values))
    logging.info('User ' + user + ' added to room ' + room_key);
    logging.info('Room ' + room_key + ' has state ' + str(room))


application = webapp.WSGIApplication([
    ('/', MainPage),
    ('/message', MessagePage),
    ('/occupants', OccupantsNumber),
    ('/_ah/channel/connected/', ConnectPage),
    ('/_ah/channel/disconnected/', DisconnectPage)
  ], debug=True)


def main():
  run_wsgi_app(application)

if __name__ == "__main__":
  main()
