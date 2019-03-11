#!/bin/bash

pid=$(ps axu | grep '[m]ain.py' | awk '{print $2}')
kill $pid
echo "$pid killed"
ps axu | grep '[m]ain.py'
