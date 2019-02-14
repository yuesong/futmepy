# -*- coding: utf-8 -*-

import logging

logger = logging.getLogger(__name__)

RARE_FLAGS = {0: 'Comm', 1: 'Rare', 3: 'TOTW'}

class Display(object):

    def __init__(self, fme):
        self.fme = fme

    def name_str(self, c, max_len=20):
        if c['itemType'] == 'player':
            pp = self.fme.lu.players[c['assetId']]
            name = pp['surname'] if pp['surname'] is not None else pp['lastname'] + ', ' + pp['firstname']
            return name if len(name) <= max_len else name[:max_len-3] + '...'
        else:
            return u'{} {}'.format(c['itemType'], c['cardType'])

    def rareflag_str(self, c):
        rf = c['rareflag']
        return RARE_FLAGS.get(rf, 'rf' + str(rf))

    def team_str(self, id):
        return none_str(self.fme.lu.teams.to_abbr(id))

    def league_str(self, id):
        return none_str(self.fme.lu.leagues.to_abbr(id))

    def nation_str(self, id):
        return none_str(self.fme.lu.nations.to_abbr(id))

    def print_list(self, cards, logger=None):
        sfmt = self.fme.disp.format(cards)
        for c in cards:
            s = self.fme.disp.sprint(sfmt, c)
            if logger is None:
                print(s)
            else:
                logger.info(s)


    def sprint(self, fmt, card, *data):
        ext = {
            'name':   self.name_str(card),
            'pos':    none_str(card['position']),
            'team':   self.team_str(card['teamid']),
            'league': self.league_str(card['leagueId']),
            'nation': self.nation_str(card['nation']),
            'rf':     self.rareflag_str(card),
            'ut':     'UT' if card['untradeable'] else 'T'
        }
        return fmt.format(p=card, e=ext, *data)

    def to_list(self, card):
        return [
            card['id'],
            card['assetId'],
            card['resourceId'],
            self.name_str(card),
            none_str(card['position']),
            card['rating'],
            self.rareflag_str(card),
            'UT' if card['untradeable'] else 'T',
            self.team_str(card['teamid']),
            self.league_str(card['leagueId']),
            self.nation_str(card['nation']),
            card['discardValue'],
            card['lastSalePrice'],
        ]

    def format(self, items, prepend='', append=''):
        pw = col_widths(items)
        ew = {
            'name':   max([len(unicode(self.name_str(x))) for x in items]),
            'team':   max([len(unicode(self.team_str(x['teamid']))) for x in items]),
            'league': max([len(unicode(self.league_str(x['leagueId']))) for x in items]),
            'nation': max([len(unicode(self.nation_str(x['nation']))) for x in items]),
            'rf':     4,
            'ut':     2,
            'pos':    3
        }
        p = lambda k: '{p['+k+']:<'+str(pw[k])+'}'
        e = lambda k: '{e['+k+']:<'+str(ew[k])+'}'
        result = u'{}|{}|{}  {}  {} {}  {} {}  {}|{}|{}  dv={} ls={}'.format(
            p('id'), p('assetId'), p('resourceId'),
            e('name'), e('pos'), p('rating'), e('rf'), e('ut'),
            e('team'), e('league'), e('nation'),
            p('discardValue'), p('lastSalePrice'))
        if prepend: result = prepend + '  ' + result
        if append: result = result + '  ' + append
        return result


def col_widths(cards):
    wmap = {}
    for c in cards:
        for prop in c:
            w = len(none_str(c[prop]))
            if prop not in wmap or w > wmap[prop]:
                wmap[prop] = w
    return wmap

def max_width(lst):
    return max([len(none_str(x)) for x in lst]) if lst else 0

def none_str(v):
    return '' if v is None else unicode(v)
