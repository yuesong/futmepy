# -*- coding: utf-8 -*-

import logging
import os
import sys
import time

import fut
import requests

from . import datafile
from .club import Club
from .display import Display
from .lookup import Lookups
from .process import Proc
from .transfer import TransferMarket

logger = logging.getLogger(__name__)

class Futme(object):

    def __init__(self):
        self.db_dir = os.path.expanduser('~/.futme')
        self.lu = Lookups(self.db_dir)
        self.tm = TransferMarket(self)
        self.disp = Display(self)
        self.proc = Proc(self)
        self.club = Club(self)
        self._session = None
        logger.info('Ready to FUTME!')

    def session(self):
        if self._session is None:
            self.login()
        return self._session

    def login(self):
        logger.info('Logging in to FUT...')
        creds = datafile.load_json('credentials.json')
        self._session = fut.Core(creds['email'], creds['password'], creds['secret'], platform='ps4', sms=True)
        logger.info('Logged in')
        return self._session

    def shutdown(self):
        if self._session is not None:
            self._session.logout()
