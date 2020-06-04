#!/usr/bin/python
# coding=utf-8

import docker

from graphviz import Digraph
from collections import defaultdict
from enum import Enum
from typing import List, Dict

TRAEFIK_PORT = '80/tcp'


class GraphElement(Enum):
    '''
    Describe all possibles elements in an architecture graph
    '''
    def __repr__(self):
        return '<%s.%s>' % (self.__class__.__name__, self.name)

    TRAEFIK = 'Either the URL node or the edges between containers \
        and URL node'
    PORT = 'Either a host port or the link between host port \
        and container exposed port(s)'
    IMAGE = 'Cluster around the containers'
    LINK = 'Edge between two non-Traefik containers'
    CONTAINER = 'Concrete instance of an image'
    NETWORK = 'Cluster around containers of the same Docker network'
    VM = 'Virtual machine (host)'
    VOLUME = 'Docker volume'
    BIND_MOUNT = 'Directory mounted in a container'


class ContainerInfos:
    '''
    This class represents a Docker container with only useful members
    for GraphBuilder.
    '''
    def __init__(self, name: str):
        self.name = name
        self.image = str()
        self.ports = defaultdict(set)
        self.networks = set()
        self.links = set()
        self.bind_mounts = set()
        self.volumes = defaultdict(set)

        self.__backend_port = None
        self.__url = str()

    @property
    def backend_port(self):
        return self.__backend_port

    @backend_port.setter
    def backend_port(self, value):
        if value is not None and '/' not in value:
            value = value + '/tcp'
        self.__backend_port = value

    @property
    def url(self):
        return self.__url

    @url.setter
    def url(self, value):
        if value is not None:
            value = value.replace('Host:', '')
        self.__url = value


class GraphBuilder:
    '''
    This class asks a Docker daemon informations about running Containers
    and constructs a graph showing dependencies
    between containers, images and ports.

    We also use Traefik labels to show links
    between the reverse proxy and the containers.
    '''
    @property
    def graph(self):
        if self.__graph is None:
            self.__build_graph()
        return self.__graph

    '''
    Constructor.

    :param docker_client : docker client used to build the graph
    :param color_scheme : colors used for the graph
    :param vm_name : name of the virtual machine
    :param vm_label : label to put on the virtual machine graph
    :param exclude : name of containers to exclude of the layout
    '''
    def __init__(self,
                 docker_client: docker.DockerClient,
                 color_scheme: Dict[str, str],
                 vm_label: str,
                 vm_name: str,
                 exclude: List[str] = []):
        self.color_scheme = color_scheme
        self.docker_client = docker_client
        self.vm_label = vm_label
        self.vm_name = vm_name
        self.exclude = exclude
        self.has_traefik = False
        self.traefik = None
        self.__graph = None

    '''
    Builds a Digraph object representing a single host.
    After running this function, the Digraph object is accessible
    via the __graph property
    '''
    def __build_graph(self):
        running = self.__get_containers()
        self.__graph = Digraph(
            name='{0}'.format(self.vm_label),
            comment='Virtual machine : {}'.format(self.vm_label)
        )

        # Create a subgraph for the virtual machine
        with self.__graph.subgraph(
            name='cluster_{}'.format(self.vm_label)
        ) as vm:
            vm.attr(
                label='Virtual machine : {}'.format(self.vm_label),
                **self.__get_style(GraphElement.VM)
            )

            self.__add_containers_by_network(vm, running)
            self.__add_edges_between_containers(running)
            self.__add_host_port_mapping(running)

    '''
    Create a subgraph of parent graph for each network.
    The containers are grouped by networks.

    WARNING : if a container is in multiple networks,
    it will only be part of this first network on the
    representation. This is the consequence of grouping
    by network.
    '''
    def __add_containers_by_network(self,
                                    parent: Digraph,
                                    running: List[ContainerInfos]):
        # Group containers by networks
        network_dict = defaultdict(list)
        for cont in running:
            for net in cont.networks:
                network_dict[net].append(cont)

        # Create a subgraph for each network
        for network, containers in network_dict.items():
            network_subgraph = Digraph(
                name='cluster_{0}'.format(self.__node_name(network))
            )
            network_subgraph.attr(
                label='Network : {0}'.format(network),
                **self.__get_style(GraphElement.NETWORK)
            )
            for cont in containers:
                # This will indeed create multiple subgraph
                # for a single image, but they will be merged
                # in the final representation
                image_subgraph = Digraph(
                    name='cluster_{0}'.format(self.__node_name(cont.image))
                )
                image_subgraph.attr(
                    label=cont.image,
                    **self.__get_style(GraphElement.IMAGE)
                )
                image_subgraph.node(
                    name=self.__node_name(cont.name),
                    label=self.__record_label(cont.name, cont.ports),
                    **self.__get_style(GraphElement.CONTAINER)
                )
                # The URL of the container, if managed by Traefik, is
                # represented by a node rather than by a edge label
                # to avoid ugly large edge labels
                if self.has_traefik and cont.url is not None:
                    network_subgraph.node(
                        name=self.__node_name(cont.url),
                        label=cont.url,
                        **self.__get_style(GraphElement.TRAEFIK)
                    )

                network_subgraph.subgraph(image_subgraph)

            parent.subgraph(network_subgraph)

    '''
    Create all the edges between the running containers :
    - Docker links
    - Traefik proxying (port mapping and backend routing)

    It is preferable to call __add_containers_by_network before using
    this function, as it will properly set labels. If you don't call
    this function, the graph will render properly but without explicit labels.
    '''
    def __add_edges_between_containers(self, running: List[ContainerInfos]):
        for cont in running:
            if self.has_traefik and cont.url is not None:
                # Edge from traefik default port to URL node
                vm.edge(
                    tail_name=self.__node_name(self.traefik, TRAEFIK_PORT),
                    head_name=self.__node_name(cont.url),
                    **self.__get_style(GraphElement.TRAEFIK)
                )
                # Edge from URL node to target container exposed port
                vm.edge(
                    tail_name=self.__node_name(cont.url),
                    head_name=self.__node_name(cont.name, cont.backend_port),
                    **self.__get_style(GraphElement.TRAEFIK)
                )

            # Add one edge for each link between containers
            for link in cont.links:
                vm.edge(
                    tail_name=self.__node_name(c.name, c.name),
                    head_name=self.__node_name(link, link),
                    **self.__get_style(GraphElement.LINK)
                )

    '''
    Add nodes to the main graph representing the host ports,
    and link them to the containers' exposed ports.

    It is preferable to call __add_containers_by_network before using
    this function, as it will properly set labels. If you don't call
    this function, the graph will render properly but without explicit labels.
    '''
    def __add_host_port_mapping(self, running: List[ContainerInfos]):
        for cont in running:
            for exposed_port, host_ports in cont.ports.items():
                for port in host_ports:
                    vm.node(
                        self.__node_name(port),
                        port,
                        **self.__get_style(GraphElement.PORT)
                    )
                    vm.edge(
                        self.__node_name(port),
                        self.__node_name(c.name, exposed_port),
                        **self.__get_style(GraphElement.PORT)
                    )
    '''
    Returns a dictionary than can be unpacked to create
    a graph element (node, edge or cluster).
    This is a helper function, mainly used because
    setting the color each time is annoying.

    :param node_type : the part of the graph do we need to style
    :returns Dictionary containing the styling arguments
    :rtype Dict[str, str]
    '''
    def __get_style(self, graph_element: GraphElement):
        if graph_element == GraphElement.TRAEFIK:
            return {
                'arrowhead': "none",
                'color': self.color_scheme['traefik'],
                'fillcolor': self.color_scheme['traefik'],
                'fontcolor': self.color_scheme['bright_text']
            }
        elif graph_element == GraphElement.PORT:
            return {
                'shape': 'diamond',
                'fillcolor': self.color_scheme['port'],
                'fontcolor': self.color_scheme['bright_text']
            }
        elif graph_element == GraphElement.IMAGE:
            return {
                'style': 'filled,rounded',
                'color': self.color_scheme['image'],
                'fillcolor': self.color_scheme['image']
            }
        elif graph_element == GraphElement.LINK:
            return {
                'color': self.color_scheme['link']
            }
        elif graph_element == GraphElement.CONTAINER:
            return {
                'color': self.color_scheme['dark_text'],
                'fillcolor': self.color_scheme['container'],
                'fontcolor': self.color_scheme['dark_text']
            }
        elif graph_element == GraphElement.NETWORK:
            return {
                'style': 'filled,rounded',
                'color': self.color_scheme['network'],
                'fillcolor': self.color_scheme['network']
            }
        elif graph_element == GraphElement.VM:
            return {
                'style': 'filled,rounded',
                'fillcolor': self.color_scheme['vm']
            }
        elif graph_element == GraphElement.VOLUME:
            return {
                'style': 'filled,rounded',
                'color': self.color_scheme['volume'],
                'fillcolor': self.color_scheme['volume']
            }
        elif graph_element == GraphElement.BIND_MOUNT:
            return {
                'style': 'filled,rounded',
                'color': self.color_scheme['bind_mount'],
                'fillcolor': self.color_scheme['bind_mount']
            }
        else:
            raise Exception('Unkown graph element')

    '''
    As each node must have a unique name, and because the graph generated
    by GraphBuilder could be later a subgraph, this function compute a
    node name given a common non-unique name, the vm name, and
    an optional "subname" in case of record-shaped nodes.

    :param name : name of the node
    :param subname : name of the subnode (between <> in the record node label)
    :returns unique name of a node
    :rtype str
    '''
    def __node_name(self, name: str, subname: str = None):
        name = '{0}_{1}'.format(name, self.vm_name)
        if subname is not None:
            name += ':{0}'.format(subname)
        return name

    '''
    A record node is a node with multiple component. We use the record shape
    to show a container along with exposed ports. The container's name
    is at the left and the ports are at the right of the node,
    ordered top to bottom.

    In our case, the format is the following :
    { <label> text_container } { <label> text_port | <label> text_port ... }
    Then, we can address a specific subnode with the syntax
    global_label:label, global_label being the label of
    the record node and label being the "sublabel" (the one between <>).

    :param name : name of the container
    :param port : ports exposed by the container
    :returns label usable for the record node
    :rtype str
    '''
    def __record_label(self, name: str, ports: List[str]):
        # As the global label will already be unique,
        # no need to use __node_name here
        # Double-bracket = single bracket in format
        label = '{{ <{0}> {0} }}'.format(name, name)
        if ports:
            label += ' | { '
            for p in ports:
                label += '<{0}> {0} |'.format(p)
            label = label[:-1] + ' }'
        return label

    '''
    Get running docker containers on the host described
    by docker_client, without those excluded in configuration

    :rtype List
    :returns List of ContainerInfos representing running containers
    '''
    def __get_containers(self):

        # Names of all running containers
        running_containers = []

        # Get all running containers
        for cont in self.docker_client.containers.list():
            # Some containers may do not have an image name for various reasons
            if cont.status == 'running' \
               and cont.name not in self.exclude \
               and len(cont.image.tags) > 0:
                cont_info = ContainerInfos(cont.name)
                # Use the first image as the main name
                cont_info.image = cont.image.tags[0]

                networks_conf = cont.attrs['NetworkSettings']
                # Sometimes several host ports could be mapped on a
                # single container port : handle this situation
                for exposed_port, host_port in networks_conf['Ports'].items():
                    cont_info.ports[exposed_port].update(
                        [p['HostPort'] for p in host_port]
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
                        cont_info.backend_port = backend_port
                    else:
                        cont_info.backend_port = TRAEFIK_PORT

                for network_name, params in networks_conf['Networks'].items():
                    cont_info.networks.add(network_name)
                    links = params['Links']
                    if links is not None:
                        # The part before : is the link name (i.e. the
                        # container's name, after it's just an alias)
                        cont_info.links.update(
                            [link.split(':')[0] for link in links]
                        )

                running_containers.append(cont_info)

            # Check if a Traefik container is running
            # If so, we will represent backends routing and
            # port mapping in the graph
            for image in cont.image.tags:
                if 'traefik' == image.split(':')[0]:
                    self.has_traefik = True
                    self.traefik = cont.name

        return running_containers
