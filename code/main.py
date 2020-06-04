#!/usr/bin/env python
# coding=utf-8

import os
import logging

from render import GraphBot

if __name__ == '__main__':
    format = '%(asctime)s [%(levelname)s] ' \
             '%(message)s (%(filename)s:%(lineno)d)'
    logging.basicConfig(
        format=format,
        datefmt='%Y/%m/%d %H:%M:%S',
        level=logging.DEBUG
    )
    logging.debug('Starting GraphBot')
    bot = GraphBot(os.path.join(os.environ['CONFIG_PATH'], 'config.json'))
    bot.build()
    logging.debug('Stopping GraphBot')
