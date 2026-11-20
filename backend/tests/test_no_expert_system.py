
"""
LabMind — Automated Anti-Expert-System Guardrail
=================================================

Objectif :
Empêcher la réintroduction accidentelle d'un système expert
médical basé sur des règles, conseils ou recommandations figés.

Ce scanner analyse statiquement le code Python de backend/app/.

Il recherche :
1. Les anciens symboles du moteur de règles.
2. Les noms typiques d'une base de règles.
3. Les conseils et prescriptions codés en dur.
4. Les tables statut biologique -> conseil.
5. Les constantes et fonctions héritées du prototype.
6. La validité du disclaimer pédagogique.

Limites :
- Un scanner AST ne comprend pas toute la sémantique du programme.
- Il ne détecte pas toutes les chaînes construites dynamiquement.
- Une revue humaine du code reste indispensable.

Exécution :
    cd backend
    pip install pytest
    pytest -v tests/test_no_expert_system.py
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Iterable


# ============================================================
# 1. CONFIGURATION
# ============================================================

APP_DIR = Path(__file__).resolve().parents[1] / "app"

DISCLAIMER_NAME = "DISCLAIMER"

MINIMUM_PYTHON_FILES = 1


# ============================================================
# 2. ANCIENS SYMBOLES INTERDITS
# ============================================================

# Symboles provenant du moteur de règles du notebook prototype.
# Ils ne doivent plus exister dans le code applicatif.

FORBIDDEN_SYMBOLS = {
    "tips_for",
    "collect_tips",
    "TIPS",
    "IRON_LOW",
    "BLOOD_HIGH",
    "SUGAR_HIGH",
    "SUGAR_LOW",
    "LIPID_HIGH",
    "TG_HIGH",
    "HDL_LOW",
    "WBC_ANY",
    "PLT_ANY",
    "CHOL_LOW",
    "DEFAULT_KNOW",
    "NO_REF",
    "doctor_questions",
    "what_it_measures",
}


# ============================================================
# 3. NOMS CARACTÉRISTIQUES D'UN MOTEUR DE RÈGLES
# ============================================================

FORBIDDEN_NAME_PATTERN = re.compile(
    r"^(?:"
    r"(?:.*_)?(?:tips?|advice|conseils?|recommendations?|recommandations?)(?:_.*)?"
    r"|rules?|regles?"
    r"|doctor_questions|what_it_measures"
    r"|iron_low|lipid_high|sugar_high|sugar_low|tg_high|hdl_low|blood_high"
    r"|knowledge_base|medical_rules|diagnosis_rules|prescription_rules"
    r")$",
    re.IGNORECASE,
)


# ============================================================
# 4. CONSEILS MÉDICAUX ET RECOMMANDATIONS INTERDITS
# ============================================================

# On recherche principalement des formulations de conseil.
# Un simple mot médical isolé ne suffit pas à faire échouer le test.

FORBIDDEN_ADVICE_PATTERNS = [
    r"\bmisez\s+sur\b",
    r"\bprivilégiez\b",
    r"\bprivilégier\b",
    r"\blimitez\s+(?:les|la|le|votre)\b",
    r"\bremplacez\s+(?:les|la|le)\b",
    r"\bévitez\s+(?:les|la|le|de)\b",
    r"\béviter\s+(?:les|la|le|de)\b",
    r"\bmangez\b",
    r"\bbuvez\b",
    r"\bconsommez\b",
    r"\bprenez\s+(?:un|une|des|du|de la)\b",
    r"\barrêtez\s+(?:de|le|la|les)\b",
    r"\bne\s+sautez\s+pas\s+de\s+repas\b",
    r"\bboissons?\s+sucrées?\b",
    r"\bhuile\s+d['’]olive\b",
    r"\blentilles\b",
    r"\bépinards\b",
    r"\bpois\s+chiches\b",
    r"\bcharcuterie\b",
    r"\bviennoiseries\b",
    r"\bvitamine\s+c\b",
    r"\bmarche\s+rapide\b",
    r"\bnatation\b",
    r"\bmusculation\b",
]


# ============================================================
# 5. MÉDICAMENTS ET PRESCRIPTIONS
# ============================================================

FORBIDDEN_PRESCRIPTION_PATTERNS = [
    r"\bposologie\b",
    r"\bprescription\s+de\b",
    r"\bprenez\s+(?:ce|un|une|des)\s+médicament",
    r"\bcommencez\s+un\s+traitement\b",
    r"\barrêtez\s+votre\s+traitement\b",
    r"\baugmentez\s+la\s+dose\b",
    r"\bdiminuez\s+la\s+dose\b",
    r"\bmg\s+par\s+jour\b",
    r"\bà\s+prendre\s+chaque\s+jour\b",
    r"\bstatine\b",
    r"\binsuline\b",
    r"\bantibiotique\b",
    r"\bcomplément\s+alimentaire\b",
    r"\bsupplément\s+alimentaire\b",
]


# ============================================================
# 6. TABLES DE STATUTS BIOLOGIQUES INTERDITES
# ============================================================

# Une table qui associe directement un statut à un texte de
# conseil constitue une forme classique de moteur de règles.

STATUS_VALUES = {
    "below_reference",
    "above_reference",
    "within_reference",
    "low",
    "high",
    "normal",
    "abnormal",
    "below_normal",
    "above_normal",
}


# ============================================================
# 7. OUTILS DE LECTURE AST
# ============================================================

def iter_app_python_files() -> list[Path]:
    """Retourne tous les fichiers Python de app/."""

    if not APP_DIR.exists():
        raise AssertionError(
            f"Le dossier applicatif est introuvable : {APP_DIR}"
        )

    files = sorted(
        path
        for path in APP_DIR.rglob("*.py")
        if "__pycache__" not in path.parts
    )

    if len(files) < MINIMUM_PYTHON_FILES:
        raise AssertionError(
            f"Aucun fichier Python applicatif trouvé dans {APP_DIR}"
        )

    return files


def parse_python_file(path: Path) -> ast.AST:
    """Analyse syntaxiquement un fichier Python."""

    source = path.read_text(encoding="utf-8")

    try:
        return ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        raise AssertionError(
            f"Erreur syntaxique dans {path}:{exc.lineno}: {exc.msg}"
        ) from exc


def get_relative_path(path: Path) -> str:
    """Retourne un chemin relatif à app/."""

    return str(path.relative_to(APP_DIR))


def is_disclaimer_assignment(node: ast.AST) -> bool:
    """Vérifie si un nœud représente l'affectation DISCLAIMER."""

    if isinstance(node, ast.Assign):
        return any(
            isinstance(target, ast.Name)
            and target.id == DISCLAIMER_NAME
            for target in node.targets
        )

    if isinstance(node, ast.AnnAssign):
        return (
            isinstance(node.target, ast.Name)
            and node.target.id == DISCLAIMER_NAME
        )

    return False


def get_docstring_nodes(tree: ast.AST) -> set[int]:
    """Identifie les docstrings pour ne pas les traiter comme du contenu métier."""

    ignored = set()

    for node in ast.walk(tree):
        if isinstance(
            node,
            (
                ast.Module,
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.ClassDef,
            ),
        ):
            body = getattr(node, "body", [])

            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                ignored.add(id(body[0].value))

    return ignored


def get_ignored_string_nodes(
    path: Path,
    tree: ast.AST,
) -> set[int]:
    """
    Retourne les chaînes explicitement exclues du contrôle.

    Les exclusions sont limitées :
    - docstrings ;
    - valeur de la constante DISCLAIMER dans schemas.py.

    Les autres chaînes restent analysées.
    """

    ignored = get_docstring_nodes(tree)

    if path.name == "schemas.py":
        for node in ast.walk(tree):
            if is_disclaimer_assignment(node):
                value = (
                    node.value
                    if isinstance(node, (ast.Assign, ast.AnnAssign))
                    else None
                )

                if value is not None:
                    for child in ast.walk(value):
                        ignored.add(id(child))

    return ignored


def iter_string_literals(
    path: Path,
    tree: ast.AST,
) -> Iterable[tuple[int, str]]:
    """Retourne les chaînes littérales hors zones explicitement exclues."""

    ignored = get_ignored_string_nodes(path, tree)

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in ignored
        ):
            yield node.lineno, node.value


def iter_defined_names(tree: ast.AST):
    """Retourne les noms définis par les affectations et fonctions."""

    for node in ast.walk(tree):

        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    yield node.lineno, target.id

        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                yield node.lineno, node.target.id

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node.lineno, node.name


# ============================================================
# 8. DÉTECTEUR 1 : ANCIENS SYMBOLES
# ============================================================

def find_forbidden_symbols(tree: ast.AST) -> list[str]:
    """Recherche les symboles hérités du moteur de règles."""

    violations = []

    for node in ast.walk(tree):

        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
        ):
            if node.name in FORBIDDEN_SYMBOLS:
                violations.append(
                    f"Ligne {node.lineno}: définition interdite '{node.name}'"
                )

        elif isinstance(node, ast.Name):
            if node.id in FORBIDDEN_SYMBOLS:
                violations.append(
                    f"Ligne {node.lineno}: identifiant interdit '{node.id}'"
                )

        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value in FORBIDDEN_SYMBOLS:
                violations.append(
                    f"Ligne {node.lineno}: chaîne interdite '{node.value}'"
                )

    return violations


# ============================================================
# 9. DÉTECTEUR 2 : CONSEILS ET PRESCRIPTIONS
# ============================================================

def find_forbidden_medical_content(
    path: Path,
    tree: ast.AST,
) -> list[str]:
    """Recherche les conseils et prescriptions dans les chaînes."""

    violations = []

    patterns = (
        FORBIDDEN_ADVICE_PATTERNS
        + FORBIDDEN_PRESCRIPTION_PATTERNS
    )

    for lineno, content in iter_string_literals(path, tree):

        normalized = content.lower()

        for pattern in patterns:
            if re.search(pattern, normalized, flags=re.IGNORECASE):
                violations.append(
                    f"Ligne {lineno}: contenu interdit "
                    f"'{pattern}' dans {content[:100]!r}"
                )

    return violations


# ============================================================
# 10. DÉTECTEUR 3 : NOMS DE BASES DE RÈGLES
# ============================================================

def find_forbidden_names(tree: ast.AST) -> list[str]:
    """Recherche les noms typiques d'un moteur de règles."""

    violations = []

    for lineno, name in iter_defined_names(tree):

        if FORBIDDEN_NAME_PATTERN.fullmatch(name):
            violations.append(
                f"Ligne {lineno}: nom de variable/fonction interdit '{name}'"
            )

    return violations


# ============================================================
# 11. DÉTECTEUR 4 : TABLES STATUT -> TEXTE
# ============================================================

def is_status_literal(node: ast.AST) -> bool:
    """Vérifie si une clé est un statut biologique interdit."""

    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.lower() in STATUS_VALUES
    )


def is_static_content_value(node: ast.AST) -> bool:
    """Vérifie si une valeur contient directement du contenu statique."""

    if isinstance(node, ast.Constant):
        return isinstance(node.value, str)

    if isinstance(node, (ast.List, ast.Tuple, ast.Set, ast.Dict)):
        return True

    return False


def find_status_to_text_tables(tree: ast.AST) -> list[str]:
    """
    Recherche les dictionnaires de type :

    {
        "below_reference": "Conseil prédéfini",
        "above_reference": ["Recommandation prédéfinie"]
    }

    Cette détection est volontairement ciblée.
    """

    violations = []

    for node in ast.walk(tree):

        if not isinstance(node, ast.Dict):
            continue

        for key, value in zip(node.keys, node.values):

            if key is None:
                continue

            if (
                is_status_literal(key)
                and is_static_content_value(value)
            ):
                violations.append(
                    f"Ligne {node.lineno}: table statut -> contenu détectée"
                )

    return violations


# ============================================================
# 12. DÉTECTEUR 5 : VÉRIFICATION DU DISCLAIMER
# ============================================================

def find_disclaimer_value(tree: ast.AST):
    """Récupère la valeur littérale de DISCLAIMER."""

    for node in ast.walk(tree):

        if not is_disclaimer_assignment(node):
            continue

        value = (
            node.value
            if isinstance(node, (ast.Assign, ast.AnnAssign))
            else None
        )

        if value is None:
            continue

        try:
            return ast.literal_eval(value)
        except (ValueError, TypeError):
            return None

    return None


def test_disclaimer_is_pedagogical():
    """
    Vérifie le disclaimer réel de app/schemas.py.

    Le texte doit préciser le caractère pédagogique
    et l'absence de diagnostic et de prescription.
    """

    schemas_path = APP_DIR / "schemas.py"

    assert schemas_path.exists(), (
        f"Fichier introuvable : {schemas_path}"
    )

    tree = parse_python_file(schemas_path)
    disclaimer = find_disclaimer_value(tree)

    assert isinstance(disclaimer, str), (
        "DISCLAIMER doit être une constante chaîne dans schemas.py."
    )

    normalized = " ".join(disclaimer.lower().split())

    assert "outil pédagogique" in normalized, (
        "Le disclaimer doit préciser que LabMind est un outil pédagogique."
    )

    assert (
        "ne constitue ni un diagnostic ni une prescription"
        in normalized
    ), (
        "Le disclaimer doit préciser l'absence de diagnostic "
        "et de prescription."
    )


# ============================================================
# 13. TEST PRINCIPAL : ANALYSE DE TOUS LES FICHIERS
# ============================================================

def test_no_expert_system_in_application():
    """Exécute tous les détecteurs sur le code applicatif."""

    all_violations = []

    for path in iter_app_python_files():

        relative_path = get_relative_path(path)
        tree = parse_python_file(path)

        detectors = [
            (
                "ANCIENS SYMBOLES",
                find_forbidden_symbols(tree),
            ),
            (
                "CONSEILS ET PRESCRIPTIONS",
                find_forbidden_medical_content(path, tree),
            ),
            (
                "NOMS DE BASES DE RÈGLES",
                find_forbidden_names(tree),
            ),
            (
                "TABLES STATUT -> TEXTE",
                find_status_to_text_tables(tree),
            ),
        ]

        for detector_name, violations in detectors:

            for violation in violations:
                all_violations.append(
                    f"[{detector_name}] {relative_path}: {violation}"
                )

    assert not all_violations, (
        "\n\n"
        "LABMIND : CONTENU DE TYPE SYSTÈME EXPERT DÉTECTÉ\n"
        "=================================================\n"
        + "\n".join(all_violations)
    )


# ============================================================
# 14. AUTO-TESTS DES DÉTECTEURS
# ============================================================

def test_detector_finds_legacy_symbols():
    """Vérifie que le détecteur trouve un ancien symbole."""

    source = """
TIPS = {}
"""

    tree = ast.parse(source)

    violations = find_forbidden_symbols(tree)

    assert violations, (
        "Le détecteur n'a pas identifié le symbole TIPS."
    )


def test_detector_finds_hardcoded_advice():
    """Vérifie la détection d'un conseil alimentaire."""

    source = """
MESSAGE = "Misez sur les lentilles et limitez les boissons sucrées."
"""

    tree = ast.parse(source)

    violations = find_forbidden_medical_content(
        Path("example.py"),
        tree,
    )

    assert violations, (
        "Le détecteur n'a pas identifié le conseil codé en dur."
    )


def test_detector_finds_prescription():
    """Vérifie la détection d'une prescription."""

    source = """
MESSAGE = "Prenez ce médicament chaque jour."
"""

    tree = ast.parse(source)

    violations = find_forbidden_medical_content(
        Path("example.py"),
        tree,
    )

    assert violations, (
        "Le détecteur n'a pas identifié la prescription."
    )


def test_detector_finds_status_to_text_table():
    """Vérifie la détection d'une table statut -> texte."""

    source = """
RESULTS = {
    "below_reference": ["Conseil prédéfini"],
    "above_reference": "Recommandation prédéfinie"
}
"""

    tree = ast.parse(source)

    violations = find_status_to_text_tables(tree)

    assert violations, (
        "Le détecteur n'a pas identifié la table statut -> texte."
    )


def test_detector_finds_forbidden_function_name():
    """Vérifie la détection d'une fonction typique d'un moteur de règles."""

    source = """
def tips_for(parameter):
    return None
"""

    tree = ast.parse(source)

    violations = find_forbidden_names(tree)

    assert violations, (
        "Le détecteur n'a pas identifié la fonction tips_for."
    )


def test_detector_does_not_flag_neutral_explanation():
    """
    Vérifie qu'une explication pédagogique neutre
    n'est pas automatiquement considérée comme un conseil.
    """

    source = """
MESSAGE = (
    "L'hémoglobine est une protéine présente "
    "dans les globules rouges."
)
"""

    tree = ast.parse(source)

    advice_violations = find_forbidden_medical_content(
        Path("example.py"),
        tree,
    )

    assert not advice_violations, (
        "Une explication pédagogique neutre a été signalée."
    )


def test_scanner_finds_application_files():
    """Vérifie que le scanner analyse réellement le dossier app/."""

    files = iter_app_python_files()

    assert len(files) >= MINIMUM_PYTHON_FILES, (
        "Le scanner ne trouve aucun fichier applicatif."
    )


# ============================================================
# 15. FIN
# ============================================================
