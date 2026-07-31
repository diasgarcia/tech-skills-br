"""Graficos: distribuicao de vagas por area e principais tecnologias por area.

Decisoes de forma (e por que):

- **Barras horizontais, nao pizza.** A tarefa do leitor e comparar grandezas e os
  nomes das areas sao longos.
- **Uma cor so, nao um degrade por valor.** Areas de tecnologia sao categorias
  *nominais* (nao tem ordem natural). Pintar a barra maior mais escura gastaria o
  canal de cor repetindo o que o comprimento da barra ja diz.
- **Small multiples para as tecnologias.** Um painel por area, em vez de 8 cores
  disputando a mesma figura -- a pergunta e "quais techs nesta area?", e cada
  painel responde isso sozinho.
- Valor rotulado na ponta de cada barra, entao nao ha grade nem eixo x: rotulo
  direto vem antes de gridline.
"""

from __future__ import annotations

import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # sem interface grafica: so grava arquivo
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Rectangle  # noqa: E402

from .export import build_ranking  # noqa: E402
from .models import Job  # noqa: E402
from .skills import skills_by_area  # noqa: E402

logger = logging.getLogger(__name__)

# Paleta (modo claro). Cores de marca ficam nas barras; texto usa tokens de texto.
SURFACE = "#fcfcfb"
SERIES_1 = "#2a78d6"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"

FONT_STACK = ["Segoe UI", "DejaVu Sans", "sans-serif"]
BAR_THICKNESS = 0.46  # fracao da faixa: marca fina, com ar entre as barras
CORNER_PX = 9  # raio do canto arredondado, em pixels da imagem final


def _style() -> None:
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": FONT_STACK,
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "savefig.facecolor": SURFACE,
            "axes.edgecolor": INK_MUTED,
            "text.color": INK_PRIMARY,
        }
    )


def _add_rounded_bars(ax, values: list[float], color: str = SERIES_1,
                      height: float = BAR_THICKNESS) -> None:
    """Desenha as barras com a ponta do dado arredondada e a base quadrada.

    O raio e calculado em PIXELS e convertido para unidades de dado de cada eixo.
    Fazer o contrario (raio fixo em unidades de dado, como e o obvio no
    matplotlib) deforma o canto quando os eixos tem escalas diferentes: num
    painel cujo eixo x vai so ate 3, um raio em unidades de dado vira uma
    "pilula" horizontal. Por isso esta funcao roda depois do layout, quando as
    dimensoes reais do eixo em pixels ja existem.
    """
    ax.figure.canvas.draw()
    bbox = ax.get_window_extent()
    x_min, x_max = ax.get_xlim()
    y_min, y_max = ax.get_ylim()
    x_per_px = (x_max - x_min) / max(bbox.width, 1)
    y_per_px = (y_max - y_min) / max(bbox.height, 1)

    bar_height_px = height / y_per_px
    radius_px = min(CORNER_PX, bar_height_px / 2)
    radius_y = radius_px * y_per_px

    for i, value in enumerate(values):
        if value <= 0:
            continue
        radius_x = min(radius_px * x_per_px, value / 2)
        # mutation_aspect estica o arredondamento no eixo y: com isso o raio
        # fica igual (em pixels) nas duas direcoes.
        aspect = radius_y / radius_x if radius_x > 0 else 1.0
        ax.add_patch(
            FancyBboxPatch(
                (0, i - height / 2),
                max(value - radius_x, 1e-9),
                height,
                boxstyle=f"round,pad=0,rounding_size={radius_x}",
                mutation_aspect=aspect,
                facecolor=color,
                edgecolor="none",
                linewidth=0,
                zorder=2,
            )
        )
        # Quadra a extremidade encostada na linha de base.
        ax.add_patch(
            Rectangle(
                (0, i - height / 2), radius_x, height,
                facecolor=color, edgecolor="none", zorder=2,
            )
        )


def _bare_axes(ax) -> None:
    """Remove tudo que nao e dado: sem grade, sem eixo x, sem moldura."""
    for side in ("top", "right", "bottom", "left"):
        ax.spines[side].set_visible(False)
    ax.set_xticks([])
    ax.tick_params(axis="y", length=0, pad=8)
    ax.grid(False)


def chart_areas(jobs: list[Job], output_path: Path, subtitle: str = "") -> Path:
    """Grafico 1 -- distribuicao das vagas por area de tecnologia."""
    _style()
    ranking = build_ranking(jobs)
    if not ranking:
        raise ValueError("Sem vagas para plotar.")

    # Menor em cima -> maior embaixo fica invertido em barh; plotamos ascendente.
    rows = list(reversed(ranking))
    labels = [r["area"] for r in rows]
    values = [r["vagas"] for r in rows]
    percents = [r["percentual"] for r in rows]

    height = max(3.0, 0.42 * len(rows) + 1.1)
    fig, ax = plt.subplots(figsize=(9.5, height), dpi=200)

    for i, (value, pct) in enumerate(zip(values, percents)):
        ax.text(
            value + max(values) * 0.015, i, f"{value}  ({pct}%)",
            va="center", ha="left", fontsize=10, color=INK_SECONDARY,
        )

    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=11, color=INK_PRIMARY)
    ax.set_xlim(0, max(values) * 1.22)
    ax.set_ylim(-0.6, len(rows) - 0.4)
    _bare_axes(ax)

    # Titulo preso ao eixo (e nao a figura): assim o tight_layout reserva o
    # espaco certo e nao sobra faixa vazia entre o subtitulo e a primeira barra.
    ax.set_title(
        "Vagas júnior de tecnologia por área",
        loc="left", fontsize=15, fontweight="600", color=INK_PRIMARY,
        pad=34 if subtitle else 16,
    )
    if subtitle:
        ax.text(
            0, 1.012, subtitle, transform=ax.transAxes,
            ha="left", va="bottom", fontsize=9.5, color=INK_MUTED,
        )

    fig.tight_layout()
    _add_rounded_bars(ax, values)
    fig.savefig(output_path, bbox_inches="tight", pad_inches=0.32)
    plt.close(fig)
    return output_path


def chart_skills(
    jobs: list[Job],
    output_path: Path,
    top_areas: int = 6,
    top_skills: int = 8,
    min_jobs: int = 5,
    subtitle: str = "",
) -> Path | None:
    """Grafico 2 -- small multiples: principais tecnologias por area."""
    _style()
    per_area = skills_by_area(jobs, top_n=top_skills)
    area_sizes = {r["area"]: r["vagas"] for r in build_ranking(jobs)}

    # Areas com volume suficiente para a contagem significar alguma coisa.
    areas = [
        a for a in sorted(per_area, key=lambda a: -area_sizes.get(a, 0))
        if area_sizes.get(a, 0) >= min_jobs and per_area[a]
    ][:top_areas]

    if not areas:
        logger.warning("Nenhuma area com vagas suficientes para o grafico de skills.")
        return None

    cols = 2 if len(areas) > 1 else 1
    rows = (len(areas) + cols - 1) // cols
    fig, axes = plt.subplots(
        rows, cols, figsize=(11.5, 2.55 * rows + 1.5), dpi=200, squeeze=False
    )

    panels: list[tuple] = []
    for idx, ax in enumerate(axes.flat):
        if idx >= len(areas):
            ax.set_visible(False)
            continue

        area = areas[idx]
        data = list(reversed(per_area[area]))
        names = [d[0] for d in data]
        counts = [d[1] for d in data]
        panels.append((ax, counts))

        for i, count in enumerate(counts):
            ax.text(
                count + max(counts) * 0.04, i, str(count),
                va="center", ha="left", fontsize=9, color=INK_SECONDARY,
            )

        ax.set_yticks(range(len(names)))
        ax.set_yticklabels(names, fontsize=9.5, color=INK_PRIMARY)
        ax.set_xlim(0, max(counts) * 1.26)
        ax.set_ylim(-0.6, len(names) - 0.4)
        _bare_axes(ax)
        ax.set_title(
            f"{area}  ·  {area_sizes.get(area, 0)} vagas",
            loc="left", fontsize=11.5, fontweight="600",
            color=INK_PRIMARY, pad=10,
        )

    fig.suptitle(
        "Tecnologias mais pedidas em vagas júnior, por área",
        x=0.02, y=0.985, ha="left", fontsize=15, fontweight="600",
        color=INK_PRIMARY,
    )
    note = subtitle or "Número de vagas da área que citam cada tecnologia"
    fig.text(0.02, 0.952, note, ha="left", fontsize=9.5, color=INK_MUTED)

    fig.tight_layout(rect=(0, 0, 1, 0.93), h_pad=2.6, w_pad=4.0)
    for ax, counts in panels:
        _add_rounded_bars(ax, counts)
    fig.savefig(output_path, bbox_inches="tight", pad_inches=0.35)
    plt.close(fig)
    return output_path


def export_charts(jobs: list[Job], output_dir: Path, stamp: str,
                  subtitle: str = "") -> dict[str, Path]:
    """Gera os dois graficos e devolve os caminhos."""
    output_dir.mkdir(parents=True, exist_ok=True)
    files: dict[str, Path] = {}

    files["chart_areas"] = chart_areas(
        jobs, output_dir / f"grafico_areas_{stamp}.png", subtitle=subtitle
    )
    skills_path = chart_skills(
        jobs, output_dir / f"grafico_skills_{stamp}.png"
    )
    if skills_path:
        files["chart_skills"] = skills_path
    return files
