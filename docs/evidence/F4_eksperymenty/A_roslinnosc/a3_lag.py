"""A3 (V5): lagged vegetation response. Correlate vegetation anomaly at scene day t with ISMN 20-30 cm z
at t-L (L = 0, 10, 20, 30 d) and with the trailing 30-d mean of ISMN z. L chosen by leave-one-year-out."""
import logging
import warnings

import numpy as np
import pandas as pd

from common import OUT, ins_z, r_ci, pair, paired_diff_ci

logging.basicConfig(level=logging.WARNING)
warnings.filterwarnings("ignore")

y = ins_z("rz")
ser = pd.read_csv(f"{OUT}/a2_variant_series.csv", index_col=0, parse_dates=True)
LAGS = [0, 10, 20, 30]


def target(kind):
    if kind.startswith("lag"):
        L = int(kind[3:])
        t = y.copy()
        t.index = t.index + pd.Timedelta(days=L)          # value at t is ISMN z at t-L
        return t
    if kind == "trail30":
        yd = y.asfreq("D")
        return yd.rolling(31, min_periods=20).mean()      # mean over [t-30, t]
    raise ValueError(kind)


KINDS = [f"lag{L}" for L in LAGS] + ["trail30"]
rows = []
for var in ("B0_ndvi_scene", "V6_harmonic_loyo", "V3a_ndmi_scene", "V3d_meanz_ndvi_ndmi_crswir"):
    x = ser[var].dropna()
    days = pair(x, y).index                               # same days as lag-0 evaluation
    x = x[x.index.isin(days)]
    res = {}
    for k in KINDS:
        a = r_ci(x, target(k))
        res[k] = a
        rows.append(dict(variant=var, target=k, r=a["r"], lo=a["lo"], hi=a["hi"], n=a["n"]))
    # LOYO selection of target among KINDS (max R on other years), evaluated on the held-out year
    held, held0 = [], []
    chosen = {}
    for yr in np.unique(x.index.year):
        best, bk = -np.inf, None
        for k in KINDS:
            p = pair(x[x.index.year != yr], target(k))
            r = np.corrcoef(p["x"], p["y"])[0, 1]
            if r > best:
                best, bk = r, k
        chosen[int(yr)] = bk
        p = pair(x[x.index.year == yr], target(bk))
        held.append(p)
        held0.append(pair(x[x.index.year == yr], target("lag0")))
    H, H0 = pd.concat(held), pd.concat(held0)
    j = H.join(H0["y"].rename("y0"), how="inner")
    r_sel = np.corrcoef(j["x"], j["y"])[0, 1]
    r_0 = np.corrcoef(j["x"], j["y0"])[0, 1]
    rows.append(dict(variant=var, target="LOYO-selected", r=r_sel, lo=np.nan, hi=np.nan, n=len(j),
                     note=f"lag0 same days R={r_0:.3f}; chosen per held-out year: {chosen}"))
out = pd.DataFrame(rows)
out.to_csv(f"{OUT}/a3_lag.csv", index=False)
pd.set_option("display.width", 250, "display.max_colwidth", 200)
print(out.round(3).to_string(index=False))
