"""Tests de l'extraction du règlement.

Les tests qui lisent le PDF officiel sont ignorés s'il n'a pas été téléchargé
(``python scripts/download_sources.py``), puisqu'il n'est pas versionné.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from volley_rag.extraction import (
    DEFAULT_PDF,
    build_sections,
    extract_articles,
    extract_definitions,
    join_margin_lines,
    split_refs,
)

ROOT = Path(__file__).resolve().parents[1]

needs_pdf = pytest.mark.skipif(not DEFAULT_PDF.exists(), reason="PDF officiel absent de data/raw/")


# --------------------------------------------------------------------------- renvois (sans PDF)


def test_split_refs_simple():
    assert split_refs("6.2, 6.3, 7.3.1") == ["6.2", "6.3", "7.3.1"]


def test_split_refs_keeps_parentheses_together():
    assert split_refs("Fig.9, Fig.11 (6a, 6b, 7, 8, 25)") == ["Fig.9", "Fig.11 (6a, 6b, 7, 8, 25)"]


def test_split_refs_expands_letter_suffix():
    assert split_refs("13.3.6, 23.3.2.3d, e") == ["13.3.6", "23.3.2.3d", "23.3.2.3e"]


def test_join_margin_lines_rebuilds_wrapped_figure():
    assert join_margin_lines(["Fig.5a, Fig.11", "(22)"]) == "Fig.5a, Fig.11 (22)"
    assert join_margin_lines(["1.1, Fig.1a,", "Fig.1b"]) == "1.1, Fig.1a, Fig.1b"
    assert join_margin_lines(["7.6.1", "8.1"]) == "7.6.1, 8.1"


# --------------------------------------------------------------------------- extraction (avec PDF)


@pytest.fixture(scope="module")
def articles():
    return {a.id: a for a in extract_articles(DEFAULT_PDF)}


@needs_pdf
def test_all_30_rules_are_present(articles):
    assert {a.regle for a in articles.values()} == {str(i) for i in range(1, 31)}


@needs_pdf
def test_rule_titles(articles):
    assert articles["7"].titre == "STRUCTURE DU JEU"
    assert articles["7.4"].titre == "POSITIONS"
    assert articles["19"].titre == "LE JOUEUR LIBÉRO"


@needs_pdf
def test_serving_team_free_position_2025(articles):
    texte = articles["7.4"].texte
    assert "équipe en réception doivent être dans l’ordre de rotation" in texte
    assert "équipe au service sont libres d’occuper n’importe quelle position" in texte


@needs_pdf
def test_superscript_is_glued(articles):
    assert "le 5ème set décisif" in articles["6.3.2"].texte


@needs_pdf
def test_page_numbers(articles):
    assert articles["7.4"].page_imprimee == 25
    assert articles["1"].page_imprimee == 12


@needs_pdf
def test_margin_refs(articles):
    assert articles["6.4.1"].renvois == ["6.2", "6.3"]
    assert articles["1"].renvois == ["1.1", "Fig.1a", "Fig.1b"]


@needs_pdf
def test_fivb_only_passages_are_flagged(articles):
    flagged = [p for p in articles["1.1"].paragraphes if p["fivb"]]
    assert flagged and "Pour les compétitions FIVB" in flagged[0]["texte"]
    assert not any(p["fivb"] for p in articles["11.3.1"].paragraphes)


@needs_pdf
def test_chapters(articles):
    assert articles["19.3.1.3"].chapitre == "Chapitre 6 – Le joueur libéro"


@needs_pdf
def test_sections_are_self_contained(articles):
    sections = {s["id"]: s for s in build_sections(list(articles.values()))}
    s = sections["11.3"]
    assert s["texte"].startswith("Règle 11.3 – CONTACT AVEC LE FILET (règle 11 : JOUEUR AU FILET)")
    assert "11.3.2" in s["texte"] and "à l’extérieur des antennes" in s["texte"]
    assert s["articles"] == ["11.3", "11.3.1", "11.3.2", "11.3.3"]


@needs_pdf
def test_definitions():
    terms = {d["terme"] for d in extract_definitions(DEFAULT_PDF)}
    assert "ESPACE DE PASSAGE" in terms


@needs_pdf
def test_eval_set_only_cites_existing_rules(articles):
    """Chaque numéro de règle du jeu de test doit exister dans le règlement extrait."""
    questions = yaml.safe_load((ROOT / "eval" / "questions.yaml").read_text(encoding="utf-8"))["questions"]
    missing = {
        (q["id"], regle)
        for q in questions
        for regle in q["regles"]
        if regle not in articles
    }
    assert not missing, f"règles citées mais introuvables : {sorted(missing)}"
