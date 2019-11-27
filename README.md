# Graph Bot

<!-- TOC depthFrom:2 depthTo:6 withLinks:1 updateOnSave:0 orderedList:0 -->

- [Fonctionnement](#fonctionnement)
- [Modes de fonctionnement](#modes-de-fonctionnement)
- [Usage](#usage)
	- [Commun](#commun)
	- [TLS](#tls)
	- [Cas particuliers](#cas-particuliers)
- [Sécurité](#scurit)
- [Todo](#todo)

<!-- /TOC -->

## Fonctionnement

Ce projet vise à automatiser la construction des schémas de l’infrastructure se trouvant sur [cette page](https://wiki.picasoft.net/doku.php?id=infrastructure:architecture_globale).

Les schémas sont constamment obsolètes : nouveaux services, dépréciations... Ils ont donc une utilité toute relative. De plus, certaines informations sont manquantes, comme les mapping de ports.

L'idée est donc d'automatiser la construction de ces schémas, en suivant grossièrement les étapes suivantes :

* Le script interroge périodiquement les machines virtuelles cibles (`cron`)
* On interroge le démon Docker pour récupérer les informations intéressantes sur les conteneurs lancés
* Si Traefik est utilisé comme reverse-proxy, on ajoute le mapping d'URL en tant que lien virtuel entre conteneurs
* Un graphe au format DOT synthétisant ces informations est créé et une ou des images sont générées
* Des actions post-génération sont déclenchées, comme l'upload WebDAV.

Enfin, on précise sur le wiki que les schémas sont générés automatiquement.

Tel que conçu, il ne devrait pas y avoir d'informations privées se retrouvant sur les schémas : seulements les conteneurs qui tournent et le cas échéant leur URL publique. Les ports exposés en interne ainsi que les mappings sont également précisés.

## Modes de fonctionnement

Comme on peut le voir dans le fichier [config_example.json](./config_example.json), il est possible de spécifier plusieurs hôtes à interroger :

* Si un seul hôte est précisé, le graphe final est identique au graphe de l'hôte
* Si plusieurs hôtes sont précisés, un ou plusieurs graphes sont générés en fonction du paramètre `merge` de la configuration.

Les hôtes peuvent être locaux ou distants. Cette dernière possibilité nécessite :
* Un démon Docker distant configuré pour être exposé via TCP et une CA configurée ;
* Un certificat client, une clé ainsi que le certificat de la CA côté local.

L'avantage d'interroger plusieurs hôtes à distance est d'exécuter le script à un seul endroit et de centraliser les résultats.
Les efforts de maintenance et de configuration sont ainsi réduits, puisqu'il n'y a plus qu'un seul conteneur `graph-bot`.

## Usage

### Commun

Le `Dockerfile` et le `docker-compose.yml` sont prévus pour fonctionner clé en main. Il faut simplement rédiger la configuration. Exemple ci-dessous :

```bash
git clone https://gitlab.utc.fr/picasoft/projets/graph-bot.git
cd graph-bot
docker build -t graph-bot .
# On peut utiliser autre chose que config, mais il faut modifier docker-compose.yml
mkdir config output
# Attention : config.json doit au minimum avoir o=r comme permission
mv config_example.json config/config.json
docker-compose up -d
docker logs -f graph-bot
```

Docker Compose initialise plusieurs variables d'environnement par défaut que vous pouvez mettre à jour :
* `CONFIG_PATH` : point de montage de la configuration - défaut : `/config`
* `OUTPUT_PATH` : point de montage du répertoire d'images générées - défaut : `/output`
* `CRON_CONFIG` : au format `crontab` - défault : `0 * * * *`, soit toutes les minutes.

Une fois générés, les fichiers sont accessibles dans `OUTPUT_PATH` au format PNG et DOT.

* Si `merge` vaut `true`, le fichier sortant porteront les noms `<organization>` et `<organization>.png`
* Sinon, les noms seront au format `<vm>` et `<vm>.png`.

La légende correspond au(x) fichier(s) généré(s) se trouve dans `OUTPUT_PATH/legend.png`.

### TLS

Si on interroge des hôtes à distance, il faut rajouter de la configuration supplémentaire. Pour chaque hôte distant, on ajoutera dans `config.json` :

```json
"tls_config":
{
	"ca_cert": "auth/pica01/ca.pem",
	"cert": "auth/pica01/cert.pem",
	"key": "auth/pica01/key.pem"
}
```

Avec :
* `ca_cert` : certificat de la CA de l'hôte distant
* `cert` : certificat du client
* `key`  : clé du client

Les chemins sont donnés relativement à `DATA_PATH`. Dans l'exemple ci-dessus, les certificats seront donc montés dans `/config/auth/<vm>/*.pem`.

### Cas particuliers

Si les hôtes ainsi que les conteneurs sont nombreux, il est possible que le graphe final généré par défaut soit très large.
GraphViz n'est pas prévu pour aligner verticalement les sous-graphes, ou clusters.

À cet effet, il est possible de passer le paramètre `merge` à `false` afin de générer un graphe par hôte.

Le nom du graphe généré aura le format `<vm>.png`.

## Sécurité

Le conteneur est lancé en tant qu'utilisateur privilégié. En effet, les clés privées appartiendront très probablement à `root` sur l'hôte, en `600`, et il est souhaitable qu'elles le restent.

Aussi, le socket Docker est monté à l'intérieur du conteneur ; il leake l'ensemble des informations associées à tous les conteneurs et permet de modifier leur état sans restrictions.
**Pire, monter le socket Docker est équivalent à donner un accès `root` sur l'hôte.**

Il est donc **obligatoire** de le laisser dans un réseau Docker isolé et sans ports exposés (il n'y a aucune raison que ce soit le cas!).
De plus, si les hôtes sont distants, l'accès s'étend aux machines distantes car le conteneur a alors accès aux sockets des clients.

Je répète : avoir accès au conteneur `graph-bot` est équivalent à obtenir un accès `root` sur l'hôte ainsi que sur toutes les machines distantes concernées.

Il est donc **fondamental** que les personnes ayant accès à la machine sur laquelle s'exécute `graph-bot` **et** faisant partie du groupe `docker` aient accès à l'ensemble des hôtes configurés, sans quoi ces personnes pourraient escalader leurs privilèges. Autrement dit, il est préférable que `graph-bot` s'exécute sur la machine la plus restreinte de l'infrastructure.

## Todo

* Ré-écrire le README
* Traduction anglais/français
* Utiliser le type hinting plutôt que ma doc dégueu des fonctions
* Configuration d'un cron
* Ajout doc développeur
