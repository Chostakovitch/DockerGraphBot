#!/usr/bin/python
# coding=utf-8
"""Logic to build a graph representing the Docker architecture of host."""
from collections import defaultdict
from enum import Enum
from typing import List, Dict, Set

import logging

import docker
from graphviz import Digraph

from docker_info import DockerInfo, ContainerInfos


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
    VOLUME = 'Docker volume or host folder'
    MOUNT_POINT = 'Directory mounted in a container'


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
                 host_name: str,
                 host_label: str,
                 exclude: List[str] = None,
                 hide: List[str] = None,
                 default_network: str = None):
        """
        Initialize a graph builder.

        :param docker_client : docker client used to build the graph
        :param color_scheme : colors used for the graph
        :param host_name : name of the host
        :param host_label : label to put on the host graph
        :param exclude : name of containers to exclude of the layout
        :param hide : elements to hide (volumes, binds and/or urls)
        :param default_network : network with lower priority if multiple
        """
        self.color_scheme = color_scheme
        self.docker_client = docker_client
        self.host_label = host_label
        self.host_name = host_name
        self.exclude = exclude if exclude is not None else []
        self.default_network = default_network

        # Individual variables for hiding elements
        hide = hide if hide is not None else []
        self.__hide_urls = 'urls' in hide
        self.__hide_volumes = 'volumes' in hide
        self.__hide_binds = 'binds' in hide

        # Name of Traefik container if applicable
        self.__traefik_container = ''
        # Source port of Traefik container in mapping with backends
        self.__traefik_source_port = ''

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
        # Get all needed informations about running containers
        docker_info = DockerInfo(self.docker_client)
        running = docker_info.containers
        self.__traefik_container = docker_info.traefik_container
        self.__traefik_source_port = docker_info.traefik_source_port

        # Ignore containers excluded in configuration
        running = [x for x in running if x.name not in self.exclude]

        # Create a subgraph for the host
        # This is necessary to get a nice colored box for the host
        with self.__graph.subgraph(name=f'cluster_{self.host_label}') as host:
            host.attr(
                label=self.host_label,
                **self.__get_style(GraphElement.HOST)
            )
            self.__add_containers_by_network(host, running)
            self.__add_links_between_containers(running)
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

        :param parent Parent graph to create networks subgraph
        :param running List of running containers
        """
        # Create a virtual subgraph for volume sources
        volume_source = Digraph(graph_attr={'rank': 'same'})
        # Group containers by networks
        network_dict = defaultdict(list)
        for cont in running:
            if self.default_network in cont.networks \
                    and len(cont.networks) > 1:
                cont.networks.remove(self.default_network)
                warn = 'Container %s belongs to more than one network, ' \
                       'including default network %s : ignore it. '
                logging.warning(warn, cont.name, self.default_network)

            network = list(cont.networks)[0]
            if len(cont.networks) > 1:
                warn = 'Container %s belongs to multiple networks, choose %s.'
                logging.warning(warn, cont.name, network)
            network_dict[network].append(cont)

        # Create a subgraph for each network
        for network, containers in network_dict.items():
            network_subgraph = Digraph(f'cluster_{self.__node_name(network)}')
            network_subgraph.attr(
                label=network,
                **self.__get_style(GraphElement.NETWORK)
            )
            for cont in containers:
                # This will indeed create multiple subgraph
                # for a single image if there is multiple containers
                # but they will be merged in the final representation
                node_partial_name = self.__node_name(cont.image, network)
                image_subgraph_name = f'cluster_{node_partial_name}'
                image_subgraph = Digraph(image_subgraph_name)
                image_subgraph.attr(
                    label=cont.image,
                    **self.__get_style(GraphElement.IMAGE)
                )

                # Create a simple node for the container
                image_subgraph.node(
                    name=self.__node_name(cont.name),
                    label=self.__record_label(cont.name, list(cont.ports)),
                    **self.__get_style(GraphElement.CONTAINER)
                )

                # Add host ports : guaranteed to be unique as no port can be bound twice.
                # Adding the host port to this subgraph gives a better layout by avoiding
                # very long edges from the outside.
                for exposed_port, host_ports in cont.ports.items():
                    for port in host_ports:
                        image_subgraph.node(
                            self.__node_name(port),
                            port,
                            **self.__get_style(GraphElement.PORT)
                        )

                # Add volumes
                if not self.__hide_binds:
                    self.__add_volumes_to_container(
                        cont,
                        image_subgraph,
                        volume_source,
                        cont.bind_mounts
                    )

                if not self.__hide_volumes:
                    self.__add_volumes_to_container(
                        cont,
                        image_subgraph,
                        volume_source,
                        cont.volumes
                    )

                # The URL of the container, if managed by Traefik, is
                # represented by a node rather than by a edge label
                # to avoid ugly large edge labels
                if (self.__traefik_container and
                        cont.url is not None):
                    image_subgraph.node(
                        name=self.__node_name(cont.url),
                        label='Traefik' if self.__hide_urls else cont.url,
                        **self.__get_style(GraphElement.TRAEFIK)
                    )

                network_subgraph.subgraph(image_subgraph)

            parent.subgraph(network_subgraph)

        parent.subgraph(volume_source)

    def __add_links_between_containers(self, running: List[ContainerInfos]):
        """
        Create all the links between the running containers.

        It is preferable to call __add_containers_by_network before using
        this function, as it will properly set labels.
        If you don't call this function, the graph will render
        properly but without explicit labels.

        :param graph Graph where container belongs
        :param running Running containers
        """
        for cont in running:
            if self.__traefik_container and cont.url is not None:
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

        :param running Running containers
        """
        for cont in running:
            for exposed_port, host_ports in cont.ports.items():
                for port in host_ports:
                    self.__graph.edge(
                        tail_name=self.__node_name(port),
                        head_name=self.__node_name(cont.name, exposed_port),
                        **self.__get_style(GraphElement.PORT)
                    )

    def __add_volumes_to_container(
            self,
            cont: ContainerInfos,
            cont_parent: Digraph,
            source_parent: Digraph,
            volumes: Dict[str, Set[str]]):
        """
        Add volumes to a specific subgraph.

        Sources are always represented in the main graph.
        Destination mount points are represented in the parent graph.

        The subgraph should be the container subgraph, but can be any
        Digraph.

        :param cont Container
        :param cont_parent Subgraph of container
        :param source_parent Subgraph for Docker volumes and host folders
        :param volumes Source folder or Docker volumes and mount points
        """
        for source, dests in volumes.items():
            # Cut name if too long
            label = source[:20] + '...' if len(source) > 20 else source
            source_parent.node(
                # Avoid duplicates with container name (dirty)
                name=self.__node_name(source + source),
                label=label,
                **self.__get_style(GraphElement.VOLUME)
            )
            for dest in dests:
                cont_parent.node(
                    # Prevent mount point duplicates, add container name
                    name=self.__node_name(dest + cont.name),
                    label=dest,
                    **self.__get_style(GraphElement.MOUNT_POINT)
                )
                # Edge from container to mount point
                cont_parent.edge(
                    tail_name=self.__node_name(cont.name),
                    head_name=self.__node_name(dest + cont.name),
                    color=self.color_scheme['bind_mount']
                )
                # Edge from source to mount point
                self.__graph.edge(
                    tail_name=self.__node_name(dest + cont.name),
                    head_name=self.__node_name(source + source),
                    color=self.color_scheme['bind_mount'],
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
        elif graph_element == GraphElement.MOUNT_POINT:
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
        an optional "subname" in case of record-shaped nodes or to further
        desambiguish (e.g. same image name in two different networks)

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
