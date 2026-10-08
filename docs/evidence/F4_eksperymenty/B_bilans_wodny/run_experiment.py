"""Experiment B: FAO-56 water balance (S-2 Kcb) and climatic water balance vs ISMN Condom.

Pre-registered variants (fixed before looking at validation numbers; parameters in config.py):
  B0   ERA5-Land root zone 0-100 cm (v1.0 baseline)
  V1   WB_vine_SR      FAO-56 dual Kc, Kcb from VINEYARD_06 NDVI SR 2.5 m (Campos 2010), Zr 1.0 m (TAW 140 mm)
  V2   WB_vine_10m     as V1 with native 10 m NDVI (SR ablation)
  V3   WB_vine_clim    as V1 with the climatological Kcb curve of V1 (no interannual S-2 information)
  V4   WB_station      Kcb from station 50 m buffer S2_L2A NDVI (grass at the probe), grass p/h
  V5   WB_vine_SR_cvZr Zr chosen by leave-one-year-out CV from ZR_GRID_M
  V6-8 SPEI-like 30/60/90 d: z-score of rolling sum of P - ET0 (Hargreaves)
  V9   ERA5 + V1 combined (LOYO OLS) - added-value test
Outputs: results_*.csv / .json, series_daily_z.csv
"""
import json

import numpy as np
import pandas as pd

import common as C
import config as K
import wb_model as W

f = pd.read_csv(f"{C.OUT}/inputs_forcing.csv", index_col="date", parse_dates=True)
kc = pd.read_csv(f"{C.OUT}/inputs_kcb.csv", index_col="date", parse_dates=True)
e = C.era5()
assert f.index.equals(e.index) and kc.index.equals(e.index)

VINE = dict(K.SOIL_BASE, **K.VINE)
GRASS = dict(K.SOIL_BASE, **K.GRASS)

# ----------------------------------------------------------------------------- model runs
runs = {
    "V1_WB_vine_SR": W.run_wb(f, kc["vine_SR"], VINE),
    "V2_WB_vine_10m": W.run_wb(f, kc["vine_10m"], VINE),
    "V3_WB_vine_clim": W.run_wb(f, kc["vine_SR_clim"], VINE),
    "V4_WB_station": W.run_wb(f, kc["station_L2A"], GRASS),
}
zr_runs = {zr: W.run_wb(f, kc["vine_SR"], dict(VINE, zr_m=zr)) for zr in K.ZR_GRID_M}

products = {"B0_ERA5L_RZ": C.s4.rootzone(e)}
for k, r in runs.items():
    products[k] = r["RSW"]
for n in K.SPEI_DAYS:
    products[f"V{5 + K.SPEI_DAYS.index(n) + 1}_SPEI{n}_like"] = (f["precip_mm"] - f["et0"]).rolling(n, min_periods=n).sum()

z_common = {k: C.anom_common(v) for k, v in products.items()}
z_oper = {k: C.anom_oper(v) for k, v in products.items()}
zr_common = {zr: C.anom_common(r["RSW"]) for zr, r in zr_runs.items()}
zr_oper = {zr: C.anom_oper(r["RSW"]) for zr, r in zr_runs.items()}

y_rz, y_10 = C.ins_z("rz"), C.ins_z("10")
years = list(range(2016, 2025))

# ----------------------------------------------------------------------------- V5: LOYO choice of Zr
def r_on(zs: pd.Series, y: pd.Series, mask_years):
    p = C.pair(zs, y)
    p = p[np.isin(p.index.year, mask_years)]
    return np.corrcoef(p["x"], p["y"])[0, 1]


cv_rows, held = [], []
for yv in years:
    train = [y for y in years if y != yv]
    scores = {zr: r_on(zr_common[zr], y_rz, train) for zr in K.ZR_GRID_M}
    best = max(scores, key=scores.get)
    cv_rows.append({"held_out": yv, "best_zr_m": best, **{f"r_train_zr{zr}": s for zr, s in scores.items()}})
    held.append(zr_common[best][zr_common[best].index.year == yv])
z_common["V5_WB_vine_SR_cvZr"] = pd.concat(held).sort_index()
cv_choice = pd.DataFrame(cv_rows)
# operational anomaly for V5: Zr chosen on all ISMN years is not allowed (leak) -> use per-year choice too
z_oper["V5_WB_vine_SR_cvZr"] = pd.concat(
    [zr_oper[r["best_zr_m"]][zr_oper[r["best_zr_m"]].index.year == r["held_out"]] for r in cv_rows]).sort_index()
cv_choice.to_csv(f"{C.OUT}/results_V5_zr_cv.csv", index=False)

# ----------------------------------------------------------------------------- V9: ERA5 + WB combined, LOYO OLS
def loyo_ols(xcols, y):
    d = pd.concat([*(x.rename(f"x{i}") for i, x in enumerate(xcols)), y.rename("y")], axis=1, join="inner")
    d = d.replace([np.inf, -np.inf], np.nan).dropna()
    d = d[np.isin(d.index.year, years)]
    pred = pd.Series(np.nan, index=d.index)
    coefs = []
    for yv in years:
        tr, te = d.index.year != yv, d.index.year == yv
        X = np.column_stack([np.ones(tr.sum()), d.loc[tr, [c for c in d if c != "y"]].to_numpy()])
        b, *_ = np.linalg.lstsq(X, d.loc[tr, "y"].to_numpy(), rcond=None)
        Xt = np.column_stack([np.ones(te.sum()), d.loc[te, [c for c in d if c != "y"]].to_numpy()])
        pred[te] = Xt @ b
        coefs.append(b)
    return pred, np.array(coefs)


pred_era, _ = loyo_ols([z_common["B0_ERA5L_RZ"]], y_rz)
pred_comb, coefs_comb = loyo_ols([z_common["B0_ERA5L_RZ"], z_common["V1_WB_vine_SR"]], y_rz)
z_common["V9_ERA5+WB_loyo"] = pred_comb
z_common["B0_ERA5L_RZ_loyo"] = pred_era

# ----------------------------------------------------------------------------- metrics
rows = []
base = z_common["B0_ERA5L_RZ"]
season = lambda s, months: s[(s.index.month >= months[0]) & (s.index.month <= months[1])] if months[0] <= months[1] \
    else s[(s.index.month >= months[0]) | (s.index.month <= months[1])]
for name, z in z_common.items():
    for ref_name, y in (("ISMN_20_30cm", y_rz), ("ISMN_10cm", y_10)):
        rr = C.r_ci(z, y)
        row = {"variant": name, "reference": ref_name, "subset": "all", **rr}
        if name != "B0_ERA5L_RZ":
            d30 = C.paired_delta_r(z, base, y, "30d")
            dyr = C.paired_delta_r(z, base, y, "year")
            row.update(baseline_same_dates=d30["r_b"], n_paired=d30["n"], delta_r=d30["delta"],
                       delta_lo_30d=d30["lo"], delta_hi_30d=d30["hi"], delta_lo_year=dyr["lo"], delta_hi_year=dyr["hi"])
        rows.append(row)
    for sub, months in (("IV-X", (4, 10)), ("XI-III", (11, 3))):
        zz, yy = season(z, months), season(y_rz, months)
        rr = C.r_ci(zz, yy)
        row = {"variant": name, "reference": "ISMN_20_30cm", "subset": sub, **rr}
        if name != "B0_ERA5L_RZ":
            d30 = C.paired_delta_r(zz, season(base, months), yy, "30d")
            row.update(baseline_same_dates=d30["r_b"], n_paired=d30["n"], delta_r=d30["delta"],
                       delta_lo_30d=d30["lo"], delta_hi_30d=d30["hi"])
        rows.append(row)
res = pd.DataFrame(rows)
res.to_csv(f"{C.OUT}/results_daily_r.csv", index=False)

# per-year R (consistency across held-out years) for the main variants vs ERA5 on the same days
py = {}
for name in ["B0_ERA5L_RZ", "V1_WB_vine_SR", "V2_WB_vine_10m", "V3_WB_vine_clim", "V4_WB_station",
             "V5_WB_vine_SR_cvZr", "V6_SPEI30_like", "V7_SPEI60_like", "V8_SPEI90_like", "V9_ERA5+WB_loyo"]:
    common_idx = C.pair(z_common[name], y_rz).index.intersection(C.pair(base, y_rz).index)
    py[name] = C.r_by_year(z_common[name].reindex(common_idx), y_rz)
    py[name + "__base_same_days"] = C.r_by_year(base.reindex(common_idx), y_rz)
py = pd.DataFrame(py)
py.to_csv(f"{C.OUT}/results_r_by_year.csv", index_label="year")

# dekadal events
ins_dk = C.dekad_mean(y_rz)
ev = []
for name in list(products) + ["V5_WB_vine_SR_cvZr"]:
    for refkind, zz in (("operational_1991-2020", z_oper[name].loc["2016":]), ("common_2016-2024", z_common[name])):
        pf = C.pod_far_ci(C.dekad_mean(zz), ins_dk)
        ev.append({"variant": name, "anomaly_ref": refkind, **pf})
ev = pd.DataFrame(ev)
ev.to_csv(f"{C.OUT}/results_events.csv", index=False)

# added-value diagnostics
p = pd.concat([y_rz.rename("y"), base.rename("era"), z_common["V1_WB_vine_SR"].rename("wb"),
               z_common["V3_WB_vine_clim"].rename("wbclim"), z_common["V4_WB_station"].rename("wbst"),
               z_common["V6_SPEI30_like"].rename("spei30"), z_common["V8_SPEI90_like"].rename("spei90")],
              axis=1, join="inner").replace([np.inf, -np.inf], np.nan).dropna()


def partial_r(y, x, ctrl):
    X = np.column_stack([np.ones(len(ctrl)), ctrl])
    ry = y - X @ np.linalg.lstsq(X, y, rcond=None)[0]
    rx = x - X @ np.linalg.lstsq(X, x, rcond=None)[0]
    return float(np.corrcoef(ry, rx)[0, 1])


def boot_partial(pp, xcol, ctrl_cols, n_boot=1000, seed=42):
    blk = ((pp.index - pp.index.min()) / pd.Timedelta(days=30)).astype(int).to_numpy()
    ub = np.unique(blk)
    by = {k: np.flatnonzero(blk == k) for k in ub}
    rng = np.random.default_rng(seed)
    st = []
    for _ in range(n_boot):
        idx = np.concatenate([by[k] for k in rng.choice(ub, len(ub), replace=True)])
        q = pp.iloc[idx]
        st.append(partial_r(q["y"].to_numpy(), q[xcol].to_numpy(), q[ctrl_cols].to_numpy()))
    return float(np.percentile(st, 2.5)), float(np.percentile(st, 97.5))


s2_component = p["wb"] - p["wbclim"]          # part of the WB anomaly due to observed (vs climatological) Kcb
diag = {
    "n_days_all_defined": len(p),
    "r_era_vs_wb_vineSR": float(np.corrcoef(p["era"], p["wb"])[0, 1]),
    "r_wb_vs_wbclim": float(np.corrcoef(p["wb"], p["wbclim"])[0, 1]),
    "partial_r_y_wb_given_era": partial_r(p["y"].to_numpy(), p["wb"].to_numpy(), p[["era"]].to_numpy()),
    "partial_r_y_wb_given_era_ci": boot_partial(p, "wb", ["era"]),
    "partial_r_y_wbst_given_era": partial_r(p["y"].to_numpy(), p["wbst"].to_numpy(), p[["era"]].to_numpy()),
    "partial_r_y_wbst_given_era_ci": boot_partial(p, "wbst", ["era"]),
    "partial_r_y_spei30_given_era": partial_r(p["y"].to_numpy(), p["spei30"].to_numpy(), p[["era"]].to_numpy()),
    "partial_r_y_spei30_given_era_ci": boot_partial(p, "spei30", ["era"]),
    "partial_r_y_S2component_given_era_and_wbclim": partial_r(p["y"].to_numpy(), s2_component.to_numpy(),
                                                              p[["era", "wbclim"]].to_numpy()),
    "std_z_wb_vineSR": float(p["wb"].std()),
    "std_S2component_z_all": float(s2_component.std()),
    "std_S2component_z_IV-X": float(s2_component[(s2_component.index.month >= 4) & (s2_component.index.month <= 10)].std()),
    "V9_loyo_coefs_mean[intercept,era,wb]": coefs_comb.mean(axis=0).tolist(),
    "V9_loyo_coefs_min": coefs_comb.min(axis=0).tolist(),
    "V9_loyo_coefs_max": coefs_comb.max(axis=0).tolist(),
    "V5_zr_choices": cv_choice["best_zr_m"].tolist(),
    "frac_days_RSW_eq_1_V1": float((runs["V1_WB_vine_SR"]["RSW"].loc["2016":"2024"] > 0.999).mean()),
    "annual_ETa_mm_V1_2016_2024": runs["V1_WB_vine_SR"]["ETa"].loc["2016":"2024"].resample("YE").sum().round(0).tolist(),
    "annual_ETa_mm_V4_2016_2024": runs["V4_WB_station"]["ETa"].loc["2016":"2024"].resample("YE").sum().round(0).tolist(),
    "annual_DP_mm_V1_2016_2024": runs["V1_WB_vine_SR"]["DP"].loc["2016":"2024"].resample("YE").sum().round(0).tolist(),
}
with open(f"{C.OUT}/results_diagnostics.json", "w") as fh:
    json.dump(diag, fh, indent=1, default=float)

# daily series for plots / later use
ser = pd.DataFrame({f"z_{k}": v for k, v in z_common.items()})
ser["z_ISMN_20_30"] = y_rz
ser["z_ISMN_10"] = y_10
for k, r in runs.items():
    ser[f"RSW_{k}"] = r["RSW"]
    ser[f"Ks_{k}"] = r["Ks"]
ser.loc["2016":"2024"].to_csv(f"{C.OUT}/series_daily_z.csv", index_label="date")
oper = pd.DataFrame({f"zoper_{k}": v for k, v in z_oper.items()})
oper.loc["1991":].to_csv(f"{C.OUT}/series_daily_z_operational.csv", index_label="date")

pd.set_option("display.width", 250)
cols = ["variant", "reference", "subset", "r", "lo", "hi", "n", "baseline_same_dates", "delta_r", "delta_lo_30d",
        "delta_hi_30d", "delta_lo_year", "delta_hi_year"]
print(res[cols].round(3).to_string(index=False))
print(ev.round(3).to_string(index=False))
print(py.round(2).to_string())
print(json.dumps(diag, indent=1, default=float))
