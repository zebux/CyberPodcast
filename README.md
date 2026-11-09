# CyberPodcast

Annuaire statique de podcasts francophones et internationaux consacrés à la cybersécurité, au cloud et au développement.

Site : https://zebux.github.io/CyberPodcast/

## Fonctionnalités

- Recherche instantanée et filtres par catégorie, statut, langue, plateforme et sujets multiples.
- Favoris stockés localement dans le navigateur, sans compte ni cookie.
- Lecteur audio intégré pour le dernier épisode, lecteur global sur l'annuaire et liste des épisodes récents.
- Fiches détaillées par podcast avec liens d'écoute, métadonnées, sujets, tags et podcasts proches.
- Pages secondaires : sujets, statistiques, à propos et rapport de santé.
- SEO statique : sitemap, robots.txt, flux RSS, JSON-LD, Open Graph et Twitter Cards.
- API JSON publique : `docs/api/podcasts.json`, `docs/api/stats.json`, `docs/api/health.json`.
- Thème clair/sombre avec préférence système et mémorisation locale.

## Architecture

Le projet reste volontairement simple et sans runtime serveur :

```text
data/podcasts-*.yaml     sources maintenues à la main
data/curated.yaml        corrections vérifiées (liens, flux, descriptions)
scripts/enrich_podcasts.py   fusion, déduplication, enrichissement RSS/Apple/sites
scripts/check_health.py      contrôle des liens et rapport de santé
scripts/render_html.py       génération complète du site statique
podcasts.yaml            base enrichie version 3
docs/                    site publié par GitHub Pages
reports/health.json      dernier rapport de santé
```

Le workflow GitHub Actions tourne chaque jour : enrichissement, contrôle santé, rendu, validation, commit et déploiement GitHub Pages.

## Modèle de données

Chaque podcast de `podcasts.yaml` contient notamment :

- identité : `id`, `name`, `category`, `language`, `country`, `hosts`, `author` ;
- liens : `website`, `rss`, `apple_podcast`, `spotify`, `youtube`, `deezer`, `pocket_casts`, `podcast_addict`, `amazon_music`, `castbox`, `linkedin` ;
- contenu : `description`, `image`, `episodes`, `last_episode`, `last_episode_title`, `last_episode_url`, `last_episode_audio`, `last_episode_duration` ;
- rythme : `frequency`, `frequency_days` ;
- qualité : `status`, `episode_count`, `average_duration`, `community_rating`, `community_rating_count` ;
- suivi : `first_seen`, `updated_at`, `platform`, `topics`, `tags`.

Les statuts sont `active`, `slow` et `archived` ; l'interface les affiche comme « Actif », « Peu actif » et « Inactif ».

## Commandes locales

```bash
python -m pip install -r requirements.txt
python scripts/enrich_podcasts.py
python scripts/check_health.py
python scripts/render_html.py
python -m http.server 8000 --directory docs
```

Pour tester le rendu sans réseau :

```bash
python scripts/check_health.py --skip-network
python scripts/render_html.py
```

## Ajouter ou corriger un podcast

1. Ajouter l'entrée minimale dans le fichier source adapté (`data/podcasts-cyber.yaml`, `-cloud` ou `-dev`).
2. Ajouter si nécessaire une correction dans `data/curated.yaml` : site officiel, flux RSS, lien Apple, description, animateurs, pays ou plateforme.
3. Lancer l'enrichissement puis vérifier la fiche générée.

Les valeurs de `data/curated.yaml` ont priorité sur la découverte automatique. Les champs absents sont enrichis depuis le site officiel, le flux RSS et Apple Podcasts. En cas d'échec réseau, les valeurs de la dernière exécution sont conservées.

## Contribuer

Une erreur, un flux cassé, un podcast manquant ? Ouvrez une issue ou proposez une correction dans `data/curated.yaml`. Les liens officiels et les flux vérifiés sont prioritaires.

## Notes

- Les notes affichées proviennent d'Apple Podcasts et sont indicatives.
- Les liens d'écoute renvoient vers les plateformes officielles.
- Le site ne dépose aucun cookie et n'utilise aucun tracker.
- Les données et le code sont publics sur GitHub.
