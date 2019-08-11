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

class ShortContainer:
	'''
	This class represents a Docker container with only useful members
	for GraphBot.
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

class GraphBot:
	'''
	This class asks the Docker daemon informations about running Containers
	and constructs a graph showing dependencies between containers, images and ports.

	We also use Traefik labels to show links between the reverse proxy and the containers.
	'''

	DIR_NAME = os.path.dirname(os.path.realpath(__file__))

	def __init__(self, config_path = DIR_NAME, output_dir = DIR_NAME):
		# Get configuration
		with open(os.path.join(config_path, 'config.json'), 'r') as fd:
			self.config = json.load(fd)
		self.output_dir = os.path.join(config_path, 'output')
		self.docker_client = docker.from_env()
		self.has_traefik = False

	def build_graph(self):
		running = self.__get_containers()
		graph_attr = {'splines': 'false', 'concentrate': 'true', 'ranksep': '0.8 equally', 'fontcolor': self.config['color_scheme']['dark_text']}
		node_attr = {'style': 'filled,rounded', 'shape': 'record'}
		edge_attr = {}
		g = graphviz.Digraph(comment = 'Machine virtuelle : {0}'.format(self.config['vm_name']), format = 'png', graph_attr = graph_attr, node_attr = node_attr, edge_attr = edge_attr)

		# Create a subgraph for the virtual machine
		with g.subgraph(name = 'cluster_0') as vm:
			vm.attr(label = 'Machine virtuelle : {0}'.format(self.config['vm_name']), style = 'filled,rounded', fillcolor = self.config['color_scheme']['vm'])

			# Group containers by networks
			network_dict = defaultdict(list)
			for c in running:
				for n in c.networks:
					network_dict[n].append(c)

			# Add all running containers as a node in their own network subgraph
			for k, v in network_dict.items():
				with vm.subgraph(name = 'cluster_{0}'.format(k)) as network:
					network.attr(label = 'Réseau : {0}'.format(k), style = 'filled,rounded', color = self.config['color_scheme']['network'], fillcolor = self.config['color_scheme']['network'])
					for c in v:
						with network.subgraph(name = 'cluster_{0}'.format(c.image)) as image:
							image.attr(label = c.image, style = 'filled,rounded', color = self.config['color_scheme']['image'], fillcolor = self.config['color_scheme']['image'])
							label = '{' + '<{0}> {0}'.format(c.name) + '}'
							if c.ports:
								label = '{' + '<{0}> {0}'.format(c.name) + '}|{'
								for p in c.ports:
									label += '<{0}> {0}|'.format(p)
								label = label[:-1] + '}'
							image.node(c.name, label, color = self.config['color_scheme']['dark_text'], fillcolor = self.config['color_scheme']['container'], fontcolor = self.config['color_scheme']['dark_text'])
						# Instead of using a link label (takes a lot of space), put a node without shape for the container's url
						if self.has_traefik and c.url is not None:
							network.node(c.url, c.url, color = self.config['color_scheme']['traefik'], fillcolor = self.config['color_scheme']['traefik'], fontcolor = self.config['color_scheme']['bright_text'])

			for c in running:
				# Add reverse-proxy links
				if self.has_traefik and c.url is not None:
					vm.edge('{0}:{1}'.format(self.traefik_container, TRAEFIK_DEFAULT_PORT), c.url, arrowhead = "none", color = self.config['color_scheme']['traefik'])
					vm.edge(c.url, '{0}:{1}'.format(c.name, c.backend_port), color = self.config['color_scheme']['traefik'])

				# Add links between containers
				for l in c.links:
					vm.edge('{0}:{1}'.format(c.name, c.name), '{0}:{1}'.format(l, l), color = self.config['color_scheme']['link'])

				# Add port mapping
				for expose, host_ports in c.ports.items():
					for host in host_ports:
						vm.node(host, host, shape = 'diamond', fillcolor = self.config['color_scheme']['port'], fontcolor = self.config['color_scheme']['bright_text'])
						vm.edge(host, '{0}:{1}'.format(c.name, expose), color = self.config['color_scheme']['port'])

		# Render PNG
		g.render(os.path.join(self.output_dir, '{0}.gv'.format(self.config['vm_name'])))

	def __get_containers(self):
		'''
		Get running docker containers on the host described by docker_client, without those excluded in configuration

		:rtype List
		:returns List of ShortContainer representing running containers
		'''

		# Names of all running containers
		running_containers = []

		# Get all running containers
		for c in self.docker_client.containers.list():
			if c.status == 'running' and c.name not in self.config['exclude']:
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

def main():
	graph = GraphBot()
	graph.build_graph()

if __name__ == '__main__':
    main()
