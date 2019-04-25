#!/usr/bin/env python

import docker
import graphviz
import json
from ruamel.yaml import YAML

yaml = YAML(typ='safe')
client = docker.from_env()

#dc_services = 
#running_containers = 

with open('docker-compose.yml', 'r') as f:
	dc = yaml.load(f)

for service, desc in dict(dc["services"]).items():
	print(desc)

for container in client.containers.list():
	print(container.name, container.status)