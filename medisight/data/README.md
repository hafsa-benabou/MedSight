# Données MEDISIGHT

| Dossier | Contenu | Statut affiché |
|---|---|---|
| `samples/` | Extraits **réels** transcrits à la main depuis les pages publiques de l'AMMPS (consultées le 25/10/2026), avec leurs anomalies d'origine | `official` |
| `demo/` | Jeu de **démonstration simulé** (prix, présentations, pharmacies, stocks et gardes fictifs) | `simulated` |
| `reference/` | Synonymes de substances (DCI, INN anglais, arabe, variantes) utilisés par l'import et le NLP | — |
| `templates/` | En-têtes attendus pour les imports manuels (gardes, interactions sourcées, exports AMMPS) | — |
| `raw/` | Fichiers officiels téléchargés par l'équipe (non versionnés) | — |
| `nlp/` | Corpus d'énoncés annotés (lot suivant) | — |

Les fichiers officiels complets ne sont pas redistribués ici : voir `docs/DATA_SOURCES.md` pour les obtenir
(référentiel CNOPS sur data.gov.ma sous ODbL, export AMMPS à demander, OpenStreetMap via `fetch-osm`).
