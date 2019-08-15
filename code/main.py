#!/usr/bin/env python
#coding=utf-8

import docker
import graphviz
import json
import socket
import os
from ruamel.yaml import YAML
from collections import defaultdict

TRAEFIK_DEFAULT_PORT = '80/tcp'
BASE_PATH = os.environ['DATA_PATH']

class ShortContainer:
    '''
    This class represents a Docker container with only useful members
    for GraphBuilder.
    '''

    def __init__(self, name):
        self.name = name;
        self.image = str()
        self.ports = defaultdict(set)
        self.networks = set()
        self.links = set()

        self.__backend_port = TRAEFIK_DEFAULT_PORT
        self.__url = str()

    @property
    def backend_port(self):
        return self.__backend_port;

    @backend_port.setter
    def backend_port(self, value):
        if value is not None and '/' not in value:
            value = value + '/tcp'
        self.__backend_port = value

    @property
    def url(self):
        return self.__url;

    @url.setter
    def url(self, value):
        if value is not None:
            value = value.replace('Host:', '')
        self.__url = value

class GraphBuilder:
    '''
    This class asks the Docker daemon informations about running Containers
    and constructs a graph showing dependencies between containers, images and ports.

    We also use Traefik labels to show links between the reverse proxy and the containers.
    '''

    '''
    Constructor.

    :param docker_client (DockerClient): docker client used to build the graph
    :param color_scheme (dict): colors used for the graph
    :param vm_name (str): name of the virtual machine
    :param exclude (list): name of containers to exclude of the layout
    '''
    def __init__(self, docker_client, color_scheme, vm_name, exclude = []):
        self.color_scheme = color_scheme
        self.docker_client = docker_client
        self.vm_name = vm_name
        self.exclude = exclude
        self.has_traefik = False

    '''
    Builds a Digraph object representing a single host.
    After running this function, the Digraph object is accessible
    via the graph property.
    '''
    def build_graph(self):
        running = self.__get_containers()
        graph_attr = {'splines': 'false', 'concentrate': 'true', 'ranksep': '0.8 equally', 'fontcolor': self.color_scheme['dark_text']}
        node_attr = {'style': 'filled,rounded', 'shape': 'record'}
        edge_attr = {}
        self.graph = graphviz.Digraph(comment = 'Machine virtuelle : {0}'.format(self.vm_name), format = 'png', graph_attr = graph_attr, node_attr = node_attr, edge_attr = edge_attr)

        # Create a subgraph for the virtual machine
        with self.graph.subgraph(name = 'cluster_0') as vm:
            vm.attr(label = 'Machine virtuelle : {0}'.format(self.vm_name), style = 'filled,rounded', fillcolor = self.color_scheme['vm'])

            # Group containers by networks
            network_dict = defaultdict(list)
            for c in running:
                for n in c.networks:
                    network_dict[n].append(c)

            # Add all running containers as a node in their own network subgraph
            for k, v in network_dict.items():
                with vm.subgraph(name = 'cluster_{0}'.format(k)) as network:
                    network.attr(label = 'Réseau : {0}'.format(k), style = 'filled,rounded', color = self.color_scheme['network'], fillcolor = self.color_scheme['network'])
                    for c in v:
                        with network.subgraph(name = 'cluster_{0}'.format(c.image)) as image:
                            image.attr(label = c.image, style = 'filled,rounded', color = self.color_scheme['image'], fillcolor = self.color_scheme['image'])
                            image.node(self.__node_name(c.name), self.__record_label(c.name, c.ports), color = self.color_scheme['dark_text'], fillcolor = self.color_scheme['container'], fontcolor = self.color_scheme['dark_text'])
                        # Instead of using a link label (takes a lot of space), put a node without shape for the container's url
                        if self.has_traefik and c.url is not None:
                            network.node(self.__node_name(c.url), c.url, color = self.color_scheme['traefik'], fillcolor = self.color_scheme['traefik'], fontcolor = self.color_scheme['bright_text'])

            for c in running:
                # Add reverse-proxy links
                if self.has_traefik and c.url is not None:
                    vm.edge(self.__node_name(self.traefik_container, TRAEFIK_DEFAULT_PORT), self.__node_name(c.url), arrowhead = "none", color = self.color_scheme['traefik'])
                    vm.edge(self.__node_name(c.url), self.__node_name(c.name, c.backend_port), color = self.color_scheme['traefik'])

                # Add links between containers
                for l in c.links:
                    vm.edge(self.__node_name(c.name, c.name), self.__node_name(l, l), color = self.color_scheme['link'])

                # Add port mapping
                for expose, host_ports in c.ports.items():
                    for port in host_ports:
                        vm.node(self.__node_name(port), port, shape = 'diamond', fillcolor = self.color_scheme['port'], fontcolor = self.color_scheme['bright_text'])
                        vm.edge(self.__node_name(port), self.__node_name(c.name, expose), color = self.color_scheme['port'])

        self.graph.render(os.path.join(BASE_PATH, 'output', '{0}'.format(self.vm_name)))

    '''
    As each node must have a unique name, and because the graph generated by GraphBuilder
    could be later a subgraph, this function compute a node name given a common non-unique
    name, the vm name, and an optional "subname" in case of record-shaped nodes.

    :param name(str): name of the node
    :param subname(str): name of the subnode (the one between <> in the record node label)
    :returns unique name of a node
    :rtype str
    '''
    def __node_name(self, name, subname = ''):
        name = '{0}_{1}'.format(name, self.vm_name)
        if subname:
            name += ':{0}'.format(subname)
        return name

    '''
    A record node is a node with multiple component. We use the record shape to show a
    container along with exposed ports. The container's name is at the left and the ports
    are at the right of the node, ordered top to bottom.

    In our case, the format is the following :
    { <label> text_container } { <label> text_port | <label> text_port ... }
    Then, we can address a specific subnode with the syntax global_label:label, global_label
    being the label of the record node and label being the "sublabel" (the one between <>).

    :param name (str): name of the container
    :param port (list(str)): ports exposed by the container
    :returns label usable for the record node
    :rtype str
    '''
    def __record_label(self, name, ports):
        # As the global label will already be unique, no need to use __node_name here
        # Double-bracket = single bracket in format
        label = '{{ <{0}> {0} }}'.format(name, name)
        if ports:
            label += ' | { '
            for p in ports:
                label += '<{0}> {0} |'.format(p)
            label = label[:-1] + ' }'
        return label

    '''
    Get running docker containers on the host described by docker_client, without those excluded in configuration

    :rtype List
    :returns List of ShortContainer representing running containers
    '''
    def __get_containers(self):

        # Names of all running containers
        running_containers = []

        # Get all running containers
        for c in self.docker_client.containers.list():
            if c.status == 'running' and c.name not in self.exclude:
                s = ShortContainer(c.name)
                s.image = c.image.tags[0]
                networks_conf = c.attrs['NetworkSettings']
                for expose, host in networks_conf['Ports'].items():
                    s.ports[expose].update([p['HostPort'] for p in host] if host is not None else [])
                s.url = c.labels.get('traefik.frontend.rule')
                backend_port = c.labels.get('traefik.port')
                if backend_port is not None:
                    s.backend_port = backend_port
                for n, v in networks_conf['Networks'].items():
                    s.networks.add(n)
                    if v['Links'] is not None:
                        s.links.update([l.split(':')[0] for l in v['Links']])
                running_containers.append(s)

            for i in c.image.tags:
                if 'traefik' in i.split(':')[0]:
                    self.has_traefik = True
                    self.traefik_container = c.name

        return running_containers

class GraphBot:
    '''
    This class is used to create a graph per machine given in the configuration,
    and then combines those graphs to create the "big-picture" graph.

    This graph can then be pushed to a cloud or a Git repository.
    '''

    def __init__(self):
        with open(os.path.join(BASE_PATH, 'config.json'), 'r') as fd:
            self.config = json.load(fd)

    '''
    Builds a Digraph object representing the architecture of all hosts.
    After running this function, the graph attribute contains a Digraph object.
    '''
    def create_graph(self):
        graphs = []
        for host in self.config['hosts']:
            if host['host_url'] == 'localhost':
                docker_client = docker.from_env()
            elif 'tls_config' in host:
                tls_config = docker.tls.TLSConfig(
                    client_cert = (os.path.join(BASE_PATH, host['tls_config']['cert']), os.path.join(BASE_PATH, host['tls_config']['key'])),
                    ca_cert = os.path.join(BASE_PATH, host['tls_config']['ca_cert']),
                    assert_hostname = True,
                    # Should work but raise TypeError: inet_aton() argument 1 must be str, not bool.
                    # The code [here](https://github.com/docker/docker-py/blob/master/docker/tls.py#L100) seems ok...
                    # So we'll get InsecureRequestWarning: Unverified HTTPS request is being made when running this script
                    # verify = True
                )
                docker_client = docker.DockerClient(base_url = host['host_url'], tls = tls_config)
            else:
                raise Exception('Missing tls_config !')

            builder = GraphBuilder(docker_client, self.config['color_scheme'], host['vm'])
            builder.build_graph()
            graphs.append(builder.graph)

if __name__ == '__main__':
    bot = GraphBot()
    bot.create_graph()
