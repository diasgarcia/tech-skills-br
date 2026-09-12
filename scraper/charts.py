"""Graficos compactos publicados no README por meio do GitHub Pages."""

from __future__ import annotations

import logging
import textwrap
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from matplotlib.ticker import MaxNLocator  # noqa: E402


BACKGROUND = "#0d1117"
PANEL = "#111820"
TEXT = "#f0f6fc"
MUTED = "#8b9aaa"
GRID = "#29313b"
BLUE = "#388bfd"
PURPLE = "#bc8cff"
FONT_STACK = ["Segoe UI", "DejaVu Sans", "sans-serif"]


@dataclass(frozen=True)
class ChartJob:
    """Campos minimos de uma vaga usados pelos graficos do README."""

    published_date: date | None
    area: str
    skills: tuple[str, ...] = ()


@dataclass(frozen=True)
class DailyActivity:
    dates: tuple[date, ...]
    jobs: tuple[int, ...]
    skills: tuple[int, ...]
    total_jobs: int
    period_jobs: int
    period_skills: int
    last_date: date


@dataclass(frozen=True)
class AreaSkillMatrix:
    areas: tuple[str, ...]
    area_sizes: tuple[int, ...]
    skills: tuple[str, ...]
    percentages: tuple[tuple[float, ...], ...]


def _style() -> None:
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": FONT_STACK,
            "figure.facecolor": BACKGROUND,
            "axes.facecolor": PANEL,
            "axes.edgecolor": GRID,
            "text.color": TEXT,
            "axes.labelcolor": MUTED,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "savefig.facecolor": BACKGROUND,
            "svg.fonttype": "none",
        }
    )


def _format_int(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def _format_pct(value: float) -> str:
    return f"{value:.1f}%".replace(".", ",")


def _hide_spines(ax) -> None:
    for spine in ax.spines.values():
        spine.set_visible(False)


def build_daily_activity(
    jobs: list[ChartJob], days: int = 30
) -> DailyActivity:
    """Agrupa vagas e habilidades distintas pela data de publicacao."""
    if days < 1:
        raise ValueError("O periodo precisa ter ao menos um dia.")

    dated_jobs = [job for job in jobs if job.published_date is not None]
    if not dated_jobs:
        raise ValueError("Nenhuma vaga com data de publicacao.")

    last_date = max(job.published_date for job in dated_jobs if job.published_date)
    first_date = last_date - timedelta(days=days - 1)
    dates = tuple(first_date + timedelta(days=offset) for offset in range(days))
    jobs_by_date: Counter[date] = Counter()
    skills_by_date: dict[date, set[str]] = defaultdict(set)

    for job in dated_jobs:
        published = job.published_date
        if published is None or published < first_date or published > last_date:
            continue
        jobs_by_date[published] += 1
        skills_by_date[published].update(skill for skill in job.skills if skill)

    job_counts = tuple(jobs_by_date[current] for current in dates)
    skill_counts = tuple(len(skills_by_date[current]) for current in dates)
    period_skills = len(set().union(*(skills_by_date[current] for current in dates)))
    return DailyActivity(
        dates=dates,
        jobs=job_counts,
        skills=skill_counts,
        total_jobs=len(jobs),
        period_jobs=sum(job_counts),
        period_skills=period_skills,
        last_date=last_date,
    )


def build_area_skill_matrix(
    jobs: list[ChartJob], top_areas: int = 6, top_skills: int = 6
) -> AreaSkillMatrix:
    """Seleciona e cruza dinamicamente as areas e habilidades mais frequentes."""
    if not jobs:
        raise ValueError("Nenhuma vaga para o heatmap.")

    area_counts = Counter(job.area for job in jobs if job.area)
    skill_counts: Counter[str] = Counter()
    for job in jobs:
        skill_counts.update(set(skill for skill in job.skills if skill))

    areas = tuple(
        name
        for name, _ in sorted(
            area_counts.items(), key=lambda item: (-item[1], item[0].casefold())
        )[:top_areas]
    )
    skills = tuple(
        name
        for name, _ in sorted(
            skill_counts.items(), key=lambda item: (-item[1], item[0].casefold())
        )[:top_skills]
    )
    if not areas or not skills:
        raise ValueError("Areas ou habilidades insuficientes para o heatmap.")

    intersections: Counter[tuple[str, str]] = Counter()
    selected_areas = set(areas)
    selected_skills = set(skills)
    for job in jobs:
        if job.area not in selected_areas:
            continue
        for skill in set(job.skills) & selected_skills:
            intersections[(job.area, skill)] += 1

    area_sizes = tuple(area_counts[area] for area in areas)
    percentages = tuple(
        tuple(
            100 * intersections[(area, skill)] / area_counts[area]
            for skill in skills
        )
        for area in areas
    )
    return AreaSkillMatrix(
        areas=areas,
        area_sizes=area_sizes,
        skills=skills,
        percentages=percentages,
    )


def chart_daily_jobs_and_skills(
    jobs: list[ChartJob], output_path: Path, days: int = 30
) -> Path:
    """Colunas de vagas e linha de habilidades distintas por dia."""
    data = build_daily_activity(jobs, days=days)
    _style()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(12, 4.8), dpi=180)
    fig.subplots_adjust(left=0.075, right=0.97, bottom=0.18, top=0.72)
    ax.bar(
        data.dates,
        data.jobs,
        width=0.82,
        color=BLUE,
        alpha=0.48,
        linewidth=0,
        zorder=2,
    )
    ax.plot(
        data.dates,
        data.skills,
        color=PURPLE,
        linewidth=2.8,
        solid_capstyle="round",
        zorder=3,
    )

    ax.set_xlim(data.dates[0] - timedelta(days=1), data.dates[-1] + timedelta(days=1))
    ax.set_ylim(bottom=0)
    ax.yaxis.set_major_locator(MaxNLocator(nbins=5, integer=True))
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
    ax.grid(axis="y", color=GRID, linewidth=0.8, alpha=0.75, zorder=1)
    ax.grid(axis="x", visible=False)
    ax.tick_params(axis="both", length=0, labelsize=9)
    ax.tick_params(axis="x", pad=10)
    _hide_spines(ax)

    fig.text(0.075, 0.91, "Vagas e habilidades por dia", fontsize=19, fontweight="bold")
    fig.text(
        0.075,
        0.835,
        f"Últimos {days} dias · agrupadas pela data de publicação",
        fontsize=10.5,
        color=MUTED,
    )
    fig.text(
        0.97,
        0.91,
        _format_int(data.period_jobs),
        fontsize=19,
        fontweight="bold",
        ha="right",
    )
    fig.text(
        0.97,
        0.835,
        f"vagas · {data.period_skills} habilidades distintas",
        fontsize=10.5,
        color=MUTED,
        ha="right",
    )
    legend = [
        Patch(facecolor=BLUE, alpha=0.48, label="Vagas coletadas"),
        Line2D(
            [0],
            [0],
            color=PURPLE,
            linewidth=2.8,
            label="Habilidades distintas identificadas",
        ),
    ]
    ax.legend(
        handles=legend,
        loc="upper left",
        bbox_to_anchor=(0, 1.15),
        frameon=False,
        ncol=2,
        fontsize=9.5,
        labelcolor=MUTED,
        handlelength=2,
        columnspacing=1.8,
    )
    fig.text(
        0.075,
        0.055,
        f"Base: {_format_int(data.total_jobs)} vagas · "
        f"atualizada em {data.last_date.strftime('%d/%m/%Y')}",
        fontsize=8.7,
        color=MUTED,
    )

    fig.savefig(output_path, facecolor=BACKGROUND)
    plt.close(fig)
    return output_path


def chart_area_skill_heatmap(
    jobs: list[ChartJob], output_path: Path, top_n: int = 6
) -> Path:
    """Heatmap das areas e habilidades mais citadas na base."""
    data = build_area_skill_matrix(jobs, top_areas=top_n, top_skills=top_n)
    _style()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    values = np.array(data.percentages)
    cmap = LinearSegmentedColormap.from_list(
        "tech_skills_heatmap", [PANEL, "#193b66", BLUE, PURPLE]
    )
    fig, ax = plt.subplots(figsize=(12, 6.2), dpi=180)
    fig.subplots_adjust(left=0.23, right=0.9, bottom=0.21, top=0.74)
    image = ax.imshow(values, aspect="auto", cmap=cmap, vmin=0, vmax=values.max())

    ax.set_xticks(range(len(data.skills)))
    ax.set_xticklabels(
        ["\n".join(textwrap.wrap(skill, 14)) for skill in data.skills],
        fontsize=9.5,
    )
    ax.set_yticks(range(len(data.areas)))
    ax.set_yticklabels(
        [
            f"{area}  ·  {_format_int(size)}"
            for area, size in zip(data.areas, data.area_sizes)
        ],
        fontsize=9.5,
    )
    ax.tick_params(axis="x", length=0, pad=12)
    ax.tick_params(axis="y", length=0, pad=12)
    _hide_spines(ax)

    threshold = values.max() * 0.48
    for row in range(values.shape[0]):
        for column in range(values.shape[1]):
            value = values[row, column]
            ax.text(
                column,
                row,
                "—" if value == 0 else _format_pct(value),
                ha="center",
                va="center",
                fontsize=10,
                fontweight="bold" if value >= threshold else "normal",
                color=TEXT if value >= threshold else "#c7d1dc",
            )

    colorbar = fig.colorbar(image, ax=ax, fraction=0.03, pad=0.035)
    colorbar.ax.tick_params(length=0, labelsize=8.5, colors=MUTED)
    colorbar.outline.set_visible(False)
    colorbar.set_label("Percentual das vagas da área", color=MUTED, labelpad=12)

    fig.text(
        0.08,
        0.92,
        "Onde as habilidades mais citadas aparecem",
        fontsize=19,
        fontweight="bold",
    )
    fig.text(
        0.08,
        0.85,
        f"{top_n} maiores áreas × {top_n} habilidades mais citadas na base",
        fontsize=10.5,
        color=MUTED,
    )

    fig.savefig(output_path, facecolor=BACKGROUND)
    plt.close(fig)
    return output_path


def export_readme_charts(
    jobs: list[ChartJob], output_dir: Path
) -> dict[str, Path]:
    """Gera os dois SVGs estaveis publicados pelo GitHub Pages."""
    if not jobs:
        return {}
    output_dir.mkdir(parents=True, exist_ok=True)
    return {
        "daily": chart_daily_jobs_and_skills(
            jobs, output_dir / "vagas-habilidades-30d.svg"
        ),
        "heatmap": chart_area_skill_heatmap(
            jobs, output_dir / "areas-habilidades.svg"
        ),
    }
