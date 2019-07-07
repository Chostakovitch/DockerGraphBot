#!/usr/bin/env python
# coding=utf-8

import docker
import graphviz
import json
import socket
import os
from ruamel.yaml import YAML
from collections import defaultdict

class GraphBot:
	'''
	This class asks the Docker daemon informations about running Containers
	and constructs a graph showing dependencies between containers.

	We also use Traefik labels to show links between the reverse proxy and the containers.
	'''

	DIR_NAME = os.path.dirname(os.path.realpath(__file__))

	def __init__(self, config_path = DIR_NAME, output_dir = DIR_NAME):
		# Get configuration
		with open(os.path.join(config_path, 'config.json'), 'r') as fd:
			self.config = json.load(fd)
		self.OUTPUT_DIR = os.path.join(config_path, 'output')
		self.docker_client = docker.from_env()
		self.has_traefik = False

	def build_graph(self):
		running = self.__get_containers()
		g = graphviz.Digraph(comment = 'Machine physique : {0}'.format(self.config['machine_name']), format = 'png')
		g.attr(label = 'Machine physique : {0}'.format(self.config['machine_name']))

		# Create a subgraph for the virtual machine
		with g.subgraph(name = 'cluster_0') as vm:
			vm.attr(label = 'Machine virtuelle : {0}'.format(socket.gethostname()))
			vm.attr(color = 'lightgrey')
			vm.node_attr.update(style = 'filled', color = 'orange')

			# Discover networks and containers belonging to them
			network_dict = defaultdict(list)
			for c in running:
				for n in c.attrs['NetworkSettings']['Networks']:
					network_dict[n].append(c)

			# Add all running containers as a node in their own network subgraph
			for k, v in network_dict.items():
				with vm.subgraph(name = 'cluster_{0}'.format(k)) as cluster:
					cluster.attr(label = 'Réseau : {0}'.format(k))
					for c in v:
						with cluster.subgraph(name = 'cluster_{0}'.format(c.name)) as container:
							cluster.attr(label = 'Image : {0}'.format(c.image.tags[0]))
							container.node(c.name)

			for c in running:
				# Add reverse-proxy links
				if self.has_traefik:
					frontend = c.labels.get('traefik.frontend.rule')
					if frontend is not None:
						vm.edge(self.traefik_container, c.name, label = frontend.split('Host:')[1], style = "dashed")

				# Add links
				links = set()
				for _, v in c.attrs['NetworkSettings']['Networks'].items():
					if v['Links'] is not None:
						links.update([l.split(':')[0] for l in v['Links']]);
				for l in links:
					vm.edge(c.name, l)

		# Create PNG
		g.render(os.path.join(self.OUTPUT_DIR, '{0}.gv'.format(socket.gethostname())))

	def __get_containers(self):
		'''
		Get running docker containers on the host described by docker_client, without those excluded in configuration

		:param docker_client: docker client for target host
		:type docker_client: DockerClient
		:rtype List
		:returns List of Containers (running containers)
		'''

		# Names of all running containers
		running_containers = []

		# Get all running containers
		for container in self.docker_client.containers.list():
			if container.status == 'running' and container.name not in self.config['exclude']:
				running_containers.append(container)
			for i in container.image.tags:
				if 'traefik' in i.split(':')[0]:
					self.has_traefik = True
					self.traefik_container = container.name

		return running_containers

def main():
	graph = GraphBot()
	graph.build_graph()

if __name__ == '__main__':
    main()
