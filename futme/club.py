# -*- coding: utf-8 -*-

import logging
import sys

from . import datafile

logger = logging.getLogger(__name__)

class Club(object):

    def __init__(self, fme):
        self.fme = fme

    def by_teams(self, teams, level=None):
        """Find all club players of specific teams

        :param teams: single or a list of team ids, abbrs, or names.
        :param level: gold/silver/bronze
        :return: a list of players
        """
        all = []
        ids = [x['id'] for x in self.fme.lu.teams.find(teams)]
        for id in ids:
            players = []
            while True:
                page = self.fme.session().club(level=level, start=len(players), club=id)
                if len(page) == 0:
                    break
                players.extend(page)
            all.extend(players)
        return all

    def by_league(self, league, level=None):
        """Find all club players from a specific league

        :param league: league id, abbr, or name.
        :param level: gold/silver/bronze
        :return: a list of players
        """
        all = []
        ids = [x['id'] for x in self.fme.lu.leagues.find(league)]
        for id in ids:
            players = []
            while True:
                page = self.fme.session().club(level=level, start=len(players), league=id)
                if len(page) == 0:
                    break
                players.extend(page)
            all.extend(players)
        return all

    def by_nations(self, nations, level=None):
        """Find all club players from a specific country

        :param league: nation id, abbr, or name.
        :param level: gold/silver/bronze
        :return: a list of players
        """
        all = []
        ids = [x['id'] for x in self.fme.lu.nations.find(nations)]
        for id in ids:
            players = []
            while True:
                page = self.fme.session().club(level=level, start=len(players), nationality=id)
                if len(page) == 0:
                    break
                players.extend(page)
            all.extend(players)
        return all

    def special(self, rareflags=[]):
        """Find all special players
        """
        players = []
        while True:
            page = self.fme.session().club(start=len(players), rare=True)
            if len(page) == 0:
                break
            players.extend(page)
        return [p for p in players if p['rareflag'] in rareflags] if rareflags else players

    def club_all_pages(self, max_page=sys.maxsize, **kwargs):
        players = []
        page_count = 0
        while True:
            page = self.fme.session().club(start=len(players), **kwargs)
            players.extend(page)
            page_count += 1
            if not page or page_count >= max_page:
                break
        return players

    def dump_players(self, level='gold', max_page=10000):
        logger.info('Start dumping club players...')
        players = []
        for _ in range(0, max_page):
            page = self.fme.session().club(level=level, start=len(players))
            if len(page) == 0:
                break
            players.extend(page)

        filename = 'futme_club_players_' + level + '.json'
        self.fme.lu.save_json(players, filename)

        filename = 'futme_club_players_' + level + '.tsv'
        rows = [['iid', 'aid', 'rid', 'name', 'pos', 'rat', 'rf', 'tr', 'club', 'league', 'nation', 'dv', 'ls']]
        for p in players:
            rows.append(self.fme.disp.to_list(p))
        datafile.save_tsv(rows, filename)

        logger.info('Saved %s club players (level=%s)', len(players), level)
