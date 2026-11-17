## Résumé des changements

Décrivez ce que change cette pull request et pourquoi. Si elle résout une issue, ajoutez `Closes #123`.

## Type de modification

- [ ] Nouvelle ressource ou correction de données (`data/podcasts-*.yaml`)
- [ ] Correction de bug
- [ ] Amélioration ou nouvelle fonctionnalité
- [ ] Documentation
- [ ] Maintenance ou outillage (`chore`)

## Captures d’écran

Ajoutez des captures ou une courte vidéo si le rendu visuel change. Supprimez cette section sinon.

## Détails techniques

Précisez les fichiers modifiés, les commandes exécutées et les éventuels effets de bord. Les fichiers générés dans `docs/`, `podcasts.yaml` et `reports/` doivent être inclus s’ils changent après le rendu.

## Checklist de vérification

- [ ] Le YAML est valide et les champs obligatoires sont renseignés.
- [ ] `python scripts/enrich_podcasts.py` a été exécuté si les données source changent.
- [ ] `python scripts/check_health.py` a été exécuté et les nouveaux liens ont été vérifiés.
- [ ] Aucun lien cassé, flux RSS invalide ou lien non officiel n’a été ajouté.
- [ ] `python scripts/render_html.py` a été exécuté et les fichiers générés sont inclus.
- [ ] `python -m py_compile scripts/*.py` passe si le code Python change.
- [ ] `node --check docs/assets/app.js` passe si le JavaScript change.
- [ ] `git diff --check` ne remonte aucun problème.
- [ ] Le site a été contrôlé localement avec `python -m http.server 8000 --directory docs`.
- [ ] La branche est à jour avec `main` (`git pull --rebase origin main`).
- [ ] Les messages de commit suivent les conventions de `CONTRIBUTING.md`.
- [ ] Aucun secret, jeton ou fichier de cache n’est inclus.
