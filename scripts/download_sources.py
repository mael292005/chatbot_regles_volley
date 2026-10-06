"""Télécharge les documents officiels listés dans data/sources.yaml vers data/raw/.

Usage :
    python scripts/download_sources.py           # télécharge ce qui manque
    python scripts/download_sources.py --force   # retélécharge tout
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCES_FILE = ROOT / "data" / "sources.yaml"
RAW_DIR = ROOT / "data" / "raw"


def load_sources() -> list[dict]:
    with SOURCES_FILE.open(encoding="utf-8") as f:
        return yaml.safe_load(f)["sources"]


def download(url: str, dest: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "chatbot-regles-volley/0.1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read()
    if not data.startswith(b"%PDF"):
        raise ValueError(f"le fichier reçu depuis {url} n'est pas un PDF")
    dest.write_bytes(data)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="retélécharger même si le fichier existe")
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    errors = 0
    for source in load_sources():
        dest = RAW_DIR / source["fichier"]
        if dest.exists() and not args.force:
            print(f"[ok]   {source['fichier']} (déjà présent)")
            continue
        try:
            download(source["url"], dest)
            print(f"[dl]   {source['fichier']} ({dest.stat().st_size // 1024} Ko)")
        except Exception as exc:  # noqa: BLE001 - on veut continuer avec les autres sources
            errors += 1
            print(f"[err]  {source['fichier']} : {exc}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
