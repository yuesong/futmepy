# -*- coding: utf-8 -*-

import base64
import codecs
import json
import logging
import os
import sys

import fut
import requests

from . import datafile

logger = logging.getLogger(__name__)

class Lookups(object):

    _RAW_DATA_URL = 'https://www.easports.com/fifa/ultimate-team/web-app/loc/en_US.json'

    _LU_FILE_META    = 'futme_lu_meta.json'
    _LU_FILE_NATIONS = 'futme_lu_nations.json'
    _LU_FILE_LEAGUES = 'futme_lu_leagues.json'
    _LU_FILE_TEAMS   = 'futme_lu_teams.json'
    _LU_FILE_PLAYERS = 'futme_lu_players.json'

    _RAW_KEY_PREFIXES_NATION = {'name':  'search.nationName.nation',
                                'abbr':  'search.nationAbbr12.nation'}
    _RAW_KEY_PREFIXES_LEAGUE = {'name':  'global.leagueFull.2019.league',
                                'abbr':  'global.leagueabbr5.2019.league',
                                'abbr2': 'global.leagueabbr15.2019.league'}
    _RAW_KEY_PREFIXES_TEAM =   {'name':  'global.teamabbr15.2019.team',
                                'abbr':  'global.teamabbr3.2019.team',
                                'abbr2': 'global.teamabbr10.2019.team'}

    def __init__(self, db_dir = '.', force_reload = False):
        self.db_dir = os.path.abspath(db_dir)
        self.nations = LookupStore('nation')
        self.leagues = LookupStore('league')
        self.teams = LookupStore('team')
        self.players = self._load_players()
        self._init_data(force_reload)
        logger.info('%s nations, %s leagues, %s teams, %s players',
            len(self.nations.items), len(self.leagues.items),
            len(self.teams.items), len(self.players))

    def _load_players(self):
        players = {}
        for id, player in fut.core.players().items():
            players[id] = player
        datafile.save_json(list(players.values()), Lookups._LU_FILE_PLAYERS)
        return players

    def _init_data(self, force_reload):
        logger.info('Initializing (db_dir is %s)', self.db_dir)
        if not os.path.isdir(self.db_dir):
            os.mkdir(self.db_dir)

        meta = datafile.load_json(Lookups._LU_FILE_META)
        if force_reload or 'lastModified' not in meta or self._modified_since(meta['lastModified']):
            self._reload()
            logger.info('Lookup loaded from source')
        else:
            self.nations.items = datafile.load_json(Lookups._LU_FILE_NATIONS)
            self.leagues.items = datafile.load_json(Lookups._LU_FILE_LEAGUES)
            self.teams.items   = datafile.load_json(Lookups._LU_FILE_TEAMS)
            logger.info('Lookup loaded from cache')

    def _reload(self):
        r = requests.get(Lookups._RAW_DATA_URL)
        raw = r.json()

        # use temp maps as workspace when parsing through raw input
        nations = {}
        leagues = {}
        teams = {}
        for k, v in raw.items():
            key = base64.b64decode(k).decode('utf-8')
            self._update(nations, Lookups._RAW_KEY_PREFIXES_NATION, key, v)
            self._update(leagues, Lookups._RAW_KEY_PREFIXES_LEAGUE, key, v)
            self._update(teams, Lookups._RAW_KEY_PREFIXES_TEAM, key, v)

        # save the values of the temp map when parsing is complete
        self.nations.items = sorted(nations.values(), key=lambda x: x['id'])
        self.leagues.items = sorted(leagues.values(), key=lambda x: x['id'])
        self.teams.items =   sorted(teams.values(),   key=lambda x: x['id'])

        datafile.save_json(self.nations.items, Lookups._LU_FILE_NATIONS)
        datafile.save_json(self.leagues.items, Lookups._LU_FILE_LEAGUES)
        datafile.save_json(self.teams.items, Lookups._LU_FILE_TEAMS)
        datafile.save_json({'lastModified': r.headers['Last-Modified']}, Lookups._LU_FILE_META)


    def _modified_since(self, time_str):
        headers = {'If-Modified-Since': time_str}
        r = requests.head(Lookups._RAW_DATA_URL, headers = headers)
        return r.status_code != 304

    def _update(self, d, raw_key_prefixes, key, raw_value):
        for prop, prefix in raw_key_prefixes.items():
            # a bit of a hack to handle keys like: 'global.leagueabbr5.2019.league83_upper'
            if key.startswith(prefix) and not key.endswith('_upper'):
                item_id = int(key[len(prefix):])
                item = d.get(item_id, {'name': None, 'abbr': None, 'abbr2': None})
                item['id'] = item_id
                item[prop] = codecs.decode(base64.b64decode(raw_value), 'utf-8')
                d[item_id] = item


class LookupStore(object):
    def __init__(self, name):
        self.name = name
        self.items = []

    def by_id(self, val):
        return self._by_prop('id', val)

    def by_abbr(self, val):
        return self._by_prop('abbr', val)

    def by_abbr2(self, val):
        return self._by_prop('abbr2', val)

    def by_name(self, val):
        return self._by_prop('name', val)

    def _by_prop(self, prop, val):
        a = [i for i in self.items if prop in i and i[prop] == val]
        return a[0] if len(a) > 0 else None

    def name_contains(self, val):
        return [i for i in self.items if val in i['name']]

    def find(self, val):
        if not isinstance(val, list):
            val = [val]
        result = [self._find_single(v) for v in val]
        return [x for x in result if x is not None]

    def _find_single(self, val):
        if isinstance(val, int): return self.by_id(val)
        val = str(val)
        result = self.by_abbr(val)
        if result is not None: return result
        result = self.by_abbr2(val)
        if result is not None: return result
        result = self.by_name(val)
        if result is not None: return result
        return self.name_contains(val)

    def to_name(self, id):
        return self._to_prop('name', id)

    def to_abbr(self, id):
        return self._to_prop('abbr', id)

    def _to_prop(self, prop, id):
        item = self.by_id(id)
        return item[prop] if item is not None and prop in item else None

def main():
    logging.basicConfig(level = logging.INFO)
    lu = Lookups(force_reload=False)

    def print_lustore(lus, max = 10):
        logger.info('>>> %s', lus.name)
        count = 0
        for i in lus.items:
            if i['name'] is not None and any(ord(c) >= 128 for c in i['name']):
                logger.info(u'id=%s | abbr=%s | abbr2=%s | name=%s',
                    i['id'], i['abbr'], i['abbr2'], i['name'])
                count += 1
                if count >= max:
                    break

    print_lustore(lu.nations)
    print_lustore(lu.leagues)
    print_lustore(lu.teams)

    logger.info('>>> players')
    count = 0
    for i in lu.players.values():
        if any(ord(c) >= 128 for c in i['firstname']) or any(ord(c) >= 128 for c in i['lastname']):
            logger.info(u'id=%s | sn=%s | fn=%s | ln=%s', i['id'], i['surname'], i['firstname'], i['lastname'])
            count += 1
            if count >= 10:
                break

if __name__ == '__main__':
    main()
