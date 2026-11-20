# Décision 0008 : Génération du rapport PDF pédagogique LabMind (18/11/2026)

## Contexte
L'endpoint `GET /v1/tasks/{task_id}/report.pdf` produisait jusque-là un PDF technique provisoire.

## Décisions
1. **Générateur ReportLab dédié (`backend/app/report/pdf_generator.py`)** :
   - Tableau des résultats avec entête répétée automatiquement sur les documents multi-pages (`repeatRows=1`), fourchettes issues uniquement du document (y compris bornes unilatérales `<` / `>`), position arithmétique neutre, confiance et numéro de page.
   - Polices TrueType Unicode (`Arial` sous Windows / `DejaVuSans` sous Linux) pour préserver les accents, `µ` et `²`.
   - Section dédiée aux limites et paramètres non analysés sans deviner les champs manquants.
   - Explications pédagogiques accompagnées de leurs `source_id`, URL et dates.
   - Section *Informations générales (hygiène de vie)* affichée **uniquement** si des sources correspondantes ont été effectivement récupérées.
   - Message de précaution (`DISCLAIMER`) affiché exactement une fois en fin de document.
2. **Intégration transparente dans `TaskManager`** : aucune modification du contrat API v1 ni du schéma `Task`.