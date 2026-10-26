# Données MEDISIGHT

| Dossier | Contenu | Statut affiché |
|---|---|---|
| `samples/` | Extraits **réels** transcrits à la main depuis les pages publiques de l'AMMPS (consultées le 25/10/2026), avec leurs anomalies d'origine | `official` |
| `demo/` | Jeu de **démonstration simulé** (prix, présentations, pharmacies, stocks et gardes fictifs) | `simulated` |
| `reference/` | Synonymes de substances (DCI, INN anglais, arabe, variantes) utilisés par l'import et le NLP | — |
| `templates/` | En-têtes attendus pour les imports manuels (gardes, interactions sourcées, exports AMMPS, variantes de noms commerciaux) | — |
| `raw/` | Fichiers officiels téléchargés par l'équipe (non versionnés), un dossier daté par téléchargement, ex. `raw/bdpm_2026-10-26/CIS_COMPO_bdpm.txt` | selon la source |
| `nlp/` | Corpus d'énoncés annotés (lot suivant) | — |

Les fichiers officiels complets ne sont pas redistribués ici : voir `docs/DATA_SOURCES.md` pour les obtenir
(référentiel CNOPS sur data.gov.ma sous ODbL, export AMMPS à demander, OpenStreetMap via `fetch-osm`,
BDPM sous Licence Ouverte : https://base-donnees-publique.medicaments.gouv.fr/telechargement, fichier des compositions).
