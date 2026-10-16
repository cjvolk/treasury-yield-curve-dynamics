"""Stage 1 entry point: load -> check -> save combined table -> draw charts.

Run from the project folder:  python main.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

import interpolate as I  # noqa: E402
import load_data as L  # noqa: E402
import mean_reversion as MR  # noqa: E402
import numpy as np  # noqa: E402
import plots  # noqa: E402

# Three dates to compare. main.py stops with an error if any is not in the data.
#   2000-03-31  short rates above long rates (inverted) before the 2001 recession
#   2021-03-31  short rates near zero, steeply upward-sloping curve
#   2023-07-03  deeply inverted 2-year vs 10-year after rapid rate rises
CURVE_DATES = ["2000-03-31", "2021-03-31", "2023-07-03"]

# Date for the interpolated par-yield curve (must be a date in the data).
INTERP_DATE = "2023-07-03"

FIG_DIR = ROOT / "outputs" / "figures"


def main() -> None:
    pd.set_option("display.width", 120)
    df = L.load_all()
    tenors = L.tenor_columns(df)

    print(f"Rows: {len(df)}   Dates: {df['date'].min().date()} to {df['date'].max().date()}")
    print(f"Sorted ascending: {df['date'].is_monotonic_increasing}")

    dups = L.check_duplicates(df)
    print(f"Duplicate dates: {len(dups)}")
    if len(dups):
        print(dups[["date", "source_file"]])
        raise SystemExit("Duplicate dates found - resolve them before continuing.")

    print("\nMissing values per tenor (NOT filled):")
    print(L.missing_report(df).to_string())
    empty = df[df[tenors].isna().all(axis=1)]
    if len(empty):
        print("\nDates with NO yields at all:", [d.date().isoformat() for d in empty["date"]])

    df = L.add_spread_bp(df)
    out_csv = L.PROCESSED_DIR / "yields_combined_percent.csv"
    df.to_csv(out_csv, index=False)
    print(f"\nSaved combined table (yields in PERCENT, spread in bp) -> {out_csv.relative_to(ROOT)}")

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    plots.plot_curves(df, CURVE_DATES, FIG_DIR / "yield_curves.png")
    plots.plot_spread(df, "spread_10Y_2Y_bp", FIG_DIR / "spread_10y_2y_bp.png")
    print(f"Saved charts -> {FIG_DIR.relative_to(ROOT)}/")

    # Stage 2: interpolated par-yield curve for one date.
    print(f"\nInterpolated par-yield curve for {INTERP_DATE}:")
    pts = I.observed_points(df, INTERP_DATE)
    print(pts.to_string(index=False))
    I.verify_curve(pts)
    lo, hi = pts["maturity_years"].min(), pts["maturity_years"].max()
    grid = np.unique(np.concatenate([np.linspace(lo, hi, 600), pts["maturity_years"]]))
    plots.plot_interpolated_curve(pts, grid, I.interpolate_par_curve(pts, grid),
                                  INTERP_DATE, FIG_DIR / "interpolated_par_curve.png")
    for yrs in (4.0, 15.0):  # example in-between maturities
        print(f"  Interpolated par yield at {yrs:g} years: "
              f"{I.interpolate_par_curve(pts, [yrs])[0]:.3f}%")
    print(f"Saved -> {(FIG_DIR / 'interpolated_par_curve.png').relative_to(ROOT)}")

    # Stage 3: does the 10Y-2Y spread revert toward its trailing average?
    run_mean_reversion(df)


def run_mean_reversion(df: pd.DataFrame) -> None:
    """Descriptive test of spread mean reversion. Not a trading strategy."""
    pd.set_option("display.float_format", lambda v: f"{v:,.3f}")
    s = MR.prepare_spread(df)
    k = MR.split_position(len(s))
    print(f"\nMean-reversion study: {len(s)} observations with a spread "
          f"(blank days dropped, not filled)")
    print(f"  initial period    : {s.index[0].date()} to {s.index[k - 1].date()} "
          f"({k} obs)")
    print(f"  evaluation period : {s.index[k].date()} to {s.index[-1].date()} "
          f"({len(s) - k} obs)")
    MR.verify_no_lookahead(s)

    sample = MR.build_sample(s)
    summary = MR.summarize(sample)
    buckets = MR.bucket_table(sample)
    print("\nCorrelation of z with the spread change over the next h observations")
    print("(negative = tends to move back toward the average)")
    print(summary.to_string(index=False))
    print("\nAverage spread change by signal bucket (bp; thresholds fixed at +/-1)")
    print(buckets.to_string(index=False))

    out = L.PROCESSED_DIR
    sample.to_csv(out / "mean_reversion_signal_and_forward_changes.csv")
    summary.to_csv(out / "mean_reversion_summary.csv", index=False)
    buckets.to_csv(out / "mean_reversion_buckets.csv", index=False)
    plots.plot_spread_band(sample, s.index[k], FIG_DIR / "spread_trailing_band.png")
    plots.plot_signal_scatter(sample, summary, MR.HORIZONS, FIG_DIR / "mean_reversion_scatter.png")
    print(f"\nSaved tables -> {out.relative_to(ROOT)}/, charts -> {FIG_DIR.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
