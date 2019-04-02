#!/bin/bash

cd futmepy
source venv/bin/activate
echo "packs infinite!"
while true; sleep 1800; do python main.py packs; done
