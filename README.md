# Graph Bot

/!\ WIP

Ce projet vise à automatiser la construction des schémas de l’infrastructure, en particulier au niveau des conteneurs Docker.

Les schémas sont constamment obsolètes : nouveaux services, dépréciations... Ils ont donc une utilité toute relative.
L'idée est donc d'automatiser la construction de ces schémas, en suivant grossièrement les étapes suivantes :

* Le script est invoqué pour une VM en particulière, avec un nom de machine en paramètre
* On regarde quels conteneurs sont lancés, afin de ne pas répertorier des entrées obsolètes du `docker-compose`.
* Pour ces conteneurs, on inspecte le contenu du `docker-compose.yml` : ports mappés, liens, volumes, réseaux...
* On ajoute les règles Traefik (en particulier `frontend.rule`) qui constituent des liens "artificiels"
* On sélectionne ces informations et on créée un fichier au format DOT. 
* Ce fichier est poussé sur un repo, et une CI le compile au format voulu et met à jour l'image utilisée par le Wiki (la CI est optionnelle et peut être même superflue, à voir).

Enfin, on précise sur le wiki que les schémas sont générés automatiquement, et la date de la dernière génération réussie.

Tel que conçu, il ne devrait pas y avoir d'informations privées se retrouvant sur les schémas : seulements les conteneurs qui tournent et le cas échéant leur URL publique.

Pour toute la partie DNS, il est envisageable de garder ces informations "à la main", étant donné qu'elles ne changent pas souvent.
