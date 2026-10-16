"""Load, clean-check, and combine the raw Treasury par yield CSV files.

Purpose of this file
--------------------
The Treasury publishes par yield curve data in several CSV files. They do not
share one layout, so before we can analyse them we must put them into a single
table with consistent column names and a real date index.

What this file does NOT do
--------------------------
* It never edits the files in data/raw (they are opened read-only).
* It never fills in or interpolates missing values. A blank in the CSV stays NaN.
  Blanks are usually *meaningful*: e.g. the 1-month bill did not exist as a
  benchmark in 2000, so there is nothing to fill.
* It never converts yields to decimals unless you explicitly call
  `percent_to_decimal`.

Units
-----
All yield columns are in PERCENT, exactly as published. A value of 4.25 means
4.25% per year. Par yields are bond-equivalent yields at which a Treasury would
trade at par for that maturity. They are NOT spot (zero-coupon) rates.
"""

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

# Maturity of each column in years. Used to order columns from short to long
# and to label charts. (1 month = 1/12 year, etc.)
MATURITY_YEARS = {
    "1M": 1 / 12, "2M": 2 / 12, "3M": 3 / 12, "4M": 4 / 12, "6M": 6 / 12,
    "1Y": 1, "2Y": 2, "3Y": 3, "5Y": 5, "7Y": 7, "10Y": 10, "20Y": 20, "30Y": 30,
}
TENOR_ORDER = list(MATURITY_YEARS)  # insertion order is short -> long


def _standardise_column(name: str) -> str:
    """Turn '1 Mo', '1 mo', '10 Yr' into '1M', '1M', '10Y'.

    The three files use different capitalisation, so we normalise first.
    """
    num, unit = name.strip().lower().split()
    return num + {"mo": "M", "yr": "Y"}[unit]


def _parse_dates(raw: pd.Series, source: str) -> pd.Series:
    """Parse dates strictly. Files use 'm/d/yy' (2000s, 2010s) or 'mm/dd/yyyy'.

    We try each known format and require that ALL values parse with the same
    one, so a bad date raises an error instead of silently becoming NaT.
    """
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return pd.to_datetime(raw, format=fmt)
        except ValueError:
            continue
    raise ValueError(f"{source}: dates match neither m/d/Y nor m/d/y")


def load_raw_file(path: Path) -> pd.DataFrame:
    """Read one raw CSV into a tidy frame with a 'date' column and tenor columns."""
    df = pd.read_csv(path, dtype=str)  # read as text first; convert deliberately
    df.columns = ["date"] + [_standardise_column(c) for c in df.columns[1:]]
    df["date"] = _parse_dates(df["date"], path.name)
    tenors = [c for c in df.columns if c != "date"]
    # errors="raise": a non-numeric entry is a data problem we want to see.
    df[tenors] = df[tenors].apply(pd.to_numeric, errors="raise")
    df["source_file"] = path.name
    return df


def load_all(raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    """Load every CSV in raw_dir, stack them, sort by date, and order columns.

    Files that lack a tenor (e.g. no 4M before 2022) simply give NaN for it.
    Duplicate dates are NOT removed here; `check_duplicates` reports them.
    """
    paths = sorted(raw_dir.glob("*.csv"))
    if not paths:
        raise FileNotFoundError(f"No CSV files found in {raw_dir}")
    frames = [load_raw_file(p) for p in paths]
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values("date").reset_index(drop=True)
    tenors = [t for t in TENOR_ORDER if t in combined.columns]
    return combined[["date"] + tenors + ["source_file"]]


def tenor_columns(df: pd.DataFrame) -> list:
    """Yield columns in short -> long order."""
    return [t for t in TENOR_ORDER if t in df.columns]


def check_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """Return rows whose date appears more than once (empty frame = none)."""
    return df[df["date"].duplicated(keep=False)]


def missing_report(df: pd.DataFrame) -> pd.DataFrame:
    """Count missing values per tenor, plus the first/last date each tenor has data.

    Missing values are only reported, never filled.
    """
    rows = []
    for t in tenor_columns(df):
        observed = df.loc[df[t].notna(), "date"]
        rows.append({
            "tenor": t,
            "missing": int(df[t].isna().sum()),
            "pct_missing": round(100 * df[t].isna().mean(), 1),
            "first_observed": observed.min().date() if len(observed) else None,
            "last_observed": observed.max().date() if len(observed) else None,
        })
    return pd.DataFrame(rows).set_index("tenor")


def percent_to_decimal(df: pd.DataFrame) -> pd.DataFrame:
    """CONVERSION: percent -> decimal. 4.25 (%) becomes 0.0425.

    Returns a NEW frame whose columns are renamed with a '_decimal' suffix so a
    decimal value can never be mistaken for a published percent value.
    """
    cols = tenor_columns(df)
    out = df[["date"]].copy()
    for c in cols:
        out[f"{c}_decimal"] = df[c] / 100.0
    return out


def add_spread_bp(df: pd.DataFrame, long: str = "10Y", short: str = "2Y") -> pd.DataFrame:
    """Add the (long - short) yield spread in BASIS POINTS.

    Yields are in percent, so the difference is in percentage points.
    1 percentage point = 100 basis points, hence the factor of 100:
        (4.25% - 4.75%) = -0.50 pp = -50 bp
    If either yield is missing that day, the spread is NaN (not filled).
    """
    out = df.copy()
    out[f"spread_{long}_{short}_bp"] = (out[long] - out[short]) * 100.0
    return out
