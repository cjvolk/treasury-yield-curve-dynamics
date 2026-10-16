"""Does the 10Y-2Y spread tend to move back toward its recent average?

Purpose of this file
--------------------
Stage 3 is a descriptive research question, NOT a trading strategy:

    When the spread is unusually high (low) compared with its own trailing
    1-year average, does it tend to FALL (RISE) over the next 5, 20 or 60
    observations?

Definitions (all fixed in advance; nothing here is tuned)
---------------------------------------------------------
* Observation: one date with a published 10Y and 2Y par yield. The one
  all-blank date (2010-10-11) has no spread and is dropped, not filled.
  "5 observations ahead" therefore means 5 rows ahead, roughly one trading
  week, and is not a fixed number of calendar days.
* Spread s_t = (10Y% - 2Y%) x 100, in basis points (bp).
* Trailing mean m_t and standard deviation sd_t use the 252 observations
  BEFORE t (t-252 ... t-1). The value at t itself is not in its own window.
* Signal z_t = (s_t - m_t) / sd_t. z = +1 means "1 trailing standard deviation
  above the trailing average". If the spread reverts, z should be NEGATIVELY
  related to the future change.
* Forward change over h observations: s_{t+h} - s_t, in bp. This is a change
  in a yield spread. It is not a return, not a profit, and not a P&L.

Train/evaluation split
----------------------
The earliest 70% of observations are the "initial" period (used for first
look); the latest 30% are the "evaluation" period. An initial-period
observation is dropped for a horizon h if t + h would land in the evaluation
period, so no initial measurement peeks into the evaluation period.
Evaluation signals still use the trailing window, which may reach back into
the initial period: that is only past data, so it is legitimate.
"""

import numpy as np
import pandas as pd

WINDOW = 252
HORIZONS = (5, 20, 60)
INITIAL_FRACTION = 0.70
Z_THRESHOLD = 1.0  # fixed a priori for the bucket table; not tuned
SPREAD_COL = "spread_10Y_2Y_bp"


def prepare_spread(df: pd.DataFrame) -> pd.Series:
    """Spread series (bp) indexed by date, sorted, with missing days dropped."""
    s = df.set_index("date")[SPREAD_COL].sort_index()
    if s.index.duplicated().any():
        raise ValueError("duplicate dates in spread series")
    return s.dropna()


def trailing_signal(s: pd.Series, window: int = WINDOW) -> pd.DataFrame:
    """Trailing mean, std and z-score using ONLY observations before each date.

    rolling(window) at row t covers t-window+1 ... t. `.shift(1)` moves it so
    row t holds the statistics of t-window ... t-1 (excluding t itself).
    std uses ddof=1 (sample standard deviation).
    """
    mean = s.rolling(window).mean().shift(1)
    sd = s.rolling(window).std(ddof=1).shift(1)
    return pd.DataFrame({"spread_bp": s, "trail_mean_bp": mean, "trail_sd_bp": sd,
                         "z": (s - mean) / sd})


def split_position(n: int, fraction: float = INITIAL_FRACTION) -> int:
    """First row position of the evaluation period (rows 0..k-1 are initial)."""
    return int(np.floor(n * fraction))


def build_sample(s: pd.Series, window: int = WINDOW, horizons=HORIZONS,
                 fraction: float = INITIAL_FRACTION) -> pd.DataFrame:
    """One row per signal date, with z, trailing mean and each forward change.

    Columns `fwd_h` hold s_{t+h} - s_t (bp). Rows are labelled 'initial' or
    'evaluation'. A forward change is set to NaN (excluded) when:
      * t + h runs past the end of the data, or
      * the row is in the initial period but t + h reaches the evaluation period.
    Rows with no signal yet (first 252 observations) are dropped.
    """
    sig = trailing_signal(s, window)
    n = len(s)
    k = split_position(n, fraction)
    pos = np.arange(n)
    sig["period"] = np.where(pos < k, "initial", "evaluation")
    for h in horizons:
        fwd = s.shift(-h) - s  # s_{t+h} - s_t
        end = pos + h
        too_far = end >= n
        crosses = (pos < k) & (end >= k)
        fwd[too_far | crosses] = np.nan
        sig[f"fwd_{h}"] = fwd
        sig[f"toward_{h}"] = np.where(
            fwd.isna(), np.nan,
            (np.abs(s.shift(-h) - sig["trail_mean_bp"]) < np.abs(s - sig["trail_mean_bp"])).astype(float))
    return sig.dropna(subset=["z"])


def verify_no_lookahead(s: pd.Series, window: int = WINDOW, horizons=HORIZONS,
                        fraction: float = INITIAL_FRACTION) -> None:
    """Self-checks that run every time. Raise AssertionError if any fails."""
    sig = trailing_signal(s, window)
    n = len(s)
    t = n // 2

    # 1. Window is exactly the 252 observations before t (hand calculation).
    hand = s.iloc[t - window:t]
    assert np.isclose(sig["trail_mean_bp"].iloc[t], hand.mean())
    assert np.isclose(sig["trail_sd_bp"].iloc[t], hand.std(ddof=1))
    assert t - window >= 0 and len(hand) == window

    # 2. Changing the FUTURE (everything after t) cannot change the signal at t.
    rng = np.random.default_rng(0)
    s2 = s.copy()
    s2.iloc[t + 1:] = rng.normal(0, 500, n - t - 1)
    sig2 = trailing_signal(s2, window)
    assert np.isclose(sig["z"].iloc[t], sig2["z"].iloc[t]), "signal depends on future"
    # ... and changing s_t itself must not change the mean/sd at t.
    s3 = s.copy()
    s3.iloc[t] += 1000.0
    sig3 = trailing_signal(s3, window)
    assert np.isclose(sig["trail_mean_bp"].iloc[t], sig3["trail_mean_bp"].iloc[t])

    # 3. No initial-period forward window reaches the evaluation period.
    k = split_position(n, fraction)
    sample = build_sample(s, window, horizons, fraction)
    pos = {d: i for i, d in enumerate(s.index)}
    for h in horizons:
        init = sample[(sample["period"] == "initial") & sample[f"fwd_{h}"].notna()]
        last = max(pos[d] for d in init.index)
        assert last + h <= k - 1, f"initial window for h={h} reaches evaluation"
        ev = sample[(sample["period"] == "evaluation") & sample[f"fwd_{h}"].notna()]
        assert min(pos[d] for d in ev.index) >= k
    print("  [ok] trailing window = the 252 observations before the signal date")
    print("  [ok] altering future data leaves today's signal unchanged")
    print("  [ok] no initial-period forward window reaches the evaluation period")


def _ols_slope(x: np.ndarray, y: np.ndarray) -> float:
    """Slope of y on x: bp of forward change per +1 unit of z."""
    xc = x - x.mean()
    return float((xc * (y - y.mean())).sum() / (xc ** 2).sum())


def _stats(z: pd.Series, y: pd.Series) -> dict:
    ok = z.notna() & y.notna()
    z, y = z[ok], y[ok]
    if len(z) < 10:
        return {"n": len(z), "corr": np.nan, "spearman": np.nan, "slope_bp_per_z": np.nan}
    # Spearman correlation = Pearson correlation of the ranks.
    return {"n": len(z), "corr": z.corr(y), "spearman": z.rank().corr(y.rank()),
            "slope_bp_per_z": _ols_slope(z.to_numpy(), y.to_numpy())}


def summarize(sample: pd.DataFrame, horizons=HORIZONS) -> pd.DataFrame:
    """Per period and horizon: n, correlation of z with forward change, slope.

    Also reports the same statistic on NON-overlapping subsamples (every h-th
    observation, at each of the h possible starting offsets) as a robustness
    check, giving the min..max of the correlations across offsets, and the
    approximate number of independent forward windows (n / h).
    """
    rows = []
    for period in ("initial", "evaluation"):
        part = sample[sample["period"] == period]
        for h in horizons:
            col = f"fwd_{h}"
            valid = part[part[col].notna()]
            st = _stats(valid["z"], valid[col])
            offs = []
            for o in range(h):
                sub = valid.iloc[o::h]
                if len(sub) >= 10:
                    offs.append(sub["z"].corr(sub[col]))
            st.update({
                "period": period, "horizon_obs": h,
                "approx_independent_windows": round(st["n"] / h),
                "nonoverlap_corr_min": min(offs) if offs else np.nan,
                "nonoverlap_corr_max": max(offs) if offs else np.nan,
                "mean_fwd_change_bp": valid[col].mean(),
            })
            rows.append(st)
    cols = ["period", "horizon_obs", "n", "approx_independent_windows", "corr",
            "spearman", "slope_bp_per_z", "nonoverlap_corr_min", "nonoverlap_corr_max",
            "mean_fwd_change_bp"]
    return pd.DataFrame(rows)[cols]


def bucket_table(sample: pd.DataFrame, horizons=HORIZONS,
                 threshold: float = Z_THRESHOLD) -> pd.DataFrame:
    """Average forward change when z is high (>= +1), middle, or low (<= -1).

    'share_toward_mean' = fraction of cases where the spread ended closer to
    its signal-date trailing mean than it started. If there were no pull toward
    the mean this would be roughly 50% for the two outer buckets.
    """
    rows = []
    bucket = np.select([sample["z"] >= threshold, sample["z"] <= -threshold],
                       ["z >= +1", "z <= -1"], default="-1 < z < +1")
    for period in ("initial", "evaluation"):
        for h in horizons:
            for b in ("z <= -1", "-1 < z < +1", "z >= +1"):
                m = (sample["period"] == period) & (bucket == b) & sample[f"fwd_{h}"].notna()
                sub = sample[m]
                rows.append({
                    "period": period, "horizon_obs": h, "bucket": b, "n": len(sub),
                    "mean_fwd_change_bp": sub[f"fwd_{h}"].mean() if len(sub) else np.nan,
                    "median_fwd_change_bp": sub[f"fwd_{h}"].median() if len(sub) else np.nan,
                    "share_toward_mean": sub[f"toward_{h}"].mean() if len(sub) else np.nan,
                })
    return pd.DataFrame(rows)
