# -*- coding: utf-8 -*-

import logging
import time
import statistics

import requests
from beaker.cache import cache_region, cache_regions

from . import timeutil

logger = logging.getLogger(__name__)

MIN_PRICE = 150
MAX_PRICE = 15000000

PRICE_STEP_SIZES = [
    (1000, 50),
    (10000, 100),
    (50000, 250),
    (100000, 500)
]

cache_regions.update({
    'price_history':{
        'expire': 3600,
        'type': 'memory'
    }
})

def pbound(price):
    if price < 0:
        return 0
    if price > MAX_PRICE:
        return MAX_PRICE
    return price

def pround(price):
    price = pbound(price)

    for bucket_upper_bound, step_size in PRICE_STEP_SIZES:
        if price < bucket_upper_bound:
            return int(round(price / float(step_size))) * step_size

    return int(round(price / 1000.0)) * 1000

def pincrement(price, steps = 1):
    result = pround(price)
    for _ in range(abs(steps)):
        if steps > 0:
            delta = 1000
            for bucket_upper_bound, step_size in PRICE_STEP_SIZES:
                if result < bucket_upper_bound:
                    delta = step_size
                    break
        else:
            delta = -1000
            for bucket_upper_bound, step_size in PRICE_STEP_SIZES:
                if result <= bucket_upper_bound:
                    delta = -step_size
                    break
        result += delta
    return pbound(result)


def quick(player):
    rid = str(player['resourceId'] if isinstance(player, dict) else player)
    data = futbin_get_json('https://www.futbin.com/19/playerPrices?player=' + rid)
    if data is None: return 0
    v = data[rid]['prices']['ps']['LCPrice']
    if isinstance(v, int):
        return v
    return int(v.replace(',', ''))


def history(player, include_hourly=0):
    rid = str(player['resourceId'] if isinstance(player, dict) else player)
    return _history(rid, include_hourly)

@cache_region('price_history', 'history')
def _history(rid, include_hourly):
    d = {}

    def futbin_price_graph(gtype):
        url = 'https://www.futbin.com/19/playerGraph?type={}&year=19&player={}'.format(gtype, rid)
        data = futbin_get_json(url)
        if data is None:
            return
        if 'ps' in data:
            for k, v in data['ps']:
                t = int(k/1000)
                d[t] = PricePoint(t, v)

    # order is important as we want more recent data to override older want
    futbin_price_graph('daily_graph')
    if include_hourly >= 1:
        futbin_price_graph('today')
    if include_hourly >= 2:
        futbin_price_graph('yesterday')
    if include_hourly >= 3:
        futbin_price_graph('da_yesterday')


    return PriceHistory(sorted(d.values(), key=lambda x: x.timestamp, reverse=True))

def futbin_get_json(url):
    for _ in range(3):
        try:
            return requests.get(url).json()
        except:
            continue
    return None

class PriceHistory(object):

    def __init__(self, points):
        self.points = sorted(points, key=lambda x: x.timestamp, reverse=True)

    def high(self):
        return max(self.points, key=lambda x: x.value)

    def low(self):
        return min(self.points, key=lambda x: x.value)

    def mean(self):
        return statistics.mean(self.values())

    def stdev(self):
        return statistics.stdev(self.values())

    def values(self):
        return [x.value for x in self.points]

    def latest_price(self):
        return self.points[0].value if self.points else None

    def slice(self, *days_offsets):
        """
        h = PriceHistory(data_last_month)

        h1 = h.slice(7)
        h2 = h.slice(-7)
        h3 = h.slice(0, 7)
        h4 = h.slice(-7, 0)

        h1 to h4 all contain the same data - price history of the past 7 days
        """
        if len(days_offsets) == 0:
            return self
        elif len(days_offsets) == 1:
            t1 = abs(days_offsets[0]) * timeutil.SECONDS_PER_DAY
            t2 = 0
        else:
            t1 = abs(days_offsets[0]) * timeutil.SECONDS_PER_DAY
            t2 = abs(days_offsets[1]) * timeutil.SECONDS_PER_DAY
        now = time.time()
        return PriceHistory([p for p in self.points if p.time_within(now - t1, now - t2)])

    def add(self, current_price):
        pp = PricePoint(int(time.time()), current_price)
        self.points.insert(0, pp)

    def trade_score(self, price, days=90):
        s = self.slice(days)
        mean = s.mean()
        stdev = s.stdev()
        return round(float(price - mean)/stdev, 1)

class PricePoint(object):
    def __init__(self, timestamp, value):
        self.timestamp = timestamp
        self.value = value

    def __repr__(self):
        return 'PricePoint(timestamp={}, age={}, value={})'.format(
            self.timestamp, timeutil.dur_str(self.age()), self.value)

    def __str__(self):
        return '{} ({})'.format(self.value, timeutil.dur_str(self.age()))

    def time_within(self, t1, t2):
        return timeutil.time_within(self.timestamp, t1, t2)

    def age(self):
        return (time.time() - self.timestamp)

def main():
    logging.basicConfig(
        format='%(asctime)s %(levelname)-8s %(message)s',
        datefmt='%m-%d %H:%M:%S',
        level=logging.INFO)

    hist = history(164169)
    print(len(hist))

if __name__ == '__main__':
    main()
