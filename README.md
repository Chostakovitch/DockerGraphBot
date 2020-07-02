# Docker Graph Bot

<!-- TOC depthFrom:2 depthTo:6 withLinks:1 updateOnSave:1 orderedList:0 -->

- [Presentation](#presentation)
- [Configuration](#configuration)
	- [General parameters](#general-parameters)
	- [Hosts](#hosts)
	- [Actions](#actions)
	- [Color scheme](#color-scheme)
- [Usage](#usage)
- [Security considerations](#security-considerations)
- [Limitations](#limitations)
- [Contributing](#contributing)

<!-- /TOC -->

## Presentation

Docker Graph bot (DGB) is a Python tool whose goal is to automate the building of diagrams representing a dynamic Docker-based infrastructure. Indeed, if you draw manual diagrams, they will constantly be obsolete.
This is especially useful :
* If you want to be transparent to your users
* If you want to see the "big picture" of your infrastructure
* To check the coherence of container linking, naming schemes, networks...

DGB will produce diagrams (graphs) containing the following informations :
* Running containers, clustered by images
* Networks
* Port mappings between host and containers
* Links between containers
* Traefik labels and backend port mappings, **when used**

Roughly, DGB follows these steps :

* Query the Docker daemon to retrieve interesting information about the launched containers
* If Traefik is used as a reverse-proxy, retrieve labels and port mapping to create virtual link between containers
* A DOT file summarizing all gathered information is built
* One or several images are created depending on the configuration
* Post-generation actions are triggered, such as WebDAV/SFTP upload.

No private information should be leaked on the final diagrams. See below for an example diagram generated from one of the [Picasoft](https://picasoft.net) virtual machines.

![Example of generated diagram](https://gitlab.utc.fr/picasoft/projets/graph-bot/raw/master/img/example_pica02.png)

## Configuration

All the configuration happens in `config/config.json`. You can use [`config.example.json`](./config_example.json) as a base.

### General parameters

* `organization` : mainly used for labels and file naming, this is the name of your organization/structure/whatever it is
* `merge` : a boolean which tells DGB if it should merge the generated diagrams in case you specify multiple hosts

Example :

```json
{
  "organization": "Picasoft",
  "merge": true
}
```
### Hosts

You can specify multiple hosts, for example if your infrastructure is made of several hosts.

In either case :
* `name` field is used for labels and file naming
* `url` is the URL of the host, either local or public
* `exclude` is a list of container **names** that you may want to exclude from the diagram

If you want to build a diagram for a remote host, the Docker socket must be reachable through the network. TLS is mandatory here because this is basic security. See [the official documentation](https://docs.docker.com/engine/security/https/) to learn how to expose your Docker socket.

Once you have your CA, server and client key, just fill the `ca_cert`, `cert` and `key` field with paths **relative** to your `CERTS_DIRECTORY` folder (see [Usage](#usage)). Don't forget to specify the Docker socket port.

The main advantage to use multiple hosts is that it reduces the burden of maintaining an instance of DGB on each host. With only one instance, you can build, generate and upload all your diagrams at once.

Example with a remote host and a local host :
```json
"hosts": [
  {
    "name": "<hostname>",
    "url": "<host>.tld",
    "port": 2376,
    "exclude": [
      "[container_name]"
    ],
    "tls_config": {
      "ca_cert": "/CONFIG/ca.pem",
      "cert": "/CONFIG/cert.pem",
      "key": "/CONFIG/key.pem"
    }
  },
  {
    "name": "<hostname>",
    "url": "localhost"
  }
]
```
### Actions

Actions are like post generation hooks. Each configured action is applied to DOT or PNG generated files.

For now, there is only two available actions : upload all generated PNG diagrams to
* A WebDAV compatible server (*e.g.* NextCloud).
* A SFTP server

Examples

```json
"actions": [
  {
    "type": "webdav",
    "hostname": "https://example.com/nextcloud/remote.php/dav/files/<login>",
    "login": "login",
    "password": "password",
    "remote_path": "graph_output"
  },
  {
    "type": "sftp",
    "hostname": "https://sftp.tld",
    "port": 2222,
    "login": "login",
    "password": "password",
    "remote_path": "graph_output"
  }
]
```

Note that `remote_path` is just a relative path to the "home" directory of the WebDAV user or the SFTP user.

### Hide elements

For clarity or privacy, you may want to hide some elements on the graph.
You can currently hide :
* URL of containers, when using Traefik (`urls`)
* Docker volumes (`volumes`)
* Bind mounts (`binds`) - this is especially if you want to hide host folder paths.

For example, to hide Docker volumes and bind mounts, use :
```json
"hide": ["volumes", "binds"]
```

### Color scheme

This is pretty self-explanatory. Just use hexadecimal values to control the look-and-feel of your diagrams.

## Usage

### Docker Image

DGB is distributed as a Docker image and is ready for use. You just need to provide a valid configuration file and TLS needed files if necessary.

You can pull the latest stable version from [the Docker Hub](https://hub.docker.com/r/chosto/graphbot) :

``` bash
$ docker pull chosto/graphbot
```

Or build the image from the repository :

```bash
$ git clone https://gitlab.utc.fr/picasoft/projets/graph-bot.git
$ cd graph-bot
$ docker build -t chosto/graph-bot .
```

Then, create required directories :

```bash
$ # These are the bind-mounted directories. If you change their names, change bind-mounts !.
$ mkdir config output
$ mv config_example.json config/config.json
```

Those are the environment variables that you can override at your convenience :
* `CONFIG_FILE` : mount point of the configuration file
* *Optional* : `CERTS_DIRECTORY` : mount point of the certificates directory (if you use TLS to connect to a remote Docker instance)
* *Optional* : `OUTPUT_DIRECTORY` : mount point of the output volume (if you want to keep track of the diagrams)
* *Optional* : `CRON_CONFIG` : cron setting (*e.g.* `0 0 * * *` for every day at midnight). If you don't provide it, DGB will execute once and stop.
* *Optional* : `LOG_LEVEL` : `debug`, `info`, `warning` or `error`. Default to `info`.

If you want to use Docker Compose (recommended), use the one provided in this repository and tune the environment variables in the file to match the host mount points :

```bash
$ docker-compose up -d
$ docker logs -f graph-bot
# And voilà !
```

If you don't want to use Docker Compose, you can still use the following Docker commands, by adjusting the host paths and removing non-relevant environment variables.

```bash
$ docker network create graphbot
$ docker run -d --name graph-bot \
	--volume "$(pwd)/config.json:/config.json" --volume "$(pwd)/output:/output" --volume "/var/run/docker.sock:/var/run/docker.sock"
	--volume "$(pwd)/certs:/certs"
	-e CONFIG_FILE='/config.json' -e OUTPUT_DIRECTORY='/output' -e CERTS_DIRECTORY='/certs' -e CRON_CONFIG='0 0 * * *'
	--restart unless-stopped --net graphbot graph-bot
```

### Standalone

You can also use the Python code without the Docker image, which is provided for convenience and cron jobs.
Make sure to run **Python 3.8** or higher.
Just hit :

```bash
$ python3 -m pip install -r requirements.txt
$ ./code/dgb.py --help
usage: dgb.py [-h] [-o OUTPUT_DIRECTORY] [-c CONFIG_FILE] [-t CERTS_DIRECTORY] [-l {debug,info,warning,error}]

optional arguments:
  -h, --help            show this help message and exit
  -o OUTPUT_DIRECTORY, --output-directory OUTPUT_DIRECTORY
                        path for output directory of DOT and PNG files
  -c CONFIG_FILE, --config-file CONFIG_FILE
                        path of the configuration file
  -t CERTS_DIRECTORY, --certs-directory CERTS_DIRECTORY
                        path of the directory container certificates
  -l {debug,info,warning,error}, --log-level {debug,info,warning,error}
                        verbosity of logging
```
## Security considerations

DGB is launched as `root`, especially because private keys will probably we own by `root` on the host with permissions `600` (and they **should be**).

Also, the Docker socket is mounted inside the container so that DGB can query the running containers. Mounting the Docker socket is equivalent to :
* Allowing any modification of all containers, images, volumes...
* Giving a `root` access **to the host** itself ! (with little tricks)

As a consequence, it is mandatory to keep DGB in an isolated Docker network, without exposed port (I cannot see a reason to do so).
Also, when you use remote host, you also give a `root` access to these hosts to DGB. You must ensure that each person than can access your DGB instance (*i.e.* in `docker` group on the host running DGB) has a `root` or equivalent access on all hosts, otherwise you expose yourself to privilege escalation.

## Limitations

If you run a lot of containers across multiple hosts, the final diagrams may be unreadable. Indeed, GraphViz is not made to manage vertically aligned clusters and the final diagram will be too wide. If so, you may want to set `merge` to `false` and generate a single diagram per host.

Also, as the graph is distributed per-network, if a host belongs to more than one network, it will be rendered on a single network only.

## Contributing

Contributions are very welcomed. I am not a developer, so feel free to give feedback, improve the code or develop new features.

* `dgb.py` contains the entrypoint of DGB
* `render.py` contains the code needed to put diagrams together and generate images
* `build.py` contains the code to build diagrams themselves, with DOT python library
* `docker_info.py` contains the code needed to get informations about running Docker containers
* `actions.py` is the place to put all post generation hooks
