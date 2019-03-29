# -*- coding: utf-8 -*-

import logging
import traceback
import time
from collections import Counter

import fut
from beaker.cache import cache_region, cache_regions, region_invalidate

from . import core, price, util, timeutil

logger = logging.getLogger(__name__)

cache_regions.update({
    'transfer_tradepile':{
        'expire': 10,
        'type': 'memory'
    },
    'transfer_market_price':{
        'expire': 1200,
        'type': 'memory'
    }
})

class TransferMarket(object):

    _SEARCH_PAGE_SIZE = fut.urls.itemsPerPage['transferMarket']

    def __init__(self, fme):
        self.fme = fme
        self.tradepile = Tradepile(fme)

    def tradepile_cleanup_targets(self, keep_all_above_rating=83, sell_all_below_rating=75):
        a = self.tradepile.inactive()
        counts = dict(Counter([x['resourceId'] for x in a]))

        targets = []
        dups = {}
        for x in a:
            rid, rating, rf = x['resourceId'], x['rating'], x['rareflag']
            if rating > keep_all_above_rating or rf not in [0, 1]:
                # skip high-rating or non-regular cards
                continue
            elif rf == 0:
                # sell all common cards
                targets.append(x)
            elif rating < sell_all_below_rating:
                # sell all low-rating cards
                targets.append(x)
            elif counts[rid] > 1:
                # record the dups - they need further processing
                dups[rid] = dups.get(rid, []) + [x]

        for a in dups.values():
            # keep the dup item with loyalty bonues and/or non-basic chem style
            a.sort(key=lambda x: x['loyaltyBonus'] * 100000 + x['playStyle'], reverse=True)
            targets.extend(a[1:])

        return util.psorted(targets)


    def price_players(self, players, inc_history=False, search_mkt_price=False):
        append = 'qp={:5}'
        if inc_history:
            append += ' {}'
        if search_mkt_price:
            append = 'mp={} ' + append
        sfmt = self.fme.disp.format(players, append=append)
        for p in players:
            q_prc = price.quick(p)
            args = [q_prc]
            if inc_history:
                phist = price.history(p)
                ph7d, ph30d, ph90d = phist.slice(7), phist.slice(30), phist.slice(90)
                phist_str = 'hl7d={}/{} hl30d={}/{} hl90d={}/{}'.format(
                    ph7d.high().value, ph7d.low().value,
                    ph30d.high().value, ph30d.low().value,
                    ph90d.high().value, ph90d.low().value)
                args.append(phist_str)
            if search_mkt_price:
                mkt_prc = self.get_market_price_cached(p)
                args.insert(0, mkt_prc)
            logging.info(self.fme.disp.sprint(sfmt, p, *args))

    def trade_rec(self, players, search_mkt_price=False):
        append = 'tn={:3}d ts={:4}'
        append += ' mp={:5}' if search_mkt_price else ' qp={:5}'
        append += ' pr={:5} {}'
        sfmt = self.fme.disp.format(players, append=append)
        for p in players:
            tenure = timeutil.dur_days(time.time() - p['timestamp'])
            prc = self.get_market_price_cached(p) if search_mkt_price else price.quick(p)
            phist = price.history(p)
            tscore = phist.trade_score(prc)
            lsp = p['lastSalePrice']
            profit = prc - lsp
            profit_pct = 'all' if lsp == 0 else str(int(profit * 100.0/lsp)) + '%'
            logging.info(self.fme.disp.sprint(sfmt, p, tenure, tscore, prc, profit, profit_pct))

    def relist_expired(self, rid, max_buy=None):
        players = [x for x in self.tradepile.expired() if x['resourceId'] == rid]
        if not players:
            logger.warn('No expired listing for rid=%s', rid)
            return

        if max_buy is None:
            max_buy = self.get_market_price_cached(rid)
        for p in players:
            self.sell(p, max_buy)
        logger.info('%s items (rid=%s) relisted at %s', len(players), rid, max_buy)


    def search_min_price(self, player, seen_prices=3):
        mkt_min, mkt_max = price.MIN_PRICE, price.MAX_PRICE
        if isinstance(player, int):
            rid = player
        else:
            rid = player['resourceId']
            p_mkt_min, p_mkt_max = player['marketDataMinPrice'], player['marketDataMaxPrice']
            if p_mkt_min is not None and p_mkt_min > 0:
                mkt_min = p_mkt_min
            if p_mkt_max is not None and p_mkt_max > 0:
                mkt_max = p_mkt_max
            # debug print to track down a bug:
            if p_mkt_min <= 0 or p_mkt_max <= 0:
                logger.error('marketDataMinPrice or marketDataMaxPrice of a player is <= 0:')
                logger.info(player)

        session = self.fme.session()
        current_player = None
        current = mkt_max
        attempt = mkt_max
        failed_attempt = mkt_min
        seen = {}
        # XXX cap the number of iterations in case there is a bug to cause infinite loop...
        for i in range(8):
            logger.debug('round %s: current=%s, attempt=%s, failed_attempt=%s',
                         i, current, attempt, failed_attempt)
            # if current low is just one step above hard min or last failed attempt, we are done
            if current == price.pincrement(mkt_min) or current <= price.pincrement(failed_attempt):
                logger.debug('break - current is the lowest possible')
                break
            search_result = session.search('player', defId=rid, max_buy=attempt)
            for x in search_result:
                seen[x['id']] = x
            logger.debug('search returned %s items (%s)',
                         len(search_result),
                         [(x['buyNowPrice'], x['expires']) for x in search_result])
            if not search_result:
                if attempt == mkt_max:
                    logger.debug('break - nothing on market')
                    break
                else:
                    # nothing returned - attempt price is too low. record the failed attempt, and
                    # set new attempt price to be closer to the current low
                    failed_attempt = attempt
                    attempt = price.pround((failed_attempt + current)/2)
            elif len(search_result) < TransferMarket._SEARCH_PAGE_SIZE:
                # if search returned less than the full page, return the min value
                maybe_player, maybe_price = _sticky_min(search_result)
                if maybe_player is not None:
                    current_player = maybe_player
                    current = maybe_price
                    logger.debug('break - found min price (search result is less than full page)')
                    break
                else:
                    failed_attempt = attempt
                    attempt = price.pround((failed_attempt + current)/2)
            else:
                # full page returned. set new attemp price to be between previous
                # failed attemp and current low
                maybe_player, maybe_price = _sticky_min(search_result)
                if maybe_player is not None:
                    current_player = maybe_player
                    current = maybe_price
                    attempt = price.pround((failed_attempt + current)/2)
                else:
                    failed_attempt = attempt
                    attempt = price.pround((failed_attempt + current)/2)

        seen = sorted(seen.values(), key=lambda x: x['buyNowPrice'])
        seen = [(x['buyNowPrice'], x['expires']) for x in seen]
        return (current_player, current, seen if seen_prices is None else seen[:seen_prices])

    def get_market_price_cached(self, player):
        rid = player if isinstance(player, int) else player['resourceId']
        return self._get_market_price_cached(rid)

    @cache_region('transfer_market_price', 'get_market_price')
    def _get_market_price_cached(self, player):
        _, mp, _ = self.search_min_price(player)
        return mp

    def sell(self, item, buy_now, starting_bid=None):
        '''List an item for sale

        :param item: the item or item id.
        '''
        if isinstance(item, dict):
            item_id = item['id']
            send_to_tradepile_first = (item['pile'] != 5)
        else:
            item_id = item
            send_to_tradepile_first = True

        if starting_bid is None:
            starting_bid = price.pincrement(buy_now, steps=-1)

        if starting_bid >= buy_now:
            logger.error('starting_bid %s is >= buy_now %s. Abort selling item %s',
                         starting_bid, buy_now, item)
            return None

        session = self.fme.session()
        if send_to_tradepile_first:
            if session.sendToTradepile(item_id):
                return session.sell(item_id, starting_bid, buy_now)
            else:
                logger.warning('Failed to send item to tradepile. Abort selling item %s', item)
                return None
        else:
            return session.sell(item_id, starting_bid, buy_now)


    def sell_all(self, items, price_check=lambda x: True):
        sfmt = self.fme.disp.format(items, append='mp={}')
        for p in items:
            mkt_prc = self.get_market_price_cached(p)
            if price_check(mkt_prc):
                logger.info(self.fme.disp.sprint(sfmt, p, mkt_prc))
                self.sell(p, mkt_prc)


    def buy_now(self, resource_id, max_buy):
        if max_buy <= 0:
            logging.error('There is a bug! max_buy passed to buy_now() is %s for rid %s',
                          max_buy, resource_id)
            return None

        session = self.fme.session()
        failed_bid_attempts = 0
        while failed_bid_attempts < 3:
            for_sale = session.search('player', defId=resource_id, max_buy=max_buy)
            for_sale.sort(key=lambda x: x['buyNowPrice'])
            if for_sale:
                # retry if we found items but bid failed
                logging.info('%s items (rid=%s) for sale at %s or less',
                             len(for_sale), resource_id, max_buy)
                sfmt = self.fme.disp.format(for_sale, append='bid={} won={}')
                for p in for_sale:
                    bid = p['buyNowPrice']
                    won = session.bid(p['tradeId'], bid, fast=True)
                    logger.info(self.fme.disp.sprint(sfmt, p, bid, won))
                    if won:
                        return p
                failed_bid_attempts += 1
            else:
                # quit if we didn't find anything
                break
        return None

def _sticky_min(search_result):
    # exlude brand new listings (very close to an hour) when we determine market low
    # this is to avoid the situation where someone else listed at too low a price that
    # we happened to find and followed suit
    player = None
    min_price = price.MAX_PRICE
    for x in search_result:
        expires, buy_now = x['expires'], x['buyNowPrice']
        if (expires > 3600 and buy_now < min_price) or (expires < 3540 and buy_now <= min_price):
            player, min_price = x, buy_now
    return player, min_price

class Tradepile(object):

    def __init__(self, fme):
        self.fme = fme

    def expired(self):
        return self.filter_by_state('expired')

    def active(self):
        return self.filter_by_state('active')

    def closed(self):
        return self.filter_by_state('closed')

    def inactive(self):
        return self.filter_by_state(None)

    def filter_by_state(self, trade_state):
        return [x for x in self.all() if x['tradeState'] == trade_state]

    def group_by_state(self):
        d = {}
        for x in self.all():
            ts = x['tradeState']
            l = d.get(ts, [])
            l.append(x)
            d[ts] = l
        return d

    @cache_region('transfer_tradepile', 'all')
    def all(self):
        tp = self.fme.session().tradepile()
        return util.psorted(tp)

    def refresh(self):
        region_invalidate(self.all, 'transfer_tradepile', 'all')
        return self.all()

def main():
    logging.basicConfig(
        format='%(asctime)s %(levelname)-8s %(message)s',
        datefmt='%m-%d %H:%M:%S',
        level=logging.INFO)

    fme = core.Futme()
    tp = Tradepile(fme)
    logger.info('inactive=%s, active=%s, expired=%s, closed=%s',
                len(tp.inactive()), len(tp.active()), len(tp.expired()), len(tp.closed()))

    tp.refresh()

    d = tp.group_by_state()
    for k in d:
        logger.info('tradeState %s: %s', k, len(d[k]))


if __name__ == '__main__':
    main()
