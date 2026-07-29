from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGES = (ROOT / "index.html", ROOT / "static" / "index.html", ROOT / "404.html")


def main() -> None:
    missing: list[tuple[str, str]] = []
    duplicate_ids: dict[str, list[str]] = {}
    for page in PAGES:
        text = page.read_text(encoding="utf-8")
        ids = re.findall(r"""\bid=["']([^"']+)""", text)
        duplicate_ids[page.name] = sorted({item for item in ids if ids.count(item) > 1})
        for reference in re.findall(r"""(?:src|href)=["']([^"'#?]+)""", text):
            if reference.startswith(("http:", "https:", "data:", "mailto:")):
                continue
            clean_reference = reference.removeprefix("./")
            # Both index files are served from the application root.  The copy
            # under static/ is a backend template, not a public /static/ page.
            base = ROOT if page.name == "index.html" else page.parent
            target = (base / clean_reference).resolve()
            if not target.exists():
                missing.append((page.name, repr(reference), str(target)))

    css = "".join(path.read_text(encoding="utf-8") for path in (ROOT / "static").glob("*.css"))
    assert css.count("{") == css.count("}"), "Las llaves CSS no están equilibradas."
    assert not missing, f"Recursos ausentes: {missing}"
    assert not any(duplicate_ids.values()), f"IDs duplicados: {duplicate_ids}"
    json.loads((ROOT / "static" / "manifest.webmanifest").read_text(encoding="utf-8"))

    forbidden_parts = {"__pycache__", ".pytest_cache", ".venv", "node_modules"}
    forbidden_suffixes = (".db", ".db-wal", ".db-shm")
    forbidden = [
        str(path.relative_to(ROOT))
        for path in ROOT.rglob("*")
        if path.is_file()
        and (any(part in forbidden_parts for part in path.parts) or path.name.endswith(forbidden_suffixes))
    ]
    assert not forbidden, f"Archivos temporales: {forbidden}"

    secret_patterns = (
        re.compile(r"gsk_[A-Za-z0-9]{12,}"),
        re.compile(r"sk-proj-[A-Za-z0-9_-]{12,}"),
        re.compile(r"AIza[0-9A-Za-z_-]{20,}"),
    )
    secret_hits: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() in {".png", ".webp", ".zip"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if any(pattern.search(text) for pattern in secret_patterns):
            secret_hits.append(str(path.relative_to(ROOT)))
    assert not secret_hits, f"Posibles secretos: {secret_hits}"
    print("ASSETS_IDS_CSS_MANIFEST_SECRETS_OK")


if __name__ == "__main__":
    main()

