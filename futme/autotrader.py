# -*- coding: utf-8 -*-

import logging
import time

import fut
from beaker.cache import cache_region, cache_regions, region_invalidate

from . import core, datafile, display, price, timeutil, worker, util

logger = logging.getLogger(__name__)

class AutoTrader:

    _CONF_FILE = 'autotrader.json'

    def __init__(self, fme):
        self.fme = fme
        self.traders = self.create_traders()
        self.conf_last_modified = datafile.last_modified(AutoTrader._CONF_FILE)
        self.worker = worker.LoopyWorker()
        self.worker.register_task('status', self.print_trader_statuses, 1200)
        self.worker.register_task('reload_conf', self.reload_conf, 60, delay=60)

    def create_traders(self):
        traders = []
        conf = datafile.load_json(AutoTrader._CONF_FILE)
        for ttype in ['buy', 'flip']:
            default = conf[ttype]['default']
            for c in conf[ttype]['targets']:
                if c:
                    self.add_default(c, default)
                    pdef = self.validate_trader_conf(c)
                    if pdef is not None:
                        if ttype == 'buy':
                            traders.append(Buyer(self.fme, pdef, c))
                        elif ttype == 'flip':
                            traders.append(Flipper(self.fme, pdef, c))
        logger.info('%s traders initialized:', len(traders))
        self.print_trader_confs(traders)
        return traders

    def add_default(self, conf, default):
        for k in default:
            if k not in conf:
                conf[k] = default[k]

    def validate_trader_conf(self, c):
        rid = c['rid']
        if not c['flexbid'] and c['bid'] == 0:
            logger.error('Invaid conf for rid %s: flexbid is False but bid is 0', rid)
            return None

        return util.searchDefinition(self.fme.session(), rid)

    def print_trader_confs(self, traders):
        tname_width = display.max_width([t.trader_name() for t in traders])
        sfmt = '{:'+str(tname_width)+'}  {}'
        for t in traders:
            logger.info(sfmt.format(t.trader_name(), t.conf_str()))

    def run(self):
        for trader in self.traders:
            if trader.state != 'done':
                trader.run()
        self.worker.run()

    def print_trader_statuses(self):
        sfmt = self.fme.disp.format([x.pdef for x in self.traders], prepend='{} {}', append='{}')
        for t in self.traders:
            ttype = t.trader_type()
            state = t.state[0].upper()
            logging.info(self.fme.disp.sprint(sfmt, t.pdef, ttype, state, t.status_str()))

    def reload_conf(self):
        mtime = datafile.last_modified(AutoTrader._CONF_FILE)
        if mtime > self.conf_last_modified:
            logger.info('Reloading %s - it was modified %s ago',
                        AutoTrader._CONF_FILE, timeutil.dur_str(time.time() - mtime))
            self.traders = self.create_traders()
            self.conf_last_modified = mtime


class BaseTrader:

    def __init__(self, fme, pdef, conf):
        self.fme = fme
        self.pdef = pdef
        self.rid = pdef['resourceId']
        self.conf = conf

        self.suggested_bid = conf['bid']
        self.interval = conf['interval']
        self.discount = conf['discount']
        self.flexbid = conf['flexbid']

        self.bid = 0
        self.mkt_price = 0
        self.attempts = 0

        self.worker = worker.LoopyWorker()
        self.state = 'active'

    def run(self):
        self.worker.run()

    def update_bid(self):
        if self.flexbid:
            p, mp, _ = self.fme.tm.search_min_price(self.rid)
            if p is None:
                self.mkt_price = 0
                self.bid = 0
            else:
                self.mkt_price = mp
                discounted_price = price.pround(self.mkt_price * self.discount)
                if self.suggested_bid == 0:
                    adjusted_bid = discounted_price
                else:
                    adjusted_bid = min(self.suggested_bid, discounted_price)
                min_price = price.pincrement(p['discardValue'])
                self.bid = max(min_price, adjusted_bid)
        else:
            self.bid = self.suggested_bid

    def set_state(self, new_state, reason=''):
        if reason != '':
            reason = ' ({})'.format(reason)
        if self.state != new_state:
            logger.warning('%s  State change: %s -> %s%s',
                           self.trader_name(), self.state, new_state, reason)
            self.state = new_state

    def trader_type(self):
        return type(self).__name__[0].upper()

    def trader_name(self):
        pname = self.fme.disp.name_str(self.pdef)
        return '{} {}'.format(self.trader_type(), pname)

    def _conf_str(self, *keys):
        return ', '.join(['{}={}'.format(k, self.conf[k]) for k in keys])


class Buyer(BaseTrader):

    def __init__(self, fme, pdef, conf):
        super().__init__(fme, pdef, conf)
        self.quick_price = 0
        self.bought = None
        self.worker.register_task('update_bid', self.update_bid, 1200)
        self.worker.register_task('update_quick_price', self.update_quick_price, 1800)
        self.worker.register_task('attempt', self.attempt, self.interval)

    def update_quick_price(self):
        self.quick_price = price.quick(self.rid)

    def attempt(self):
        if self.bid == 0:
            self.set_state('paused', 'nothing in market')
            return

        self.set_state('active')
        self.attempts += 1
        won = self.fme.tm.buy_now(self.rid, self.bid)
        if won is not None:
            item_id = won['id']
            un = self.fme.session().unassigned()
            self.bought = next(x for x in un if x['id'] == item_id)
            if item_id in self.fme.session().duplicates:
                self.fme.session().sendToTradepile(item_id)
            else:
                self.fme.session().sendToClub(item_id)
            self.set_state('done')

    def conf_str(self):
        return self._conf_str('interval', 'discount', 'bid', 'flexbid')

    def status_str(self):
        return 'bid={} mp={} qp={} atps={} paid={}'.format(
            self.bid, self.mkt_price, self.quick_price, self.attempts,
            self.bought['lastSalePrice'] if self.bought is not None else 'na')


class Flipper(BaseTrader):

    def __init__(self, fme, pdef, conf):
        super().__init__(fme, pdef, conf)
        self.maxflips = conf['maxflips']
        self.sellfor = conf['sellfor']
        self.worker.register_task('update_bid', self.update_bid, 1200)
        self.worker.register_task('attempt', self.attempt, self.interval)

    def attempt(self):
        if self.bid == 0:
            self.set_state('paused', 'nothing in market')
            return

        # no more than configured active flips (default 2) for an item at any give time
        num_listed = self._num_listed()
        if num_listed >= self.maxflips:
            self.set_state('paused', '{} active flips. {} max'.format(num_listed, self.maxflips))
            return

        # should not sell for loss
        if self.sellfor != 0 and self.sellfor < self.bid:
            self.set_state('paused',
                           'sellfor ({}) is less than bid ({})'.format(self.sellfor, self.bid))
            return

        self.set_state('active')
        self.attempts += 1
        won = self.fme.tm.buy_now(self.rid, self.bid)
        if won is not None:
            # get current market price - we are not selling for less
            _, current_mkt_price, _ = self.fme.tm.search_min_price(self.rid)
            if self.sellfor != 0:
                self.fme.tm.sell(won['id'], max(self.sellfor, current_mkt_price))
            else:
                self.fme.tm.sell(won['id'], max(self.mkt_price, current_mkt_price))
            # TODO update mkt_price and bid

    def _num_listed(self):
        '''Returns the number of active listings'''
        lst = self.fme.tm.tradepile.active() + self.fme.tm.tradepile.expired()
        return len([x for x in lst if x['resourceId'] == self.rid])

    def conf_str(self):
        return self._conf_str('interval', 'discount', 'bid', 'flexbid', 'maxflips', 'sellfor')

    def status_str(self):
        return 'bid={} mp={} atps={}'.format(self.bid, self.mkt_price, self.attempts)


def main():
    logging.basicConfig(
        format='%(asctime)s %(levelname)-8s %(message)s',
        datefmt='%m-%d %H:%M:%S',
        level=logging.INFO)

    fme = core.Futme()
    fme.shutdown()


if __name__ == '__main__':
    main()
