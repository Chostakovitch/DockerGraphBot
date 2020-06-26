#!/usr/bin/env python
# coding=utf-8
"""
Get specific informations from running docker containers.

This module is especially interested in the links between containers,
ports, volumes, networks, and support the Traefik reverse-proxy.

Theses informations are wrapped into a simplified object, ContainerInfos.
"""

import logging

from collections import defaultdict
from typing import Set, List, Dict, Optional

import docker

TRAEFIK_DEFAULT_PORT = '80/tcp'


class ContainerInfos:
    """Represent a Docker container with useful members for GraphBuilder."""

    def __init__(self, name: str):
        """
        Create an object with default values, except for name.

        Attributes should be filled after the object creation.
        :param name Name of the container.
        """
        self.name = name
        self.image = str()

        self.ports: Dict[str, Set[str]]
        self.ports = defaultdict(set)

        self.network = str()

        self.links: Set[str]
        self.links = set()

        self.bind_mounts: Set[str]
        self.bind_mounts = set()

        self.volumes: Dict[str, Set[str]]
        self.volumes = defaultdict(set)

        self.__backend_port = None
        self.__url = str()

    @property
    def backend_port(self) -> Optional[str]:
        """Return the Traefik backend port of the container."""
        return self.__backend_port

    @backend_port.setter
    def backend_port(self, value):
        """
        Set the Traefik backend port of the container.

        The value can be with /tcp suffix or not.
        """
        if value is not None and '/' not in value:
            value += '/tcp'
        self.__backend_port = value

    @property
    def url(self) -> str:
        """Return the Traefik URL of the container."""
        return self.__url

    @url.setter
    def url(self, value):
        """Set the URL of the container from the Traefik host label."""
        if value is not None:
            value = value.replace('Host:', '')
        self.__url = value


class DockerInfo:
    """
    Summarize information about docker containers in ContainerInfos objects.

    These objects are mainly used to simplify the building of a graph.
    You can get them by getting the property containers, but be careful, they
    won't be updated each time you get the property.

    You can update the containers with current state
    by calling the update_containers() method.
    """

    @property
    def containers(self) -> List[ContainerInfos]:
        """Get running containers. Create the information if necessary."""
        if not self.__containers:
            self.update_containers()
        return self.__containers

    def __init__(self, docker_client: docker.DockerClient):
        """Initialize the builder from an existing DockerClient."""
        self.__docker_client = docker_client
        self.__containers: List[ContainerInfos] = []

        # Name of Traefik container if applicable
        self.traefik_container = ''
        # Source port of Traefik container in mapping with backends
        self.traefik_source_port = ''

    def update_containers(self) -> List[ContainerInfos]:
        """
        Get running docker containers on the host.

        Excluse those excluded in configuration.
        """
        # Drop existing containers
        self.__containers = []

        # Get all running containers
        for cont in self.__docker_client.containers.list():
            # Some containers may do not have an image name for various reasons
            if cont.status == 'running' and len(cont.image.tags) > 0:
                cont_info = ContainerInfos(cont.name)
                # Use the first image as the main name
                cont_info.image = cont.image.tags[0]
                if len(cont.image.tags) > 1:
                    warn = 'Multiple image tags for container %s ' \
                           'choosing image %s.'
                    logging.warning(warn,
                                    cont.name,
                                    cont_info.image)

                networks_conf = cont.attrs['NetworkSettings']
                # Sometimes several host ports could be mapped on a
                # single container port : handle this situation
                for exposed_port, host_port in networks_conf['Ports'].items():
                    cont_info.ports[exposed_port].update(
                        [port['HostPort'] for port in host_port]
                        if host_port is not None
                        else []
                    )

                cont_info.url = cont.labels.get('traefik.frontend.rule')

                # If Traefik is routing to this container, but that
                # no backend port is defined, we assume that the
                # backend port is the default
                if cont_info.url is not None:
                    backend_port = cont.labels.get('traefik.port')
                    if backend_port is None:
                        cont_info.backend_port = TRAEFIK_DEFAULT_PORT
                        warn = 'Traefik host rule found but no backend port ' \
                               'found for container %s : assume %s port.'
                        logging.warning(warn,
                                        cont_info.name,
                                        TRAEFIK_DEFAULT_PORT)
                    else:
                        cont_info.backend_port = backend_port

                # The graph representation is per-network, so choose
                # a random network if multiple. However we still
                # represent the links between containers, so
                # iterate through all networks. The last will be
                # the one choosen.
                for network_name, params in networks_conf['Networks'].items():
                    cont_info.network = network_name
                    links = params['Links']
                    if links is not None:
                        # The part before : is the link name (i.e. the
                        # container's name, after it's just an alias)
                        cont_info.links.update(
                            [link.split(':')[0] for link in links]
                        )

                if len(networks_conf['Networks']) > 1:
                    warn = 'Container %s belongs to more ' \
                           'than one network, using network ' \
                           '%s as main network.'
                    logging.warning(warn,
                                    cont.name,
                                    cont_info.network)
                self.__containers.append(cont_info)

                # Check if a Traefik container is running
                # If so, we will represent backends routing and
                # port mapping in the graph
                if cont_info.image.split(':')[0] == 'traefik':
                    print(cont_info)
                    self.traefik_container = cont_info.name
                    self.traefik_source_port = list(cont_info.ports)[0]
                    info = 'Traefik found, using %s as source port in mapping'
                    logging.info(info, self.traefik_source_port)

        return self.__containers
