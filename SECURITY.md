# Politique de sécurité

CyberPodcast est un site statique public. La sécurité concerne principalement le dépôt, le pipeline GitHub Actions, les dépendances Python et les fichiers générés publiés via GitHub Pages.

## Versions prises en charge

| Version | Prise en charge |
| --- | --- |
| `main` / site public | Oui |
| Anciens commits et forks | Non |
| Services tiers liés (Apple Podcasts, plateformes d’écoute, hébergeurs RSS) | Non |

## Signaler une vulnérabilité

Merci d’utiliser le signalement privé de GitHub : https://github.com/zebux/CyberPodcast/security/advisories/new

Ne publiez pas de détail exploitable dans une issue publique, une pull request, un commentaire ou un réseau social. Si le formulaire privé n’est pas disponible, contactez les mainteneurs via GitHub en demandant un canal privé, sans joindre de preuve d’exploitation.

Votre signalement doit inclure, si possible :

- la description de la vulnérabilité et son impact ;
- l’URL, le fichier, la dépendance ou le workflow concerné ;
- les étapes de reproduction ou un proof of concept minimal ;
- la version ou le commit observé ;
- une piste de correction, si vous en avez une.

## Périmètre

Sont notamment concernés :

- le script de génération `scripts/render_html.py` et l’enrichissement `scripts/enrich_podcasts.py` ;
- les workflows GitHub Actions et les permissions du dépôt ;
- les dépendances déclarées dans `requirements.txt` ;
- les fichiers générés dans `docs/` et les données exposées par l’API JSON.

Sont hors périmètre : les failles propres aux plateformes tierces, les contenus des podcasts et les simples liens cassés non sécuritaires. Ces derniers peuvent être signalés avec le modèle d’issue **Lien cassé**.

## Traitement

Les signalements sont accusés réception sous 5 jours ouvrés. Un état d’avancement est fourni au moins toutes les semaines jusqu’à la résolution. La correction est priorisée selon la gravité, l’exposition publique et la facilité d’exploitation. Le mainteneur peut demander une coordination de divulgation avant toute publication.

## Bonne foi

Les signalements effectués de bonne foi, sans accès non autorisé à des données privées, sans destruction et sans perturbation du service, sont acceptés. Merci d’agir de manière responsable et de laisser le temps de corriger avant toute divulgation publique.
