# -*- coding: utf-8 -*-

import logging
import re

import requests

logger = logging.getLogger(__name__)

FH_BASE_URL='https://www.futhead.com'
TOTW_PAGE_PATH='/19/totw/totw{}/'

def totw(week):
    page_url = FH_BASE_URL + TOTW_PAGE_PATH.format(week)
    html = requests.get(page_url).text
    p = re.compile('"apiRetrievalUrl": "(.*?)"')
    m = p.search(html)
    api_url = FH_BASE_URL + m.group(1)
    data = requests.get(api_url).json()
    result = [_convert(x['data']) for x in data['players']]
    return sorted(result, key=lambda x: x['rating'], reverse=True)

def _convert(x):
    p = {
        'itemType':'player',
        'rareflag':3,
        'untradeable':True,
        'discardValue':0,
        'lastSalePrice':0
    }
    p['id'] = x['def_id']
    p['assetId'] = x['player_id']
    p['resourceId'] = x['def_id']
    p['position'] = x['position']
    p['rating'] = x['rating']
    p['teamid'] = x['club_ea_id']
    p['leagueId'] = x['league_ea_id']
    p['nation'] = x['nation_ea_id']
    p['fh_short_name'] = x['short_name']
    return p

def print_autotrader_config(totw):
    for p in totw:
        sfmt = ['"rid": {p[resourceId]}',
                '"bid": 1000',
                '"flexbid": true',
                '"_": "{p[fh_short_name]} {p[position]} {p[rating]}"']
        sfmt = ', '.join(sfmt)
        print('{' + sfmt.format(p=p) + '},')


def main():
    logging.basicConfig(
        format='%(asctime)s %(levelname)-8s %(message)s',
        datefmt='%m-%d %H:%M:%S',
        level=logging.INFO)

    print_autotrader_config(totw(24))

if __name__ == '__main__':
    main()
