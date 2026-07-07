# apps/web — Frontend Next.js

Reserve pour la semaine 4 (voir `orbit-coding-guide.md` §8).

Ne pas initialiser `create-next-app` avant d'avoir le dashboard basique a construire —
ordre recommande : d'abord faire tourner le backend (semaines 1-3), puis brancher
le frontend une fois que `/runs` renvoie de vraies donnees classifiees.

Quand pret :
```bash
npx create-next-app@latest . --typescript --tailwind --app
```

Puis appliquer les design tokens de `charte-ai-commandos.md` (§1) dans
`styles/tokens.css` et `tailwind.config.ts` (voir `orbit-coding-guide.md` §4).
