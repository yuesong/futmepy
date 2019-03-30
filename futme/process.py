# -*- coding: utf-8 -*-

import logging
import time

from . import price

logger = logging.getLogger(__name__)

class Proc(object):

    # unassigned item actions
    REVIEW, KEEP, DISCARD, REDEEM, SELL = 'review', 'keep', 'discard', 'redeem', 'sell'

    def __init__(self, fme):
        self.fme = fme

    def packs(self):
        coins_before = self.fme.session().keepalive()
        while True:
            # handle sold and expired items
            self.refresh_tradepile()

            # check room on transfer list
            vacancy = self.fme.session().tradepile_size - len(self.fme.session().tradepile())
            logger.info('%s open spots left on the transfer list.', vacancy)
            if vacancy < 15:
                logger.warning('It is nearly full. Not buying new packs.')
                break
            bronze = [x for x in self.fme.session().tradepile() if x['rating'] <= 64]
            if len(bronze) >= 70:
                logger.warning('%s bronze cards in transfer list. Not buying new packs.')
                break

            self.pack()

            # make sure all pack items have been processed
            if self.fme.session().unassigned():
                logger.warning('Unassigned items need attention. No more packs they are cleared.')
                break

        coins_after = self.fme.session().keepalive()
        logger.info('Coins before=%s, after=%s, profit=%s',
                    coins_before, coins_after, coins_after - coins_before)

    def refresh_tradepile(self):
        # handle sold and expired items
        tradepile = self.fme.session().tradepile()
        sold = [x for x in tradepile if x['tradeState'] == 'closed']
        if sold:
            sale = sum([x['currentBid'] for x in sold])
            logger.info('%s items sold for a total of %s coins. Clear=%s',
                        len(sold), sale, self.fme.session().tradepileClear())

        expired = [x for x in tradepile if x['tradeState'] == 'expired']
        if expired:
            relisted = self.fme.session().relist()['tradeIdList']
            logger.info('%s items listing expired. Relist=%s', len(expired), len(relisted))

    def pack(self):
        # buy a new pack only if there is no unassigned items
        if not self.fme.session().unassigned():
            logger.info('Buying a new pack now!')
            self.fme.session().buyPack(100)
        self.unassigned()

    def unassigned(self):
        unassigned = sorted(self.fme.session().unassigned(), key=lambda c: c['itemType'])
        logger.info('Processing %s unassigned cards', len(unassigned))
        sfmt = self.fme.disp.format(unassigned, prepend='{:7}', append='mp={} {}')

        review, keep, discard, redeem, sell = [], [], [], [], []
        for c in unassigned:
            action, prc, seen = self.what_to_do(c)
            if   action == self.DISCARD:
                discard.append(c['id'])
            elif action == self.KEEP:
                keep.append(c['id'])
            elif action == self.REDEEM:
                redeem.append(c['id'])
            elif action == self.SELL:
                sell.append((c, prc))
            elif action == self.REVIEW:
                review.append(c)
            # if we need to call cardInfo(), note that it throws exception for kits, so do:
            # cinfo = self.fme.session().cardInfo(c['resourceId']) if item_type != 'kit' else {}
            logger.info(self.fme.disp.sprint(sfmt, c, action, prc, seen))

        if keep:
            self.fme.session().sendToClub(keep)
        if discard:
            self.fme.session().quickSell(discard)
        for id in redeem:
            self.redeem_item(id)
        for c, prc in sell:
            self.fme.tm.sell(c['id'], prc)

        return review

    def what_to_do(self, c):
        item_id, item_type, card_type = c['id'], c['itemType'], c['cardType']
        prc, seen = c['discardValue'], []
        action = self.REVIEW
        if item_type == 'training': # player and gk training consumables
            action = self.KEEP
        elif ((item_type in ['ball', 'contract', 'kit', 'physio', 'stadium']) or
              (item_type == 'custom' and card_type == 11)): # Badge
            action = self.DISCARD
        elif item_type == 'misc':
            if card_type in [231, 233]: # MiscCoins, Bronze Pack
                action = self.REDEEM
        elif item_type in ['fitnessCoach', 'gkCoach', 'headCoach', 'manager']:
            action = self.DISCARD if item_id in self.fme.session().duplicates else self.KEEP
        elif item_type == 'health':
            if card_type in [211, 212, 213, 215, 216, 217]: # Healing items (HealthXxxxx)
                action = self.KEEP
            elif card_type in [218, 219]: # HealthAll, FitnessPlayer
                action, prc = self.SELL, 200
            elif card_type == 220: # FitnessTeam
                action, prc = self.SELL, 1100
        elif item_type == 'player':
            _, prc, seen = self.fme.tm.search_min_price(c)
            if item_id in self.fme.session().duplicates:
                # sell duplicate players
                action = self.SELL
            else:
                # sell if not in sbc leagues and worthwhile (400 for common, 600 for rare)
                league = self.fme.lu.leagues.to_abbr(c['leagueId'])
                asking_price = 400 if c['rareflag'] == 0 else 600
                if prc > asking_price and league not in ['CHN 1', 'JPN 1']:
                    action = self.SELL
                else:
                    action = self.KEEP
        return action, prc, seen

    def redeem_item(self, item_id):
        url = 'item/{}'.format(item_id)
        data = '{"apply":[]}'
        return self.fme.session().__request__('POST', url, data=data)


def main():
    logging.basicConfig(
        format='%(asctime)s %(levelname)-8s %(message)s',
        datefmt='%m-%d %H:%M:%S',
        level=logging.INFO)


if __name__ == '__main__':
    main()
