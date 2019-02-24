# -*- coding: utf-8 -*-

import codecs
import json
import logging
import os

import unicodecsv as csv

logger = logging.getLogger(__name__)

DB_DIR = os.path.expanduser('~/.futme')

def last_modified(filename):
    filepath = dbfilepath(filename)
    return os.path.getmtime(filepath)

def load_json(filename):
    data = []
    filepath = dbfilepath(filename)
    try:
        with codecs.open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        logger.warn('Error loading json from %s: %s', filename, e)
    return data

def save_json(data, filename):
    filepath = dbfilepath(filename)
    try:
        with codecs.open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, sort_keys=True)
    except Exception as e:
        logger.warn('Error saving json to %s: %s', filename, e)

def save_tsv(rows, filename):
    filepath = dbfilepath(filename)
    try:
        with open(filepath, 'w') as f:
            tsv_writer = csv.writer(f, delimiter='\t', encoding='utf-8')
            for row in rows:
                tsv_writer.writerow(row)
    except Exception as e:
        logger.warn('Error saving data to %s: %s', filename, e)

def dbfilepath(filename):
    return os.path.join(DB_DIR, filename)