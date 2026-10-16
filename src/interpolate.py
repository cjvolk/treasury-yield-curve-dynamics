"""Linear interpolation of a par-yield curve for one date.

Purpose of this file
--------------------
The Treasury publishes par yields at only 11-13 fixed maturities (1 month,
3 months, 1 year, ...). Sometimes we want a yield at a maturity in between,
such as 4 years. Interpolation estimates it from the two nearest published
points.

What the result is, and is not
------------------------------
The output is an interpolated PAR-YIELD curve: par yield (percent) versus
maturity (years). It is NOT a spot-rate (zero-coupon) curve and NOT a
forward-rate curve. Turning par yields into spot or forward rates requires a
different calculation (bootstrapping) that is not done here.

Units
-----
* Maturity is in YEARS everywhere (1 month = 1/12 = 0.0833 years).
* Yields stay in PERCENT, as published.
"""

import numpy as np
import pandas as pd

from load_data import MATURITY_YEARS, tenor_columns


def observed_points(df: pd.DataFrame, date) -> pd.DataFrame:
    """Published (maturity_years, yield_pct) points for one date, sorted by maturity.

    Maturities with no published value that day are dropped, not filled.
    """
    date = pd.Timestamp(date)
    row = df.loc[df["date"] == date]
    if row.empty:
        raise ValueError(f"{date.date()} is not in the dataset")
    row = row.iloc[0]
    pts = pd.DataFrame(
        {"tenor": t, "maturity_years": MATURITY_YEARS[t], "yield_pct": row[t]}
        for t in tenor_columns(df)
    ).dropna(subset=["yield_pct"])
    if len(pts) < 2:
        raise ValueError(f"{date.date()} has fewer than 2 published yields")
    return pts.sort_values("maturity_years").reset_index(drop=True)


def interpolate_par_curve(pts: pd.DataFrame, maturities_years) -> np.ndarray:
    """Linearly interpolate par yields (%) at the requested maturities (years).

    Linear interpolation: for a maturity m between published points
    (m0, y0) and (m1, y1), the estimate is

        y = y0 + (y1 - y0) * (m - m0) / (m1 - m0)

    i.e. a straight line joining the two neighbouring points.

    No extrapolation: any maturity outside [shortest, longest] published
    maturity raises an error instead of being guessed (np.interp would
    otherwise silently repeat the end value).
    """
    m = np.asarray(maturities_years, dtype=float)
    lo, hi = pts["maturity_years"].min(), pts["maturity_years"].max()
    if (m < lo - 1e-12).any() or (m > hi + 1e-12).any():
        raise ValueError(
            f"Requested maturities outside the observed range "
            f"[{lo:.4f}, {hi:.4f}] years; extrapolation is not allowed")
    return np.interp(m, pts["maturity_years"], pts["yield_pct"])


def verify_curve(pts: pd.DataFrame) -> None:
    """Check the interpolated curve against the original data. Raises if wrong.

    1. At every published maturity the curve equals the published yield.
    2. A hand-computed midpoint between two neighbours matches the function.
    3. Every interpolated value on a fine grid lies between its neighbours'
       yields (linear interpolation can never overshoot).
    4. A maturity beyond the range is rejected (no extrapolation).
    """
    m, y = pts["maturity_years"].to_numpy(), pts["yield_pct"].to_numpy()

    at_obs = interpolate_par_curve(pts, m)
    max_err = float(np.max(np.abs(at_obs - y)))
    assert max_err < 1e-12, f"curve misses observations (max error {max_err})"

    mid_m = (m[0] + m[1]) / 2
    by_hand = y[0] + (y[1] - y[0]) * (mid_m - m[0]) / (m[1] - m[0])
    assert abs(interpolate_par_curve(pts, [mid_m])[0] - by_hand) < 1e-12

    grid = np.linspace(m.min(), m.max(), 2000)
    vals = interpolate_par_curve(pts, grid)
    idx = np.searchsorted(m, grid, side="right").clip(1, len(m) - 1)
    low = np.minimum(y[idx - 1], y[idx]) - 1e-12
    high = np.maximum(y[idx - 1], y[idx]) + 1e-12
    assert ((vals >= low) & (vals <= high)).all(), "interpolated value outside neighbours"

    for bad in (m.min() - 0.01, m.max() + 1):
        try:
            interpolate_par_curve(pts, [bad])
        except ValueError:
            continue
        raise AssertionError("extrapolation was not rejected")

    print(f"  [ok] curve passes through all {len(m)} observations "
          f"(max abs difference {max_err:.1e} percentage points)")
    print(f"  [ok] midpoint check: {mid_m:.4f} yr -> {by_hand:.4f}% by hand = function")
    print("  [ok] no interpolated value lies outside its two neighbouring yields")
    print(f"  [ok] maturities outside {m.min():.4f}-{m.max():.0f} years are rejected")
