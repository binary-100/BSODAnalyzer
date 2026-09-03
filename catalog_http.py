"""Shared HTTP helpers for catalog / vendor fetch (extracted from driver_catalog)."""

from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.request

_HTTP_TIMEOUT = 22


def catalog_user_agent() -> str:
    """User-Agent string synced with product version."""
    try:
        from product_version import product_version

        ver = product_version() or "unknown"
    except Exception:
        ver = "unknown"
    return f"BSODAnalyzer/{ver} (Windows driver/firmware comparison)"


def _looks_like_html_payload(data: bytes) -> bool:
    head = data[:2048].lstrip().lower()
    return head.startswith(b"<!doctype") or head.startswith(b"<html") or b"<html" in head[:512]


def _http_browser_headers() -> dict[str, str]:
    ua = catalog_user_agent()
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            f"(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 {ua.split('(')[0].strip()}"
        ),
        "Accept": "text/html,application/json,text/plain,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }


def _http_get(
    url: str,
    headers: dict | None = None,
    *,
    referer: str | None = None,
    insecure_fallback: bool = False,
) -> tuple[bool, str]:
    base = _http_browser_headers()
    if referer:
        base["Referer"] = referer
    base.update(headers or {})
    req = urllib.request.Request(url, headers=base)
    last_err = ""
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
                return True, resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            last_err = str(e)
            if e.code == 403 and attempt == 0:
                base["User-Agent"] = catalog_user_agent()
                req = urllib.request.Request(url, headers=base)
                continue
            return False, last_err
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_err = str(e)
            if (
                insecure_fallback
                and attempt == 0
                and "CERTIFICATE_VERIFY_FAILED" in last_err
            ):
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                try:
                    with urllib.request.urlopen(
                        req, timeout=_HTTP_TIMEOUT, context=ctx
                    ) as resp:
                        return True, resp.read().decode("utf-8", errors="replace")
                except (urllib.error.URLError, TimeoutError, OSError) as e2:
                    last_err = str(e2)
            return False, last_err
    return False, last_err


def _http_post_json(
    url: str,
    payload: dict,
    headers: dict | None = None,
    *,
    referer: str | None = None,
) -> tuple[bool, str]:
    """POST JSON body; returns (ok, response_text)."""
    base = _http_browser_headers()
    if referer:
        base["Referer"] = referer
    base.update(headers or {})
    base.setdefault("Content-Type", "application/json")
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=base, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
            return True, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return False, str(e)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return False, str(e)


def _vendor_http_get_robust(
    url: str,
    *,
    referer: str | None = None,
    accept: str = "text/html,application/xhtml+xml",
    attempts: int = 3,
    insecure_fallback: bool = False,
) -> tuple[bool, str]:
    """Static GET with retry past intermittent bot-manager challenges."""
    try:
        import vendor_page_render as vpr

        is_challenge = vpr.looks_like_bot_challenge
    except ImportError:
        def is_challenge(_h: str) -> bool:  # type: ignore[misc]
            return False

    headers = {"Accept": accept} if accept else None
    last = ""
    for i in range(max(1, attempts)):
        ok, body = _http_get(
            url, headers=headers, referer=referer, insecure_fallback=insecure_fallback
        )
        if ok and body and not is_challenge(body):
            return True, body
        if ok and body:
            last = body
        else:
            el = (body or "").lower()
            if any(c in el for c in ("403", "401", "404", "forbidden", "not found")):
                return False, body
        if i < attempts - 1:
            time.sleep(0.4 * (i + 1))
    return False, last


def _amd_http_get_robust(url: str, *, attempts: int = 3) -> tuple[bool, str]:
    """AMD download pages via the shared robust vendor getter."""
    return _vendor_http_get_robust(url, attempts=attempts)
