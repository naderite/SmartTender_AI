# SmartTender AI Local MVP

Ce module fournit un pipeline local plus structuré pour le challenge `SmartTender AI`, sans GCS, Firestore, Firebase ou Cloud Run.

Architecture locale :

1. upload ou lecture locale d'un tender (`.pdf`, `.txt`, `.md`)
2. ingestion des CVs dans une base SQLite locale
3. parsing heuristique des CVs et des tenders
4. création d'un texte de recherche sémantique par profil
5. indexation persistante des CVs dans Chroma
6. recherche sémantique + scoring lexical hybride
7. génération d'un rapport shortlist `.docx`
8. UI minimale pour la vidéo de démonstration

## Démarrage local

```powershell
cd Backend\LocalMVP
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app:app --reload --host 0.0.0.0 --port 8080
```

Puis ouvrir `http://localhost:8080`.

Note :

- au premier lancement sémantique, Chroma télécharge une fois un modèle ONNX local d'embedding
- ensuite il est réutilisé depuis le cache local de la machine

## Où fournir les clés API

Créer un fichier `.env` à côté de `app.py` à partir de `.env.example`.

Variables reconnues :

- `OPENAI_API_KEY`
- `GOOGLE_API_KEY`
- `GEMINI_API_KEY`
- `OPENROUTER_API_KEY`
- `OPENROUTER_MODEL`
- `GEMINI_MODEL`
- `SEARCH_TOP_K`

Important :

- le pipeline sémantique actuel n'a besoin d'aucune clé pour fonctionner
- `OPENROUTER_API_KEY` permet d'utiliser un modèle distant via OpenRouter
- `GEMINI_API_KEY` permet d'utiliser Gemini direct
- si les deux existent, le helper essaie Gemini direct d'abord puis OpenRouter

## Données locales

- `data/cv_bank/` : CVs déjà présents dans la base locale
- `data/tender_bank/` : exemples de tenders
- `data/uploads/` : fichiers envoyés via l'UI
- `data/parsed/` : JSON extraits
- `data/generated/` : rapports shortlist générés
- `data/chroma/` : index vectoriel local persistant
- `data/smarttender.db` : base SQLite locale

## Démo recommandée

1. montrer qu'une base locale de CV existe dans `data/cv_bank/`
2. expliquer que ces CVs sont ingérés dans `smarttender.db`
3. montrer que Chroma conserve un index sémantique réutilisable
4. charger un tender
5. lancer le matching
6. afficher le top candidats avec score lexical + score sémantique
7. télécharger/ouvrir le rapport Word généré

## Limites

- l'extraction CV et tender reste heuristique et non exhaustive
- l'index sémantique dépend de la qualité du texte extrait du PDF
- les clés API sont optionnelles mais pas encore exploitées pour un parsing LLM complet

Ce choix permet une démo stable en local tout en préparant une vraie montée en gamme vers un matching plus sémantique.
