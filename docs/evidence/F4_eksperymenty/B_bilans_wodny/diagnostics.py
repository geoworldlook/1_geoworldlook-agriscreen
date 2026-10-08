"""Diagnostics for Experiment B (no new model selection; explains WHY the S-2 Kcb adds little).

 a) sign check: S-2 component of the WB anomaly (z_V1 - z_V3) vs the v1.0 NDVI scene anomaly of VINEYARD_06
 b) robustness of 'S-2 Kcb adds nothing': Zr 0.5 m, and a stress test with the interannual Kcb deviation x2
 c) water-limited regime: annual ETa, first day with Ks < 1 per year, mean August RSW (V1, V3, V4)
 d) depth-mismatch diagnostic: ERA5-Land 0-28 cm anomaly; partial r of WB / SPEI30 given ERA5 0-28 cm
 e) paired dR of V9 (ERA5+WB, LOYO) vs ERA5 LOYO; exploratory post-hoc V10 = ERA5 + SPEI30 (LOYO)
 f) figure: daily anomalies 2016-2024
"""
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import common as C  # noqa: E402
import config as K  # noqa: E402
import wb_model as W  # noqa: E402

f = pd.read_csv(f"{C.OUT}/inputs_forcing.csv", index_col="date", parse_dates=True)
kc = pd.read_csv(f"{C.OUT}/inputs_kcb.csv", index_col="date", parse_dates=True)
ser = pd.read_csv(f"{C.OUT}/series_daily_z.csv", index_col="date", parse_dates=True)
e = C.era5()
VINE = dict(K.SOIL_BASE, **K.VINE)
GRASS = dict(K.SOIL_BASE, **K.GRASS)
y = C.ins_z("rz")
out = {}

# a) sign check vs v1.0 NDVI anomaly (registry gwl_anomalies, VINEYARD_06, S2SR_2.5m_NDVI)
an = pd.read_csv(f"{C.DATA}/gwl_anomalies.csv")
nd = an[(an["site_id"] == "VINEYARD_06") & (an["product"] == "S2SR_2.5m_NDVI")].copy()
nd["date"] = pd.to_datetime(nd["date"])
nd = nd.set_index("date")["z"].groupby(level=0).mean()
comp = (ser["z_V1_WB_vine_SR"] - ser["z_V3_WB_vine_clim"]).rename("s2comp")
kdev = (kc["vine_SR"] - kc["vine_SR_clim"]).rename("kcb_dev")
j = pd.concat([nd.rename("ndvi_z"), comp, kdev], axis=1, join="inner").dropna()
out["a_r_ndviZ_vs_S2component"] = float(np.corrcoef(j["ndvi_z"], j["s2comp"])[0, 1])
out["a_r_ndviZ_vs_KcbDeviation"] = float(np.corrcoef(j["ndvi_z"], j["kcb_dev"])[0, 1])
out["a_n_scenes"] = len(j)
out["a_S2component_quantiles_z_IV-X"] = comp[comp.index.month.isin(range(4, 11))].quantile([0.01, 0.5, 0.99]).round(3).tolist()


# b) robustness
def zrsw(kcb, soil):
    return C.anom_common(W.run_wb(f, kcb, soil)["RSW"])


rob = {}
for label, soil in (("zr0.5", dict(VINE, zr_m=0.5)), ("zr1.0", VINE)):
    z_obs = zrsw(kc["vine_SR"], soil)
    z_cli = zrsw(kc["vine_SR_clim"], soil)
    z_x2 = zrsw((kc["vine_SR_clim"] + 2 * (kc["vine_SR"] - kc["vine_SR_clim"])).clip(lower=K.SOIL_BASE["kc_min"]), soil)
    rob[label] = {"R_obsKcb": C.r_ci(z_obs, y)["r"], "R_climKcb": C.r_ci(z_cli, y)["r"],
                  "R_Kcbdev_x2": C.r_ci(z_x2, y)["r"],
                  "dR_obs_minus_clim": C.paired_delta_r(z_obs, z_cli, y, "30d"),
                  "r_zobs_vs_zclim": float(C.pair(z_obs, z_cli).corr().iloc[0, 1])}
out["b_robustness"] = rob

# c) water-limited regime
runs = {"V1": W.run_wb(f, kc["vine_SR"], VINE), "V3": W.run_wb(f, kc["vine_SR_clim"], VINE),
        "V4": W.run_wb(f, kc["station_L2A"], GRASS)}
reg = {}
for k, r in runs.items():
    r = r.loc["2016":"2024"]
    first_ks = r[r["Ks"] < 1].groupby(r[r["Ks"] < 1].index.year).apply(lambda g: g.index.min().dayofyear)
    reg[k] = {"annual_ETa_mm_mean": float(r["ETa"].resample("YE").sum().mean()),
              "annual_T_mm_mean": float(r["T"].resample("YE").sum().mean()),
              "annual_Kcb_ET0_mm_mean (potential T)": float((r["kcb"] * f.loc["2016":"2024", "et0"]).resample("YE").sum().mean()),
              "first_doy_Ks_lt_1_by_year": {int(a): int(b) for a, b in first_ks.items()},
              "mean_RSW_August": float(r.loc[r.index.month == 8, "RSW"].mean()),
              "days_per_year_Ks_lt_1": float((r["Ks"] < 1).groupby(r.index.year).sum().mean())}
out["c_regime"] = reg

# d) depth mismatch: ERA5 0-28 cm (layers 1-2 thickness-weighted)
era28 = (7 * e["sm_l1"] + 21 * e["sm_l2"]) / 28.0
z28 = C.anom_common(era28)
zrz = C.anom_common(C.s4.rootzone(e))
out["d_R_ERA5_0-28cm_vs_ISMN2030"] = C.r_ci(z28, y)
out["d_dR_ERA5_0-28_minus_0-100"] = C.paired_delta_r(z28, zrz, y, "30d")
p = pd.concat([y.rename("y"), z28.rename("e28"), zrz.rename("erz"), ser["z_V1_WB_vine_SR"].rename("wb"),
               ser["z_V6_SPEI30_like"].rename("sp30")], axis=1, join="inner").replace([np.inf, -np.inf], np.nan).dropna()


def partial_r(yv, xv, ctrl):
    X = np.column_stack([np.ones(len(ctrl)), ctrl])
    ry = yv - X @ np.linalg.lstsq(X, yv, rcond=None)[0]
    rx = xv - X @ np.linalg.lstsq(X, xv, rcond=None)[0]
    return float(np.corrcoef(ry, rx)[0, 1])


out["d_partial_r_wb_given_era0-28"] = partial_r(p["y"].values, p["wb"].values, p[["e28"]].values)
out["d_partial_r_spei30_given_era0-28"] = partial_r(p["y"].values, p["sp30"].values, p[["e28"]].values)
out["d_partial_r_wb_given_era0-28_and_era0-100"] = partial_r(p["y"].values, p["wb"].values, p[["e28", "erz"]].values)

# e) LOYO combinations evaluated against the LOYO ERA5-only model (same fitting procedure)
years = list(range(2016, 2025))


def loyo(xcols):
    d = pd.concat([*(x.rename(f"x{i}") for i, x in enumerate(xcols)), y.rename("y")], axis=1, join="inner")
    d = d.replace([np.inf, -np.inf], np.nan).dropna()
    pred = pd.Series(np.nan, index=d.index)
    xc = [c for c in d if c != "y"]
    for yv in years:
        tr, te = d.index.year != yv, d.index.year == yv
        X = np.column_stack([np.ones(tr.sum()), d.loc[tr, xc].to_numpy()])
        b = np.linalg.lstsq(X, d.loc[tr, "y"].to_numpy(), rcond=None)[0]
        pred[te] = np.column_stack([np.ones(te.sum()), d.loc[te, xc].to_numpy()]) @ b
    return pred


p_era = loyo([zrz])
p_wb = loyo([zrz, ser["z_V1_WB_vine_SR"]])
p_sp = loyo([zrz, ser["z_V6_SPEI30_like"]])
out["e_V9_ERA5+WB_vs_ERA5_loyo"] = C.paired_delta_r(p_wb, p_era, y, "30d")
out["e_V9_ERA5+WB_vs_ERA5_loyo_yearblocks"] = C.paired_delta_r(p_wb, p_era, y, "year")
out["e_V10_ERA5+SPEI30_vs_ERA5_loyo_POSTHOC"] = C.paired_delta_r(p_sp, p_era, y, "30d")
out["e_V10_ERA5+SPEI30_vs_ERA5_loyo_yearblocks_POSTHOC"] = C.paired_delta_r(p_sp, p_era, y, "year")
out["e_V10_vs_raw_ERA5_POSTHOC"] = C.paired_delta_r(p_sp, zrz, y, "30d")
out["e_V10_R_ci_POSTHOC"] = C.r_ci(p_sp, y)
out["e_V9_R_ci"] = C.r_ci(p_wb, y)
out["e_ERA5_loyo_R_ci"] = C.r_ci(p_era, y)
yr_gain = pd.DataFrame({"era": C.r_by_year(p_era, y), "wb": C.r_by_year(p_wb, y), "sp": C.r_by_year(p_sp, y)})
out["e_years_V9_better_than_ERA5loyo"] = int((yr_gain["wb"] > yr_gain["era"]).sum())
out["e_years_V10_better_than_ERA5loyo"] = int((yr_gain["sp"] > yr_gain["era"]).sum())
out["e_per_year_R"] = yr_gain.round(3).to_dict()

with open(f"{C.OUT}/results_diagnostics2.json", "w") as fh:
    json.dump(out, fh, indent=1, default=float)
print(json.dumps(out, indent=1, default=float))

# f) figure
fig, axes = plt.subplots(3, 1, figsize=(13, 9), sharex=True)
s = ser.loc["2016":"2024"]
ax = axes[0]
ax.plot(s.index, s["z_ISMN_20_30"], color="k", lw=1.2, label="ISMN Condom 20-30 cm")
ax.plot(s.index, s["z_B0_ERA5L_RZ"], color="tab:blue", lw=0.9, label="ERA5-Land 0-100 cm (v1.0)")
ax.plot(s.index, s["z_V1_WB_vine_SR"], color="tab:red", lw=0.9, label="FAO-56 WB, Kcb from vineyard S-2 SR")
ax.axhline(-1, color="grey", ls=":")
ax.set_ylabel("anomaly z (ref 2016-2024)")
ax.legend(loc="lower left", fontsize=8, ncol=3)
ax = axes[1]
ax.plot(s.index, s["z_V1_WB_vine_SR"] - s["z_V3_WB_vine_clim"], color="tab:green", lw=0.9,
        label="S-2 component of WB anomaly: z(obs Kcb) - z(clim Kcb)")
ax.set_ylabel("dz")
ax.legend(loc="lower left", fontsize=8)
ax = axes[2]
ax.plot(kc.loc["2016":"2024"].index, kc.loc["2016":"2024", "vine_SR"], color="tab:red", lw=0.9, label="Kcb vineyard (S-2 SR)")
ax.plot(kc.loc["2016":"2024"].index, kc.loc["2016":"2024", "vine_SR_clim"], color="grey", lw=0.9, label="Kcb climatology")
ax.plot(s.index, s["RSW_V1_WB_vine_SR"], color="tab:blue", lw=0.9, label="relative soil water 1-Dr/TAW (V1)")
ax.plot(s.index, s["Ks_V1_WB_vine_SR"], color="tab:orange", lw=0.7, label="Ks (V1)")
ax.legend(loc="lower left", fontsize=8, ncol=4)
fig.tight_layout()
fig.savefig(f"{C.OUT}/fig_wb_vs_era5_ismn.png", dpi=110)
