"""A5: where does R ~ 0.43 come from? Between-year vs within-year decomposition, and the
trailing-30-day ISMN target (vegetation integrates the past month) with a paired CI."""
import logging
import warnings

import numpy as np
import pandas as pd

from common import OUT, ins_z, pair, year_boot, s7, VCFG

logging.basicConfig(level=logging.WARNING)
warnings.filterwarnings("ignore")

y = ins_z("rz")
y_tr30 = y.asfreq("D").rolling(31, min_periods=20).mean()
ser = pd.read_csv(f"{OUT}/a2_variant_series.csv", index_col=0, parse_dates=True)
VARS = ["B0_ndvi_scene", "V1a_ndvi_whittaker", "V1c_ndvi_trailing30d", "V3a_ndmi_scene", "V3c_negcrswir_scene",
        "V3d_meanz_ndvi_ndmi_crswir", "V6_harmonic_loyo"]
base_days = pair(ser["B0_ndvi_scene"].dropna(), y).index


def within(q):
    a = q["x"] - q.groupby(q.index.year)["x"].transform("mean")
    b = q["y"] - q.groupby(q.index.year)["y"].transform("mean")
    return np.corrcoef(a, b)[0, 1]


def between(q):
    m = q.groupby(q.index.year)[["x", "y"]].mean()
    return np.corrcoef(m["x"], m["y"])[0, 1]


rows = []
for v in VARS:
    x = ser[v].dropna()
    x = x[x.index.isin(base_days)]
    p = pair(x, y)
    rw = within(p)
    lo_w, hi_w = s7._block_bootstrap_ci(pd.Series(p.index), np.arange(len(p)).astype(float),
                                        np.zeros(len(p)), lambda a, b: within(p.iloc[a.astype(int)]), VCFG)
    rb = between(p)
    m = p.groupby(p.index.year)[["x", "y"]].mean()
    rho_b = m.corr(method="spearman").iloc[0, 1]
    # trailing-30 d target vs instantaneous target on the same days (paired 30-d block bootstrap)
    q = x.to_frame("x").join(y.rename("y0")).join(y_tr30.rename("y30")).dropna()
    r0, r30 = np.corrcoef(q["x"], q["y0"])[0, 1], np.corrcoef(q["x"], q["y30"])[0, 1]
    idx = np.arange(len(q)).astype(float)
    lo_d, hi_d = s7._block_bootstrap_ci(
        pd.Series(q.index), idx, idx,
        lambda a, b: (np.corrcoef(q["x"].to_numpy()[a.astype(int)], q["y30"].to_numpy()[a.astype(int)])[0, 1]
                      - np.corrcoef(q["x"].to_numpy()[a.astype(int)], q["y0"].to_numpy()[a.astype(int)])[0, 1]),
        VCFG)
    rows.append(dict(variant=v, n=len(p), r_total=np.corrcoef(p["x"], p["y"])[0, 1], r_within_year=rw,
                     within_lo=lo_w, within_hi=hi_w, r_between_year_means=rb, rho_between_year=rho_b,
                     n_years=len(m), r_target_t0=r0, r_target_trail30=r30, d_trail30=r30 - r0,
                     d_lo=lo_d, d_hi=hi_d, n_trail=len(q)))
out = pd.DataFrame(rows)
out.to_csv(f"{OUT}/a5_decomposition.csv", index=False)
pd.set_option("display.width", 250)
print(out.round(3).to_string(index=False))
m = pair(ser["B0_ndvi_scene"].dropna(), y)
print(m.groupby(m.index.year)[["x", "y"]].mean().round(2).T.to_string())
