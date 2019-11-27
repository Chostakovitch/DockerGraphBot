#!/usr/bin/env python
#coding=utf-8

import os

from render import GraphBot

if __name__ == '__main__':
    bot = GraphBot(os.path.join(os.environ['CONFIG_PATH'], 'config.json'))
    bot.build()
