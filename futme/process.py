# -*- coding: utf-8 -*-

import logging
import time

from . import timeutil

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
            tradepile = self.fme.session().tradepile()
            sold = [x for x in tradepile if x['tradeState'] == 'closed']
            if len(sold) > 0:
                sale = sum([x['currentBid'] for x in sold])
                logger.info('%s items sold for a total of %s coins. Clear=%s', 
                    len(sold), sale, self.fme.session().tradepileClear())
            
            expired = [x for x in tradepile if x['tradeState'] == 'expired']
            if len(expired) > 0:
                relisted = self.fme.session().relist()['tradeIdList']
                logger.info('%s items listing expired. Relist=%s', len(expired), len(relisted))
            
            # check room on transfer list
            vacancy = self.fme.session().tradepile_size - len(self.fme.session().tradepile())
            logger.info('%s open spots left on the transfer list.', vacancy)
            if vacancy < 15:
                logger.warn('It is nearly full. We are done for now')
                break

            self.pack()

            # make sure all pack items have been processed
            if len(self.fme.session().unassigned()) > 0:
                logger.warn('Unassigned items need attention. No more packs they are cleared.')
                break

        coins_after = self.fme.session().keepalive()
        logger.info('Coins before=%s, after=%s, profit=%s', 
            coins_before, coins_after, coins_after - coins_before)

    def pack(self):
        # buy a new pack only if there is no unassigned items
        if len(self.fme.session().unassigned()) == 0:
            logger.info('Buying a new pack now!')
            self.fme.session().buyPack(100)
        self.unassigned()

    def unassigned(self):
        unassigned = sorted(self.fme.session().unassigned(), key=lambda c: c['itemType'])
        logger.info('Processing %s unassigned cards', len(unassigned))
        sfmt = self.fme.disp.format(unassigned, prepend='{:7}', append='mp={} {}')

        review, keep, discard, redeem, sell = [], [], [], [], []
        for c in unassigned:
            action, price, seen = self.what_to_do(c)
            if   action == self.DISCARD: discard.append(c['id'])
            elif action == self.KEEP:    keep.append(c['id'])
            elif action == self.REDEEM:  redeem.append(c['id'])
            elif action == self.SELL:    sell.append((c, price))
            elif action == self.REVIEW:  review.append(c)
            # if we need to call cardInfo(), note that it throws exception for kits, so do:
            # cinfo = self.fme.session().cardInfo(c['resourceId']) if item_type != 'kit' else {}
            logger.info(self.fme.disp.sprint(sfmt, c, action, price, seen))

        if keep:            self.fme.session().sendToClub(keep)
        if discard:         self.fme.session().quickSell(discard)
        for id in redeem:   self.redeem_item(id)
        for c, pri in sell: self.fme.tm.sell(c['id'], pri)

        return review

    def what_to_do(self, c):
        item_id, item_type, card_type = c['id'], c['itemType'], c['cardType']
        price, seen = c['discardValue'], []
        action = self.REVIEW
        if item_type == 'training': # player and gk training consumables
            action = self.KEEP
        elif ((item_type in ['ball', 'contract', 'kit', 'physio', 'stadium']) or
                (item_type == 'custom' and card_type == 11)): # Badge
            action = self.DISCARD
        elif item_type == 'misc':
            if card_type == 231: # MiscCoins
                action = self.REDEEM
        elif item_type in ['fitnessCoach', 'gkCoach', 'headCoach', 'manager']:
            action = self.DISCARD if item_id in self.fme.session().duplicates else self.KEEP
        elif item_type == 'health':
            if card_type in [211, 212, 213, 215, 216, 217]: # Healing items (HealthXxxxx)
                action = self.KEEP
            elif card_type in [218, 219]: # HealthAll, FitnessPlayer
                action, price = self.SELL, 200
            elif card_type == 220: # FitnessTeam
                action, price = self.SELL, 1100
        elif item_type == 'player':
            _, price, seen = self.fme.tm.search_min_price(c)
            if item_id in self.fme.session().duplicates: 
                # sell duplicate players
                action = self.SELL
            else:
                # sell if not in sbc leagues and worthwhile (400 for common, 600 for rare)
                league = self.fme.lu.leagues.to_abbr(c['leagueId'])
                asking_price = 400 if c['rareflag'] == 0 else 600
                if price > asking_price and league not in ['CHN 1', 'JPN 1']:
                    action = self.SELL
                else:
                    action = self.KEEP
        return action, price, seen

    def redeem_item(self, item_id):
        return self.fme.session().__request__('POST', 'item/{}'.format(item_id), data='{"apply":[]}')


class Worker(object):

    def __init__(self):
        self.tasks = []
    
    def register_task(self, name, func, interval, delay = 0):
        self.tasks.append(Task(name, func, interval, delay))

    def do_work(self):
        for t in self.tasks:
            t.execute()

    def set_task_interval(self, task_name, new_value):
        return [t.set_interval(new_value) for t in self.tasks if t.name == task_name]

class Flipper(Worker):

    def __init__(self, fme, rid):
        super(Flipper, self).__init__()
        self.fme = fme
        self.rid = rid
        defs = [p for p in self.fme.session().searchDefinition(rid) if p['resourceId'] == rid]
        if defs:
            self.definion = defs[0]
            self.register_task('flipper.update_price', self.update_price, 1200)
            self.register_task('flipper.attempt', self.attempt, 10)
        else:
            logger.warn("No definition found for rid=%s. Flipper disabled.")

    def update_price(self):
        logger.info('TODO: update price')
        player, mkt_price, seen = self.fme.tm.search_min_price(self.rid)

    def attempt(self):
        logger.info('TODO: attempt to buy')


class Task(object):

    def __init__(self, name, func, interval, delay):
        self.func = func
        self.interval = interval
        self.last_execution_time = 0 if delay == 0 else time.time() + delay

    def execute(self):
        if time.time() - self.last_execution_time > self.interval:
            self.func()
            self.last_execution_time = time.time()

    def set_interval(self, new_value):
        old_value, self.interval = self.interval, new_value
        return old_value
        

def main():
    logging.basicConfig(
        format='%(asctime)s %(levelname)-8s %(message)s',
        datefmt='%m-%d %H:%M:%S',
        level=logging.INFO)
    flipper = Flipper(None, None)
    for _ in range(60):
        flipper.do_work()
        time.sleep(1)



if __name__ == '__main__':
    main()
