# -*- coding: utf-8 -*-

import logging
import time

import fut

from . import datafile
from .autotrader import AutoTrader
from .core import Futme
from .util import sms
from .worker import LoopyWorker

logger = logging.getLogger(__name__)

class AutoPilot:

    def __init__(self, fme, conf_file):
        self.fme = fme
        self.conf = datafile.load_json(conf_file)
        self.min_coins = self.conf['min_coins']

        self.worker = LoopyWorker()
        self.reg_task('status', self.print_status)
        self.reg_task('refresh_tradepile', self.fme.proc.refresh_tradepile)
        self.reg_task('packs', self.fme.proc.packs)
        self.reg_task('consumeables', self.fme.proc.sell_excess_consumables)
        self.reg_task('check_traders', self.check_traders)

        self.buyers = AutoTrader(self.fme, self.conf['autotraders']['buyers'])
        self.flippers = AutoTrader(self.fme, self.conf['autotraders']['flippers'])

        self.round = 0


    def run(self):
        try:
            while True:
                self.round += 1
                self.worker.run()
                self.buyers.run()
                self.flippers.run()
                time.sleep(1)
        except Exception as e:
            logger.exception('Error in autopilot main loop')
            sms(repr(e))

    def reg_task(self, name, func):
        if name in self.conf:
            c = self.conf[name]
            interval = c['interval']
            delay = c.get('delay', 0)
            self.worker.register_task(name, func, interval, delay)

    def print_status(self):
        coins = self.fme.session().keepalive()
        logger.info('Round %s: coins=%s', self.round, coins)
        if coins < self.min_coins:
            logger.error('Only %s coins left. Shutting down now.', coins)
            self.fme.shutdown()
            exit(1)

    def check_traders(self):
        active_buyers = len([x for x in self.buyers.traders if x.state == 'active'])
        if active_buyers >= 3:
            self.flippers.disable()
        else:
            self.flippers.enable()


def main():
    logging.basicConfig(
        format='%(asctime)s %(levelname)-8s %(message)s',
        datefmt='%m-%d %H:%M:%S',
        level=logging.INFO)

    fme = Futme()
    fme.shutdown()


if __name__ == '__main__':
    main()
