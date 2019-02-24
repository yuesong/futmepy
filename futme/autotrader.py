# -*- coding: utf-8 -*-

import logging
import time
from beaker.cache import cache_region, cache_regions, region_invalidate

import fut

from . import core
from . import price
from . import datafile
from . import worker
from . import display
from . import timeutil

logger = logging.getLogger(__name__)

class AutoTrader:

    _CONF_FILE = 'autotrader.json'

    def __init__(self, fme):
        self.fme = fme
        self.traders = self._create_traders()
        self.conf_last_modified = datafile.last_modified(AutoTrader._CONF_FILE)
        self.worker = worker.LoopyWorker()
        self.worker.register_task('status', self.print_status, 1200)
        self.worker.register_task('reload_conf', self.reload_conf, 60, delay=60)

    def _create_traders(self):
        traders = []
        conf = datafile.load_json(AutoTrader._CONF_FILE)
        for ttype in ['buy', 'flip']:
            for c in conf.get(ttype, []):
                if c['enable']:
                    pdef = self.search_definition(c['rid'])
                    if pdef is not None:
                        if ttype == 'buy':
                            traders.append(Buyer(self.fme, pdef, c))
                        elif ttype == 'flip':
                            traders.append(Flipper(self.fme, pdef, c))
        logger.info('%s traders initialized', len(traders))
        return traders

    def reload_conf(self):
        mtime = datafile.last_modified(AutoTrader._CONF_FILE)
        if mtime > self.conf_last_modified:
            logger.info('Reloading %s - it was modified %s ago',
                        AutoTrader._CONF_FILE, timeutil.dur_str(time.time() - mtime))
            self.traders = self._create_traders()
            self.conf_last_modified = mtime
            self.print_status()

    def search_definition(self, rid):
        defs = self.fme.session().searchDefinition(rid)
        defs = [p for p in defs if p['resourceId'] == rid]
        if len(defs) == 1:
            return defs[0]
        else:
            logger.warning("Invalid rid %s: exactly 1 def expected but %s found", rid, len(defs))
            return None

    def run(self):
        for trader in self.traders:
            if trader.state != 'done':
                trader.run()
        self.worker.run()

    def print_status(self):
        sfmt = self.fme.disp.format([x.pdef for x in self.traders], prepend='{} {}', append='{}')
        for t in self.traders:
            typ = type(t).__name__[0].upper()
            state = t.state[0].upper()
            logging.info(self.fme.disp.sprint(sfmt, t.pdef, typ, state, t.status_str()))


class BaseTrader:

    def __init__(self, fme, pdef):
        self.fme = fme
        self.pdef = pdef
        self.rid = pdef['resourceId']
        self.worker = worker.LoopyWorker()
        self.state = 'active'

    def run(self):
        self.worker.run()

    def set_state(self, new_state):
        if self.state != new_state:
            logger.info('TR[%s] State change: %s -> %s', self.rid, self.state, new_state)
            self.state = new_state

class Buyer(BaseTrader):

    def __init__(self, fme, pdef, conf):
        super().__init__(fme, pdef)
        self.bid = conf['bid']
        # self.strategy = conf['strategy']
        self.interval = conf.get('interval', 10)
        self.bought = None
        self.quick_price = 0
        self.attempts = 0
        self.worker.register_task('update_quick_price', self.update_quick_price, 1800)
        self.worker.register_task('attempt', self.attempt, self.interval)

    def attempt(self):
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

    def update_quick_price(self):
        self.quick_price = price.quick(self.rid)

    def status_str(self):
        return 'bid={} qp={} atps={} paid={}'.format(
            self.bid, self.quick_price, self.attempts,
            self.bought['lastSalePrice'] if self.bought is not None else 'n/a')



class Flipper(BaseTrader):

    def __init__(self, fme, pdef, conf):
        super().__init__(fme, pdef)
        self.interval = conf.get('interval', 10)
        self.discount = conf.get('discount', 0.9)
        self.attempts = 0
        self.bid = 0
        self.mkt_price = 0
        self.price_history = price.history(self.rid)
        self.worker.register_task('update_bid', self.update_bid, 1200)
        self.worker.register_task('attempt', self.attempt, self.interval)


    def update_bid(self):
        p, mp, _ = self.fme.tm.search_min_price(self.rid)
        if p is None:
            self.mkt_price = 0
            self.bid = 0
        else:
            self.mkt_price = mp
            potential_bid = price.pincrement(self.mkt_price * self.discount)
            min_price = price.pincrement(p['discardValue'])
            self.bid = max(min_price, potential_bid)


    def attempt(self):
        self.attempts += 1
        # no more than 2 active flips for an item at any give time
        if self._num_listed() >= 2:
            self.set_state('paused')
            return

        self.set_state('active')
        won = self.fme.tm.buy_now(self.rid, self.bid)
        if won is not None:
            # get current market price in case it increasd.
            _, current_mkt_price, _ = self.fme.tm.search_min_price(self.rid)
            self.fme.tm.sell(won['id'], max(self.mkt_price, current_mkt_price))
            # TODO trigger update_bid

    def _num_listed(self):
        lst = self.fme.tm.tradepile.active() + self.fme.tm.tradepile.expired()
        return len([x for x in lst if x['resourceId'] == self.rid])


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
