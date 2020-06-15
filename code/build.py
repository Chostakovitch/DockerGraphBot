#!/usr/bin/python
# coding=utf-8
"""Logic to build a graph representing the Docker architecture of host."""
import logging
from collections import defaultdict
from enum import Enum
from typing import List, Dict, Set, Optional

import docker
from graphviz import Digraph


TRAEFIK_PORT = '80/tcp'


class GraphElement(Enum):
    """Describe all possibles elements in an architecture graph."""

    def __repr__(self) -> str:
        """Format the element with its name and description."""
        return '<%s.%s>' % (self.__class__.__name__, self.name)

    TRAEFIK = 'Either the URL node or the edges between containers \
        and URL node'
    PORT = 'Either a host port or the link between host port \
        and container exposed port(s)'
    IMAGE = 'Cluster around the containers'
    LINK = 'Edge between two non-Traefik containers'
    CONTAINER = 'Concrete instance of an image'
    NETWORK = 'Cluster around containers of the same Docker network'
    HOST = 'Host running Docker'
    VOLUME = 'Docker volume'
    BIND_MOUNT = 'Directory mounted in a container'


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


class GraphBuilder:
    """
    Construct a graph showing containers, images and ports on a Docker install.

    We also use Traefik labels to show links
    between the reverse proxy and the containers.
    """

    @property
    def graph(self) -> Digraph:
        """Build the graph and return it."""
        self.__build_graph()
        return self.__graph

    def __init__(self,
                 docker_client: docker.DockerClient,
                 color_scheme: Dict[str, str],
                 host_label: str,
                 host_name: str,
                 exclude: List[str] = None):
        """
        Initialize a graph builder.

        :param docker_client : docker client used to build the graph
        :param color_scheme : colors used for the graph
        :param host_name : name of the host
        :param host_label : label to put on the host graph
        :param exclude : name of containers to exclude of the layout
        """
        self.color_scheme = color_scheme
        self.docker_client = docker_client
        self.host_label = host_label
        self.host_name = host_name
        self.exclude = exclude if exclude is not None else []
        self.traefik = None

        # Initialize parent graph
        self.__graph = Digraph(
            name=self.host_label,
            comment=self.host_label
        )

    def __build_graph(self):
        """
        Build a Digraph object representing a single host.

        After running this function, the Digraph object is accessible
        via the __graph property.
        """
        running = self.__get_containers()

        # Create a subgraph for the host
        # This is necessary to get a nice colored box for the host
        with self.__graph.subgraph(name=f'cluster_{self.host_label}') as host:
            host.attr(
                label=self.host_label,
                **self.__get_style(GraphElement.HOST)
            )
            if self.traefik:
                info = 'Will use port %s as source for mapping between ' \
                       'Traefik and containers for host %s.'
                logging.info(info, self.host_name, TRAEFIK_PORT)
            self.__add_containers_by_network(host, running)
            self.__add_edges_between_containers(running)
            self.__add_host_port_mapping(running)

    def __add_containers_by_network(self,
                                    parent: Digraph,
                                    running: List[ContainerInfos]):
        """
        Create a subgraph of parent graph for each network.

        The containers are grouped by networks.

        WARNING : if a container is in multiple networks,
        it will only be part of this first network on the
        representation. This is the consequence of grouping
        by network.

        :param parent Panret graph where networks subgraph
        :param running List of running containers
        """
        # Group containers by networks
        network_dict = defaultdict(list)
        for cont in running:
            network_dict[cont.network].append(cont)

        # Create a subgraph for each network
        for network, containers in network_dict.items():
            network_subgraph = Digraph(f'cluster_{self.__node_name(network)}')
            network_subgraph.attr(
                label=network,
                **self.__get_style(GraphElement.NETWORK)
            )
            for cont in containers:
                # This will indeed create multiple subgraph
                # for a single image, but they will be merged
                # in the final representation
                image_subgraph_name = f'cluster_{self.__node_name(cont.image)}'
                image_subgraph = Digraph(image_subgraph_name)
                image_subgraph.attr(
                    label=cont.image,
                    **self.__get_style(GraphElement.IMAGE)
                )
                image_subgraph.node(
                    name=self.__node_name(cont.name),
                    label=self.__record_label(cont.name, list(cont.ports)),
                    **self.__get_style(GraphElement.CONTAINER)
                )
                # The URL of the container, if managed by Traefik, is
                # represented by a node rather than by a edge label
                # to avoid ugly large edge labels
                if self.traefik and cont.url is not None:
                    network_subgraph.node(
                        name=self.__node_name(cont.url),
                        label=cont.url,
                        **self.__get_style(GraphElement.TRAEFIK)
                    )

                network_subgraph.subgraph(image_subgraph)

            parent.subgraph(network_subgraph)

    def __add_edges_between_containers(self, running: List[ContainerInfos]):
        """
        Create all the edges between the running containers.

        This includes :
        - Docker links
        - Traefik proxying (port mapping and backend routing)

        It is preferable to call __add_containers_by_network before using
        this function, as it will properly set labels.
        If you don't call this function, the graph will render
        properly but without explicit labels.

        :param graph Graph where container belongs
        :param running Running containers
        """
        for cont in running:
            if self.traefik and cont.url is not None:
                # Edge from traefik default port to URL node
                self.__graph.edge(
                    tail_name=self.__node_name(self.traefik, TRAEFIK_PORT),
                    head_name=self.__node_name(cont.url),
                    **self.__get_style(GraphElement.TRAEFIK)
                )
                # Edge from URL node to target container exposed port
                self.__graph.edge(
                    tail_name=self.__node_name(cont.url),
                    head_name=self.__node_name(cont.name, cont.backend_port),
                    **self.__get_style(GraphElement.TRAEFIK)
                )

            # Add one edge for each link between containers
            for link in cont.links:
                self.__graph.edge(
                    tail_name=self.__node_name(cont.name, cont.name),
                    head_name=self.__node_name(link, link),
                    **self.__get_style(GraphElement.LINK)
                )

    def __add_host_port_mapping(self, running: List[ContainerInfos]):
        """
        Add nodes and edges representing the host ports to the main graph.

        Host ports are linked to the containers' exposed ports.

        It is preferable to call __add_containers_by_network before using
        this function, as it will properly set labels.
        If you don't call this function, the graph will render
        properly but without explicit labels.
        """
        for cont in running:
            for exposed_port, host_ports in cont.ports.items():
                for port in host_ports:
                    self.__graph.node(
                        self.__node_name(port),
                        port,
                        **self.__get_style(GraphElement.PORT)
                    )
                    self.__graph.edge(
                        self.__node_name(port),
                        self.__node_name(cont.name, exposed_port),
                        **self.__get_style(GraphElement.PORT)
                    )

    def __get_style(self, graph_element: GraphElement) -> Dict[str, str]:
        """
        Return a dictionary containing style for a given graph element.

        This is a helper function, mainly used because
        setting the color each time is annoying.

        :param graph_element : Type of element to style.
        """
        if graph_element == GraphElement.TRAEFIK:
            style = {
                'arrowhead': "none",
                'color': self.color_scheme['traefik'],
                'fillcolor': self.color_scheme['traefik'],
                'fontcolor': self.color_scheme['bright_text']
            }
        elif graph_element == GraphElement.PORT:
            style = {
                'shape': 'diamond',
                'fillcolor': self.color_scheme['port'],
                'fontcolor': self.color_scheme['bright_text']
            }
        elif graph_element == GraphElement.IMAGE:
            style = {
                'style': 'filled,rounded',
                'color': self.color_scheme['image'],
                'fillcolor': self.color_scheme['image']
            }
        elif graph_element == GraphElement.LINK:
            style = {
                'color': self.color_scheme['link']
            }
        elif graph_element == GraphElement.CONTAINER:
            style = {
                'color': self.color_scheme['dark_text'],
                'fillcolor': self.color_scheme['container'],
                'fontcolor': self.color_scheme['dark_text']
            }
        elif graph_element == GraphElement.NETWORK:
            style = {
                'style': 'filled,rounded',
                'color': self.color_scheme['network'],
                'fillcolor': self.color_scheme['network']
            }
        elif graph_element == GraphElement.HOST:
            style = {
                'style': 'filled,rounded',
                'fillcolor': self.color_scheme['host']
            }
        elif graph_element == GraphElement.VOLUME:
            style = {
                'style': 'filled,rounded',
                'color': self.color_scheme['volume'],
                'fillcolor': self.color_scheme['volume']
            }
        elif graph_element == GraphElement.BIND_MOUNT:
            style = {
                'style': 'filled,rounded',
                'color': self.color_scheme['bind_mount'],
                'fillcolor': self.color_scheme['bind_mount']
            }
        else:
            raise Exception('Unkown graph element')
        return style

    def __node_name(self, name: str, subname: str = None) -> str:
        """
        Return an unique name for a node or subnode.

        As each node must have a unique name, and because the graph generated
        by GraphBuilder could be later a subgraph, this function compute a
        node name given a common non-unique name, the host name, and
        an optional "subname" in case of record-shaped nodes.

        This is reasonable because a container name must be unique on a host.

        :param name : name of the node
        :param subname : name of the subnode (<X> in the record node label)
        """
        name = f'{name}_{self.host_name}'
        if subname is not None:
            name += f':{subname}'
        return name

    @staticmethod
    def __record_label(name: str, ports: List[str]) -> str:
        """
        Return a label for a record node (name of container and ports).

        A record node is a node with multiple components.
        We use the record shape to show a container along with exposed ports.
        The container's name is at the left and the ports are
        at the right of the node, ordered top to bottom.

        In our case, the format is the following :
        {<label> text_container} {<label> text_port | <label> text_port ...}
        Then, we can address a specific subnode with the syntax
        global_label:label, global_label being the label of
        the record node and label being the "sublabel" (the one between <>).

        :param name : name of the container
        :param port : ports exposed by the container
        """
        # As the global label will already be unique,
        # no need to use __node_name here
        # Double-bracket = single bracket in f-string
        label = f'{{ <{name}> {name} }}'
        if ports:
            label += ' | { '
            for port in ports:
                label += f'<{port}> {port} |'
            # Remove ultimate | character
            label = label[:-1]
            label += ' }'
        return label

    # TODO put in a separate class and split
    def __get_containers(self) -> List[ContainerInfos]:
        """
        Get running docker containers on the host.

        Excluse those excluded in configuration.
        """
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
                if len(cont.image.tags) > 1:
                    warn = 'Multiple image tags for container %s ' \
                           'of host %s, choosing image %s.'
                    logging.warning(warn,
                                    cont.name,
                                    self.host_label,
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
                        cont_info.backend_port = backend_port
                    else:
                        cont_info.backend_port = TRAEFIK_PORT
                        warn = 'Traefik host rule found but no backend port ' \
                               'found for container %s of host %s : ' \
                               'suppose %s port.'
                        logging.warning(warn,
                                        cont_info.name,
                                        self.host_label,
                                        TRAEFIK_PORT)

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

                if len(networks_conf['Networks'].items()) > 1:
                    warn = 'Container %s of host %s belongs to more ' \
                           'than one network, it won''t be properly ' \
                           'rendered. We will only consider network %s.'
                    logging.warning(warn,
                                    cont.name,
                                    self.host_name,
                                    cont_info.network)
                running_containers.append(cont_info)

            # Check if a Traefik container is running
            # If so, we will represent backends routing and
            # port mapping in the graph
            for image in cont.image.tags:
                if image.split(':')[0] == 'traefik':
                    self.traefik = cont.name

        return running_containers
