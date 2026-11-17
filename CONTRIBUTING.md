# Contribuer à CyberPodcast

Merci de vouloir améliorer CyberPodcast. Ce dépôt est public, sans runtime serveur : les données source sont des fichiers YAML et le site est généré statiquement dans `docs/`.

- Page publique : https://cyberpodcast.fr/contribuer.html
- Signalement guidé : https://github.com/zebux/CyberPodcast/issues/new/choose
- Sécurité : [SECURITY.md](SECURITY.md)

## Critères d’acceptation

Une ressource ou une correction est acceptée lorsque :

- le sujet concerne la cybersécurité, le cloud, le développement ou un sujet adjacent utile à la communauté ;
- la ressource est publique, consultable sans accès privé et dispose d’un site officiel ou d’un flux RSS stable ;
- le podcast est actif ou récemment actif, ou son intérêt historique est explicitement justifié ;
- aucun doublon n’existe déjà dans l’annuaire ou dans les issues ouvertes ;
- les liens fournis sont officiels, accessibles et ne renvoient pas vers un revendeur ;
- le contenu n’est ni illégal, ni haineux, ni trompeur ;
- le YAML est valide, les champs obligatoires sont renseignés et les vérifications locales passent.

Pour un simple signalement, une issue suffit. Pour une nouvelle ressource, une pull request est appréciée mais pas obligatoire.

## Conventions de nommage

- `id` : minuscules, chiffres et tirets uniquement, en kebab-case, par exemple `radio-csirt` ou `cloud-native-fr`.
- `id` doit rester stable : il est utilisé par les fiches, l’API, les favoris locaux et les liens internes.
- `name` : nom public exact, tel qu’affiché par la ressource.
- `category` et `topics` : valeurs lisibles et cohérentes, par exemple `Cybersécurité`, `Cloud`, `DevOps`, `IA`.
- `language` : `fr` ou `en`.
- `platform` : hébergeur RSS connu, par exemple `Ausha`, `Anchor`, `Transistor`, `Podcastics`.
- Branches : `feat/<sujet>`, `fix/<sujet>`, `docs/<sujet>` ou `chore/<sujet>`.

## Structure des fichiers

```text
data/podcasts-*.yaml         sources maintenues à la main, prioritaires
scripts/enrich_podcasts.py   fusion, déduplication et enrichissement
scripts/check_health.py      contrôle des liens et rapport de santé
scripts/render_html.py       génération du site statique
podcasts.yaml                base enrichie générée, ne pas éditer à la main
docs/                        site généré, ne pas éditer à la main
reports/health.json          rapport généré
.github/ISSUE_TEMPLATE/      modèles d’issues
.github/workflows/           automatisation GitHub Actions
```

## Ajouter une ressource

Ajoutez une entrée dans `data/podcasts-cyber.yaml`, `data/podcasts-cloud.yaml` ou `data/podcasts-dev.yaml` :

```yaml
  - id: mon-podcast
    name: 'Mon Podcast'
    category: ['Cybersécurité', 'Blue Team']
    language: fr
    host: 'Prénom Nom'
    status: active
    website: https://exemple.fr
    rss: https://exemple.fr/feed.xml
    apple_podcast: https://podcasts.apple.com/...
    description: 'Description courte et factuelle du podcast.'
    platform: Ausha
```

Champs obligatoires : `id`, `name`, `category`, `language`, et au moins `website` ou `rss`. Le flux RSS est fortement recommandé. Les autres champs sont facultatifs mais améliorent la fiche générée.

## Procédure de pull request

1. Forkuez le dépôt puis créez une branche courte depuis `main`.
2. Modifiez uniquement le fichier source concerné dans `data/`.
3. Lancez les vérifications locales :

```bash
python -m pip install -r requirements.txt
python scripts/enrich_podcasts.py
python scripts/check_health.py
python scripts/render_html.py
```

4. Ajoutez les fichiers générés s’ils changent après le rendu.
5. Créez un commit atomique avec un message conventionnel : `feat:`, `fix:`, `docs:` ou `chore:`.
6. Poussez la branche et ouvrez la pull request avec le modèle fourni.
7. Répondez aux retours de relecture en ajoutant des commits ou en rebasant proprement votre branche.

## Bonnes pratiques Git

- Un commit = une intention claire ; évitez les commits fourre-tout.
- Ne commitez jamais de secret, de jeton, de données personnelles ou de fichier de cache.
- Utilisez `git pull --rebase origin main` avant de pousser.
- Si le remote a généré des fichiers, résolvez les conflits YAML/JSON en relançant `python scripts/render_html.py`, puis `git add -A` et `git rebase --continue`.
- Ne forcez pas le push sur `main`.
- Vérifiez `git diff --check` avant de proposer une pull request.

## Code de conduite

Soyez respectueux, précis et bienveillant. Aucune insulte, discrimination, harassment ou publication d’informations privées n’est acceptée. Présumez la bonne foi, discutez des idées plutôt que des personnes et acceptez les décisions des mainteneurs. Les comportements inappropriés peuvent entraîner la clôture d’une issue, d’une pull request ou l’accès restreint au dépôt.

Pour une vulnérabilité, ne suivez pas cette procédure : utilisez [SECURITY.md](SECURITY.md).
