#!/bin/bash

cd futmepy
source venv/bin/activate
nohup python main.py &> futme.log&
