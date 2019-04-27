#!/usr/bin/env python
# coding=utf-8

import docker
import graphviz
import json
import socket
import os
from ruamel.yaml import YAML

DIR_NAME = os.path.dirname(os.path.realpath(__file__))
CONFIG_FILE = os.path.join(DIR_NAME, 'config.json')
DOCKER_COMPOSE_FILE = os.path.join(DIR_NAME, 'docker-compose.yml')
OUTPUT_DIR = os.path.join(DIR_NAME, 'output')

def get_containers(docker_client):
	''' 
	Get running docker containers on the host described by docker_client
	
	:param docker_client: docker client for target host
	:type docker_client: DockerClient
	:rtype (dict, set)
	:returns The dict describes containers runned by Docker Compose {service_name: <config>}. The set contains container names not runned by Docker Compose<
	'''

	# Services described by Docker Compose file 
	dc_services = {}

	# Names of all running containers
	running_containers = []

	# Get all services declared in Docker Compose
	with open(DOCKER_COMPOSE_FILE, 'r') as f:
		dc = YAML(typ='safe').load(f)
		dc_services = dict(dc['services'])

	# Get all running containers
	for container in docker_client.containers.list():
		if container.status == 'running':
			running_containers.append(container.name)

	# Just for testing in local
	running_containers.append('traefik')
	running_containers.append('mattermost')
	running_containers.append('mattermost-db')

	# Get all running containers declared in Docker Compose
	dc_containers = dict(filter(lambda x: x[0] in running_containers, dc_services.items()))

	# Get all running containers not declared in Docker Compose
	stdr_containers = set(running_containers) - dc_containers.keys()

	return (dc_containers, stdr_containers)

	# TODO exclude containers from config

def main():
	# Get configuration
	with open(CONFIG_FILE, 'r') as fd:
		config = json.load(fd)

	# Get containers split by Docker Compose management criteria
	client = docker.from_env()
	dc_containers, stdr_containers = get_containers(client)

	# TODO put in func
	# Add running containers as node, with different colors depending of management by Docker Compose
	g = graphviz.Digraph(comment = 'Machine physique : {0}'.format(config['machine_name']), format = 'png')
	with g.subgraph(name = 'cluster_0') as vm:
		vm.attr(label = 'Machine virtuelle : {0}'.format(socket.gethostname()))
		# Create subgraph containing all running container managed by Docker Compose
		with vm.subgraph(name = 'cluster_0_0') as dc:
			# TODO refactor styling
			dc.attr(label = 'Lancés par Docker Compose')
			dc.attr(style = 'filled')
			dc.attr(color = 'lightgrey')
			dc.node_attr.update(style = 'filled', color = 'orange')
			for c in dc_containers.keys():
				dc.node(c)

		# Create subgraph containing all running container runned with Docker command
		with vm.subgraph(name = 'cluster_0_1') as stdr:
			stdr.attr(label = 'Lancés par une commande Docker')
			stdr.attr(style = 'filled')
			stdr.attr(color = 'lightgrey')
			stdr.node_attr.update(style = 'filled', color = 'green')
			for c in stdr_containers:
				stdr.node(c)

	# Create PNG 
	g.render(os.path.join(OUTPUT_DIR, '{0}.gv'.format(socket.gethostname())))

if __name__ == '__main__':
    main()