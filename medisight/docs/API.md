# API REST MEDISIGHT

Documentation interactive : http://localhost:8000/docs (Swagger, générée par FastAPI).
Erreurs : `{"error": {"code", "message", "details"}}` (ou `{"detail": ...}` pour les 404/422 de FastAPI).
Limitation de débit par IP (fenêtre 60 s) : chat 30, pills 10, autres 120 → `429 rate_limited` avec `Retry-After`.

## Système
| Méthode | Chemin | Rôle |
|---|---|---|
| GET | `/api/health` | état base, nombre de fiches par statut, modules (OCR, lecteurs de codes-barres) |
| GET | `/api/sources` | sources chargées, licence, dernier import |

## Catalogue
| Méthode | Chemin | Rôle |
|---|---|---|
| GET | `/api/medicines/search?q=&form=&status=&page=&size=` | recherche tolérante aux fautes ; code-barres EAN-13/GTIN-14 accepté ; `meta.dosage_found`, `available_dosages`, `did_you_mean` |
| GET | `/api/medicines/autocomplete?q=` | suggestions |
| GET | `/api/medicines/{id}` | fiche : présentations, prix sourcés, remboursements, sections cliniques |
| GET | `/api/medicines/{id}/generics` | génériques réglementaires (Répertoire AMMPS) et de composition |

## Pharmacies
| Méthode | Chemin | Rôle |
|---|---|---|
| GET | `/api/pharmacies/search?city=&q=&lat=&lon=&medicine_id=` | pharmacies ; `availability.kind` = verified / simulated / unverified |
| GET | `/api/pharmacies/on-duty?city=` | gardes en cours |

## Pill Identifier
`POST /api/pills/identify` (multipart, champ `file`, JPEG/PNG/WEBP ≤ 8 Mo) → `status` ∈ `identified`, `ambiguous`,
`contradictory`, `not_found`, `unreadable`, `ocr_unavailable` ; `candidates[]` (score heuristique 0-100, `evidence`,
`explanation`, `medicine_id`), `barcodes`, `extracted`, `ocr`, `quality`, `warnings`. Détail : `docs/PILL_IDENTIFIER.md`.

## Chatbot
### `POST /api/chat`
```json
{ "message": "Ch7al taman dyal Doliprane 500mg ?", "conversation_id": null, "context_medicine_id": null }
```
- `message` : 1 à 1000 caractères ; `conversation_id` : renvoyé par la réponse précédente ;
  `context_medicine_id` : identifiant PostgreSQL d'un médicament (vérifié).

Réponse :
| Champ | Contenu |
|---|---|
| `message` | réponse rédigée (texte, sauts de ligne) |
| `language` | `code` (fr, ar, darija, darija_latin, en), `script`, `reply_language` (fr/ar), `confidence` |
| `intent` | `name` détectée, `resolved` (après prise en compte des entités), `confidence`, `matched`, `alternatives` |
| `entities` | `medicines[]` (texte, marque, score, méthode), `ingredients[]`, `dose`, `city` |
| `understanding` | `understood`, `partial`, `ambiguous`, `not_found`, `clarification_needed`, `dosage_not_found`, `information_unavailable`, `refused_medical_advice`, `emergency`, `not_understood` |
| `medicines[]` | cartes médicament (même format que la recherche) |
| `pharmacies[]` | pharmacies trouvées, avec disponibilité qualifiée |
| `sources[]` | `code`, `name`, `url`, `license`, `data_status` |
| `warnings[]`, `contains_simulated_data` | données simulées, contexte ignoré, etc. |
| `context_medicine`, `suggestions[]` | médicament de la conversation et questions proposées |
| `generation` | `template` (aucun LLM) ; `disclaimer` |

### `GET /api/chat/suggestions?medicine_id=&lang=fr|ar`
Carte du médicament et questions suggérées (404 si l'identifiant n'existe pas).

### `DELETE /api/chat/{conversation_id}`
Efface la conversation et son analyse.
