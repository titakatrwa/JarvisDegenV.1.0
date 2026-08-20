# Publication de JarvisV1 sur GitHub

Ce dossier est autonome et ne contient ni environnement virtuel, ni dépendances installées,
ni base SQLite, ni logs, ni secret.

## Publication

```powershell
cd C:\Users\Gorkus\Documents\Projet_Crypto\JarvisV1
git init
git add .
git commit -m "Publication de JarvisDegen V1"
git branch -M main
git remote add origin https://github.com/VOTRE-COMPTE/VOTRE-DEPOT.git
git push -u origin main
```

## Vérification locale

```powershell
python -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\streamlit.exe run streamlit_app.py
```

Pour la partie TypeScript :

```powershell
pnpm install
pnpm check
```

La V1 est exclusivement une simulation. Aucun wallet ou mécanisme de transaction réelle
n'est inclus.
