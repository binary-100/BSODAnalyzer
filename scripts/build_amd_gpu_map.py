"""Build bundled data/amd_gpu_product_urls.json from AMD download hub embedded JSON."""
from __future__ import annotations

import html as hm
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import driver_catalog as dc

_HUB_URL = dc._amd_drivers_download_url()
_PAIR_RE = re.compile(
    r'"url"\s*:\s*"(https://www\.amd\.com/en/support/downloads/drivers\.html/graphics/[^"]+\.html)"'
    r'[^}]{0,400}?"title"\s*:\s*"([^"]+)"',
    re.I,
)
_LEAF_RE = re.compile(
    r"https://www\.amd\.com/en/support/downloads/drivers\.html/graphics/[a-z0-9/_.-]+\.html",
    re.I,
)


def _clean_title(title: str) -> str:
    t = (title or "").replace("\ufffd", "")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _is_notebook_entry(url: str, title: str) -> bool:
    u = (url or "").lower()
    t = (title or "").lower()
    if "mobility" in u or "-m.html" in u or u.endswith("m.html"):
        return True
    return any(k in t for k in (" mobility", "mobile", " notebook", " laptop")) or bool(
        re.search(r"\b\d+m\b", t)
    )


def _leaf_depth(url: str) -> int:
    """Prefer deepest (most specific) product leaf over series pages."""
    path = url.split("/graphics/", 1)[-1] if "/graphics/" in url else url
    return path.count("/")


def extract_products_from_hub(html: str) -> list[dict]:
    text = hm.unescape(html or "")
    seen: set[str] = set()
    rows: list[dict] = []

    for url, title in _PAIR_RE.findall(text):
        url = url.split("&#")[0].split('"')[0].strip()
        if url in seen:
            continue
        seen.add(url)
        title = _clean_title(title)
        if not title:
            continue
        rows.append(
            {
                "url": url,
                "title": title,
                "notebook": _is_notebook_entry(url, title),
                "depth": _leaf_depth(url),
            }
        )

    # Fallback: leaf URLs without titles (series pages)
    for url in _LEAF_RE.findall(text):
        url = url.split("&#")[0].split('"')[0].strip()
        if url in seen:
            continue
        seen.add(url)
        slug = url.rsplit("/", 1)[-1].replace(".html", "").replace("-", " ")
        rows.append(
            {
                "url": url,
                "title": slug.title(),
                "notebook": _is_notebook_entry(url, slug),
                "depth": _leaf_depth(url),
            }
        )

    rows.sort(key=lambda r: (-r["depth"], r["title"].lower()))
    return rows


def main() -> None:
    ok, html = dc._amd_http_get_robust(_HUB_URL)
    if not ok or not html:
        raise SystemExit(f"Failed to fetch AMD hub: {_HUB_URL}")
    rows = extract_products_from_hub(html)
    out_path = Path(__file__).resolve().parents[1] / "data" / "amd_gpu_product_urls.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": _HUB_URL,
        "product_count": len(rows),
        "products": rows,
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {len(rows)} AMD graphics products -> {out_path}")
    for row in rows[:12]:
        nb = " [NB]" if row["notebook"] else ""
        print(f"  {row['title'][:48]:48} {nb}")


if __name__ == "__main__":
    main()
