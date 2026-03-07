from __future__ import annotations

from pathlib import Path

import pytest

from dashboard_reporter import reporting


def test_write_pdf_raises_when_playwright_missing(tmp_path: Path, monkeypatch) -> None:
    html_path = tmp_path / "report.html"
    pdf_path = tmp_path / "report.pdf"
    html_path.write_text("<html><body><h1>Relatório</h1></body></html>", encoding="utf-8")

    def _raise() -> None:
        raise RuntimeError("Playwright não instalado. Instale com: pip install playwright && playwright install chromium")

    monkeypatch.setattr(reporting, "_get_sync_playwright", _raise)

    with pytest.raises(RuntimeError, match="Playwright não instalado"):
        reporting._write_pdf_from_html(html_path, pdf_path)


def test_write_pdf_uses_playwright_with_background(tmp_path: Path, monkeypatch) -> None:
    html_path = tmp_path / "report.html"
    pdf_path = tmp_path / "report.pdf"
    html_path.write_text("<html><body><h1>Relatório</h1></body></html>", encoding="utf-8")

    calls: dict[str, object] = {}

    class _FakePage:
        def goto(self, url: str, wait_until: str) -> None:
            calls["url"] = url
            calls["wait_until"] = wait_until

        def pdf(self, *, path: str, print_background: bool, format: str) -> None:
            calls["print_background"] = print_background
            calls["format"] = format
            Path(path).write_bytes(b"%PDF-1.4\n%fake\n")

    class _FakeBrowser:
        def __init__(self) -> None:
            self.page = _FakePage()

        def new_page(self) -> _FakePage:
            return self.page

        def close(self) -> None:
            calls["closed"] = True

    class _FakePlaywrightContext:
        def __enter__(self):
            class _Chromium:
                @staticmethod
                def launch() -> _FakeBrowser:
                    calls["launched"] = True
                    return _FakeBrowser()

            self.chromium = _Chromium()
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    monkeypatch.setattr(reporting, "_get_sync_playwright", lambda: (lambda: _FakePlaywrightContext()))

    reporting._write_pdf_from_html(html_path, pdf_path)

    assert pdf_path.exists()
    assert calls["launched"] is True
    assert calls["print_background"] is True
    assert calls["format"] == "A4"
