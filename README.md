# Graph Bot (WIP)

## Fonctionnement

Ce projet vise à automatiser la construction des schémas de l’infrastructure se trouvant sur [cette page](https://wiki.picasoft.net/doku.php?id=infrastructure:architecture_globale).

Les schémas sont constamment obsolètes : nouveaux services, dépréciations... Ils ont donc une utilité toute relative. De plus, certaines informations sont manquantes, comme les mapping de ports.

L'idée est donc d'automatiser la construction de ces schémas, en suivant grossièrement les étapes suivantes :

* Le script est invoqué périodiquement sur les machines virtuelles cibles.
* On interroge le démon Docker pour récupérer les informations intéressantes sur les conteneurs lancés
* Si Traefik est utilisé comme reverse-proxy, on ajoute le mapping d'URL en tant que lien virtuel entre conteneurs
* Un graphe au format DOT synthétisant ces informations est créé puis poussé sur un dépôt Git
* Ce fichier est poussé sur un repo, une CI le compile et :
	* Met à jour l'image utilisée par le Wiki, ou ;
	* Pousse le fichier sur le Cloud, dont le lien connu à l'avance est répertorié dans le Wiki

La CI est peut-être superflue, à voir s'il est souhaitable de versionner les fichiers DOT. Si non, on pourra directement pousser les images sur le Cloud.

Enfin, on précise sur le wiki que les schémas sont générés automatiquement, et la date de la dernière génération réussie.

Tel que conçu, il ne devrait pas y avoir d'informations privées se retrouvant sur les schémas : seulements les conteneurs qui tournent et le cas échéant leur URL publique. Les ports exposés en interne ainsi que les mappings sont également précisés.

## Usage

Le Dockerfile devrait faire tourner sans problèmes le script.

```
git clone https://gitlab.utc.fr/picasoft/projets/graph-bot.git
cd graph-bot
docker build -t graph-bot .
mv config_example.json config.json
```

Modifier le fichier `config.json` pour s'adapter à la machine virtuelle courante, puis :

```
docker-compose up -d
docker logs -f graph-bot
```

Si tout se passe bien, le résultat se trouve dans `output/<vm>.gv.png`. Pour l'instant, le PNG est généré directement par le script.

## Sécurité

Le conteneur est lancé en tant qu'utilisateur non-privilégié, en revanche le socket Docker est monté à l'intérieur, et le socket leake l'ensemble des informations associées à tous les conteneurs.

Il est donc important de le laisser dans un réseau Docker isolé, sans connexion avec l'extérieur et sans ports exposés.

## Todo

* Mettre en place la CI
* Refacto le code, en particulier sur la partie coloration, agencement
* Régler les problèmes de permission sur le dossier de sortie du conteneur.
* Ajouter des liens invisibles entre clusters pour forcer l'agencement de haut en bas
* Mettre en place une archi maître-esclave ou interroger le socket Docker exposé via TCP pour centraliser les infos
* Produire un seul gros graphe avec les infos DNS
* Ajouter la légende
