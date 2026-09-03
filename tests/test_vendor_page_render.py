"""Tests for optional headless-browser vendor page fetch."""
from __future__ import annotations

from unittest import mock

import driver_catalog as dc
import vendor_page_render as vpr

JS_SHELL_HTML = (
    "<html><head>"
    '<script src="/etc.clientlibs/intel/clientlibs/bundles/resources/js/runtime.script.abc.bundle.js"></script>'
    "</head><body><div id=\"root\"></div>"
    + ("<!-- shell -->" * 200)
    + "</body></html>"
)

RENDERED_INTEL_HTML = """
Version
10.1.20398.8776 (Latest)
Date 4/15/2026
Download inf_install.exe
"""

NEXT_DATA_INTEL = """
<script id="__NEXT_DATA__">{"props":{"pageProps":{"driverVersion":"10.1.20398.8776"}}}</script>
"""


def test_page_likely_needs_js_render_shell() -> None:
    assert vpr.page_likely_needs_js_render(JS_SHELL_HTML) is True


def test_page_likely_needs_js_render_with_version() -> None:
    assert vpr.page_likely_needs_js_render(RENDERED_INTEL_HTML) is False


def test_intel_page_needs_js_render_when_empty_shell() -> None:
    assert dc._intel_page_needs_js_render(JS_SHELL_HTML, hint="chipset") is True


def test_parse_intel_version_from_embedded_json() -> None:
    ver = dc._parse_intel_version_from_embedded_json(NEXT_DATA_INTEL, hint="chipset")
    assert ver == "10.1.20398.8776"


def test_fetch_html_with_js_fallback_uses_http_when_parsed() -> None:
    def http_get(_url: str) -> tuple[bool, str]:
        return True, RENDERED_INTEL_HTML

    ok, body, method = vpr.fetch_html_with_js_fallback(
        "https://example.test/page",
        http_get,
        needs_js=lambda _h: False,
    )
    assert ok is True
    assert method == "http"
    assert "10.1.20398.8776" in body


def test_fetch_html_with_js_fallback_renders_when_shell() -> None:
    def http_get(_url: str) -> tuple[bool, str]:
        return True, JS_SHELL_HTML

    with mock.patch(
        "vendor_page_render.render_page_html",
        return_value=(True, RENDERED_INTEL_HTML),
    ):
        ok, body, method = vpr.fetch_html_with_js_fallback(
            "https://example.test/page",
            http_get,
            needs_js=vpr.page_likely_needs_js_render,
        )
    assert ok is True
    assert method == "js_render"
    assert "10.1.20398.8776" in body


def test_scrape_intel_download_page_uses_js_render(monkeypatch) -> None:
    with mock.patch(
        "driver_catalog._fetch_intel_page_html",
        return_value=(True, RENDERED_INTEL_HTML, "js_render"),
    ):
        ver, _date, _url, _direct = dc._scrape_intel_download_page(
            "https://www.intel.com/content/www/us/en/download/17608/intel-chipset-inf-utility.html",
            hint="chipset",
        )
    assert ver == "10.1.20398.8776"


def test_js_render_disabled_skips_browser() -> None:
    def http_get(_url: str) -> tuple[bool, str]:
        return True, JS_SHELL_HTML

    with mock.patch(
        "vendor_page_render.render_page_html",
    ) as render_mock:
        ok, body, method = vpr.fetch_html_with_js_fallback(
            "https://example.test/page",
            http_get,
            needs_js=vpr.page_likely_needs_js_render,
            settings={"vendor_js_render_fallback": False},
        )
    render_mock.assert_not_called()
    assert method == "http"
    assert body == JS_SHELL_HTML
    assert ok is True


def test_url_scheme_guard_blocks_non_http() -> None:
    assert vpr.url_scheme_allowed("https://example.test/page") is True
    assert vpr.url_scheme_allowed("http://example.test/page") is True
    assert vpr.url_scheme_allowed("file:///etc/passwd") is False
    assert vpr.url_scheme_allowed("javascript:alert(1)") is False

    ok, body, method = vpr.fetch_html_with_js_fallback(
        "file:///tmp/x",
        lambda _u: (True, "x"),
    )
    assert ok is False
    assert method == "http"
    assert "unsupported URL scheme" in body


def test_browser_from_registry(monkeypatch, tmp_path) -> None:
    import sys

    class FakeKey:
        """_browser_from_registry opens keys with `with`, so the double needs the protocol."""

        def __enter__(self):
            return self

        def __exit__(self, *_exc) -> bool:
            return False

    # _browser_from_registry only returns paths that exist, so point at a real file
    # rather than a hard-coded Edge install location.
    exe = tmp_path / "msedge.exe"
    exe.write_bytes(b"")

    fake_winreg = type("W", (), {
        "HKEY_LOCAL_MACHINE": 1,
        "HKEY_CURRENT_USER": 2,
        "OpenKey": staticmethod(lambda hive, subkey: FakeKey()),
        "QueryValueEx": staticmethod(lambda key, name: (f'"{exe}"', None)),
    })
    monkeypatch.setitem(sys.modules, "winreg", fake_winreg)
    monkeypatch.setattr(vpr.sys, "platform", "win32")
    path = vpr._browser_from_registry("msedge.exe")
    assert path is not None
    assert path.name.lower() == "msedge.exe"


if __name__ == "__main__":
    test_page_likely_needs_js_render_shell()
    test_page_likely_needs_js_render_with_version()
    test_intel_page_needs_js_render_when_empty_shell()
    test_parse_intel_version_from_embedded_json()
    test_fetch_html_with_js_fallback_uses_http_when_parsed()
    test_fetch_html_with_js_fallback_renders_when_shell()
    test_scrape_intel_download_page_uses_js_render(None)
    test_js_render_disabled_skips_browser()
    test_url_scheme_guard_blocks_non_http()
    print("vendor_page_render tests OK")
