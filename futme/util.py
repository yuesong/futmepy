# -*- coding: utf-8 -*-

def sorter(item, descending=True):
    val = item['rating'] * 1e15 + item['discardValue'] * 1e12 + item['assetId'] * 1e6 + item['resourceId']
    if descending:
        val = -val
    return val

def sorter_key(descending=True):
    return lambda x: sorter(x)