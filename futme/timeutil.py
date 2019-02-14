# -*- coding: utf-8 -*-

import time

SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR   = SECONDS_PER_MINUTE * 60
SECONDS_PER_DAY    = SECONDS_PER_HOUR * 24

def time_within(t, t1, t2):
    start, end = (t1, t2) if t1 <= t2 else (t2, t1)
    return start <= t and t < end

def dur_str(val):
    fmt = ''
    args = []
    
    d = dur_days(val)
    if d > 0:
        fmt = '{}d'
        args.append(d)
    
    val -= d * SECONDS_PER_DAY
    h = dur_hours(val)
    if len(fmt) > 0 or h > 0:
        fmt += '{}h'
        args.append(h)
    
    val -= h * SECONDS_PER_HOUR
    m = dur_minutes(val)
    if len(fmt) > 0 or m > 0:
        fmt += '{}m'
        args.append(m)

    val -= m * SECONDS_PER_MINUTE
    s = dur_seconds(val)
    if len(fmt) > 0 or s > 0:
        fmt += '{}s'
        args.append(s)

    return fmt.format(*args)


def dur_seconds(val):
    return conv_dur(val)

def dur_minutes(val):
    return conv_dur(val, SECONDS_PER_MINUTE)

def dur_hours(val):
    return conv_dur(val, SECONDS_PER_HOUR)

def dur_days(val):
    return conv_dur(val, SECONDS_PER_DAY)

def conv_dur(val, base=1):
    return int(float(val)/base)
