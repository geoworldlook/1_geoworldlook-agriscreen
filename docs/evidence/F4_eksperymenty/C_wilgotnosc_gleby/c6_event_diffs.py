"""C6 - paired comparisons of event skill (year-block bootstrap of differences), false alarms by month, and the
operational footprint of switching the warning layer (warning dekads per year 2016-2026, 1991-2020 base).
Outputs: out/c6_event_diffs.csv, out/c6_fa_by_month.csv, out/c6_warning_counts.csv
"""
import numpy as np
import pandas as pd

from common import CLIM_REF, COMMON, OUT, YEARS, contingency, era5_full, era5_layers, ismn_ref, to_dekad, zclim

e_full = era5_full()
lay_full = era5_layers(e_full)
obs_dk = to_dekad(zclim(ismn_ref()))
cv = pd.read_csv(f"{OUT}/c4_cv_series.csv", index_col=0, parse_dates=True)
P = {
    "RZ_op1991": to_dekad(zclim(lay_full["RZ_0_100"], ref=CLIM_REF, min_n=30).loc["2016-01-01":COMMON[1]]),
    "L2_op1991": to_dekad(zclim(lay_full["L2_7_28"], ref=CLIM_REF, min_n=30).loc["2016-01-01":COMMON[1]]),
    "W028_op1991": to_dekad(zclim(lay_full["W_0_28"], ref=CLIM_REF, min_n=30).loc["2016-01-01":COMMON[1]]),
    "RZ_cv2016": to_dekad(cv["E_RZ"]), "L2_cv2016": to_dekad(cv["E_L2"]), "EQ_RZ_S1_cv2016": to_dekad(cv["EQ_RZ_S"]),
}
J = pd.concat({k: v for k, v in P.items()}, axis=1).join(obs_dk.rename("obs"), how="inner").dropna()
O = (J["obs"] <= -1).to_numpy()
yrs = J.index.year.to_numpy()
ib = {y: np.flatnonzero(yrs == y) for y in YEARS}


def scores(o, f):
    c = contingency(o, f)
    return np.array([c["pod"], c["far"], c["csi"]])


pairs = [("RZ_cv2016", "RZ_op1991", "base period only"), ("L2_op1991", "RZ_op1991", "layer, operational base"),
         ("W028_op1991", "RZ_op1991", "layer 0-28, operational base"),
         ("L2_cv2016", "RZ_cv2016", "layer, consistent base"), ("EQ_RZ_S1_cv2016", "RZ_cv2016", "S-1 fusion, consistent base"),
         ("L2_cv2016", "RZ_op1991", "layer + consistent base vs v1.0")]
rng = np.random.default_rng(42)
draws = [np.concatenate([ib[y] for y in rng.choice(YEARS, len(YEARS))]) for _ in range(2000)]
rows = []
for a, b, why in pairs:
    fa, fb = (J[a] <= -1).to_numpy(), (J[b] <= -1).to_numpy()
    d0 = scores(O, fa) - scores(O, fb)
    ds = np.array([scores(O[i], fa[i]) - scores(O[i], fb[i]) for i in draws])
    lo, hi = np.nanpercentile(ds, 2.5, axis=0), np.nanpercentile(ds, 97.5, axis=0)
    per_year = [scores(O[ib[y]], fa[ib[y]])[2] - scores(O[ib[y]], fb[ib[y]])[2] for y in YEARS]
    rows.append({"a": a, "b": b, "effect": why, "dPOD": d0[0], "dPOD_lo": lo[0], "dPOD_hi": hi[0],
                 "dFAR": d0[1], "dFAR_lo": lo[1], "dFAR_hi": hi[1], "dCSI": d0[2], "dCSI_lo": lo[2], "dCSI_hi": hi[2],
                 "years_CSI_up": int(np.nansum(np.array(per_year) > 0)), "years_CSI_down": int(np.nansum(np.array(per_year) < 0))})
D = pd.DataFrame(rows)
D.to_csv(f"{OUT}/c6_event_diffs.csv", index=False)
pd.set_option("display.width", 250)
print(D.round(3).to_string(index=False))

# false alarms / misses by month (thr -1)
fm = []
for k in ("RZ_op1991", "L2_op1991", "RZ_cv2016", "L2_cv2016"):
    f = J[k] <= -1
    t = pd.DataFrame({"m": J.index.month, "fa": f & ~(J["obs"] <= -1), "miss": ~f & (J["obs"] <= -1),
                      "hit": f & (J["obs"] <= -1)})
    g = t.groupby("m")[["hit", "fa", "miss"]].sum()
    g.columns = [f"{k}_{c}" for c in g.columns]
    fm.append(g)
FM = pd.concat(fm, axis=1)
FM["obs_events"] = (J["obs"] <= -1).groupby(J.index.month).sum()
FM.to_csv(f"{OUT}/c6_fa_by_month.csv")
print("\nHits / false alarms / misses by month:\n", FM.to_string())

# operational footprint 2016-2026: warning dekads (z<=-1, 1991-2020 base) per year, RZ vs L2
wc = pd.DataFrame({k: (to_dekad(zclim(lay_full[k], ref=CLIM_REF, min_n=30).loc["2016-01-01":]) <= -1)
                   for k in ("RZ_0_100", "L2_7_28", "W_0_28")})
cnt = wc.groupby(wc.index.year).sum()
cnt["agree_RZ_L2"] = (wc["RZ_0_100"] == wc["L2_7_28"]).groupby(wc.index.year).mean().round(2)
cnt.to_csv(f"{OUT}/c6_warning_counts.csv")
print("\nWarning dekads per year (z<=-1 vs 1991-2020):\n", cnt.to_string())
