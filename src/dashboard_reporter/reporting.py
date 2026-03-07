from __future__ import annotations

import json
import importlib.resources as resources
import os
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import PatchCollection
from matplotlib.colors import Normalize
from matplotlib.patches import Polygon
from jinja2 import Environment, PackageLoader, select_autoescape

from .models import NormalizationResult, ReportArtifacts, RunContext
from .utils import ensure_dir

_BRAZIL_STATE_CODES = {
    "AC",
    "AL",
    "AP",
    "AM",
    "BA",
    "CE",
    "DF",
    "ES",
    "GO",
    "MA",
    "MT",
    "MS",
    "MG",
    "PA",
    "PB",
    "PR",
    "PE",
    "PI",
    "RJ",
    "RN",
    "RS",
    "RO",
    "RR",
    "SC",
    "SP",
    "SE",
    "TO",
}


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


def _extract_uf_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        raw_value = str(row.get("valor", "")).strip().upper()
        amount = int(row.get("quantidade", 0))

        if raw_value in _BRAZIL_STATE_CODES:
            counts[raw_value] = amount
            continue

        token = raw_value[:2]
        if token in _BRAZIL_STATE_CODES:
            counts[token] = amount

    return counts


def _state_geojson_path() -> Path:
    return Path(resources.files("dashboard_reporter") / "assets" / "brazil_states.geojson")


def _iter_outer_rings(geometry: dict[str, Any]) -> list[list[tuple[float, float]]]:
    gtype = geometry.get("type")
    coordinates = geometry.get("coordinates", [])
    rings: list[list[tuple[float, float]]] = []

    if gtype == "Polygon":
        if coordinates:
            rings.append([(float(lon), float(lat)) for lon, lat in coordinates[0]])
    elif gtype == "MultiPolygon":
        for polygon in coordinates:
            if polygon:
                rings.append([(float(lon), float(lat)) for lon, lat in polygon[0]])

    return rings


def _polygon_area_centroid(points: list[tuple[float, float]]) -> tuple[float, tuple[float, float]]:
    if len(points) < 3:
        if not points:
            return 0.0, (0.0, 0.0)
        x_mean = sum(point[0] for point in points) / len(points)
        y_mean = sum(point[1] for point in points) / len(points)
        return 0.0, (x_mean, y_mean)

    area_term = 0.0
    cx_term = 0.0
    cy_term = 0.0

    for idx in range(len(points)):
        x0, y0 = points[idx]
        x1, y1 = points[(idx + 1) % len(points)]
        cross = (x0 * y1) - (x1 * y0)
        area_term += cross
        cx_term += (x0 + x1) * cross
        cy_term += (y0 + y1) * cross

    area = area_term / 2.0
    if abs(area) < 1e-9:
        x_mean = sum(point[0] for point in points) / len(points)
        y_mean = sum(point[1] for point in points) / len(points)
        return 0.0, (x_mean, y_mean)

    centroid_x = cx_term / (6.0 * area)
    centroid_y = cy_term / (6.0 * area)
    return abs(area), (centroid_x, centroid_y)


def _plot_brazil_state_map(uf_counts: dict[str, int], output_path: Path) -> None:
    geojson_path = _state_geojson_path()
    geojson_data = json.loads(geojson_path.read_text(encoding="utf-8"))

    patches: list[Polygon] = []
    patch_values: list[int] = []
    labels: list[tuple[str, int, float, float]] = []

    min_lon = 999.0
    max_lon = -999.0
    min_lat = 999.0
    max_lat = -999.0

    for feature in geojson_data.get("features", []):
        properties = feature.get("properties", {})
        uf = str(properties.get("sigla", "")).strip().upper()
        if uf not in _BRAZIL_STATE_CODES:
            continue

        rings = _iter_outer_rings(feature.get("geometry", {}))
        if not rings:
            continue

        count = int(uf_counts.get(uf, 0))
        best_area = -1.0
        best_centroid = (0.0, 0.0)

        for ring in rings:
            if len(ring) < 3:
                continue

            patches.append(Polygon(ring, closed=True))
            patch_values.append(count)

            for lon, lat in ring:
                min_lon = min(min_lon, lon)
                max_lon = max(max_lon, lon)
                min_lat = min(min_lat, lat)
                max_lat = max(max_lat, lat)

            area, centroid = _polygon_area_centroid(ring)
            if area > best_area:
                best_area = area
                best_centroid = centroid

        labels.append((uf, count, best_centroid[0], best_centroid[1]))

    if not patches:
        return

    vmax = max(patch_values) if patch_values else 1
    if vmax <= 0:
        vmax = 1

    fig, ax = plt.subplots(figsize=(9, 9))

    norm = Normalize(vmin=0, vmax=vmax)
    cmap = matplotlib.colormaps["YlOrRd"]
    collection = PatchCollection(patches, cmap=cmap, norm=norm, edgecolor="#1f2937", linewidths=0.45)
    collection.set_array(patch_values)
    ax.add_collection(collection)

    lon_margin = (max_lon - min_lon) * 0.03
    lat_margin = (max_lat - min_lat) * 0.03

    ax.set_xlim(min_lon - lon_margin, max_lon + lon_margin)
    ax.set_ylim(min_lat - lat_margin, max_lat + lat_margin)
    ax.set_aspect("equal", adjustable="box")
    ax.axis("off")
    ax.set_title("Mapa do Brasil por estado (quantidade de pessoas)", fontsize=13, pad=12)

    for uf, count, lon, lat in labels:
        ax.text(
            lon,
            lat,
            f"{uf}\n{count}",
            ha="center",
            va="center",
            fontsize=6,
            color="#0f172a",
            bbox={"boxstyle": "round,pad=0.15", "fc": "white", "ec": "none", "alpha": 0.75},
        )

    colorbar = fig.colorbar(collection, ax=ax, fraction=0.032, pad=0.02)
    colorbar.set_label("Quantidade")

    fig.tight_layout()
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _get_sync_playwright() -> Callable[..., Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Playwright não instalado. Instale com: pip install playwright && playwright install chromium"
        ) from exc
    return sync_playwright


def _write_pdf_with_playwright(html_path: Path, output_path: Path) -> None:
    sync_playwright = _get_sync_playwright()

    try:
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch()
            except Exception as exc:
                raise RuntimeError(
                    "Chromium do Playwright não encontrado. Execute: playwright install chromium"
                ) from exc

            try:
                page = browser.new_page()
                page.goto(html_path.resolve().as_uri(), wait_until="networkidle")
                page.pdf(path=str(output_path), print_background=True, format="A4")
            finally:
                browser.close()
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"Falha ao gerar PDF via Playwright: {exc}") from exc


def _write_pdf_with_xhtml2pdf(html_path: Path, output_path: Path) -> None:
    try:
        from xhtml2pdf import pisa
    except ModuleNotFoundError as exc:
        raise RuntimeError("xhtml2pdf não instalado. Instale com: pip install xhtml2pdf") from exc

    html_content = html_path.read_text(encoding="utf-8")
    # xhtml2pdf does not support CSS variables. Resolve known theme vars first.
    html_content = (
        html_content.replace("var(--bg)", "#f4f6f8")
        .replace("var(--paper)", "#ffffff")
        .replace("var(--ink)", "#102a43")
        .replace("var(--muted)", "#486581")
        .replace("var(--accent)", "#114b5f")
        .replace("var(--line)", "#d9e2ec")
    )
    base_dir = html_path.parent.resolve()

    def _link_callback(uri: str, _: str | None = None) -> str:
        parsed = urlparse(uri)
        if parsed.scheme in {"http", "https", "data"}:
            return uri

        if parsed.scheme == "file":
            return parsed.path

        normalized = uri.replace("\\", "/").lstrip("/")
        return str((base_dir / normalized).resolve())

    with output_path.open("wb") as pdf_file:
        result = pisa.CreatePDF(
            src=html_content,
            dest=pdf_file,
            encoding="utf-8",
            link_callback=_link_callback,
        )

    if result.err:
        raise RuntimeError("Falha ao gerar PDF via xhtml2pdf")


def _write_pdf_from_html(html_path: Path, output_path: Path) -> None:
    engine = os.getenv("DASHBOARD_REPORTER_PDF_ENGINE", "auto").strip().lower()

    if engine == "playwright":
        _write_pdf_with_playwright(html_path, output_path)
        return

    if engine in {"xhtml2pdf", "pisa"}:
        _write_pdf_with_xhtml2pdf(html_path, output_path)
        return

    if engine != "auto":
        raise RuntimeError("DASHBOARD_REPORTER_PDF_ENGINE inválido. Use: auto, xhtml2pdf ou playwright")

    last_error: Exception | None = None
    for backend in (_write_pdf_with_xhtml2pdf, _write_pdf_with_playwright):
        try:
            backend(html_path, output_path)
            return
        except Exception as exc:  # pragma: no cover - fallback path
            last_error = exc

    raise RuntimeError(
        "Nenhum backend de PDF disponível. Instale xhtml2pdf (recomendado) "
        "ou Playwright+Chromium. Último erro: "
        f"{last_error}"
    )


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

    demografia = metrics.get("demografia", {})
    for dimension, rows in demografia.items():
        if not rows:
            continue

        top_rows = rows[:10]
        labels = [str(item["valor"]) for item in top_rows]
        values = [int(item["quantidade"]) for item in top_rows]

        chart_name = f"demografia_{dimension}.png"
        chart_path = charts_dir / chart_name
        _plot_bar_chart(labels, values, f"Distribuição por {dimension}", chart_path)
        chart_paths[f"demografia_{dimension}"] = chart_path

    regiao_rows = demografia.get("regiao", [])
    if regiao_rows:
        uf_counts = _extract_uf_counts(regiao_rows)
        if uf_counts:
            map_path = charts_dir / "mapa_brasil_regioes.png"
            _plot_brazil_state_map(uf_counts, map_path)
            if map_path.exists():
                chart_paths["mapa_brasil_regioes"] = map_path

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
        demografia=demografia,
        qualidade=metrics.get("qualidade_dados", {}),
        charts={key: str(path.relative_to(context.output_dir)).replace("\\", "/") for key, path in chart_paths.items()},
        candidates=[candidate.to_dict() for candidate in normalization.candidates[:30]],
    )

    html_path = context.output_dir / "report.html"
    pdf_path = context.output_dir / "report.pdf"

    html_path.write_text(report_html, encoding="utf-8")
    _write_pdf_from_html(html_path, pdf_path)

    return ReportArtifacts(html_path=html_path, pdf_path=pdf_path, chart_paths=chart_paths)
