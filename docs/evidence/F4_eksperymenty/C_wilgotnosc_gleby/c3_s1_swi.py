"""C3 - Sentinel-1 change detection at the station (S1_CD_A, 50 m buffer, 4 relative orbits) as a soil-moisture
source, raw and propagated to depth with the exponential filter (SWI).

Physical reasoning: C-band backscatter senses ~0-5 cm. The 20-30 cm layer integrates surface wetting with a delay
and damping; the exponential filter (Wagner et al. 1999; Albergel et al. 2008, developed on SMOSMANIA) models this
as a first-order (low-pass) response with characteristic time T. Larger T = deeper / slower layer. The filter also
averages down speckle and the per-orbit calibration noise of single S-1 retrievals.
T is a fitted parameter -> chosen in leave-one-year-out CV (predictor climatology also from training years only).
Outputs: out/c3_s1_raw.csv, out/c3_swi_grid.csv, out/c3_swi_loyo.csv
"""
import numpy as np
import pandas as pd

from common import (COMMON, OUT, YEARS, anom35, diff_r_ci, era5_full, era5_layers, insitu, ismn_ref, pair, r_ci,
                    swi, zclim, zclim_years)

sm = s1_sm = None
from common import s1_obs  # noqa: E402

s1 = s1_obs("sm_s1")
s1rel = s1_obs("sm_rel")
s1_day = s1.groupby(s1.index.floor("D")).mean()
s1rel_day = s1rel.groupby(s1rel.index.floor("D")).mean()

e = era5_full().loc[COMMON[0]:COMMON[1]]
lay = era5_layers(e)
rz_ins = ismn_ref()
d05 = insitu(0.05)
z_ins = zclim(rz_ins)

rows = []
# --- raw and anomaly agreement of single S-1 retrievals (daily mean of the acquisitions of that day)
for name, x in (("sm_s1", s1_day), ("sm_rel", s1rel_day)):
    for ref_name, y in (("ismn_5cm", d05["sm"]), ("ismn_20_30cm", rz_ins)):
        r, lo, hi, n = r_ci(x, y)
        rows.append({"product": name, "reference": ref_name, "kind": "raw", "R": r, "ci_lo": lo, "ci_hi": hi, "n": n})
        r, lo, hi, n = r_ci(anom35(x), anom35(y))
        rows.append({"product": name, "reference": ref_name, "kind": "anom35", "R": r, "ci_lo": lo, "ci_hi": hi, "n": n})
        # 5 cm: per sensor segment (sensor swap 2019 shifts the absolute level -> clim anomaly not meaningful)
    r, lo, hi, n = r_ci(zclim(x), z_ins)
    rows.append({"product": name, "reference": "ismn_20_30cm", "kind": "clim_z", "R": r, "ci_lo": lo, "ci_hi": hi, "n": n})
for seg, g in d05.groupby("segment"):
    r, lo, hi, n = r_ci(anom35(s1_day), anom35(g["sm"]))
    rows.append({"product": "sm_s1", "reference": f"ismn_5cm_{seg}", "kind": "anom35", "R": r, "ci_lo": lo, "ci_hi": hi, "n": n})
# ERA5 L1 on the same footing (context: is S-1 better than the 9 km model at 5 cm?)
r, lo, hi, n = r_ci(anom35(lay["L1_0_7"]).reindex(s1_day.index), anom35(d05["sm"]))
rows.append({"product": "ERA5_L1 (S1 days)", "reference": "ismn_5cm", "kind": "anom35", "R": r, "ci_lo": lo, "ci_hi": hi, "n": n})
raw = pd.DataFrame(rows)
raw.to_csv(f"{OUT}/c3_s1_raw.csv", index=False)
pd.set_option("display.width", 200)
print(raw.round(3).to_string(index=False))

# --- SWI grid (in-sample, descriptive): clim z of SWI vs ISMN 20-30 z and vs 5 cm 35d anomaly
TS = [1, 5, 10, 15, 20, 30, 40, 60]
swis = {T: swi(s1, T).loc[COMMON[0]:COMMON[1]] for T in TS}
grid = []
for T in TS:
    zs = zclim(swis[T])
    r, lo, hi, n = r_ci(zs, z_ins)
    r5 = r_ci(anom35(swis[T]), anom35(d05["sm"]))[0]
    r35 = r_ci(anom35(swis[T]), anom35(rz_ins))[0]
    grid.append({"T": T, "R_clim_vs_20_30": r, "ci_lo": lo, "ci_hi": hi, "n": n, "R_anom35_vs_5cm": r5,
                 "R_anom35_vs_20_30": r35})
grid = pd.DataFrame(grid)
grid.to_csv(f"{OUT}/c3_swi_grid.csv", index=False)
print("\nSWI grid (in-sample):\n", grid.round(3).to_string(index=False))

# --- LOYO: choose T on 8 years, evaluate on the held-out year. Predictor climatology from training years only.
TS_CV = [5, 10, 15, 20, 30, 40]
held, chosen = [], {}
for yv in YEARS:
    tr = [y for y in YEARS if y != yv]
    best, bestr = None, -9
    for T in TS_CV:
        zt = zclim_years(swis[T], tr)
        p = pair(zt, z_ins)
        p = p[p.index.year.isin(tr)]
        rr = p.iloc[:, 0].corr(p.iloc[:, 1])
        if rr > bestr:
            best, bestr = T, rr
    chosen[yv] = best
    zt = zclim_years(swis[best], tr)
    held.append(zt[zt.index.year == yv])
z_swi_cv = pd.concat(held).sort_index()
z_era_cv = pd.concat([zclim_years(lay["RZ_0_100"], [y for y in YEARS if y != yv]).pipe(lambda s, yv=yv: s[s.index.year == yv])
                      for yv in YEARS]).sort_index()
z_l2_cv = pd.concat([zclim_years(lay["L2_7_28"], [y for y in YEARS if y != yv]).pipe(lambda s, yv=yv: s[s.index.year == yv])
                     for yv in YEARS]).sort_index()
print("\nLOYO chosen T per held-out year:", chosen)
out = []
for name, x in (("S1_SWI_cv", z_swi_cv), ("ERA5_RZ_cv", z_era_cv), ("ERA5_L2_cv", z_l2_cv)):
    p = pair(x, z_swi_cv, z_ins, names=["x", "s", "y"])          # same days for all
    r, lo, hi, n = r_ci(p["x"], p["y"])
    yr = p.groupby(p.index.year).apply(lambda g: g["x"].corr(g["y"]))
    out.append({"product": name, "R": r, "ci_lo": lo, "ci_hi": hi, "n": n, **{f"R_{k}": v for k, v in yr.items()}})
loyo = pd.DataFrame(out)
d = diff_r_ci(z_swi_cv, z_era_cv, z_ins)
print(loyo.round(3).to_string(index=False))
print(f"dR SWI_cv - ERA5_RZ_cv: {d[0]:.3f} [{d[1]:.3f},{d[2]:.3f}] n={d[3]} P>0={d[4]:.2f}")
loyo.to_csv(f"{OUT}/c3_swi_loyo.csv", index=False)
pd.DataFrame({"z_swi_cv": z_swi_cv, "z_era_rz_cv": z_era_cv, "z_era_l2_cv": z_l2_cv}).to_csv(f"{OUT}/c3_cv_series.csv")
pd.Series(chosen).to_csv(f"{OUT}/c3_loyo_T.csv")
