# -*- coding: utf-8 -*-

import logging
import sys
import time
from random import randint

import futme.core as core
import futme.display as display
import futme.price as price
import futme.timeutil as timeutil
import futme.totw as totw
import futme.util as util
import futme.datafile as datafile

from futme.autopilot import AutoPilot
from futme.util import sms
from futme.worker import LoopyWorker
from futme.futbin import print_sbc_buyer_configs

logging.basicConfig(
    format='%(asctime)s %(levelname)-8s %(message)s',
    datefmt='%m-%d %H:%M:%S',
    level=logging.INFO)
logger = logging.getLogger(__name__)

fme = core.Futme()

def main():
    if len(sys.argv) == 2 and sys.argv[1] in ['?', 'help']:
        print('Usage:')
        print('  main.py packs')
        print('  main.py price_listed')
        print('  main.py cleanup_tradepile')
        print('  main.py dump_club_players gold|silver|bronze')
        print('  main.py dump_expandables')
        print('  main.py totw <week>')
        print('  main.py sms <message>')
        print('  main.py sbc <fbids>')
        return

    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == 'packs':
            fme.proc.packs()
        elif cmd == 'cleanup_tradepile':
            # for p in fme.tm.tradepile.inactive():
            #     fme.session().sendToClub(p['id'])
            # fme.tm.tradepile.refresh()
            cleanup = fme.tm.tradepile_cleanup_targets(keep_all_above_rating=100, sell_all_below_rating=100)
            fme.tm.sell_all(cleanup)
        elif cmd == 'price_listed':
            fme.tm.price_players(fme.tm.tradepile.inactive())
        elif cmd == 'dump_club_players':
            level = sys.argv[2]
            p = fme.club.all_players(level=level)
            datafile.dump_players(p, 'futme_club_all_players_' + level, fme)
        elif cmd == 'dump_expandables':
            p = fme.club.expandables()
            datafile.dump_players(p, 'futme_club_expandables', fme)
        elif cmd == 'totw':
            wk = sys.argv[2]
            totw.print_autotrader_config(totw.totw(wk))
        elif cmd == 'sms':
            sms(' '.join(sys.argv[2:]))
        elif cmd == 'sbc':
            fbids = sys.argv[2].split(',')
            print_sbc_buyer_configs(fme, fbids)
        else:
            logger.error('invalid command: %s', sys.argv[1:])
    else:
        AutoPilot(fme, 'autopilot.json').run()

    fme.shutdown()

def totw_prices():
    players = fme.club.special(rareflags=[3])
    players = [p for p in players if not p['untradeable']]
    sfmt = fme.disp.format(players, append='{}')
    def proc(p):
        tenure = timeutil.dur_days(time.time() - p['timestamp'])
        bought_for = p['lastSalePrice']
        est_price = price.quick(p)
        incr = est_price - bought_for
        incr_pct = str(int(incr*100.0/bought_for)) + '%' if bought_for > 0 else 'INF'
        profit = int(incr - est_price * 0.05)
        h = price.history(p)
        h7d = h.slice(7)
        h30d = h.slice(30)
        h_str = 'hilo: 1wk={}/{} 1mo={}/{}'.format(h7d.high(), h7d.low(), h30d.high(), h30d.low())
        s = 'sl={:>2}d mp={:<5} in={:<4} pf={} {}'.format(
            tenure, est_price, incr_pct, profit, h_str)
        return (p, profit, s)

    lst = [proc(p) for p in players]
    lst.sort(key=lambda x: x[1], reverse=True)
    sfmt = fme.disp.format(players, append='{}')
    for p, _, s in lst:
        logger.info(fme.disp.sprint(sfmt, p, s))


if __name__ == '__main__':
    main()
