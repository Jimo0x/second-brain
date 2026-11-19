# Injection SQL

Une injection SQL survient quand une entrée utilisateur est concaténée dans une requête. Exemple : ' OR 1=1 -- contourne une authentification naïve.

Protection : requêtes préparées avec paramètres, ORM, principe du moindre privilège sur le compte de base de données, validation des entrées.

C'est toujours dans le top 10 OWASP sous la catégorie « Injection ». #sécurité #web
