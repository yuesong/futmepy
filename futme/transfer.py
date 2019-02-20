# -*- coding: utf-8 -*-

import logging

import fut
from beaker.cache import cache_region, cache_regions, region_invalidate

from . import core
from . import price

logger = logging.getLogger(__name__)

cache_regions.update({
    'transfer_tradepile':{
        'expire': 10,
        'type': 'memory'
    }
})

class TransferMarket(object):

    _SEARCH_PAGE_SIZE = fut.urls.itemsPerPage['transferMarket']

    def __init__(self, fme):
        self.fme = fme
        self.tradepile = Tradepile(fme)

    def price_players(self, players, search_mkt_price=False, threshold_price=0):
        result = []
        append = 'qp={}'
        if search_mkt_price:
            append += ' mp={} {}'
        sfmt = self.fme.disp.format(players, append=append)
        for p in players:
            q_prc = price.quick(p)
            args = [q_prc]
            keep = q_prc >= threshold_price
            if search_mkt_price:
                _, mkt_prc, seen = self.search_min_price(p)
                args.extend([mkt_prc, seen])
                keep = mkt_prc >= threshold_price
            logging.info(self.fme.disp.sprint(sfmt, p, *args))
            if keep:
                result.append(p)
        return result

    def price_listed_players(self, max_rating=None, normal_only=True, quick=True, sell=False):

        def match(p):
            if p['itemType'] != 'player' or p['tradeState'] is not None:
                return False
            if max_rating is not None and p['rating'] > max_rating:
                return False
            if normal_only and p['rareflag'] > 1:
                return False
            return True

        target = [p for p in self.fme.session().tradepile() if match(p)]
        target.sort(key=lambda x: x['discardValue'], reverse=True)
        sfmt = self.fme.disp.format(target, append='mp={} {}')
        for p in target:
            if quick:
                pri, seen = price.quick(p), ''
            else:
                _, pri, seen = self.search_min_price(p)
            logger.info(self.fme.disp.sprint(sfmt, p, pri, seen))
            if sell:
                self.fme.session().sell(p['id'], price.pincrement(pri, steps=-1), pri)


    def search_min_price(self, player, seen_prices=3):
        mkt_min, mkt_max = price.MIN_PRICE, price.MAX_PRICE
        if isinstance(player, int):
            rid = player
        else:
            rid = player['resourceId']
            if player['marketDataMinPrice'] is not None:
                mkt_min = player['marketDataMinPrice']
            if player['marketDataMaxPrice'] is not None:
                mkt_max = player['marketDataMaxPrice']

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
            if search_result:
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

    def sell(self, item_id, buy_now):
        session = self.fme.session()
        if session.sendToTradepile(item_id):
            return session.sell(item_id, price.pincrement(buy_now, steps=-1), buy_now)
        else:
            return None

    def buy_now(self, resource_id, max_buy):
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
        return self.fme.session().tradepile()

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
