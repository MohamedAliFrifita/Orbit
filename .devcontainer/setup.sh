#!/usr/bin/env bash
set -e

echo "Installation du backend..."
cd apps/api
pip install -e ".[dev]"
cd ../..

echo "Installation du frontend..."
cd apps/web
npm install

# Génère automatiquement l'URL publique du backend Codespaces
echo "NEXT_PUBLIC_API_URL=https://${CODESPACE_NAME}-8000.app.github.dev" > .env.local
cd ..

echo "Setup terminé. Lancer 'uvicorn orbit.api.main:app --reload --port 8000' dans un terminal,"
echo "et 'npm run dev' dans apps/web dans un second terminal."