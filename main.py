#!/usr/bin/env python
# coding=utf-8

import docker
import graphviz
import json
import socket
import os
from ruamel.yaml import YAML

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

	def build_graph(self):
		running = self.__get_containers()
		g = graphviz.Digraph(comment = 'Machine physique : {0}'.format(self.config['machine_name']), format = 'png')
		g.attr(label = 'Machine physique : {0}'.format(self.config['machine_name']))
		with g.subgraph(name = 'cluster_0') as vm:
			vm.attr(label = 'Machine virtuelle : {0}'.format(socket.gethostname()))
			vm.attr(color = 'lightgrey')
			vm.node_attr.update(style = 'filled', color = 'orange')
			for c in running:
				vm.node(c.name)

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

		return running_containers

def main():
	graph = GraphBot()
	graph.build_graph()

if __name__ == '__main__':
    main()
