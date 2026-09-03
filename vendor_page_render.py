"""Headless-browser HTML fetch for vendor pages that need JavaScript execution.

Uses an installed Chromium-based browser (Microsoft Edge, Chrome, Brave) via
``--headless --dump-dom``. No Playwright bundle — keeps the portable .exe small.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from urllib.parse import urlparse

_JS_RENDER_TIMEOUT = 20
_ALLOWED_URL_SCHEMES = frozenset({"http", "https"})

# A realistic desktop UA so bot managers (e.g. Akamai on amd.com) score the
# headless render like a normal browser instead of an automation client.
_RENDER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

# Only one headless render at a time may use the shared cookie profile below
# (a Chromium profile directory cannot be opened by two processes at once).
_RENDER_LOCK = threading.Lock()
_SHARED_PROFILE_DIR: str | None = None

# Interstitial / bot-challenge markers. When a rendered DOM matches these it is
# an Akamai/Cloudflare "prove you're human" shell, not the real page — the bot
# cookie (_abck/bm_sz) is being (re)negotiated and content has not loaded yet.
_BOT_CHALLENGE_MARKERS = (
    "pardon our interruption",
    "access denied",
    "reference #",
    "errors.edgesuite.net",
    "/akam/",
    "bmak.",
    "window.bmak",
    "_abck",
    "please enable javascript and cookies",
    "checking your browser",
    "cf-browser-verification",
    "challenge-platform",
)


def looks_like_bot_challenge(html: str) -> bool:
    """True when *html* is a bot-manager interstitial rather than real content."""
    if not html:
        return False
    low = html.lower()
    # A genuine content page is large and has few/no challenge markers; a
    # challenge shell is small and dominated by the sensor script.
    hits = sum(1 for m in _BOT_CHALLENGE_MARKERS if m in low)
    if hits == 0:
        return False
    if len(html) < 4000:
        return True
    # Larger pages: only treat as a challenge when the strongest markers appear.
    return any(m in low for m in (
        "pardon our interruption",
        "access denied",
        "checking your browser",
        "cf-browser-verification",
    ))


def _shared_profile_dir() -> str:
    """Persistent Chromium profile reused across renders so bot cookies survive.

    Keeping one profile (instead of a throwaway temp dir per call) means the
    Akamai ``_abck``/``bm_sz`` cookies obtained on the first challenge are
    reused on later fetches — subsequent pages skip the challenge entirely.
    """
    global _SHARED_PROFILE_DIR
    if _SHARED_PROFILE_DIR and Path(_SHARED_PROFILE_DIR).is_dir():
        return _SHARED_PROFILE_DIR
    base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    target = Path(base) / "BSODAnalyzer" / "render_profile"
    try:
        target.mkdir(parents=True, exist_ok=True)
        _SHARED_PROFILE_DIR = str(target)
    except OSError:
        _SHARED_PROFILE_DIR = tempfile.mkdtemp(prefix="bsod_js_render_")
    return _SHARED_PROFILE_DIR


def reset_render_session() -> None:
    """Drop the shared render profile (clears stale/expired bot cookies)."""
    global _SHARED_PROFILE_DIR
    with _RENDER_LOCK:
        if _SHARED_PROFILE_DIR:
            shutil.rmtree(_SHARED_PROFILE_DIR, ignore_errors=True)
        _SHARED_PROFILE_DIR = None


def url_scheme_allowed(url: str) -> bool:
    """Only http/https URLs may be fetched or headless-rendered."""
    try:
        parsed = urlparse((url or "").strip())
    except ValueError:
        return False
    return parsed.scheme.lower() in _ALLOWED_URL_SCHEMES and bool(parsed.netloc)


def js_render_enabled(settings: dict | None = None) -> bool:
    """True when JS render fallback is allowed (on by default on Windows)."""
    if settings is None:
        try:
            import app_settings as app_set

            settings = app_set.load_settings()
        except ImportError:
            settings = {}
    default = sys.platform == "win32"
    return bool(settings.get("vendor_js_render_fallback", default))


def _browser_from_registry(exe_name: str) -> Path | None:
    if sys.platform != "win32":
        return None
    try:
        import winreg
    except ImportError:
        return None
    subkey = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe_name}"
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(hive, subkey) as key:
                val, _ = winreg.QueryValueEx(key, "")
                path = Path(str(val).strip('"'))
                if path.is_file():
                    return path
        except OSError:
            continue
    return None


def _browser_from_where(name: str) -> Path | None:
    try:
        proc = subprocess.run(
            ["where", name],
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0:
        return None
    for line in (proc.stdout or "").splitlines():
        path = Path(line.strip())
        if path.is_file():
            return path
    return None


def headless_browser_candidates() -> list[Path]:
    """Installed Chromium browsers that support ``--headless --dump-dom``."""
    seen: set[str] = set()
    out: list[Path] = []
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pfx86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    local = os.environ.get("LOCALAPPDATA", "")
    program_data = os.environ.get("ProgramData", r"C:\ProgramData")
    for rel in (
        rf"{pf}\Microsoft\Edge\Application\msedge.exe",
        rf"{pfx86}\Microsoft\Edge\Application\msedge.exe",
        rf"{local}\Microsoft\Edge\Application\msedge.exe",
        rf"{program_data}\Microsoft\Windows\Start Menu\Programs\Microsoft Edge.lnk",
        rf"{pf}\Google\Chrome\Application\chrome.exe",
        rf"{pfx86}\Google\Chrome\Application\chrome.exe",
        rf"{local}\Google\Chrome\Application\chrome.exe",
        rf"{pf}\BraveSoftware\Brave-Browser\Application\brave.exe",
    ):
        p = Path(rel)
        key = str(p).lower()
        if p.suffix.lower() == ".lnk":
            continue
        if p.is_file() and key not in seen:
            seen.add(key)
            out.append(p)
    for exe in ("msedge.exe", "chrome.exe", "brave.exe"):
        reg = _browser_from_registry(exe)
        if reg:
            key = str(reg).lower()
            if key not in seen:
                seen.add(key)
                out.append(reg)
    for name in ("msedge", "chrome", "brave"):
        found = shutil.which(name)
        if found:
            key = found.lower()
            if key not in seen:
                seen.add(key)
                out.append(Path(found))
        where = _browser_from_where(name)
        if where:
            key = str(where).lower()
            if key not in seen:
                seen.add(key)
                out.append(where)
    return out


def headless_browser_available() -> bool:
    return bool(headless_browser_candidates())


def page_likely_needs_js_render(html: str) -> bool:
    """Heuristic: HTML shell with client bundles but no obvious driver version text."""
    if not html or len(html) < 1500:
        return False
    if re.search(r"\d+\.\d+\.\d+\.\d+\s*\(Latest\)", html, re.I):
        return False
    markers = (
        "clientlibs/bundles",
        "__NEXT_DATA__",
        "window.__INITIAL_STATE__",
        "window.__NUXT__",
        "/wap.js",
        "runtime.script.",
    )
    return any(m in html for m in markers)


def _run_headless_once(browser: Path, url: str, profile_dir: str, timeout: int) -> tuple[bool, str]:
    """Single ``--dump-dom`` render pass. Returns ``(ok, html_or_error)``."""
    args = [
        str(browser),
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        # Look like a real browser to bot managers (Akamai on amd.com, etc.).
        "--disable-blink-features=AutomationControlled",
        f"--user-agent={_RENDER_UA}",
        "--window-size=1280,800",
        "--lang=en-US",
        f"--user-data-dir={profile_dir}",
        f"--virtual-time-budget={min(max(timeout, 5), 30) * 1000}",
        "--dump-dom",
        url,
    ]
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            timeout=timeout + 10,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    except subprocess.TimeoutExpired:
        return False, f"{browser.name}: timeout"
    except OSError as exc:
        return False, f"{browser.name}: {exc}"
    html = proc.stdout.decode("utf-8", errors="replace").strip()
    if len(html) < 400:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        return False, err or f"{browser.name}: empty render (exit {proc.returncode})"
    return True, html


def render_page_html(
    url: str,
    *,
    timeout: int = _JS_RENDER_TIMEOUT,
    reuse_profile: bool = True,
    challenge_retries: int = 2,
) -> tuple[bool, str]:
    """Fetch *url* after JavaScript runs; returns ``(ok, html_or_error)``.

    Uses a persistent Chromium profile so bot-manager cookies (Akamai
    ``_abck``/``bm_sz``) survive between calls. When a render comes back as a
    bot-challenge shell, it retries with the same profile: the first pass runs
    the sensor JS and plants the cookie, later passes get the real content.
    """
    if not url_scheme_allowed(url):
        return False, "unsupported URL scheme (http/https only)"
    browsers = headless_browser_candidates()
    if not browsers:
        return False, "no headless browser (Edge/Chrome not found)"

    # Serialize renders that share the persistent profile (Chromium locks it).
    lock = _RENDER_LOCK if reuse_profile else None
    if lock:
        lock.acquire()
    try:
        last_err = ""
        for browser in browsers:
            if reuse_profile:
                profile_dir = _shared_profile_dir()
                cleanup = False
            else:
                profile_dir = tempfile.mkdtemp(prefix="bsod_js_render_")
                cleanup = True
            try:
                attempts = max(1, challenge_retries + 1)
                challenged = False
                for attempt in range(attempts):
                    ok, html = _run_headless_once(browser, url, profile_dir, timeout)
                    if not ok:
                        last_err = html
                        break
                    if looks_like_bot_challenge(html):
                        challenged = True
                        last_err = f"{browser.name}: bot-challenge interstitial"
                        # Let the sensor settle; the cookie is now in the profile.
                        if attempt < attempts - 1:
                            time.sleep(1.5)
                        continue
                    return True, html
                if challenged:
                    # Try the next browser rather than returning a challenge shell.
                    continue
            finally:
                if cleanup:
                    shutil.rmtree(profile_dir, ignore_errors=True)
        return False, last_err or "js render failed"
    finally:
        if lock:
            lock.release()


def fetch_html_with_js_fallback(
    url: str,
    http_get,
    *,
    needs_js=None,
    allow_js: bool = True,
    settings: dict | None = None,
) -> tuple[bool, str, str]:
    """
    Try plain HTTP first; optionally re-fetch with a headless browser.

    Returns ``(ok, body, method)`` where *method* is ``http`` or ``js_render``.
    *http_get* is a callable ``(url) -> (ok, body)``.
    *needs_js* is an optional ``(html) -> bool`` predicate (default: shell heuristic).
    """
    if not url_scheme_allowed(url):
        return False, "unsupported URL scheme (http/https only)", "http"
    ok, html = http_get(url)
    predicate = needs_js or page_likely_needs_js_render
    # A plain-HTTP body that is really a bot-challenge shell must not be trusted.
    http_challenged = ok and html and looks_like_bot_challenge(html)
    if ok and html and not http_challenged and not predicate(html):
        return True, html, "http"
    if not allow_js or not js_render_enabled(settings):
        # Never return a challenge shell as if it were content.
        if http_challenged:
            return False, "", "http"
        return ok, html if ok else "", "http"
    ok_js, rendered = render_page_html(url)
    if ok_js:
        return True, rendered, "js_render"
    if http_challenged:
        return False, "", "js_render"
    return ok, html if ok else "", "http"
