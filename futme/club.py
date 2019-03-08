# -*- coding: utf-8 -*-

import logging
import sys

from . import datafile, util

logger = logging.getLogger(__name__)

class Club(object):

    def __init__(self, fme):
        self.fme = fme

    def all_players(self, level='gold', max_page=10000):
        return self.club_all_pages(level=level)

    def expandables(self):
        '''Returns normal players that are: on transfer list, unassinged, or untradeable
        '''
        def normal(lst):
            return [x for x in lst if x['rareflag'] in [0, 1]]

        result = [x for x in normal(self.club_all_pages(level='gold')) if x['untradeable']]
        result += normal(self.fme.tm.tradepile.inactive())
        result += normal(self.fme.session().unassigned())
        return result


    def matchup(self, level=None, nations=None, leagues=None, teams=None):
        players = {}
        def add_all(lst):
            for p in lst:
                players[p['id']] = p

        if nations is not None:
            add_all(self.by_nations(nations=nations, level=level))
        if leagues is not None:
            add_all(self.by_leagues(leagues=leagues, level=level))
        if teams is not None:
            add_all(self.by_teams(teams=teams, level=level))
        tradable = lambda p: (not p['untradeable']) and p['rareflag'] in [0, 1]
        players = [p for p in list(players.values()) if tradable(p)]
        return sorted(players, key=util.sorter_key())


    def by_teams(self, teams, level=None):
        """Find all club players of specific teams

        :param teams: single or a list of team ids, abbrs, or names.
        :param level: gold/silver/bronze
        :return: a list of players
        """
        ids = [x['id'] for x in self.fme.lu.teams.find(teams)]
        all = []
        for id in ids:
            all.extend(self.club_all_pages(level=level, club=id))
        return all

    def by_leagues(self, leagues, level=None):
        """Find all club players from specific leagues

        :param league: single or a list of league ids, abbrs, or names.
        :param level: gold/silver/bronze
        :return: a list of players
        """
        ids = [x['id'] for x in self.fme.lu.leagues.find(leagues)]
        all = []
        for id in ids:
            all.extend(self.club_all_pages(level=level, league=id))
        return all

    def by_nations(self, nations, level=None):
        """Find all club players from a specific country

        :param league: nation id, abbr, or name.
        :param level: gold/silver/bronze
        :return: a list of players
        """
        ids = [x['id'] for x in self.fme.lu.nations.find(nations)]
        all = []
        for id in ids:
            all.extend(self.club_all_pages(level=level, nationality=id))
        return all

    def special(self, rareflags=[]):
        """Find all special players
        """
        players = self.club_all_pages(rare=True)
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


