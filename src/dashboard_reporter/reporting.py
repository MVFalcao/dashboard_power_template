from __future__ import annotations

from html import unescape
import math
import re
from pathlib import Path
from textwrap import wrap
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from jinja2 import Environment, PackageLoader, select_autoescape

from .models import NormalizationResult, ReportArtifacts, RunContext
from .utils import ensure_dir


def _plot_bar_chart(labels: list[str], values: list[int], title: str, output_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 4.5))
    bars = ax.bar(labels, values, color="#114B5F")
    ax.set_title(title)
    ax.set_ylabel("Quantidade")
    ax.grid(axis="y", linestyle="--", alpha=0.3)
    ax.set_axisbelow(True)

    for bar in bars:
        height = bar.get_height()
        ax.annotate(
            f"{int(height)}",
            xy=(bar.get_x() + bar.get_width() / 2, height),
            xytext=(0, 3),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=9,
        )

    fig.tight_layout()
    fig.savefig(output_path, dpi=140)
    plt.close(fig)


def _html_to_plain_text(html: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\\1>", "", html, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<br\\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</(p|h1|h2|h3|h4|li|tr|section|div|table|thead|tbody)>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_pdf_stream(lines: list[str]) -> str:
    if not lines:
        lines = [""]

    commands = ["BT", "/F1 10 Tf", "14 TL", "50 790 Td"]
    first = True
    for line in lines:
        safe = _pdf_escape(line)
        if first:
            commands.append(f"({safe}) Tj")
            first = False
        else:
            commands.append("T*")
            commands.append(f"({safe}) Tj")
    commands.append("ET")
    return "\n".join(commands)


def _write_simple_pdf_from_html(html: str, output_path: Path) -> None:
    text = _html_to_plain_text(html)
    wrapped_lines: list[str] = []

    for paragraph in text.splitlines():
        chunk = paragraph.strip()
        if not chunk:
            wrapped_lines.append("")
            continue
        wrapped_lines.extend(wrap(chunk, width=95) or [""])

    lines_per_page = 48
    pages = [wrapped_lines[idx : idx + lines_per_page] for idx in range(0, len(wrapped_lines), lines_per_page)] or [[""]]

    objects: list[str] = ["", ""]

    def add_obj(payload: str) -> int:
        objects.append(payload)
        return len(objects)

    font_obj = add_obj("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    page_refs: list[int] = []

    for page_lines in pages:
        stream = _build_pdf_stream(page_lines)
        stream_payload = f"<< /Length {len(stream.encode('latin-1', errors='replace'))} >>\nstream\n{stream}\nendstream"
        content_obj = add_obj(stream_payload)
        page_obj = add_obj(
            "<< /Type /Page /Parent 2 0 R "
            f"/MediaBox [0 0 595 842] /Resources << /Font << /F1 {font_obj} 0 R >> >> "
            f"/Contents {content_obj} 0 R >>"
        )
        page_refs.append(page_obj)

    kids = " ".join(f"{obj} 0 R" for obj in page_refs)
    objects[1] = f"<< /Type /Pages /Count {len(page_refs)} /Kids [{kids}] >>"
    objects[0] = "<< /Type /Catalog /Pages 2 0 R >>"

    output = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    offsets = [0]

    for obj_index, payload in enumerate(objects, start=1):
        offsets.append(len(output))
        output += f"{obj_index} 0 obj\n".encode("latin-1")
        output += payload.encode("latin-1", errors="replace")
        output += b"\nendobj\n"

    xref_position = len(output)
    output += f"xref\n0 {len(objects) + 1}\n".encode("latin-1")
    output += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        output += f"{offset:010d} 00000 n \n".encode("latin-1")
    output += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_position}\n%%EOF"
    ).encode("latin-1")

    output_path.write_bytes(output)


def _write_pdf_from_html(html: str, output_path: Path, base_url: Path) -> None:
    try:
        from weasyprint import HTML

        HTML(string=html, base_url=str(base_url)).write_pdf(str(output_path))
    except Exception:
        _write_simple_pdf_from_html(html, output_path)


def generate_report(
    metrics: dict[str, Any],
    normalization: NormalizationResult,
    context: RunContext,
) -> ReportArtifacts:
    charts_dir = ensure_dir(context.output_dir / "charts")
    chart_paths: dict[str, Path] = {}

    funnel = metrics.get("funil", {})
    funnel_labels = ["APROVADO", "NEGADO", "EM_ANALISE", "SEM_STATUS"]
    funnel_values = [int(funnel.get(label, 0)) for label in funnel_labels]

    funnel_chart = charts_dir / "funil.png"
    _plot_bar_chart(funnel_labels, funnel_values, "Funil de Candidatos", funnel_chart)
    chart_paths["funil"] = funnel_chart

    for dimension, rows in metrics.get("demografia", {}).items():
        if not rows:
            continue

        top_rows = rows[:10]
        labels = [str(item["valor"]) for item in top_rows]
        values = [int(item["quantidade"]) for item in top_rows]

        chart_name = f"demografia_{dimension}.png"
        chart_path = charts_dir / chart_name
        _plot_bar_chart(labels, values, f"Distribuição por {dimension}", chart_path)
        chart_paths[f"demografia_{dimension}"] = chart_path

    env = Environment(
        loader=PackageLoader("dashboard_reporter", "templates"),
        autoescape=select_autoescape(["html", "xml"]),
    )

    template = env.get_template("report.html.j2")

    report_html = template.render(
        run_id=context.run_id,
        run_date=context.run_date,
        source_file=str(context.input_path),
        resumo=metrics.get("resumo", {}),
        funil=metrics.get("funil", {}),
        demografia=metrics.get("demografia", {}),
        qualidade=metrics.get("qualidade_dados", {}),
        charts={key: str(path.relative_to(context.output_dir)).replace("\\", "/") for key, path in chart_paths.items()},
        candidates=[candidate.to_dict() for candidate in normalization.candidates[:30]],
    )

    html_path = context.output_dir / "report.html"
    pdf_path = context.output_dir / "report.pdf"

    html_path.write_text(report_html, encoding="utf-8")
    _write_pdf_from_html(report_html, pdf_path, context.output_dir)

    return ReportArtifacts(html_path=html_path, pdf_path=pdf_path, chart_paths=chart_paths)
