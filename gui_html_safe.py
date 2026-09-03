"""Guard QTextBrowser/setHtml against re-entrancy and oversized HTML (Qt stack stress)."""
from __future__ import annotations

from PySide6 import QtWidgets

MAX_HTML_CHARS = 512_000
_active_browser: QtWidgets.QTextBrowser | None = None


def safe_set_html(browser: QtWidgets.QTextBrowser | None, html: str) -> None:
    """Set HTML on a QTextBrowser with size cap and re-entrancy guard."""
    global _active_browser
    if browser is None:
        return
    text = html if isinstance(html, str) else str(html or "")
    if len(text) > MAX_HTML_CHARS:
        text = (
            text[: MAX_HTML_CHARS - 120]
            + "<p><i>… content truncated for stability …</i></p>"
        )
    if _active_browser is browser:
        return
    prev = _active_browser
    _active_browser = browser
    try:
        browser.setHtml(text)
    finally:
        _active_browser = prev
