# Retrieval-Augmented Generation (RAG)

Le RAG combine une recherche dans une base documentaire et un modèle de langage. On découpe les documents en passages, on les transforme en vecteurs, et pour chaque question on récupère les passages les plus proches avant de générer la réponse.

Avantages : réponses sourcées, connaissances à jour sans réentraîner le modèle, moins d'hallucinations.

Les bases vectorielles comme FAISS, Chroma ou pgvector servent à la recherche par similarité cosinus. #ia
