# -*- coding: utf-8 -*-

import json
import logging

import requests
from bs4 import BeautifulSoup

from . import util

logger = logging.getLogger(__name__)

def print_sbc_buyer_configs(fme, fbids):
    configs = [sbc_buyer_config(fme, fbid) for fbid in fbids]
    configs.sort(key=lambda x: x['discount'], reverse=True)
    for config in configs:
        print(json.dumps(config, ensure_ascii=False) + ',')

def sbc_buyer_config(fme, fbid):
    result = {'flexbid':True}
    rid = player_resource_id(fbid)
    pdef = util.searchDefinition(fme.session(), rid)
    if pdef is None:
        notes = 'Invalid rid for fbid={}'.format(fbid)
    else:
        extra = [x for x in fme.tm.tradepile.inactive() if x['resourceId'] == rid]
        owned = fme.club.by_rid(rid) + extra
        name = fme.disp.name_str(pdef)
        pos = pdef['position']
        rat = pdef['rating']
        rf = fme.disp.rareflag_str(pdef)
        notes = '{} {} {} {}'.format(name, pos, rat, rf)
        if owned:
            notes += ' (owned {})'.format(len(owned))
        if pdef['rareflag'] == 3:
            # apply discount for TOTW
            discount = 0.9
        elif rat < 84:
            discount = 1
        elif rat == 84:
            discount = 0.95
        else:
            discount = 0.9
        result['discount'] = discount
    result['rid'] = rid
    result['_'] = notes
    return result


def player_resource_id(futbin_id):
    url = 'https://www.futbin.com/19/player/{}'.format(futbin_id)
    html = requests.get(url).text
    soup = BeautifulSoup(html, 'html.parser')
    return int(soup.find(id='page-info').get('data-player-resource'))
