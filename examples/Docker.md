# Docker et conteneurs

Un conteneur isole un processus grâce aux namespaces Linux (PID, réseau, montage) et limite ses ressources avec les cgroups. Ce n'est pas une machine virtuelle : le noyau est partagé.

Une image est construite à partir d'un Dockerfile, couche par couche. docker compose orchestre plusieurs services.

Pour la sécurité : ne pas lancer en root, images minimales, scanner les vulnérabilités. #devops #sécurité
