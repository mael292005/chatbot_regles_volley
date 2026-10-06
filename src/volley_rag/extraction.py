"""Extraction du règlement officiel FIVB 2025-2028 (édition française) en articles structurés.

Le PDF a une mise en page très régulière, exploitée ici :

* colonne de gauche (x < 60) : numéro de l'article (``7``, ``7.4``, ``7.4.3.1``…) ;
* colonne centrale : le texte ; les passages en **gras** ne valent que pour les
  compétitions FIVB, mondiales et officielles ;
* marge de droite (x >= 320, police condensée) : renvois vers d'autres règles ou figures ;
* en-tête (y < 40) et pied de page (y > 565, avec le numéro de page imprimé).

Sorties (dans ``data/processed/``) :

* ``articles.jsonl``    : un objet par article numéroté, au niveau le plus fin ;
* ``sections.jsonl``    : unités de recherche, regroupées au niveau ``X.Y`` (ex. 7.4) ;
* ``definitions.jsonl`` : les définitions de la partie 3.

Usage ::

    python -m volley_rag.extraction
    python -m volley_rag.extraction --pdf data/raw/fivb_regles_2025_2028_fr.pdf --out data/processed
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PDF = ROOT / "data" / "raw" / "fivb_regles_2025_2028_fr.pdf"
DEFAULT_OUT = ROOT / "data" / "processed"

SOURCE_ID = "fivb_regles_2025_2028_fr"

# Bornes de la mise en page (en points PDF).
NUMBER_COL_MAX_X = 60
MARGIN_COL_MIN_X = 320
HEADER_MAX_Y = 40
FOOTER_MIN_Y = 565
BODY_FONT_SIZE = 7.8
SUPERSCRIPT_MAX_SIZE = 6.0
LINE_TOLERANCE = 3.0

ARTICLE_NUMBER = re.compile(r"^\d{1,2}(\.\d{1,2}){0,4}$")
FIVB_MARK = "[Compétitions FIVB, mondiales et officielles uniquement]"


@dataclass
class Article:
    id: str
    niveau: int
    regle: str
    section: str
    parent: str | None
    titre: str | None = None
    paragraphes: list[dict] = field(default_factory=list)  # {"texte": str, "fivb": bool}
    renvois: list[str] = field(default_factory=list)
    page_pdf: int = 0
    page_imprimee: int | None = None
    chapitre: str | None = None
    partie: str | None = None

    @property
    def texte(self) -> str:
        return render_paragraphs(self.paragraphes)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["texte"] = self.texte
        data["source"] = SOURCE_ID
        return data


@dataclass
class Line:
    y: float
    x: float
    text: str
    bold: bool
    roman: bool
    size: float


# --------------------------------------------------------------------------- utilitaires


def render_paragraphs(paragraphs: list[dict]) -> str:
    out = []
    for p in paragraphs:
        out.append(f"{FIVB_MARK} {p['texte']}" if p["fivb"] else p["texte"])
    return "\n".join(out)


def parent_of(article_id: str) -> str | None:
    return article_id.rsplit(".", 1)[0] if "." in article_id else None


def section_of(article_id: str) -> str:
    parts = article_id.split(".")
    return ".".join(parts[:2])


def join_text(previous: str, nxt: str) -> str:
    if not previous:
        return nxt
    if previous.endswith("-") and not previous.endswith(" -"):
        return previous + nxt  # mot coupé en fin de ligne
    return f"{previous} {nxt}"


def join_margin_lines(lines: list[str]) -> str:
    """Recolle les lignes de marge d'un même article (« Fig.11 (6a, » + « 6b, 7) »)."""
    out = ""
    for line in lines:
        line = line.replace("\xa0", " ").strip()
        if not out:
            out = line
        elif out.count("(") > out.count(")") or out.endswith(",") or line.startswith("("):
            out = f"{out} {line}"
        else:
            out = f"{out}, {line}"
    return out


def split_refs(raw: str) -> list[str]:
    """Découpe « 1.1, Fig.11 (6a, 6b), 23.3.2.3d, e » en renvois distincts."""
    chunks, depth, current = [], 0, ""
    for char in raw.replace(";", ","):
        depth += char == "("
        depth -= char == ")"
        if char == "," and depth == 0:
            chunks.append(current)
            current = ""
        else:
            current += char
    chunks.append(current)

    refs: list[str] = []
    for chunk in chunks:
        chunk = " ".join(chunk.split()).rstrip(".")
        if not chunk:
            continue
        # « 23.3.2.3d, e » : la lettre seule complète le renvoi précédent.
        if re.fullmatch(r"[a-z]", chunk) and refs and re.search(r"\d[a-z]$", refs[-1]):
            refs.append(refs[-1][:-1] + chunk)
            continue
        refs.append(chunk)
    return refs


def printed_page_number(page: pymupdf.Page) -> int | None:
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                text = span["text"].strip()
                if span["bbox"][1] > FOOTER_MIN_Y and text.isdigit():
                    return int(text)
    return None


# --------------------------------------------------------------------------- lecture des pages


def read_page(page: pymupdf.Page) -> tuple[list[tuple[float, str | None, Line]], list[tuple[float, str]]]:
    """Retourne (lignes du corps avec numéro éventuel, renvois de marge) pour une page.

    Chaque ligne du corps est ``(y, numero_ou_None, Line)``.
    """
    body_spans = []
    margin = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                text = span["text"].strip()
                if not text:
                    continue
                x0, y0 = span["bbox"][0], span["bbox"][1]
                if y0 < HEADER_MAX_Y or y0 > FOOTER_MIN_Y:
                    continue
                if x0 >= MARGIN_COL_MIN_X:
                    if "Voir Règles" not in text:
                        margin.append((y0, text))
                    continue
                body_spans.append(span)

    # Regroupe les fragments par ligne (même ordonnée, à la tolérance près).
    body_spans.sort(key=lambda s: (s["bbox"][1], s["bbox"][0]))
    rows: list[list[dict]] = []
    for span in body_spans:
        y = span["bbox"][1]
        if rows and abs(rows[-1][0]["bbox"][1] - y) <= LINE_TOLERANCE and span["size"] <= BODY_FONT_SIZE + 0.5:
            rows[-1].append(span)
        else:
            rows.append([span])

    lines = []
    for row in rows:
        row.sort(key=lambda s: s["bbox"][0])
        number = None
        first = row[0]
        if (
            first["bbox"][0] < NUMBER_COL_MAX_X
            and ARTICLE_NUMBER.match(first["text"].strip())
            and len(row) > 1
        ):
            number = first["text"].strip()
            row = row[1:]
        text = ""
        for span in row:
            piece = span["text"].strip()
            if span["size"] < SUPERSCRIPT_MAX_SIZE:
                text += piece  # exposant : « 5ème »
            else:
                text = join_text(text, piece)
        main = [s for s in row if s["size"] >= SUPERSCRIPT_MAX_SIZE] or row
        lines.append(
            (
                row[0]["bbox"][1],
                number,
                Line(
                    y=row[0]["bbox"][1],
                    x=row[0]["bbox"][0],
                    text=text.strip(),
                    bold=all("Bold" in s["font"] for s in main),
                    roman=all("Roman" in s["font"] for s in main),
                    size=max(s["size"] for s in main),
                ),
            )
        )
    margin.sort()
    return lines, margin


# --------------------------------------------------------------------------- articles


def is_heading(article_id: str, line: Line) -> bool:
    """Titre de règle (« 7 STRUCTURE DU JEU ») ou de section (« 7.4 POSITIONS »)."""
    letters = [c for c in line.text if c.isalpha()]
    upper = bool(letters) and sum(c.isupper() for c in letters) / len(letters) > 0.8
    return upper and (line.bold or line.roman) and article_id.count(".") <= 1


def extract_articles(pdf_path: Path) -> list[Article]:
    doc = pymupdf.open(pdf_path)
    articles: list[Article] = []
    by_id: dict[str, Article] = {}
    margin_lines: dict[str, list[str]] = {}
    current: Article | None = None
    chapitre = None
    partie = None
    pending_chapter_number = None

    first_rule_page = next(i for i in range(doc.page_count) if "Chapitre 1" in doc[i].get_text())
    last_rule_page = max(i for i in range(doc.page_count) if "SECTION 2" in doc[i].get_text()[:200])

    for index in range(first_rule_page, last_rule_page + 1):
        page = doc[index]
        header = page.get_text()[:200]
        if "SECTION 2" in header:
            partie = "Section 2 : les arbitres, leurs responsabilités et les gestes officiels"
        elif partie is None:
            partie = "Section 1 : le jeu"
        printed = printed_page_number(page)
        lines, margin = read_page(page)

        starts_on_page: list[tuple[float, Article]] = []
        paragraph_open = False
        previous_y = None

        for y, number, line in lines:
            # Titres de chapitre (corps plus grand que le texte courant).
            if line.size > BODY_FONT_SIZE + 1:
                if line.text.lower().startswith("chapitre"):
                    pending_chapter_number = line.text
                else:
                    chapitre = f"{pending_chapter_number} – {line.text.capitalize()}" if pending_chapter_number else line.text
                    pending_chapter_number = None
                continue
            if line.text in {"SOIT", "OU"} and current is not None:
                current.paragraphes.append({"texte": line.text, "fivb": False})
                paragraph_open = False
                previous_y = y
                continue

            if number is not None:
                level = number.count(".") + 1
                current = Article(
                    id=number,
                    niveau=level,
                    regle=number.split(".")[0],
                    section=section_of(number),
                    parent=parent_of(number),
                    page_pdf=index + 1,
                    page_imprimee=printed,
                    chapitre=chapitre,
                    partie=partie,
                )
                if number in by_id:
                    raise ValueError(f"article {number} trouvé deux fois (page PDF {index + 1})")
                by_id[number] = current
                articles.append(current)
                starts_on_page.append((y, current))
                if is_heading(number, line):
                    current.titre = line.text
                    paragraph_open = False
                else:
                    current.paragraphes.append({"texte": line.text, "fivb": line.bold})
                    paragraph_open = True
                previous_y = y
                continue

            if current is None:
                continue
            # Nouvelle ligne de texte : suite du paragraphe ou nouveau paragraphe ?
            gap = (y - previous_y) if previous_y is not None else 99
            same_paragraph = (
                paragraph_open
                and gap < 12
                and current.paragraphes
                and current.paragraphes[-1]["fivb"] == line.bold
            )
            if same_paragraph:
                last = current.paragraphes[-1]
                last["texte"] = join_text(last["texte"], line.text)
            else:
                current.paragraphes.append({"texte": line.text, "fivb": line.bold})
            paragraph_open = True
            previous_y = y

        # Renvois de marge : rattachés au dernier article commencé au-dessus d'eux
        # (ou, en haut de page, à l'article qui continue depuis la page précédente).
        if starts_on_page:
            first_index = articles.index(starts_on_page[0][1])
            carry = articles[first_index - 1] if first_index > 0 else None
        else:
            carry = current
        for y, raw in margin:
            target = carry
            for start_y, article in starts_on_page:
                if start_y <= y + LINE_TOLERANCE:
                    target = article
            if target is not None:
                margin_lines.setdefault(target.id, []).append(raw)

    for article in articles:
        refs = split_refs(join_margin_lines(margin_lines.get(article.id, [])))
        article.renvois = list(dict.fromkeys(refs))
    return articles


# --------------------------------------------------------------------------- sections


def build_sections(articles: list[Article]) -> list[dict]:
    """Regroupe les articles au niveau X.Y : ce sont les unités indexées pour la recherche."""
    titles = {a.id: a.titre for a in articles if a.titre}
    groups: dict[str, list[Article]] = {}
    for article in articles:
        groups.setdefault(article.section, []).append(article)

    sections = []
    for section_id, members in groups.items():
        regle = members[0].regle
        rule_title = titles.get(regle)
        section_title = titles.get(section_id) if section_id != regle else None
        heading = f"Règle {section_id}"
        if section_title:
            heading += f" – {section_title}"
            if rule_title:
                heading += f" (règle {regle} : {rule_title})"
        elif rule_title:
            heading += f" – {rule_title}"

        body_lines = []
        for article in members:
            text = article.texte
            if not text:
                continue
            prefix = "" if article.id == section_id else f"{article.id} "
            body_lines.append(prefix + text)

        if not body_lines:
            continue  # simple titre de règle (« 7 STRUCTURE DU JEU ») sans texte propre
        renvois = list(dict.fromkeys(r for a in members for r in a.renvois))
        sections.append(
            {
                "id": section_id,
                "regle": regle,
                "titre_regle": rule_title,
                "titre_section": section_title,
                "chapitre": members[0].chapitre,
                "partie": members[0].partie,
                "articles": [a.id for a in members],
                "pages_imprimees": sorted({a.page_imprimee for a in members if a.page_imprimee}),
                "pages_pdf": sorted({a.page_pdf for a in members}),
                "contient_passages_fivb": any(p["fivb"] for a in members for p in a.paragraphes),
                "renvois": renvois,
                "texte": heading + "\n" + "\n".join(body_lines),
                "source": SOURCE_ID,
            }
        )
    return sections


# --------------------------------------------------------------------------- définitions


def extract_definitions(pdf_path: Path) -> list[dict]:
    doc = pymupdf.open(pdf_path)
    pages = [i for i in range(doc.page_count) if "PARTIE 3" in doc[i].get_text()[:200]]
    definitions: list[dict] = []
    for index in pages:
        page = doc[index]
        printed = printed_page_number(page)
        lines, _ = read_page(page)
        for _, number, line in lines:
            text = (f"{number} {line.text}" if number else line.text).strip()
            letters = [c for c in text if c.isalpha()]
            is_term = line.roman and letters and sum(c.isupper() for c in letters) / len(letters) > 0.8
            if is_term and text not in {"DEFINITIONS", "DÉFINITIONS", "PARTIE 3"}:
                definitions.append(
                    {"terme": text, "texte": "", "page_pdf": index + 1, "page_imprimee": printed, "source": SOURCE_ID}
                )
            elif definitions:
                d = definitions[-1]
                d["texte"] = join_text(d["texte"], text)
    return [d for d in definitions if d["texte"]]


# --------------------------------------------------------------------------- CLI


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Extrait le règlement FIVB en articles structurés.")
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    articles = extract_articles(args.pdf)
    sections = build_sections(articles)
    definitions = extract_definitions(args.pdf)

    write_jsonl(args.out / "articles.jsonl", [a.to_dict() for a in articles])
    write_jsonl(args.out / "sections.jsonl", sections)
    write_jsonl(args.out / "definitions.jsonl", definitions)

    rules = sorted({a.regle for a in articles}, key=int)
    print(f"{len(articles)} articles, {len(sections)} sections, {len(definitions)} définitions")
    print(f"règles trouvées : {rules[0]} à {rules[-1]} ({len(rules)} règles)")
    print(f"écrit dans {args.out}")


if __name__ == "__main__":
    main()
