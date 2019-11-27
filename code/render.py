#!/usr/bin/env python
#coding=utf-8

import dns.resolver
import json
import socket
import os
import graphviz
import docker

from jsonschema import validate
from urllib.request import urlopen
from datetime import datetime
from typing import List

from build import GraphBuilder
from actions import WebDAVUploader

CONFIG_PATH = os.environ['CONFIG_PATH']
OUTPUT_PATH = os.environ['OUTPUT_PATH']

'''
This class is used to create a graph per machine given in the configuration,
and then combines those graphs to create the "big-picture" graph.

This graph can then be pushed to a cloud or a Git repository.
'''
class GraphBot:
    @property
    def graph(self):
        if self.__graph is None:
            self.build()
        return self.__graph

    @property
    def legend(self):
        if self.__legend is None:
            self.__legend = graphviz.Digraph('legend', node_attr = { 'style': 'rounded', 'shape': 'plain' }, format = 'png')
            self.__legend.node('legend', '''<
            <TABLE BORDER="1" CELLBORDER="0" CELLSPACING="10" CELLPADDING="4">
                <TR>
                    <TD COLSPAN="2"><B>Legend of {0} architecture</B></TD>
                </TR>
                <TR>
                    <TD ALIGN="LEFT">Traefik "Host" label</TD>
                    <TD BORDER="1" WIDTH="100" BGCOLOR="{1}"></TD>
                </TR>
                <TR>
                    <TD ALIGN="LEFT">Host port</TD>
                    <TD BORDER="1" WIDTH="100" BGCOLOR="{2}"></TD>
                </TR>
                <TR>
                    <TD ALIGN="LEFT">Docker link</TD>
                    <TD BORDER="1" WIDTH="100" BGCOLOR="{3}"></TD>
                </TR>
                <TR>
                    <TD ALIGN="LEFT">Image</TD>
                    <TD BORDER="1" WIDTH="100" BGCOLOR="{4}"></TD>
                </TR>
                <TR>
                    <TD ALIGN="LEFT">Container, exposed ports</TD>
                    <TD BORDER="1" WIDTH="100" BGCOLOR="{5}"></TD>
                </TR>
                <TR>
                    <TD ALIGN="LEFT">Docker network</TD>
                    <TD BORDER="1" WIDTH="100" BGCOLOR="{6}"></TD>
                </TR>
                <TR>
                    <TD ALIGN="LEFT">Virtual machine</TD>
                    <TD BORDER="1" WIDTH="100" BGCOLOR="{7}"></TD>
                </TR>
            </TABLE>>'''.format(
                self.config['organization'],
                self.config['color_scheme']['traefik'],
                self.config['color_scheme']['port'],
                self.config['color_scheme']['link'],
                self.config['color_scheme']['image'],
                self.config['color_scheme']['container'],
                self.config['color_scheme']['network'],
                self.config['color_scheme']['vm']
            ))
        return self.__legend

    def __init__(self, config_path = os.path.join(CONFIG_PATH, 'config.json')):
        with open(config_path) as fd:
            self.config = json.load(fd)

        # Validate configuration
        self.__check_config()

        self.__graph = None
        self.__legend = None
        self.__generated_files = []

    '''
    Builds a Digraph object representing the architecture of all hosts.
    After running this function, the __graph attribute contains the final graph.
    '''
    def build(self):
        graph_attr = {
            # Draw straight lines
            'splines': 'false',
            # Merge edges when possible
            'concentrate': 'true',
            # Minimum distance (inches) between node of successive ranks
            'ranksep': '0.8 equally',
            # Allow edges between clusters (important for our invisible edges between subgraphs)
            'compound': 'true',
            # Defaut text/border color
            'fontcolor': self.config['color_scheme']['dark_text']
        }
        node_attr = {
            # All nodes are colorfull and with rounded borders
            'style': 'filled,rounded',
            # Allow sub-nodes
            'shape': 'record'
        }
        graph_name = '{} architecture'.format(self.config['organization'])
        self.__graph = graphviz.Digraph(
            name = graph_name,
            comment = graph_name,
            graph_attr = graph_attr,
            node_attr = node_attr,
            format = 'png'
        )

        graphs = self.__build_subgraphs()
        self.__render_graph(graphs)
        self.__post_actions()

    '''
    Perform eventuals actions after rendering the files
    '''
    def __post_actions(self):
        for a in self.config['actions']:
            # Upload generated PNG
            if a['type'] == 'webdav':
                web_dav = WebDAVUploader(a['hostname'], a['login'], a['password'], a['remote_path'])
                web_dav.upload(self.__generated_files)
    '''
    Render one or several graphs in PNG format from a list of graphs
    '''
    def __render_graph(self, graphs: List[GraphBuilder]):
        for builder in graphs:
            if self.config['merge']:
                self.__graph.subgraph(graph = builder.graph)
            else:
                self.__graph.body = builder.graph.body
                path = os.path.join(OUTPUT_PATH, builder.vm_name)
                self.__graph.render(path)
                self.__generated_files.append('{}.png'.format(path))

        if self.config['merge']:
            path = os.path.join(OUTPUT_PATH, self.config['organization'])
            self.__graph.render(path)
            self.__generated_files.append('{}.png'.format(path))
            print("Global rendering is successful !")

        legend_path = os.path.join(OUTPUT_PATH, 'legend')
        self.__generated_files.append('{}.png'.format(legend_path))
        self.legend.render(legend_path)
        print("Legend rendering is successful !")

    '''
    Query all hosts and return all corresponding graphs
    :returns Graphs of hosts
    :rtype List(GraphBuilder)
    '''
    def __build_subgraphs(self):
        graphs = []
        for host in self.config['hosts']:
            vm_name = host['vm'] + ' | '
            if host['host_url'] == 'localhost':
                docker_client = docker.from_env()
                vm_name += urlopen('http://ip.42.pl/raw').read().decode("utf-8")
            else:
                tls_config = docker.tls.TLSConfig(
                    client_cert = (
                        os.path.join(CONFIG_PATH, host['tls_config']['cert']),
                        os.path.join(CONFIG_PATH, host['tls_config']['key'])
                    ),
                    verify = os.path.join(CONFIG_PATH, host['tls_config']['ca_cert'])
                )
                docker_client = docker.DockerClient(base_url = '{0}:{1}'.format(host['host_url'], host['port']), tls = tls_config)
                for result in dns.resolver.query(host['host_url']):
                    vm_name += '{}'.format(result.address)
            vm_name += ' | Generated date : {} '.format(datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
            builder = GraphBuilder(docker_client, self.config['color_scheme'], vm_name, host['vm'], host.get('exclude', []))
            print('{} built.'.format(builder.graph.name))
            graphs.append(builder)

        return graphs

    '''
    Perform syntaxic and logic checks of the configuration.
    :returns None if the configuration is clean, an informative error message otherwise
    :rtype str
    '''
    def __check_config(self):
        with open(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'schema.json')) as schema:
            try:
                validate(self.config, json.load(schema))
            except Exception as valid_err:
                raise Exception("Invalid configuration: {}".format(valid_err))

        hosts = [host['vm'] for host in self.config['hosts']]
        unique_hosts = set(hosts)
        if len(hosts) != len(unique_hosts):
            duplicate = [h for h in hosts if not h in unique_hosts or unique_hosts.remove(h)]
            raise Exception('Invalid configuration: two hosts cannot have the same name ({})'.format(duplicate[0]))
