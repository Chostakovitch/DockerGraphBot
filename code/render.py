#!/usr/bin/env python
# coding=utf-8

import dns.resolver
import json
import socket
import os
import docker
import sys

import logging

from graphviz import Digraph
from jsonschema import validate
from urllib.request import urlopen
from datetime import datetime
from typing import List, Dict

from build import GraphBuilder
from actions import WebDAVUploader, SFTPUploader

CONFIG_PATH = os.environ['CONFIG_PATH']
OUTPUT_PATH = os.environ['OUTPUT_PATH']


class GraphBot:
    '''
    This class creates a graph per machine given in the configuration
    and then combines those graphs to create a "big-picture" graph.
    '''
    @property
    def graph(self):
        if self.__graph is None:
            self.build()
        return self.__graph

    @property
    def legend(self):
        if self.__legend is None:
            self.__legend = Digraph(
                name='legend',
                node_attr={'style': 'rounded', 'shape': 'plain'},
                format='png')
            # Categories of nodes and edges are fixed, we just
            # need to update colors if they are customized
            with open(self.__get_real_path('legend.template')) as legend:
                template = legend.read()
                self.__legend.node('legend', template.format(
                    self.config['organization'],
                    self.config['color_scheme'].get('traefik', '#edb591'),
                    self.config['color_scheme'].get('port', '#86c49b'),
                    self.config['color_scheme'].get('link', '#75e9cd'),
                    self.config['color_scheme'].get('image', '#e1efe6'),
                    self.config['color_scheme'].get('container', '#ffffff'),
                    self.config['color_scheme'].get('network', '#ffffff'),
                    self.config['color_scheme'].get('vm', '#e1efe6'),
                    self.config['color_scheme'].get('volume', '#819cd9'),
                    self.config['color_scheme'].get('bind_mount', '#b19cd9')
                ))
        return self.__legend

    def __init__(self, config_path=os.path.join(CONFIG_PATH, 'config.json')):
        with open(config_path) as fd:
            self.config = json.load(fd)

        # Validate configuration
        self.__check_config()

        self.__graph = None
        self.__legend = None
        self.__generated_files = []

    '''
    Builds a Digraph object representing the architecture of all hosts
    and store the final graph in __graph.
    '''
    def build(self):
        font_color = self.config['color_scheme'].get('dark_text', '#32384f')
        graph_attr = {
            # Draw straight lines
            'splines': 'false',
            # Merge edges when possible
            'concentrate': 'true',
            # Minimum distance (inches) between node of successive ranks
            'ranksep': '0.8 equally',
            # Allow edges between clusters
            'compound': 'true',
            # Defaut text/border color
            'fontcolor': font_color
        }
        node_attr = {
            # All nodes are colorfull and with rounded borders
            'style': 'filled,rounded',
            # Allow sub-nodes
            'shape': 'record'
        }
        graph_name = '{} architecture'.format(self.config['organization'])
        self.__graph = Digraph(
            name=graph_name,
            comment=graph_name,
            graph_attr=graph_attr,
            node_attr=node_attr,
            format='png'
        )

        graphs = {}
        for host in self.config['hosts']:
            try:
                graphs[host['vm']] = self.__build_subgraph(host)
                logging.info('Graph for {} successfully built'.format(
                    host['vm'])
                )
            except docker.errors.APIError as e:
                logging.error('Error when communicating with {}, skipping.'
                              .format(host['vm']))
                logging.exception(e)
            except Exception as e:
                logging.error('Unknown error while building graph.')
                logging.exception(e)
        self.__render_graph(graphs)
        self.__post_actions()

    '''
    Perform eventuals actions after rendering the files
    '''
    def __post_actions(self):
        for action in self.config.get('actions', []):
            # Upload generated PNG
            if action['type'] == 'webdav':
                web_dav = WebDAVUploader(
                    action['hostname'],
                    action['login'],
                    action['password'],
                    action['remote_path']
                )
                web_dav.upload(self.__generated_files)
            elif action['type'] == 'sftp':
                sftp_client = SFTPUploader(
                    action['hostname'],
                    action['port'],
                    action['login'],
                    action['password'],
                    action['remote_path']
                )
                sftp_client.upload(self.__generated_files)

    '''
    Render one or several graphs in PNG format from a list of graphs
    '''
    def __render_graph(self, graphs: Dict[str, Digraph]):
        for vm_name, graph in graphs.items():
            # If we are asked to make a big picture, just
            # add each graph as a subgraph
            if self.config['merge']:
                self.__graph.subgraph(graph=graph)
            # Otherwise, replace old graph with new graph
            # and render it immediately
            else:
                self.__graph.body = graph.body
                path = os.path.join(OUTPUT_PATH, vm_name)
                self.__graph.render(path)
                self.__generated_files.append('{}.png'.format(path))

        if self.config['merge']:
            path = os.path.join(OUTPUT_PATH, self.config['organization'])
            self.__graph.render(path)
            self.__generated_files.append('{}.png'.format(path))
            logging.info("Global rendering is successful !")

        legend_path = os.path.join(OUTPUT_PATH, 'legend')
        self.__generated_files.append('{}.png'.format(legend_path))
        self.legend.render(legend_path)
        logging.info("Legend rendering is successful !")

    '''
    Query a specific host and return its built graph
    :returns Graph of host
    :rtype Digraph
    '''
    def __build_subgraph(self, host: Dict[str, Dict]):
        vm_name = host['vm'] + ' | '
        if host['host_url'] == 'localhost':
            docker_client = docker.from_env()
            # Do not use private IP
            vm_name += \
                urlopen('https://wtfismyip.com/text') \
                .read() \
                .decode("utf-8") \
                .replace('\n', '')
        else:
            # Build configuration to securely exchange with Docker socket
            cert_p = os.path.join(CONFIG_PATH, host['tls_config']['cert'])
            key_p = os.path.join(CONFIG_PATH, host['tls_config']['key'])
            ca_p = os.path.join(CONFIG_PATH, host['tls_config']['ca_cert'])
            tls_config = docker.tls.TLSConfig(
                client_cert=(cert_p, key_p),
                verify=ca_p
            )
            docker_client = docker.DockerClient(
                base_url='{0}:{1}'.format(host['host_url'], host['port']),
                tls=tls_config
            )
            # Not building for localhost, get public IP from DNS servers
            for result in dns.resolver.query(host['host_url']):
                vm_name += '{}'.format(result.address)

        # Build a nice name, with hostname, public IP and generated date
        vm_name += ' | Generated date : {} '.format(
            datetime.now().strftime("%d/%m/%Y %H:%M")
        )

        # Check if the Docker daemon is accessible with current params
        # If yes, starting graph building process
        docker_client.ping()
        builder = GraphBuilder(
            docker_client,
            self.config['color_scheme'],
            vm_name,
            host['vm'],
            host.get('exclude', [])
        )
        return builder.graph

    '''
    Perform syntaxic and logic__get_real_path checks of the configuration.
    :returns None if the configuration is clean, error message otherwise
    :rtype str
    '''
    def __check_config(self):
        with open(self.__get_real_path('schema.json')) as schema:
            try:
                validate(self.config, json.load(schema))
            except Exception as valid_err:
                raise Exception("Invalid configuration: {}".format(valid_err))

        # Ensure that there is not duplicate hostnames
        # as the name of nodes, which must be unique
        # is based on this property
        hosts = [host['vm'] for host in self.config['hosts']]
        unique_hosts = set(hosts)
        if len(hosts) != len(unique_hosts):
            raise Exception('Two hosts cannot have the same name')

    '''
    Returns absolute path of a relative_path starting
    from the current directory
    '''
    def __get_real_path(self, relative_path: str):
        return os.path.join(
                        os.path.dirname(os.path.realpath(__file__)),
                        relative_path)
