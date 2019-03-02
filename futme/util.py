# -*- coding: utf-8 -*-

from twilio.rest import Client

from . import datafile

twilio = datafile.load_json('credentials.json')['twilio']
client = Client(twilio['account_sid'], twilio['auth_token'])

def sorter(item, descending=True):
    val = item['rating'] * 1e15 + item['discardValue'] * 1e12 + item['assetId'] * 1e6 + item['resourceId']
    if descending:
        val = -val
    return val

def sorter_key(descending=True):
    return lambda x: sorter(x)

def sms(msg):
    client.messages.create(body=msg, from_=twilio['from'], to=twilio['to'])
