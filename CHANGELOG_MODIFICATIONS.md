# Journal des modifications — Audit & Finalisation LabMind

## 1. Base documentaire médicale (RAG)
- **Ajout de `knowledge_corpus/sources/medlineplus_niddk_ada_lab_tests.txt`** : synthèses traçables issues de MedlinePlus (NIH), NIDDK (tests diabète / HbA1c / glycémie) et ADA (précautions d'interprétation).
- **Ajout de `knowledge_corpus/sources/oms_has_nutrition_suivi.txt`** : synthèses traçables issues de l'OMS (alimentation saine, activité physique) et de la HAS (parcours de soins, comparaison antérieure, signes nécessitant un avis médical rapide).
- **Mise à jour de `knowledge_corpus/metadata/sources_registry.json`** : enregistrement vérifié de ces 2 sources (`collected`, URL officielles HTTPS, dates, conditions de réutilisation) portant le corpus collecté à 7 documents officiels avec réindexation automatique FAISS au démarrage (`corpus.sha256`).

## 2. Comparaison antérieure & détection d'écarts marqués (sans système expert)
- **`backend/app/schemas.py`** : ajout du modèle `PriorComparison` (`prior_value`, `prior_unit`, `prior_date`, `comparable`, `delta`, `trend`, `note`) et des champs optionnels `marked_deviation` et `prior` sur `ParameterResult`.
- **`backend/app/identification/parser.py`** : extraction structurée des valeurs et dates antérieures (`antér.`, `antériorité`, `préc.`) sans altérer le parsing de la valeur courante ni de la fourchette du laboratoire.
- **`backend/app/validation/analysis.py`** : comparaison purement arithmétique (`_build_prior_comparison`) avec vérification stricte d'égalité d'unités (sinon marquage `not_comparable`) et détection arithmétique non diagnostique d'écart marqué (`_is_marked_deviation`).

## 3. Pipeline RAG, ancrage et export PDF
- **`backend/app/generation/grounding.py`** : autorisation explicite des valeurs/dates antérieures (`parameter.prior`) dans `_allowed_numbers_for` afin que le contrôle d'ancrage valide les comparaisons chiffrées exactes.
- **`backend/app/generation/rag.py`** : enrichissement du `SYSTEM_PROMPT` et de `build_parameter_prompt` (rôle biologique, position par rapport au laboratoire, évolution antérieure neutre, limites d'interprétation, orientation vers le médecin / vigilance si écart marqué), passage à `max_tokens=420` pour éviter toute troncature.
- **`backend/app/report/pdf_generator.py`** : affichage des comparaisons antérieures dans le tableau des résultats et mise en avant d'une alerte neutre de vigilance lorsqu'un écart arithmétique marqué est détecté.

## 4. Interface utilisateur Angular (sans compte, 100 % français)
- **`accueil.component.*`** : ajout d'un aperçu visuel immédiat du document déposé (miniature image via `URL.createObjectURL` nettoyée à la destruction, ou badge PDF) avant l'envoi.
- **`attente.component.*`** : remplacement du simple indicateur d'attente par un suivi en 4 étapes aligné sur le pipeline backend réel.
- **`resultats.component.*`** : affichage des badges d'évolution antérieure, bannière de vigilance en cas d'écart arithmétique marqué, affichage des explications Qwen sourcées pour tous les paramètres (hémogramme, formule leucocytaire et biochimie), et ajout d'un bloc dédié **« Limites d'interprétation et données incertaines »**.

## 5. Tests, évaluation et documentation
- **`backend/tests/test_audit_final_suite.py`** : tests unitaires pour l'extraction photo OCR (16 paramètres), la comparaison antérieure (comparable vs non comparable), l'écart marqué, l'ancrage de chiffres antérieurs, le registre documentaire et le diagnostic d'erreur OCR.
- **`evaluation/ground_truth/eval_05_prior_comparison.json` & `eval_06_photo_magnesium.json`** : nouveaux scénarios d'évaluation de référence.
- **`README.md` & `CHANGELOG_MODIFICATIONS.md`** : documentation complète en 12 sections et historique des corrections.

---

# Journal d'amélioration — Version finale (8 sections, images alimentaires corrigées, explications concises)

## 1. Explications médicales concises & résumé général
- **`backend/app/generation/rag.py`** : raccourcissement du prompt système (`max_tokens=260`) pour imposer 2 à 3 phrases claires (rôle du paramètre, signification du résultat, brève explication si anomalie), ajout de `_build_general_summary()` et sérialisation de `general_summary`.

## 2. Suppression de la section « Limites d'interprétation et données incertaines »
- **`backend/app/report/pdf_generator.py`** & **`frontend/src/app/pages/resultats/`** : suppression complète de la section autonome des limites dans l'interface Web et le rapport PDF, tout en conservant la détection interne et une indication courte directement à côté du résultat concerné si une valeur/référence est manquante.

## 3. Correction définitive des images alimentaires
- **`frontend/public/assets/foods/`** : bibliothèque locale étendue à 8 photographies distinctes (`almonds_walnuts.jpg`, `pumpkin_seeds.jpg`, `spinach.jpg`, `lentils_chickpeas.jpg`, `fish.jpg`, `fruits.jpg`, `whole_grains.jpg`, `vegetables.jpg`).
- **`backend/app/generation/rag.py`** & **`resultats.component.ts`** : ajout de `_resolve_food_image_key()` avec correspondance sémantique par nom d'aliment et déduplication stricte (`used_keys`), plus repli visuel neutre (`"neutral"` / icône SVG) si aucune image pertinente n'est disponible — fin de la réutilisation d'une image par défaut unique.

## 4. Repères multi-catégories, questions médecin & structure en 8 sections
- **`knowledge_corpus/`** : enrichissement OMS / HAS / ADA (`https://diabetesjournals.org/care`) / NIDDK / MedlinePlus (alimentation, activité physique douce et progressive, sommeil, hydratation, tabac/alcool sans jugement, suivi médical).
- **`backend/app/generation/interface.py`**, **`rag.py`**, **`pdf_generator.py`**, **`resultats.component.html`** : réorganisation harmonisée Web + PDF selon l'ordre exact en 8 sections :
  1. Résumé général du bilan
  2. Tableau des résultats avec leur statut
  3. Explication concise des anomalies et paramètres
  4. Conseils alimentaires
  5. Activité physique et habitudes de vie
  6. Suivi médical recommandé
  7. Questions à poser au médecin
  8. Sources médicales
