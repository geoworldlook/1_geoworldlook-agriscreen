"""Vineyard experiment (VINEYARD_06): FAO-56 bucket with S-2 Kcb vs the current NDVI-anomaly layer.
Pre-registered parameters (before results):
  vine 'system' Kcb (vine + inter-row): A&P with h=1.5 m, Kcb_full=1.0, ML=1.5; alt.: Campos 2010 Kcb=1.44*NDVI-0.10
  Zr=1.2 m (FAO-56 T22 wine grapes 1.0-2.0 m), p=0.45 (FAO-56 T22 wine grapes), PTF soil as station.
  Nov-Mar: S-2 not ingested for the vineyard (IV-X filter) -> pseudo-observations NDVI=0.35 on the 15th
  (winter vineyard NDVI ~0.3, Pantaleoni Reluy 2022).
"""
import sys
import json
import numpy as np
import pandas as pd
sys.path.insert(0, "/tmp/claude-0/-home-user-1-geoworldlook-agriscreen/0b6bc240-34e1-5fd3-a139-3c46967fd603/scratchpad/wb")
from wb_proto import (load_era5, et0_hargreaves, load_ndvi, daily_ndvi, kcb_allen_pereira, saxton_rawls,
                      fao56_dual, r_ci, z_common, z_ref, insitu_daily_depth, OVR, rootzone, DATA)

e = load_era5()
e["et0"] = et0_hargreaves(e)
idx = e.index
d20, d30 = (insitu_daily_depth(z, OVR)["sm"] for z in (0.20, 0.30))
ins_z = z_common(pd.concat([d20, d30], axis=1, sort=True).dropna().mean(axis=1))
era_rz_z = z_common(rootzone(e))
thFC, thWP = saxton_rawls(0.13, 0.45, 1.2 * 1.724)


def with_winter(obs, value=0.35):
    yrs = range(idx.year.min(), idx.year.max() + 1)
    pseudo = [pd.Timestamp(y, m, 15) for y in yrs for m in (11, 12, 1, 2, 3)]
    pseudo = pd.Series(value, index=pd.DatetimeIndex(pseudo))
    pseudo = pseudo[(pseudo.index >= idx.min()) & (pseudo.index <= idx.max())]
    return pd.concat([obs, pseudo[~pseudo.index.isin(obs.index)]]).sort_index()


def run(nd_daily, Zr=1.2, p=0.45, kcb_mode="AP", h=1.5, kcb_full=1.0, ml=1.5, taw_scale=1.0):
    kcb, fc = kcb_allen_pereira(nd_daily.to_numpy(), h, kcb_full, ml)
    if kcb_mode == "campos":
        kcb = np.clip(1.44 * nd_daily.to_numpy() - 0.10, 0.1, None)
    wp = thFC - (thFC - thWP) * taw_scale
    out, taw, _ = fao56_dual(e["precip_mm"].to_numpy(), e["et0"].to_numpy(), kcb, fc, thFC, wp, Zr, p)
    out.index = idx
    out["Kcb"] = kcb
    out["NDVI"] = nd_daily.to_numpy()
    return out, taw


runs = {}
for prod in ("S2_10m", "S2SR_2.5m"):
    obs = load_ndvi("VINEYARD_06", prod)
    nd, nd_clim = daily_ndvi(with_winter(obs), idx)
    runs[f"WB_{prod}_AP"], taw = run(nd)
    runs[f"WB_{prod}_campos"], _ = run(nd, kcb_mode="campos")
    if prod == "S2_10m":
        runs["WB_climKcb_AP"], _ = run(nd_clim)
        for sc in (0.7, 1.3):
            runs[f"WB_S2_10m_AP_TAWx{sc}"], _ = run(nd, taw_scale=sc)
print("vineyard TAW = %.0f mm (Zr=1.2 m)" % taw)

# ------------- current vegetation layer anomalies (from the registry) on scene days
an = pd.read_csv(f"{DATA}/gwl_anomalies.csv", parse_dates=["date"])
veg = {p: an[(an.site_id == "VINEYARD_06") & (an["product"] == p)].groupby("date")["z"].mean()
       for p in ("S2SR_2.5m_NDVI", "S2_10m_NDVI", "S2_10m_NDMI")}
days = veg["S2SR_2.5m_NDVI"].index.intersection(veg["S2_10m_NDVI"].index)
days = days[(days >= "2016-01-01") & (days <= "2024-12-31")]


def partial(x, y, zc):
    j = pd.concat([x.rename("x"), y.rename("y"), zc.rename("z")], axis=1).dropna()
    c = j.corr()
    rxy, rxz, ryz = c.loc["x", "y"], c.loc["x", "z"], c.loc["y", "z"]
    return round((rxy - rxz * ryz) / np.sqrt((1 - rxz ** 2) * (1 - ryz ** 2)), 3), len(j)


res = {}
for p, z in veg.items():
    res[f"{p} anomaly (current layer)"] = {**r_ci(z.reindex(days), ins_z), "partial_given_ERA5RZ": partial(z.reindex(days), ins_z, era_rz_z)}
res["ERA5L_RZ on same days"] = r_ci(era_rz_z.reindex(days), ins_z)
for k, wb in runs.items():
    zt = z_common(wb["theta_rz"])
    res[k + " theta anomaly, same days"] = {**r_ci(zt.reindex(days), ins_z),
                                             "partial_given_ERA5RZ": partial(zt.reindex(days), ins_z, era_rz_z)}
res["WB_S2_10m_AP all days"] = r_ci(z_common(runs["WB_S2_10m_AP"]["theta_rz"]), ins_z)

# ------------- vine-relevant outputs by season (VI-IX)
a = runs["WB_S2_10m_AP"]
c = runs["WB_campos_dummy"] if "WB_campos_dummy" in runs else runs["WB_S2_10m_campos"]
rows = []
for y in range(2016, 2026):
    s = slice(f"{y}-06-01", f"{y}-09-30")
    rows.append({"year": y,
                 "P_VI-IX_mm": round(e["precip_mm"].loc[s].sum()),
                 "ET0_VI-IX_mm": round(e["et0"].loc[s].sum()),
                 "T_vine+cover_mm": round(a["T"].loc[s].sum()),
                 "FTSW_min": round(a["FTSW"].loc[s].min(), 2),
                 "days_FTSW<0.4": int((a["FTSW"].loc[s] < 0.4).sum()),
                 "days_FTSW<0.2": int((a["FTSW"].loc[s] < 0.2).sum()),
                 "first_day_FTSW<0.4": (a["FTSW"].loc[s][a["FTSW"].loc[s] < 0.4].index.min().strftime("%m-%d")
                                        if (a["FTSW"].loc[s] < 0.4).any() else "-"),
                 "Campos_days_FTSW<0.4": int((c["FTSW"].loc[s] < 0.4).sum()),
                 "TAWx0.7_days<0.4": int((runs["WB_S2_10m_AP_TAWx0.7"]["FTSW"].loc[s] < 0.4).sum()),
                 "TAWx1.3_days<0.4": int((runs["WB_S2_10m_AP_TAWx1.3"]["FTSW"].loc[s] < 0.4).sum()),
                 "SR_vs_10m_maxabs_dFTSW": round((runs["WB_S2SR_2.5m_AP"]["FTSW"].loc[s] - a["FTSW"].loc[s]).abs().max(), 3),
                 "NDVI_SR_z_mean": round(veg["S2SR_2.5m_NDVI"].loc[s].mean(), 2),
                 "ISMN_z_mean": round(ins_z.loc[s].mean(), 2) if y <= 2024 else None,
                 "ERA5RZ_z_mean": round(z_ref(rootzone(e)).loc[s].mean(), 2),
                 "Kcb_mean": round(a["Kcb"].loc[s].mean(), 2)})
tab = pd.DataFrame(rows).set_index("year")
print(json.dumps(res, indent=1, default=str))
pd.set_option("display.width", 250)
print(tab.T.to_string())
yrs = tab.loc[2016:2024]
print("Spearman across 2016-2024 seasons vs ISMN_z_mean:",
      {k: round(yrs[k].rank().corr(yrs["ISMN_z_mean"].rank()), 2)
       for k in ("days_FTSW<0.4", "FTSW_min", "NDVI_SR_z_mean", "ERA5RZ_z_mean")})
print("Annual vine+cover transpiration & ETa (mean 2016-2025):",
      round(a["T"].loc["2016":"2025"].resample("YE").sum().mean()), round(a["ETa"].loc["2016":"2025"].resample("YE").sum().mean()),
      " ET0:", round(e["et0"].loc["2016":"2025"].resample("YE").sum().mean()), " P:", round(e["precip_mm"].loc["2016":"2025"].resample("YE").sum().mean()))
a.to_csv("/tmp/claude-0/-home-user-1-geoworldlook-agriscreen/0b6bc240-34e1-5fd3-a139-3c46967fd603/scratchpad/wb/vineyard_wb_10m.csv")
