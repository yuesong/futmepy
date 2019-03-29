#!/bin/bash

pid=$(ps axu | grep '[m]ain.py' | awk '{print $2}')
kill $pid
echo "main.py $pid killed"
ps axu | grep '[m]ain.py'

pid=$(ps axu | grep '[p]acks.sh' | awk '{print $2}')
kill $pid
echo "packs.sh $pid killed"
ps axu | grep '[p]acks.sh'
