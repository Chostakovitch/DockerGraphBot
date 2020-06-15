#!/usr/bin/env python
# coding=utf-8
"""Logic to render DOT graphs representing a complete infrastructure in PNG."""

import json
import os
import logging

from urllib.request import urlopen
from datetime import datetime
from typing import Any, Dict, Optional

import docker
import dns.resolver
import jsonschema
from jsonschema.exceptions import ValidationError, SchemaError
from graphviz import Digraph

from build import GraphBuilder
from actions import WebDAVUploader, SFTPUploader


class GraphBot:
    """
    Create a PNG graph for each machine given in the configuration.

    Merge all graphs is requested in configuration ("big-picture").
    """

    @property
    def graph(self) -> Digraph:
        """Build the final graph if not built yet, and return it."""
        if self.__graph is None:
            self.build()
        return self.__graph

    @property
    def legend(self) -> Digraph:
        """Build the graph for legend from template and return it."""
        legend = Digraph(
            name='legend',
            node_attr={'style': 'rounded', 'shape': 'plain'},
            format='png')
        # Categories of nodes and edges are fixed, we just
        # need to update colors if they are customized
        with open(self.__get_real_path('legend.template')) as legend_template:
            template = legend_template.read()
            legend.node('legend', template.format(
                self.config['organization'],
                self.config['color_scheme'].get('traefik', '#edb591'),
                self.config['color_scheme'].get('port', '#86c49b'),
                self.config['color_scheme'].get('link', '#75e9cd'),
                self.config['color_scheme'].get('image', '#e1efe6'),
                self.config['color_scheme'].get('container', '#ffffff'),
                self.config['color_scheme'].get('network', '#ffffff'),
                self.config['color_scheme'].get('host', '#e1efe6'),
                self.config['color_scheme'].get('volume', '#819cd9'),
                self.config['color_scheme'].get('bind_mount', '#b19cd9')
            ))
        return legend

    def __init__(self, config_file, output_path, certs_path):
        """Initialize GraphBot. Read configuration from file."""
        try:
            with open(config_file) as fd:
                self.config = json.load(fd)
        except (OSError, IOError, json.JSONDecodeError) as e:
            logging.error('Failed to read configuration.')
            raise e

        # Validate configuration
        self.__check_config()

        self.__graph = None
        self.__output_path = output_path
        self.__certs_path = certs_path
        self.__generated_files = []

    def build(self):
        """
        Build a Digraph object representing the architecture of all hosts.

        The final graph is accessible with the graph property if merge is
        true in the configuration, otherwise you just get the last built
        graph.
        """
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
        graph_name = f"{self.config['organization']} architecture"
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
                graphs[host['name']] = self.__build_subgraph(host)
                logging.info('Graph for %s successfully built', host['name'])
            except docker.errors.APIError as e:
                logging.error('Error when communicating with %s, skipping.',
                              host['name'])
                logging.exception(e)
            except Exception as e:
                logging.error('Unknown error while building graph.')
                logging.exception(e)
        self.__render_graph(graphs)
        self.__post_actions()

    def __render_graph(self, graphs: Dict[str, Digraph]):
        """Render one or several graphs in PNG format from a list of graphs."""
        for host_name, graph in graphs.items():
            # If we are asked to make a big picture, just
            # add each graph as a subgraph
            if self.config['merge']:
                self.__graph.subgraph(graph=graph)
            # Otherwise, replace old graph with new graph
            # and render it immediately
            else:
                self.__graph.body = graph.body
                path = os.path.join(self.__output_path, f'{host_name}.dot')
                self.__graph.render(path)
                self.__generated_files.append(f'{path}.png')

        if self.config['merge']:
            path = os.path.join(
                self.__output_path,
                f"{self.config['organization']}.dot")
            self.__graph.render(path)
            self.__generated_files.append(f'{path}.png')
            logging.info("Global rendering is successful !")

        legend_path = os.path.join(self.__output_path, 'legend.dot')
        self.__generated_files.append(f'{legend_path}.png')
        self.legend.render(legend_path)
        logging.info("Legend rendering is successful !")

    def __post_actions(self):
        """Perform eventuals actions after rendering the files."""
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

    def __build_subgraph(self, host: Dict[str, Any]) -> Digraph:
        """Query a specific host and return its built graph."""
        host_name = f"{host['name']} ("
        if host['url'] == 'localhost':
            docker_client = docker.from_env()
            # Do not use private IP
            host_name += \
                urlopen('https://wtfismyip.com/text') \
                .read() \
                .decode("utf-8") \
                .replace('\n', '')
        else:
            # Build configuration to securely exchange with Docker socket
            cert_p = os.path.join(
                self.__certs_path,
                host['tls_config']['cert'])
            key_p = os.path.join(
                self.__certs_path,
                host['tls_config']['key'])
            ca_p = os.path.join(
                self.__certs_path,
                host['tls_config']['ca_cert'])
            tls_config = docker.tls.TLSConfig(
                client_cert=(cert_p, key_p),
                verify=ca_p
            )
            docker_client = docker.DockerClient(
                base_url=f"{host['url']}:{host['port']}",
                tls=tls_config
            )
            # Not building for localhost, get public IP from DNS servers
            for result in dns.resolver.query(host['url']):
                host_name += f'{result.address}'

        # Build a nice name, with hostname, public IP and generated date
        host_name += f') at {datetime.now().strftime("%d/%m/%Y %H:%M")}'

        # Check if the Docker daemon is accessible with current params
        # If yes, starting graph building process
        docker_client.ping()
        builder = GraphBuilder(
            docker_client,
            self.config['color_scheme'],
            host_name,
            host['name'],
            host.get('exclude', [])
        )
        return builder.graph

    def __check_config(self) -> Optional[str]:
        """Perform syntaxic and logic checks of the configuration."""
        with open(self.__get_real_path('schema.json')) as schema:
            try:
                jsonschema.validate(self.config, json.load(schema))
                return None
            except (ValidationError, SchemaError) as schema_err:
                logging.error('Invalid configuration!')
                raise schema_err

        # Ensure that there is not duplicate hostnames
        # as the name of nodes, which must be unique
        # is based on this property
        hosts = [host['name'] for host in self.config['hosts']]
        unique_hosts = set(hosts)
        if len(hosts) != len(unique_hosts):
            raise Exception('Two hosts cannot have the same name')

    @staticmethod
    def __get_real_path(relative_path: str) -> str:
        """Return absolute path of a path starting in the current directory."""
        return os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            relative_path)
