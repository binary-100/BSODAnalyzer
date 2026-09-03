"""Windows Update row scoring and bulk-offer filtering (extracted from driver_catalog)."""

from __future__ import annotations

from catalog_device_roles import wu_parent_child_preference
from catalog_oem_live import _OEM_MIN_MATCH_SCORE, _oem_row_match_score
from catalog_row_rejects import _shared_catalog_row_rejects


def _score_update_match(title: str, ctx: dict) -> int:
    t = (title or "").lower()
    score = 0
    vk = (ctx.get("vendor_key") or "").lower()
    label = (ctx.get("device_label") or "").lower()
    pnp = (ctx.get("pnp_class") or "").lower()
    pnp_mfr = (ctx.get("pnp_manufacturer") or "").lower()
    role = (ctx.get("catalog_role") or "").lower()
    if vk and vk in t:
        score += 6
    if pnp_mfr and pnp_mfr in t:
        score += 5
    if pnp == "monitor" and any(x in t for x in ("monitor", "display", "firmware")):
        score += 3
    if "softwarecomponent" in t or "audioprocessingobject" in t:
        if role == "softwarecomponent":
            score += 18
        elif role == "monitor_edid":
            score -= 12
    if "nvidia" in t and vk == "nvidia":
        score += 6
    if "amd" in t and vk == "amd":
        score += 6
    if "intel" in t and vk == "intel":
        score += 6
    if "realtek" in t and vk == "realtek":
        score += 5
    if pnp == "display" and any(x in t for x in ("display", "graphics", "video", "gpu")):
        score += 4
    if pnp == "net" and any(x in t for x in ("network", "wi-fi", "wifi", "ethernet", "wireless")):
        score += 4
    for token in label.split()[:4]:
        if len(token) > 3 and token in t:
            score += 2
    drv = (ctx.get("driver") or "").lower().replace(".sys", "")
    if drv and drv[:6] in t.replace(".sys", ""):
        score += 3
    return score


def _parse_wu_rows_for_scoring(rows: list[dict]) -> list[tuple[dict, str]]:
    parsed: list[tuple[dict, str]] = []
    for row in rows:
        hw_ids = row.get("HardwareIds") or []
        if isinstance(hw_ids, str):
            hw_ids = [hw_ids]
        hw_u = " ".join(str(h) for h in hw_ids).upper()
        parsed.append((row, hw_u))
    return parsed


def _wu_row_probe(row: dict) -> dict:
    title = row.get("Title") or row.get("title") or ""
    return {
        "source": "microsoft",
        "title": title,
        "version": row.get("Version") or row.get("version") or "",
    }


def _wu_row_update_id(row: dict) -> str:
    return (row.get("UpdateId") or row.get("update_id") or "").strip().lower()


def _wu_device_match_score(row: dict, hw_u: str, ctx: dict) -> int:
    probe = _wu_row_probe(row)
    if _shared_catalog_row_rejects(probe, ctx):
        return -1
    title = probe["title"]
    score = _score_update_match(title, ctx)
    pci = [t.upper() for t in ctx.get("pci_tokens") or []]
    ven = next((t for t in pci if t.startswith("VEN_")), "")
    dev = next((t for t in pci if t.startswith("DEV_")), "")
    sub = next((t for t in pci if t.startswith("SUBSYS_")), "")
    if ven and hw_u and ven in hw_u:
        if dev and dev in hw_u:
            score += 14
        elif sub and sub in hw_u:
            score += 12
        else:
            score += 9
    if (ctx.get("catalog_has_swc_child") and (ctx.get("catalog_role") or "") == "monitor_edid"):
        title_l = title.lower()
        if "softwarecomponent" in title_l:
            score -= 25
    return score


def _prefilter_wu_rows_for_ctx(
    rows: list[dict],
    ctx: dict,
    *,
    max_results: int = 5,
    parsed_rows: list[tuple[dict, str]] | None = None,
) -> list[dict]:
    """Score full WU driver list once per device context (batch optimization)."""
    if not rows:
        return []
    scored: list[tuple[int, dict]] = []
    row_iter = parsed_rows if parsed_rows is not None else _parse_wu_rows_for_scoring(rows)
    for row, hw_u in row_iter:
        score = _wu_device_match_score(row, hw_u, ctx)
        if score < 3:
            continue
        scored.append((score, row))
    scored.sort(key=lambda x: -x[0])
    return [row for _, row in scored[:max_results]]


def _pick_wu_owner(
    title: str,
    owner: str,
    owner_score: int,
    challenger: str,
    challenger_score: int,
    device_contexts: dict[str, dict],
) -> tuple[str, int]:
    if challenger_score > owner_score:
        return challenger, challenger_score
    if challenger_score < owner_score:
        return owner, owner_score
    preferred = wu_parent_child_preference(
        title,
        owner,
        device_contexts.get(owner) or {},
        challenger,
        device_contexts.get(challenger) or {},
    )
    if preferred == challenger:
        return challenger, challenger_score
    return owner, owner_score


def _batch_prefilter_wu_rows(
    rows: list[dict],
    device_contexts: dict[str, dict],
    *,
    max_results: int = 5,
) -> dict[str, list[dict]]:
    """
    Assign each WU optional row to at most one device (by UpdateId + score).

    Parent/child rules prefer SoftwareComponent children over monitor parents.
    """
    if not rows or not device_contexts:
        return {name: [] for name in device_contexts}

    parsed = _parse_wu_rows_for_scoring(rows)
    update_id_owner: dict[str, tuple[str, int]] = {}
    title_owner: dict[str, tuple[str, int]] = {}
    device_rows: dict[str, list[tuple[int, dict]]] = {
        name: [] for name in device_contexts
    }

    for row, hw_u in parsed:
        title = row.get("Title") or row.get("title") or ""
        uid = _wu_row_update_id(row)
        title_key = title.strip().lower()[:160]
        best_name = ""
        best_score = -1
        for name, ctx in device_contexts.items():
            score = _wu_device_match_score(row, hw_u, ctx)
            if score < 3:
                continue
            if score > best_score:
                best_name = name
                best_score = score
            elif score == best_score and best_name:
                pick, _ = _pick_wu_owner(
                    title,
                    best_name,
                    best_score,
                    name,
                    score,
                    device_contexts,
                )
                best_name = pick

        if not best_name or best_score < 3:
            continue

        if uid:
            prev = update_id_owner.get(uid)
            if prev:
                prev_name, prev_score = prev
                winner, winner_score = _pick_wu_owner(
                    title,
                    prev_name,
                    prev_score,
                    best_name,
                    best_score,
                    device_contexts,
                )
                if winner != best_name:
                    continue
                if prev_name != best_name:
                    device_rows[prev_name] = [
                        item
                        for item in device_rows[prev_name]
                        if _wu_row_update_id(item[1]) != uid
                    ]
                best_name = winner
                best_score = winner_score
            update_id_owner[uid] = (best_name, best_score)
        elif title_key:
            prev = title_owner.get(title_key)
            if prev:
                prev_name, prev_score = prev
                winner, winner_score = _pick_wu_owner(
                    title,
                    prev_name,
                    prev_score,
                    best_name,
                    best_score,
                    device_contexts,
                )
                if winner != best_name:
                    continue
                if prev_name != best_name:
                    device_rows[prev_name] = [
                        item
                        for item in device_rows[prev_name]
                        if (
                            (item[1].get("Title") or item[1].get("title") or "")
                            .strip()
                            .lower()[:160]
                            != title_key
                        )
                    ]
                best_name = winner
                best_score = winner_score
            title_owner[title_key] = (best_name, best_score)

        device_rows[best_name].append((best_score, row))

    out: dict[str, list[dict]] = {}
    for name, scored in device_rows.items():
        scored.sort(key=lambda x: -x[0])
        seen: set[str] = set()
        picked: list[dict] = []
        for _sc, row in scored:
            uid = _wu_row_update_id(row)
            if uid:
                if uid in seen:
                    continue
                seen.add(uid)
            picked.append(row)
            if len(picked) >= max_results:
                break
        out[name] = picked
    return out


def _filter_offers_for_device_ctx(
    offers: list[dict],
    ctx: dict,
    *,
    min_oem_score: int = 2,
    min_ms_score: int = 3,
) -> list[dict]:
    """Drop OEM/MS rows from bulk caches that do not match this device."""
    if not offers:
        return []
    vk = (ctx.get("vendor_key") or "").lower()
    pnp = (ctx.get("pnp_class") or "").lower()
    out: list[dict] = []
    for o in offers:
        src = (o.get("source") or "").lower()
        title = o.get("title") or ""
        if src == "oem":
            if _shared_catalog_row_rejects(o, ctx):
                continue
            if _oem_row_match_score(o, ctx) < max(min_oem_score, _OEM_MIN_MATCH_SCORE):
                continue
        elif src == "microsoft":
            if _shared_catalog_row_rejects(o, ctx):
                continue
            if _score_update_match(title, ctx) < min_ms_score:
                continue
        elif src == "vendor":
            sl = (o.get("source_label") or "").lower()
            if vk == "nvidia" and "nvidia" not in sl:
                continue
            if vk == "amd" and "amd" not in sl and "radeon" not in sl:
                continue
            if vk == "intel" and "intel" not in sl:
                continue
            if vk and vk not in sl and vk not in title.lower():
                continue
        elif src == "utility" and pnp != "display":
            continue
        out.append(o)
    return out


__all__ = [
    "_batch_prefilter_wu_rows",
    "_filter_offers_for_device_ctx",
    "_parse_wu_rows_for_scoring",
    "_prefilter_wu_rows_for_ctx",
    "_score_update_match",
    "_wu_device_match_score",
    "_wu_row_update_id",
]
