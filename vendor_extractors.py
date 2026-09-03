"""Data-driven version extraction from vendor download pages.

Extractors answer one question: given fetched page HTML / JSON text, what
version string(s) are on it? Comparison logic, URL building, and dual-scheme
mapping stay in code (driver_catalog).

Schema (locked):
  * mode: ``scalar`` (first validating version wins) | ``rows`` (list of title/version)
  * rule kinds: regex | json_next_data | json_ld | link_filename | rows_pair
  * transforms: strip | unescape_slashes | lower
  * validation: parse_driver_version with min_parts (default 2)
  * safety: input size cap, pattern length cap, regex wall-clock timeout, fail-open

Merge (used by get_extractor in a later bite): manifest rules are PREPENDED to
bundled defaults so a bad override can never wipe known-good extraction.
"""
from __future__ import annotations

import json
import re
import threading
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Safety limits (ReDoS / runaway guards)
# ---------------------------------------------------------------------------
MAX_INPUT_CHARS = 2_000_000
MAX_PATTERN_CHARS = 400
MAX_PATH_CHARS = 200
MAX_RULES_PER_EXTRACTOR = 40
MAX_LINK_CONTAINS = 16
MAX_LINK_CONTAINS_ITEM_CHARS = 64
REGEX_TIMEOUT_SEC = 0.25
ALLOWED_FLAGS = frozenset("ism")
ALLOWED_TRANSFORMS = frozenset({"strip", "unescape_slashes", "lower"})
ALLOWED_KINDS = frozenset(
    {"regex", "json_next_data", "json_ld", "link_filename", "rows_pair"}
)
ALLOWED_MODES = frozenset({"scalar", "rows"})
ALLOWED_PICK = frozenset({"first", "max"})
DEFAULT_MIN_PARTS = 2
# Soft ReDoS smell: nested quantified groups like (a+)+ / (a|a)* — timeout is the
# hard backstop; this rejects the classic shapes before they reach the engine.
_NESTED_QUANT_RE = re.compile(r"\([^()]*[+*][^()]*\)[+*{]")

# Bundled defaults — migrated from the hardcoded scrapers in driver_catalog.
# Realtek / NVIDIA stay API-driven (not HTML extractors) and are intentionally absent.
BUNDLED_EXTRACTORS: dict[str, dict[str, dict]] = {
    "amd": {
        "graphics": {
            "mode": "scalar",
            "version": [
                {
                    "kind": "json_next_data",
                    "pattern": r"(\d+\.\d+\.\d+\.\d+)",
                    "pick": "max",
                },
                {
                    "kind": "regex",
                    "pattern": r"driverPackageVersion.*?(\d+\.\d+\.\d+(?:\.\d+)?)",
                    "flags": "is",
                },
                {
                    "kind": "regex",
                    "pattern": r"Radeon.*?Software.*?(\d+\.\d+\.\d+(?:\.\d+)?)",
                    "flags": "is",
                },
                {
                    "kind": "regex",
                    "pattern": r"Adrenalin.*?(\d+\.\d+\.\d+(?:\.\d+)?)",
                    "flags": "is",
                },
                {
                    "kind": "regex",
                    "pattern": r"Version\s*(\d+\.\d+\.\d+(?:\.\d+)?)",
                    "flags": "i",
                },
                {
                    "kind": "regex",
                    "pattern": r'"version"\s*:\s*"([\d.]+)"',
                    "flags": "i",
                },
            ],
        },
        "chipset": {
            "mode": "scalar",
            "version": [
                {
                    "kind": "regex",
                    "pattern": r"chipset[^\"]{0,160}(\d+\.\d+\.\d+\.\d+)",
                    "flags": "i",
                    "pick": "max",
                },
                {
                    "kind": "regex",
                    "pattern": r"ryzen[^\"]{0,120}(\d+\.\d+\.\d+\.\d+)",
                    "flags": "i",
                    "pick": "max",
                },
                {
                    "kind": "regex",
                    "pattern": r"\b([67]\.\d+\.\d+\.\d+)\b",
                    "pick": "max",
                },
                {
                    "kind": "regex",
                    "pattern": r"Chipset.*?Driver.*?(\d+\.\d+\.\d+(?:\.\d+)?)",
                    "flags": "is",
                },
                {
                    "kind": "regex",
                    "pattern": r"AMD.?Ryzen.?Chipset.*?(\d+\.\d+\.\d+(?:\.\d+)?)",
                    "flags": "is",
                },
            ],
        },
    },
    "intel": {
        "graphics": {
            "mode": "scalar",
            "version": [
                {"kind": "regex", "pattern": r"(\d{2}\.\d+\.\d+\.\d+)\s*\(Latest\)", "flags": "i"},
                {
                    "kind": "regex",
                    "pattern": r"Version\s*[\s\S]{0,120}?(\d+\.\d+\.\d+(?:\.\d+)?)\s*\(Latest\)",
                    "flags": "i",
                },
                {
                    "kind": "regex",
                    "pattern": r"Version\s*:?\s*</[^>]+>\s*<[^>]+>\s*([\d.]+)",
                    "flags": "i",
                },
                {"kind": "regex", "pattern": r'"version"\s*:\s*"([\d.]+)"', "flags": "i"},
                {
                    "kind": "regex",
                    "pattern": r"Version\s+([\d]+\.[\d]+\.[\d]+(?:\.[\d]+)?)",
                    "flags": "i",
                },
                {
                    "kind": "json_next_data",
                    "pattern": (
                        r'"(?:version|driverVersion|fileVersion|packageVersion)"'
                        r'\s*:\s*"(3[012]\.[\d.]+)"'
                    ),
                    "flags": "i",
                    "pick": "max",
                },
                {
                    "kind": "json_next_data",
                    "pattern": r"(32\.\d+\.\d+\.\d+|31\.\d+\.\d+\.\d+)",
                    "pick": "max",
                },
                {
                    "kind": "regex",
                    "pattern": r"32\.0\.\d+\.\d+",
                    "group": 0,
                    "pick": "max",
                },
                {
                    "kind": "regex",
                    "pattern": r"31\.0\.\d+\.\d+",
                    "group": 0,
                    "pick": "max",
                },
            ],
            "date": [
                {"kind": "regex", "pattern": r"Date\s+(\d{1,2}/\d{1,2}/\d{4})", "flags": "i"},
            ],
        },
        "wifi": {
            "mode": "scalar",
            "version": [
                {"kind": "regex", "pattern": r"(\d{2}\.\d+\.\d+\.\d+)\s*\(Latest\)", "flags": "i"},
                {
                    "kind": "regex",
                    "pattern": r"Version\s*[\s\S]{0,120}?(\d+\.\d+\.\d+(?:\.\d+)?)\s*\(Latest\)",
                    "flags": "i",
                },
                {"kind": "regex", "pattern": r'"version"\s*:\s*"([\d.]+)"', "flags": "i"},
                {
                    "kind": "json_next_data",
                    "pattern": r"(24\.\d+\.\d+\.\d+|23\.\d+\.\d+\.\d+|22\.\d+\.\d+\.\d+)",
                    "pick": "max",
                },
                {
                    "kind": "regex",
                    "pattern": r"24\.\d+\.\d+\.\d+",
                    "group": 0,
                    "pick": "max",
                },
                {
                    "kind": "regex",
                    "pattern": r"23\.\d+\.\d+\.\d+",
                    "group": 0,
                    "pick": "max",
                },
                {
                    "kind": "regex",
                    "pattern": r"22\.\d+\.\d+\.\d+",
                    "group": 0,
                    "pick": "max",
                },
            ],
            "date": [
                {"kind": "regex", "pattern": r"Date\s+(\d{1,2}/\d{1,2}/\d{4})", "flags": "i"},
            ],
        },
        "chipset": {
            "mode": "scalar",
            "version": [
                {"kind": "regex", "pattern": r"(\d{2}\.\d+\.\d+\.\d+)\s*\(Latest\)", "flags": "i"},
                {
                    "kind": "regex",
                    "pattern": r"Version\s*[\s\S]{0,120}?(\d+\.\d+\.\d+(?:\.\d+)?)\s*\(Latest\)",
                    "flags": "i",
                },
                {"kind": "regex", "pattern": r'"version"\s*:\s*"([\d.]+)"', "flags": "i"},
                {
                    "kind": "json_next_data",
                    "pattern": r"(10\.\d+\.\d+\.\d+)",
                    "pick": "max",
                },
                {
                    "kind": "regex",
                    "pattern": r"10\.\d+\.\d+\.\d+",
                    "group": 0,
                    "pick": "max",
                },
                {
                    "kind": "regex",
                    "pattern": r"10\.\d+\.\d+",
                    "group": 0,
                    "pick": "max",
                },
            ],
            "date": [
                {"kind": "regex", "pattern": r"Date\s+(\d{1,2}/\d{1,2}/\d{4})", "flags": "i"},
            ],
        },
        # Killer Performance Suite pages reuse the Intel download-detail layout.
        "*": {
            "mode": "scalar",
            "version": [
                {"kind": "regex", "pattern": r"(\d{2}\.\d+\.\d+\.\d+)\s*\(Latest\)", "flags": "i"},
                {
                    "kind": "regex",
                    "pattern": r"Version\s*[\s\S]{0,120}?(\d+\.\d+\.\d+(?:\.\d+)?)\s*\(Latest\)",
                    "flags": "i",
                },
                {
                    "kind": "regex",
                    "pattern": r"Version\s*:?\s*</[^>]+>\s*<[^>]+>\s*([\d.]+)",
                    "flags": "i",
                },
                {"kind": "regex", "pattern": r'"version"\s*:\s*"([\d.]+)"', "flags": "i"},
                {
                    "kind": "regex",
                    "pattern": r"Version\s+([\d]+\.[\d]+\.[\d]+(?:\.[\d]+)?)",
                    "flags": "i",
                },
                {
                    "kind": "regex",
                    "pattern": r"\d+\.\d+\.\d+\.\d+",
                    "group": 0,
                    "pick": "max",
                },
            ],
            "date": [
                {"kind": "regex", "pattern": r"Date\s+(\d{1,2}/\d{1,2}/\d{4})", "flags": "i"},
            ],
        },
    },
    "gigabyte": {
        "*": {
            "mode": "rows",
            "version": [
                {
                    "kind": "rows_pair",
                    "pattern": (
                        r'"fileTitle"\s*:\s*"(?P<title>(?:[^"\\]|\\.)+)"\s*,\s*'
                        r'"fileVersion"\s*:\s*"(?P<version>[^"]+)"'
                    ),
                    "transforms_title": ["unescape_slashes", "strip"],
                    "transforms_version": ["strip"],
                },
            ],
        },
    },
    "marvell": {
        "*": {
            "mode": "rows",
            "version": [
                {
                    "kind": "rows_pair",
                    "pattern": (
                        r'"title"\s*:\s*"(?P<title>[^"]{4,120})"[^}]{0,300}?'
                        r'"version"\s*:\s*"(?P<version>[^"]+)"'
                    ),
                    "flags": "is",
                    "transforms_title": ["strip"],
                    "transforms_version": ["strip"],
                },
                {
                    "kind": "rows_pair",
                    "pattern": (
                        r"(?P<title>[\w\s/-]{4,80}"
                        r"(?:Yukon|Avastar|NVMe|RAID|Ethernet)"
                        r"[\w\s/-]{0,40})\s+"
                        r"(?P<version>\d+\.\d+\.\d+(?:\.\d+)?)"
                    ),
                    "flags": "i",
                    "transforms_title": ["strip"],
                    "transforms_version": ["strip"],
                },
            ],
        },
    },
    "mediatek": {
        "*": {
            "mode": "rows",
            "version": [
                {
                    "kind": "link_filename",
                    "link_pattern": r"https://[^\"'\s<>]+\.(?:exe|zip|cab|msi)",
                    "version_pattern": r"(\d+\.\d+\.\d+(?:\.\d+)?)",
                    "link_contains": ["cloudfront", "mediatek", "driver"],
                    "flags": "i",
                },
            ],
        },
    },
}


# ---------------------------------------------------------------------------
# Version validation (lazy import to avoid circular deps at module load)
# ---------------------------------------------------------------------------
def _parse_version(version: str, *, allow_bare: bool = False) -> tuple[int, ...]:
    """Parse a version string into numeric segments.

    Uses ``driver_catalog.parse_driver_version`` (requires ≥1 dotted segment).
    When ``allow_bare`` is True (min_parts=1 overrides), also accepts a lone
    integer so rare vendor tags can opt in without weakening the default.
    """
    s = (version or "").strip()
    if not s:
        return ()
    try:
        from driver_catalog import parse_driver_version

        parts = parse_driver_version(s)
        if parts:
            return parts
    except ImportError:
        m = re.search(r"(\d+(?:\.\d+){1,6})", s)
        if m:
            parts = []
            for p in m.group(1).split("."):
                try:
                    parts.append(int(p))
                except ValueError:
                    break
            if parts:
                return tuple(parts)
    if allow_bare:
        m = re.fullmatch(r"(\d{1,6})", s)
        if m:
            return (int(m.group(1)),)
    return ()


def is_version_shaped(candidate: str, *, min_parts: int = DEFAULT_MIN_PARTS) -> bool:
    """True when ``candidate`` parses to at least ``min_parts`` numeric segments."""
    need = max(1, int(min_parts))
    parts = _parse_version(candidate, allow_bare=(need <= 1))
    return bool(parts) and len(parts) >= need


def _version_sort_key(candidate: str) -> tuple[int, ...]:
    return _parse_version(candidate) or ()


# ---------------------------------------------------------------------------
# Transforms & pattern helpers
# ---------------------------------------------------------------------------
def apply_transforms(value: str, transforms: list[str] | None) -> str:
    out = value if value is not None else ""
    for name in transforms or []:
        if name == "strip":
            out = out.strip()
        elif name == "unescape_slashes":
            out = out.replace("\\/", "/")
        elif name == "lower":
            out = out.lower()
        # Unknown transforms are ignored (fail-open).
    return out


def _compile_flags(flags_str: str | None) -> int:
    flags = 0
    for ch in (flags_str or "i"):
        if ch not in ALLOWED_FLAGS:
            continue
        if ch == "i":
            flags |= re.I
        elif ch == "s":
            flags |= re.S
        elif ch == "m":
            flags |= re.M
    return flags


def _fill_pattern(pattern: str, params: dict[str, str] | None) -> str:
    """Substitute ``{name}`` placeholders; values are re.escaped for safety."""
    if not params:
        return pattern
    out = pattern
    for key, val in params.items():
        out = out.replace("{" + str(key) + "}", re.escape(str(val)))
    return out


def _pattern_ok(pattern: str) -> bool:
    if not pattern or len(pattern) > MAX_PATTERN_CHARS:
        return False
    if pattern.count("(") > 25:
        return False
    if _NESTED_QUANT_RE.search(pattern):
        return False
    return True


def sanitize_rule(rule: Any) -> dict | None:
    """Return a cleaned rule dict, or ``None`` if the rule is unusable/unsafe.

    Used at the manifest boundary (load/save/merge) so corrupt or hostile
    overrides never reach disk or runtime merge. Eval already fail-opens per rule;
    this is the stricter gate.
    """
    if not isinstance(rule, dict):
        return None
    kind = (rule.get("kind") or "").strip().lower()
    if kind not in ALLOWED_KINDS:
        return None
    out: dict[str, Any] = {"kind": kind}

    for key in ("pattern", "link_pattern", "version_pattern"):
        if key not in rule:
            continue
        pat = str(rule.get(key) or "")
        if not _pattern_ok(pat):
            return None
        out[key] = pat

    if kind in ("regex", "rows_pair") and not out.get("pattern"):
        return None
    if kind == "json_ld" and not str(rule.get("path") or "").strip():
        return None
    if kind == "json_next_data":
        # Needs a path and/or a pattern (default pattern applied at eval time).
        has_path = bool(str(rule.get("path") or "").strip())
        if not has_path and "pattern" in rule and not out.get("pattern"):
            return None

    if "path" in rule:
        path = str(rule.get("path") or "").strip()
        if len(path) > MAX_PATH_CHARS:
            return None
        if path:
            out["path"] = path

    flags_raw = str(rule.get("flags") or "")
    flags = "".join(ch for ch in flags_raw if ch in ALLOWED_FLAGS)
    if flags:
        out["flags"] = flags
    # Disallowed flag chars are dropped (fail-open); missing flags → engine default.

    pick = (rule.get("pick") or "").strip().lower()
    if pick:
        if pick not in ALLOWED_PICK:
            return None
        out["pick"] = pick

    for tkey in ("transforms", "transforms_title", "transforms_version", "transforms_date"):
        raw = rule.get(tkey)
        if raw is None:
            continue
        if not isinstance(raw, list):
            return None
        cleaned = [t for t in raw if isinstance(t, str) and t in ALLOWED_TRANSFORMS]
        # Drop unknown transforms (fail-open) but keep the key only if any remain.
        if cleaned:
            out[tkey] = cleaned

    if "link_contains" in rule:
        raw_lc = rule.get("link_contains")
        if isinstance(raw_lc, str):
            raw_lc = [raw_lc]
        if not isinstance(raw_lc, list):
            return None
        items: list[str] = []
        for item in raw_lc[:MAX_LINK_CONTAINS]:
            s = str(item or "").strip()
            if not s or len(s) > MAX_LINK_CONTAINS_ITEM_CHARS:
                continue
            items.append(s)
        if items:
            out["link_contains"] = items

    if "group" in rule:
        try:
            out["group"] = max(0, int(rule["group"]))
        except (TypeError, ValueError):
            return None

    if "min_parts" in rule:
        try:
            out["min_parts"] = max(1, min(8, int(rule["min_parts"])))
        except (TypeError, ValueError):
            return None

    if "id" in rule:
        rid = str(rule.get("id") or "").strip()
        if rid and len(rid) <= 64:
            out["id"] = rid

    return out


def sanitize_extractor(extractor: Any) -> dict | None:
    """Validate/clean an extractor override; ``None`` means fail-open (ignore it).

    ``replace: true`` with no usable rules after cleaning is rejected so a bad
    override cannot wipe bundled defaults.
    """
    if not isinstance(extractor, dict):
        return None
    replace = bool(extractor.get("replace"))
    out: dict[str, Any] = {}

    mode = (extractor.get("mode") or "").strip().lower()
    if mode:
        if mode not in ALLOWED_MODES:
            return None
        out["mode"] = mode

    if "min_parts" in extractor:
        try:
            out["min_parts"] = max(1, min(8, int(extractor["min_parts"])))
        except (TypeError, ValueError):
            return None

    usable_rules = False
    for key in ("version", "date"):
        raw = extractor.get(key)
        if raw is None:
            continue
        if not isinstance(raw, list):
            return None
        cleaned: list[dict] = []
        for rule in raw[:MAX_RULES_PER_EXTRACTOR]:
            s = sanitize_rule(rule)
            if s is not None:
                cleaned.append(s)
        if cleaned:
            out[key] = cleaned
            usable_rules = True
        elif key in extractor and isinstance(raw, list) and raw:
            # Had rules but all invalid — treat as unusable for this key.
            pass

    if replace:
        if not usable_rules:
            return None  # refuse replace that would blank the extractor
        out["replace"] = True
    elif not out:
        return None

    # Mode-only / min_parts-only stubs are allowed for merge (prepend empty).
    return out


def _safe_regex_search(
    pattern: str,
    text: str,
    *,
    flags: int = 0,
    timeout: float = REGEX_TIMEOUT_SEC,
) -> re.Match[str] | None:
    """``re.search`` with a wall-clock timeout (skip rule on hang / ReDoS)."""
    result: list[re.Match[str] | None] = [None]
    error: list[BaseException] = []

    def _run() -> None:
        try:
            result[0] = re.search(pattern, text, flags)
        except BaseException as exc:  # noqa: BLE001 — fail-open
            error.append(exc)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        return None  # timed out — treat as no match
    if error:
        return None
    return result[0]


def _safe_regex_findall(
    pattern: str,
    text: str,
    *,
    flags: int = 0,
    timeout: float = REGEX_TIMEOUT_SEC,
) -> list[str]:
    result: list[list[str]] = [[]]
    error: list[BaseException] = []

    def _run() -> None:
        try:
            found = re.findall(pattern, text, flags)
            # findall may return tuples when groups > 1; flatten to first group / str
            out: list[str] = []
            for item in found:
                if isinstance(item, tuple):
                    out.append(str(item[0]) if item else "")
                else:
                    out.append(str(item))
            result[0] = out
        except BaseException as exc:  # noqa: BLE001
            error.append(exc)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive() or error:
        return []
    return result[0]


def _safe_regex_finditer(
    pattern: str,
    text: str,
    *,
    flags: int = 0,
    timeout: float = REGEX_TIMEOUT_SEC,
) -> list[re.Match[str]]:
    result: list[list[re.Match[str]]] = [[]]
    error: list[BaseException] = []

    def _run() -> None:
        try:
            result[0] = list(re.finditer(pattern, text, flags))
        except BaseException as exc:  # noqa: BLE001
            error.append(exc)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive() or error:
        return []
    return result[0]


def _clip_input(html: str) -> str:
    if not html:
        return ""
    if len(html) <= MAX_INPUT_CHARS:
        return html
    return html[:MAX_INPUT_CHARS]


def _rule_min_parts(rule: dict, extractor: dict) -> int:
    raw = rule.get("min_parts", extractor.get("min_parts", DEFAULT_MIN_PARTS))
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return DEFAULT_MIN_PARTS


def _group_index(rule: dict) -> int:
    try:
        return max(0, int(rule.get("group", 1)))
    except (TypeError, ValueError):
        return 1


def _match_group_text(m: re.Match[str], group: int) -> str:
    try:
        if group == 0:
            return m.group(0) or ""
        return m.group(group) or ""
    except IndexError:
        return m.group(0) or ""


# ---------------------------------------------------------------------------
# Embedded JSON helpers
# ---------------------------------------------------------------------------
_EMBEDDED_JSON_PATTERNS = (
    re.compile(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(\{.+?\})</script>',
        re.I | re.S,
    ),
    re.compile(r"window\.__INITIAL_STATE__\s*=\s*(\{.+?\});", re.I | re.S),
    re.compile(r"window\.__NUXT__\s*=\s*(\{.+?\});", re.I | re.S),
)
_JSON_LD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)


def _navigate_path(data: Any, path: str) -> Any:
    """Walk a dotted path; numeric segments index lists."""
    cur = data
    for part in (path or "").split("."):
        if not part:
            continue
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list) and part.isdigit():
            idx = int(part)
            cur = cur[idx] if 0 <= idx < len(cur) else None
        else:
            return None
        if cur is None:
            return None
    return cur


def _extract_embedded_json_blobs(html: str) -> list[Any]:
    """Pull __NEXT_DATA__ / __INITIAL_STATE__ / __NUXT__ blobs (Intel/AMD-style pages)."""
    blobs: list[Any] = []
    for rx in _EMBEDDED_JSON_PATTERNS:
        for m in rx.finditer(html):
            try:
                blobs.append(json.loads(m.group(1)))
            except (json.JSONDecodeError, ValueError, TypeError):
                continue
    return blobs


def _extract_next_data(html: str) -> Any | None:
    blobs = _extract_embedded_json_blobs(html)
    return blobs[0] if blobs else None


def _extract_json_ld_blobs(html: str) -> list[Any]:
    blobs: list[Any] = []
    for m in _JSON_LD_RE.finditer(html):
        raw = (m.group(1) or "").strip()
        if not raw:
            continue
        try:
            blobs.append(json.loads(raw))
        except (json.JSONDecodeError, ValueError, TypeError):
            continue
    return blobs


# ---------------------------------------------------------------------------
# Per-kind evaluators — return str | list[dict] | None
# ---------------------------------------------------------------------------
def _eval_regex(
    rule: dict, text: str, params: dict[str, str] | None, *, min_parts: int
) -> str | None:
    pattern = _fill_pattern(str(rule.get("pattern") or ""), params)
    if not _pattern_ok(pattern):
        return None
    flags = _compile_flags(rule.get("flags"))
    pick = (rule.get("pick") or "first").lower()
    group = _group_index(rule)
    transforms = rule.get("transforms") or rule.get("transforms_version")

    if pick == "max":
        found = _safe_regex_findall(pattern, text, flags=flags)
        valid = [
            apply_transforms(v, transforms)
            for v in found
            if is_version_shaped(apply_transforms(v, transforms), min_parts=min_parts)
        ]
        if not valid:
            # When group=0 the pattern itself is the version (no capturing group).
            if group == 0:
                valid = [
                    apply_transforms(v, transforms)
                    for v in found
                    if is_version_shaped(
                        apply_transforms(v, transforms), min_parts=min_parts
                    )
                ]
            if not valid:
                return None
        return max(valid, key=_version_sort_key)

    m = _safe_regex_search(pattern, text, flags=flags)
    if not m:
        return None
    raw = _match_group_text(m, group)
    cand = apply_transforms(raw, transforms)
    if is_version_shaped(cand, min_parts=min_parts):
        return cand
    return None


def _eval_json_next_data(
    rule: dict, html: str, params: dict[str, str] | None, *, min_parts: int
) -> str | None:
    blobs = _extract_embedded_json_blobs(html)
    if not blobs:
        return None
    path = (rule.get("path") or "").strip()
    transforms = rule.get("transforms") or rule.get("transforms_version")
    if path:
        for data in blobs:
            node = _navigate_path(data, path)
            if node is None:
                continue
            if isinstance(node, (int, float, str)):
                cand = apply_transforms(str(node), transforms)
                if is_version_shaped(cand, min_parts=min_parts):
                    return cand
            else:
                blob = json.dumps(node)
                pattern = _fill_pattern(
                    str(rule.get("pattern") or r"(\d+\.\d+\.\d+(?:\.\d+)?)"),
                    params,
                )
                if not _pattern_ok(pattern):
                    continue
                sub = dict(rule)
                sub["pattern"] = pattern
                hit = _eval_regex(sub, blob, None, min_parts=min_parts)
                if hit:
                    return hit
        return None

    # No path: stringify all embedded blobs and run the pattern (pick max typical).
    blob = "\n".join(json.dumps(d) for d in blobs)
    pattern = _fill_pattern(
        str(rule.get("pattern") or r"(\d+\.\d+\.\d+(?:\.\d+)?)"), params
    )
    if not _pattern_ok(pattern):
        return None
    sub = dict(rule)
    sub["pattern"] = pattern
    return _eval_regex(sub, blob, None, min_parts=min_parts)


def _eval_json_ld(
    rule: dict, html: str, params: dict[str, str] | None, *, min_parts: int
) -> str | None:
    path = (rule.get("path") or "").strip()
    if not path:
        return None
    transforms = rule.get("transforms") or rule.get("transforms_version")
    for blob in _extract_json_ld_blobs(html):
        node = _navigate_path(blob, path)
        if node is None:
            continue
        cand = apply_transforms(str(node), transforms)
        if is_version_shaped(cand, min_parts=min_parts):
            return cand
    return None


def _eval_link_filename(
    rule: dict, html: str, params: dict[str, str] | None, *, min_parts: int
) -> list[dict]:
    link_pat = _fill_pattern(
        str(rule.get("link_pattern") or r"https://[^\"'\s<>]+\.(?:exe|zip|cab|msi)"),
        params,
    )
    ver_pat = _fill_pattern(
        str(rule.get("version_pattern") or r"(\d+\.\d+\.\d+(?:\.\d+)?)"),
        params,
    )
    if not _pattern_ok(link_pat) or not _pattern_ok(ver_pat):
        return []
    flags = _compile_flags(rule.get("flags"))
    group = _group_index(rule)
    transforms = rule.get("transforms") or rule.get("transforms_version")
    must_contain = rule.get("link_contains") or []
    if isinstance(must_contain, str):
        must_contain = [must_contain]
    rows: list[dict] = []
    seen: set[str] = set()
    for link in _safe_regex_findall(link_pat, html, flags=flags):
        if link in seen:
            continue
        low = link.lower()
        if must_contain and not any(str(x).lower() in low for x in must_contain):
            continue
        seen.add(link)
        fname = link.split("/")[-1].split("?")[0]
        m = _safe_regex_search(ver_pat, fname, flags=flags)
        if not m:
            continue
        ver = apply_transforms(_match_group_text(m, group), transforms)
        if not is_version_shaped(ver, min_parts=min_parts):
            continue
        rows.append({"title": fname[:120], "version": ver, "url": link, "date": ""})
    return rows


def _eval_rows_pair(
    rule: dict, html: str, params: dict[str, str] | None, *, min_parts: int
) -> list[dict]:
    pattern = _fill_pattern(str(rule.get("pattern") or ""), params)
    if not _pattern_ok(pattern):
        return []
    flags = _compile_flags(rule.get("flags"))
    t_title = rule.get("transforms_title") or []
    t_ver = rule.get("transforms") or rule.get("transforms_version") or []
    t_date = rule.get("transforms_date") or []
    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for m in _safe_regex_finditer(pattern, html, flags=flags):
        try:
            gd = m.groupdict()
        except IndexError:
            continue
        title = apply_transforms(gd.get("title") or "", t_title)[:120]
        ver = apply_transforms(gd.get("version") or "", t_ver)
        date = apply_transforms(gd.get("date") or "", t_date)
        if not is_version_shaped(ver, min_parts=min_parts):
            continue
        key = (title, ver)
        if key in seen:
            continue
        seen.add(key)
        rows.append({"title": title, "version": ver, "date": date, "url": ""})
    return rows


def _eval_rule(
    rule: dict,
    html: str,
    params: dict[str, str] | None,
    *,
    min_parts: int,
) -> str | list[dict] | None:
    if not isinstance(rule, dict):
        return None
    kind = (rule.get("kind") or "").strip().lower()
    if kind not in ALLOWED_KINDS:
        return None
    try:
        if kind == "regex":
            return _eval_regex(rule, html, params, min_parts=min_parts)
        if kind == "json_next_data":
            return _eval_json_next_data(rule, html, params, min_parts=min_parts)
        if kind == "json_ld":
            return _eval_json_ld(rule, html, params, min_parts=min_parts)
        if kind == "link_filename":
            return _eval_link_filename(rule, html, params, min_parts=min_parts)
        if kind == "rows_pair":
            return _eval_rows_pair(rule, html, params, min_parts=min_parts)
    except Exception:  # noqa: BLE001 — fail-open: never raise out of a single rule
        return None
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def extract_version(
    html: str,
    extractor: dict | None,
    *,
    params: dict[str, str] | None = None,
) -> str:
    """Run a scalar extractor; return the first validating version or ``\"\"``."""
    if not extractor or not isinstance(extractor, dict):
        return ""
    text = _clip_input(html or "")
    if not text:
        return ""
    rules = extractor.get("version") or []
    if not isinstance(rules, list):
        return ""
    for rule in rules:
        min_parts = _rule_min_parts(rule if isinstance(rule, dict) else {}, extractor)
        hit = _eval_rule(rule, text, params, min_parts=min_parts)
        if isinstance(hit, str) and hit:
            return hit
        # A rows-kind rule in scalar mode: take the max version among rows.
        if isinstance(hit, list) and hit:
            vers = [r.get("version") or "" for r in hit if r.get("version")]
            valid = [v for v in vers if is_version_shaped(v, min_parts=min_parts)]
            if valid:
                return max(valid, key=_version_sort_key)
    return ""


def extract_date(
    html: str,
    extractor: dict | None,
    *,
    params: dict[str, str] | None = None,
) -> str:
    """Optional date rules (scalar). Returns ``\"\"`` when absent / no match."""
    if not extractor or not isinstance(extractor, dict):
        return ""
    text = _clip_input(html or "")
    rules = extractor.get("date") or []
    if not isinstance(rules, list) or not text:
        return ""
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        # Dates are not version-shaped; use a permissive path via regex group.
        kind = (rule.get("kind") or "regex").lower()
        if kind != "regex":
            continue
        pattern = _fill_pattern(str(rule.get("pattern") or ""), params)
        if not _pattern_ok(pattern):
            continue
        flags = _compile_flags(rule.get("flags"))
        m = _safe_regex_search(pattern, text, flags=flags)
        if not m:
            continue
        raw = _match_group_text(m, _group_index(rule))
        cand = apply_transforms(raw, rule.get("transforms"))
        if cand:
            return cand
    return ""


def extract_rows(
    html: str,
    extractor: dict | None,
    *,
    params: dict[str, str] | None = None,
) -> list[dict]:
    """Run a rows extractor; return deduped ``{title, version, date, url}`` dicts."""
    if not extractor or not isinstance(extractor, dict):
        return []
    text = _clip_input(html or "")
    if not text:
        return []
    rules = extractor.get("version") or []
    if not isinstance(rules, list):
        return []
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for rule in rules:
        min_parts = _rule_min_parts(rule if isinstance(rule, dict) else {}, extractor)
        hit = _eval_rule(rule, text, params, min_parts=min_parts)
        if isinstance(hit, list):
            for row in hit:
                ver = (row.get("version") or "").strip()
                title = (row.get("title") or "").strip()
                key = (title, ver)
                if key in seen or not ver:
                    continue
                seen.add(key)
                out.append(row)
        elif isinstance(hit, str) and hit:
            key = ("", hit)
            if key not in seen:
                seen.add(key)
                out.append({"title": "", "version": hit, "date": "", "url": ""})
    return out


def run_extractor(
    html: str,
    extractor: dict | None,
    *,
    params: dict[str, str] | None = None,
) -> str | list[dict]:
    """Dispatch on ``extractor[\"mode\"]`` (default ``scalar``)."""
    mode = ((extractor or {}).get("mode") or "scalar").strip().lower()
    if mode == "rows":
        return extract_rows(html, extractor, params=params)
    return extract_version(html, extractor, params=params)


def merge_extractor_rules(
    bundled: dict | None,
    override: dict | None,
) -> dict:
    """Prepend manifest/override rules onto bundled defaults (additive merge).

    If ``override`` sets ``\"replace\": true``, the override fully replaces the
    bundled extractor for that hint — but only when sanitize leaves usable rules
    (otherwise fail-open to bundled). Invalid override fields are stripped.
    """
    bundled = dict(bundled or {})
    cleaned = sanitize_extractor(override) if override else None
    if not cleaned:
        return bundled
    if cleaned.get("replace"):
        merged = dict(cleaned)
        merged.pop("replace", None)
        if "mode" not in merged and "mode" in bundled:
            merged["mode"] = bundled["mode"]
        return merged
    merged = dict(bundled)
    if "mode" in cleaned:
        merged["mode"] = cleaned["mode"]
    if "min_parts" in cleaned:
        merged["min_parts"] = cleaned["min_parts"]
    for key in ("version", "date"):
        over_rules = cleaned.get(key)
        base_rules = bundled.get(key) or []
        if isinstance(over_rules, list):
            merged[key] = list(over_rules) + list(base_rules)
        elif key not in merged:
            merged[key] = list(base_rules)
    return merged


def get_bundled_extractor(vendor: str, hint: str = "*") -> dict | None:
    """Look up a bundled extractor; falls back to ``\"*\"`` hint for the vendor."""
    v = (vendor or "").strip().lower()
    h = (hint or "*").strip().lower() or "*"
    by_vendor = BUNDLED_EXTRACTORS.get(v) or {}
    if h in by_vendor:
        return dict(by_vendor[h])
    if "*" in by_vendor:
        return dict(by_vendor["*"])
    return None


def resolve_extractor(vendor: str, hint: str = "*") -> dict | None:
    """Bundled extractor with any ``vendor_endpoints.json`` override prepended.

    Prefers ``vendor_endpoint_health.get_extractor`` (manifest-aware). Falls back
    to bundled-only when that module is unavailable.
    """
    try:
        import vendor_endpoint_health as veh

        return veh.get_extractor(vendor, hint)
    except ImportError:
        return get_bundled_extractor(vendor, hint)


def extract_bundled_version(
    vendor: str,
    html: str,
    *,
    hint: str = "*",
    params: dict[str, str] | None = None,
) -> str:
    """Run the resolved scalar extractor for ``vendor``/``hint`` (bundled + overrides)."""
    return extract_version(html, resolve_extractor(vendor, hint), params=params)


def extract_bundled_date(
    vendor: str,
    html: str,
    *,
    hint: str = "*",
    params: dict[str, str] | None = None,
) -> str:
    return extract_date(html, resolve_extractor(vendor, hint), params=params)


def extract_bundled_rows(
    vendor: str,
    html: str,
    *,
    hint: str = "*",
    params: dict[str, str] | None = None,
) -> list[dict]:
    return extract_rows(html, resolve_extractor(vendor, hint), params=params)
