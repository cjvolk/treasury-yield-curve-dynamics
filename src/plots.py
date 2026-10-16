"""Charts for the Treasury par yield data.

Purpose of this file
--------------------
Turns the combined table from load_data.py into two figures:

1. `plot_curves`  - the yield curve (yield vs. maturity) on chosen dates.
2. `plot_spread` - the 10-year minus 2-year yield spread over time, in bp.

Yields are plotted in PERCENT (as published). Only the spread is in basis points.
Nothing here fills or interpolates missing data: a tenor with no published
value on a date is simply not drawn for that date.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # draw to files; no window needed
import matplotlib.pyplot as plt
import pandas as pd

from load_data import tenor_columns

# Colours: first three slots of a colour-blind-checked categorical palette,
# plus neutral inks for text/grid so text never takes a series colour.
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]  # blue, orange, aqua

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
    "font.family": "sans-serif",
    "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
    "text.color": INK, "axes.labelcolor": INK_2,
    "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.edgecolor": AXIS, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.axisbelow": True,
})

TENOR_LABELS = {"1M": "1 Mo", "2M": "2 Mo", "3M": "3 Mo", "4M": "4 Mo", "6M": "6 Mo",
                "1Y": "1 Yr", "2Y": "2 Yr", "3Y": "3 Yr", "5Y": "5 Yr", "7Y": "7 Yr",
                "10Y": "10 Yr", "20Y": "20 Yr", "30Y": "30 Yr"}


def plot_curves(df: pd.DataFrame, dates, out_path: Path) -> None:
    """Plot the par yield curve for each date in `dates` (must exist in df).

    The x-axis puts the maturities at EQUAL spacing (the usual way Treasury
    curves are shown). That is a category axis, not a true time axis: the gap
    between 1 Mo and 3 Mo looks the same as the gap between 10 Yr and 20 Yr.
    """
    dates = [pd.Timestamp(d) for d in dates]
    missing = [d.date() for d in dates if d not in set(df["date"])]
    if missing:
        raise ValueError(f"Dates not in dataset: {missing}")

    tenors = tenor_columns(df)
    pos = {t: i for i, t in enumerate(tenors)}
    indexed = df.set_index("date")

    fig, ax = plt.subplots(figsize=(10, 5.5))
    for color, d in zip(SERIES, dates):
        row = indexed.loc[d, tenors].dropna()  # only published points
        xs = [pos[t] for t in row.index]
        ax.plot(xs, row.values, color=color, linewidth=2, marker="o", markersize=7,
                markeredgecolor=SURFACE, markeredgewidth=1.5, label=d.strftime("%Y-%m-%d"))
        # Direct label at the right-hand end of each curve.
        ax.annotate(d.strftime("%b %d, %Y"), (xs[-1], row.values[-1]),
                    xytext=(8, 0), textcoords="offset points", va="center",
                    fontsize=9, color=INK_2)

    ax.set_xticks(range(len(tenors)))
    ax.set_xticklabels([TENOR_LABELS[t] for t in tenors], fontsize=9)
    ax.set_xlim(-0.5, len(tenors) - 1 + 1.8)  # room for end labels
    ax.set_xlabel("Maturity (equally spaced categories, not to scale)")
    ax.set_ylabel("Par yield (%, as published)")
    ax.set_ylim(bottom=-0.15)  # headroom so near-zero points are not clipped
    ax.grid(axis="x", visible=False)
    ax.set_title("US Treasury par yield curve on three dates", loc="left",
                 fontsize=13, color=INK)
    ax.legend(frameon=False, loc="center left", bbox_to_anchor=(0.01, 0.42), labelcolor=INK_2, title="Date",
              title_fontsize=9)
    fig.text(0.01, 0.01, "Source: US Treasury par yield curve rates. "
             "Par yields, not spot rates. Missing maturities are not drawn.",
             fontsize=8, color=MUTED)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_spread(df: pd.DataFrame, column: str, out_path: Path) -> None:
    """Plot the 10Y-2Y spread (basis points) through time, shading inversions.

    `column` is the spread column made by load_data.add_spread_bp. When the
    spread is negative the curve is "inverted": 2-year yields exceed 10-year
    yields.
    """
    s = df.set_index("date")[column]

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(s.index, s.values, color=SERIES[0], linewidth=1.5)
    ax.fill_between(s.index, s.values, 0, where=(s.values < 0), color=SERIES[1],
                    alpha=0.35, linewidth=0, interpolate=True)
    ax.axhline(0, color=INK_2, linewidth=1)
    ax.annotate("Inverted (10Y below 2Y)", xy=(pd.Timestamp("2023-01-01"), -70),
                xytext=(-8, -14), textcoords="offset points", ha="right",
                fontsize=9, color=INK_2)
    ax.set_ylabel("10-year minus 2-year par yield (basis points)")
    ax.set_xlabel("Date")
    ax.grid(axis="x", visible=False)
    ax.set_title("10Y - 2Y Treasury par yield spread (bp)", loc="left",
                 fontsize=13, color=INK)
    fig.text(0.01, 0.01, "Spread (bp) = (10Y % - 2Y %) x 100. 100 bp = 1 percentage point. "
             "Days where either yield is missing are left blank.",
             fontsize=8, color=MUTED)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_interpolated_curve(pts: pd.DataFrame, grid_years, grid_yields, date,
                            out_path: Path) -> None:
    """Dots = published par yields; line = linear interpolation between them.

    X axis is maturity in YEARS on a linear (to-scale) axis, so the
    straight interpolation segments look straight. The line spans only
    the published range (no extrapolation).
    """
    date = pd.Timestamp(date)
    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.plot(grid_years, grid_yields, color=SERIES[0], linewidth=2,
            label="Linear interpolation (par yield)", zorder=2)
    ax.scatter(pts["maturity_years"], pts["yield_pct"], s=64, color=SERIES[1],
               edgecolor=SURFACE, linewidth=1.5, zorder=3,
               label="Published par yields")
    ax.set_xticks([0, 1, 2, 3, 5, 7, 10, 15, 20, 25, 30])
    ax.set_xlim(-0.5, 31)
    ax.set_xlabel("Maturity (years, to scale; the 1M-6M points are bunched near zero)")
    ax.set_ylabel("Par yield (%, as published)")
    ax.grid(axis="x", visible=False)
    ax.set_title(f"Interpolated par-yield curve, {date:%b %d, %Y}", loc="left",
                 fontsize=13, color=INK)
    ax.legend(frameon=False, loc="best", labelcolor=INK_2)
    fig.text(0.01, 0.01, "Par-yield curve (not a spot-rate or forward-rate curve). "
             "Straight lines between published points; no extrapolation.",
             fontsize=8, color=MUTED)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_spread_band(sample: pd.DataFrame, split_date, out_path: Path) -> None:
    """Spread with its trailing 252-observation mean and +/-1 sd band.

    The band at each date is computed from earlier observations only. The grey
    region marks the evaluation period (latest 30% of observations).
    """
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.axvspan(split_date, sample.index.max(), color=GRID, alpha=0.6, linewidth=0)
    ax.fill_between(sample.index, sample["trail_mean_bp"] - sample["trail_sd_bp"],
                    sample["trail_mean_bp"] + sample["trail_sd_bp"],
                    color=SERIES[0], alpha=0.18, linewidth=0, label="Trailing mean ± 1 sd")
    ax.plot(sample.index, sample["trail_mean_bp"], color=SERIES[0], linewidth=1.5,
            label="Trailing 252-obs mean")
    ax.plot(sample.index, sample["spread_bp"], color=SERIES[1], linewidth=1,
            label="10Y − 2Y spread")
    ax.axhline(0, color=INK_2, linewidth=0.8)
    ax.text(split_date, ax.get_ylim()[1], "  evaluation period", va="top", fontsize=9,
            color=INK_2)
    ax.set_ylabel("Basis points")
    ax.set_xlabel("Date")
    ax.grid(axis="x", visible=False)
    ax.set_title("Spread vs. its trailing 252-observation average", loc="left",
                 fontsize=13, color=INK)
    ax.legend(frameon=False, loc="lower left", labelcolor=INK_2)
    fig.text(0.01, 0.01, "Mean and sd use only the 252 observations before each date.",
             fontsize=8, color=MUTED)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_signal_scatter(sample: pd.DataFrame, summary: pd.DataFrame, horizons,
                        out_path: Path) -> None:
    """z-score (x) vs. spread change over next h observations (y, bp).

    Rows: initial / evaluation period. Columns: horizons. Points overlap in time
    (neighbouring dates share most of their forward window), so they are NOT
    independent observations. The line is an ordinary least-squares fit.
    """
    import numpy as np

    fig, axes = plt.subplots(2, len(horizons), figsize=(12, 7), sharex=True)
    for r, period in enumerate(("initial", "evaluation")):
        for c, h in enumerate(horizons):
            ax = axes[r, c]
            part = sample[(sample["period"] == period) & sample[f"fwd_{h}"].notna()]
            ax.scatter(part["z"], part[f"fwd_{h}"], s=6, color=SERIES[0], alpha=0.25,
                       linewidth=0)
            st = summary[(summary["period"] == period) & (summary["horizon_obs"] == h)].iloc[0]
            xs = np.array([part["z"].min(), part["z"].max()])
            ys = part[f"fwd_{h}"].mean() + st["slope_bp_per_z"] * (xs - part["z"].mean())
            ax.plot(xs, ys, color=SERIES[1], linewidth=2)
            ax.axhline(0, color=INK_2, linewidth=0.8)
            ax.axvline(0, color=INK_2, linewidth=0.8)
            ax.set_title(f"{period.capitalize()}, next {h} obs   "
                         f"n={int(st['n'])}, corr={st['corr']:.2f}", loc="left",
                         fontsize=10, color=INK)
            if c == 0:
                ax.set_ylabel("Spread change (bp)")
            if r == 1:
                ax.set_xlabel("z-score vs trailing average")
    fig.suptitle("Signal vs. later spread change (overlapping windows)", x=0.01, ha="left",
                 fontsize=13, color=INK)
    fig.text(0.01, 0.005, "Spread changes, not returns or profits. Neighbouring points share "
             "most of their forward window, so the effective sample is much smaller than n.",
             fontsize=8, color=MUTED)
    fig.tight_layout(rect=(0, 0.02, 1, 0.97))
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
