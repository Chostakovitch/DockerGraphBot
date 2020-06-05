#!/usr/bin/env python
# coding=utf-8

import os
import logging
import argparse

from render import GraphBot

if __name__ == '__main__':
    # Define logger format
    format = '%(asctime)s [%(levelname)s] ' \
             '%(message)s (%(filename)s:%(lineno)d)'
    logging.basicConfig(
        format=format,
        datefmt='%Y/%m/%d %H:%M:%S',
        level=logging.DEBUG
    )
    logging.debug('Starting GraphBot')

    # Get command line arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('-o', '--output-directory',
                        help='path for output directory of DOT and PNG files')
    parser.add_argument('-c', '--config-file',
                        help='path of the configuration file')
    parser.add_argument('-t', '--certs-directory',
                        help='path of the directory container certificates')
    args = parser.parse_args()
    if args.output_directory is None:
        logging.warning('Output path not defined, default to ./output')
        args.output_directory = 'output'
    if args.config_file is None:
        logging.warning('Config file not defined, default to ./config.json ')
        args.config_file = 'config.json'
    if args.certs_directory is None:
        logging.warning('Certs directory not defined, default to ./certs')
        args.certs_directory = 'certs'
    bot = GraphBot(args.config_file, args.output_directory, args.certs_directory)
    bot.build()
    logging.debug('Stopping GraphBot')
