# Hachage des mots de passe

Un mot de passe ne doit jamais être stocké en clair ni avec un hachage rapide comme MD5 ou SHA-1 : un GPU en teste des milliards par seconde.

Il faut une fonction lente et salée : bcrypt, scrypt ou Argon2id. Le sel unique par utilisateur empêche les tables arc-en-ciel.

Le facteur de coût doit être réglé pour qu'un hachage prenne environ 250 ms sur le serveur. #sécurité #cryptographie
