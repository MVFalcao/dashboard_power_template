from __future__ import annotations

from pathlib import Path

import pytest

from dashboard_reporter import reporting


def test_write_pdf_uses_xhtml2pdf_when_selected(tmp_path: Path, monkeypatch) -> None:
    html_path = tmp_path / "report.html"
    pdf_path = tmp_path / "report.pdf"
    html_path.write_text("<html><body><h1>Relatório</h1></body></html>", encoding="utf-8")

    calls: dict[str, bool] = {"xhtml": False}

    def _fake_xhtml(_: Path, output: Path) -> None:
        calls["xhtml"] = True
        output.write_bytes(b"%PDF-1.4\n%xhtml2pdf\n")

    monkeypatch.setenv("DASHBOARD_REPORTER_PDF_ENGINE", "xhtml2pdf")
    monkeypatch.setattr(reporting, "_write_pdf_with_xhtml2pdf", _fake_xhtml)

    reporting._write_pdf_from_html(html_path, pdf_path)

    assert calls["xhtml"] is True
    assert pdf_path.exists()


def test_write_pdf_auto_falls_back_to_playwright(tmp_path: Path, monkeypatch) -> None:
    html_path = tmp_path / "report.html"
    pdf_path = tmp_path / "report.pdf"
    html_path.write_text("<html><body><h1>Relatório</h1></body></html>", encoding="utf-8")

    calls: dict[str, bool] = {"playwright": False}

    def _missing_xhtml(_: Path, __: Path) -> None:
        raise RuntimeError("xhtml2pdf não instalado")

    def _fake_playwright(_: Path, output: Path) -> None:
        calls["playwright"] = True
        output.write_bytes(b"%PDF-1.4\n%playwright\n")

    monkeypatch.delenv("DASHBOARD_REPORTER_PDF_ENGINE", raising=False)
    monkeypatch.setattr(reporting, "_write_pdf_with_xhtml2pdf", _missing_xhtml)
    monkeypatch.setattr(reporting, "_write_pdf_with_playwright", _fake_playwright)

    reporting._write_pdf_from_html(html_path, pdf_path)

    assert calls["playwright"] is True
    assert pdf_path.exists()


def test_write_pdf_rejects_invalid_engine(tmp_path: Path, monkeypatch) -> None:
    html_path = tmp_path / "report.html"
    pdf_path = tmp_path / "report.pdf"
    html_path.write_text("<html><body><h1>Relatório</h1></body></html>", encoding="utf-8")

    monkeypatch.setenv("DASHBOARD_REPORTER_PDF_ENGINE", "invalid")

    with pytest.raises(RuntimeError, match="DASHBOARD_REPORTER_PDF_ENGINE inválido"):
        reporting._write_pdf_from_html(html_path, pdf_path)
