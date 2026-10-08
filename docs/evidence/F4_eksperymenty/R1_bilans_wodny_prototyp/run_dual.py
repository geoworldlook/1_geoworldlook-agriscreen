"""Dual-source (vine + inter-row cover), two-layer FAO-56 balance (WaLIS-like vertical split) for VINEYARD_06.
Pre-registered choices (before results):
  vine Kcb(t)  = FAO-56 T11/T17 trapezoid shape for mid-latitude wine grapes (ini 30 d from 1 Apr, dev 60, mid 40, end 80;
                 Kcb 0.15/0.65/0.40) rescaled each year by S-2 vigour: Kcb_mid_y = A&P(fc_vine_y), where
                 fc_vine_y = (NDVI_JulAug_y - 0.30)/(0.85 - 0.30)   [0.30 = senescent inter-row/soil background],
                 h = 1.75 m, Kcb_full = 1.0, ML = 1.5. If a year has no Jul-Aug scenes -> FAO value 0.65.
  cover Kcb(t) = f_grass * Kcb_grass(t); f_grass = 0.5 (alternate rows grassed, unknown -> sensitivity 0 / 1),
                 Kcb_grass from station grass-plot S-2 NDVI (A&P h=0.3, Kcb_full=1.0, ML=2) as regional grass proxy.
  layers: top 0-0.4 m (cover + vine), bottom 0.4-1.2 m (vine only); p_vine=0.45, p_cover=0.5; soil PTF as before.
"""
import sys
import json
import numpy as np
import pandas as pd
sys.path.insert(0, "/tmp/claude-0/-home-user-1-geoworldlook-agriscreen/0b6bc240-34e1-5fd3-a139-3c46967fd603/scratchpad/wb")
from wb_proto import (load_era5, et0_hargreaves, load_ndvi, daily_ndvi, kcb_allen_pereira, saxton_rawls,
                      z_common, z_ref, insitu_daily_depth, OVR, rootzone)

e = load_era5()
e["et0"] = et0_hargreaves(e)
idx = e.index
d20, d30 = (insitu_daily_depth(z, OVR)["sm"] for z in (0.20, 0.30))
ins_z = z_common(pd.concat([d20, d30], axis=1, sort=True).dropna().mean(axis=1))
thFC, thWP = saxton_rawls(0.13, 0.45, 1.2 * 1.724)
AWC = thFC - thWP


def fao_trapezoid(dates, kini=0.15, kmid=0.65, kend=0.40, start=(4, 1), L=(30, 60, 40, 80)):
    out = np.full(len(dates), kini * 0 + 0.0)
    for i, t in enumerate(dates):
        d = (t - pd.Timestamp(t.year, *start)).days
        if d < 0 or d > sum(L):
            out[i] = 0.0                      # dormant vine: no transpiration
        elif d < L[0]:
            out[i] = kini
        elif d < L[0] + L[1]:
            out[i] = kini + (kmid - kini) * (d - L[0]) / L[1]
        elif d < L[0] + L[1] + L[2]:
            out[i] = kmid
        else:
            out[i] = kmid + (kend - kmid) * (d - L[0] - L[1] - L[2]) / L[3]
    return out


def vine_kcb(ndvi_obs, vigour=True, bg=0.30):
    base = fao_trapezoid(idx)
    if not vigour:
        return base, {}
    ja = ndvi_obs[ndvi_obs.index.month.isin([7, 8])]
    by_year = ja.groupby(ja.index.year).mean()
    kmid = {}
    for y, v in by_year.items():
        fc = np.clip((v - bg) / (0.85 - bg), 0.01, 0.99)
        kd = min(1.0, 1.5 * fc, fc ** (1 / (1 + 1.75)))
        kmid[y] = 0.15 + kd * (1.0 - 0.15)
    scale = np.array([kmid.get(t.year, 0.65) / 0.65 for t in idx])
    # scale only the part above the initial value so ini/dormancy stay FAO
    k = np.where(base > 0, 0.15 + (base - 0.15) * scale, 0.0)
    return np.clip(k, 0, None), kmid


def run2(kv, kc, Zt=0.4, Zr=1.2, pv=0.45, pc=0.5, Ze=0.10, REW=9.0, et0_scale=1.0, awc=AWC):
    P, ET0 = e["precip_mm"].to_numpy(), e["et0"].to_numpy() * et0_scale
    TAWt, TAWb = 1000 * awc * Zt, 1000 * awc * (Zr - Zt)
    TEW = 1000 * (thFC - 0.5 * thWP) * Ze
    Dt, Db, De = 0.0, 0.0, TEW / 2
    rows = np.full((len(P), 8), np.nan)
    for i in range(len(P)):
        p_i, et0 = P[i], ET0[i]
        kcmax = max(1.2, kv[i] + kc[i] + 0.05)
        fcv = min(0.9, kv[i] / 0.65 * 0.35) if kv[i] > 0 else 0.0     # rough vine cover for few
        few = max(1 - fcv - kc[i], 0.05)
        De = max(De - p_i, 0.0)
        Kr = 1.0 if De <= REW else max((TEW - De) / (TEW - REW), 0.0)
        Ke = max(min(Kr * (kcmax - kv[i] - kc[i]), few * kcmax), 0.0)
        E = Ke * et0
        De = min(De + E / few, TEW)
        # stress coefficients from start-of-day state
        TAW = TAWt + TAWb
        Dv = Dt + Db
        Ksv = 1.0 if Dv <= pv * TAW else max((TAW - Dv) / ((1 - pv) * TAW), 0.0)
        Ksc = 1.0 if Dt <= pc * TAWt else max((TAWt - Dt) / ((1 - pc) * TAWt), 0.0)
        Tv, Tc = Ksv * kv[i] * et0, Ksc * kc[i] * et0
        # rain: top first, excess to bottom, excess drains
        inf = p_i
        take = min(inf, Dt); Dt -= take; inf -= take
        take = min(inf, Db); Db -= take
        # vine uptake split by available water; cover + evaporation from top only
        at, ab = TAWt - Dt, TAWb - Db
        ft = at / (at + ab) if at + ab > 0 else 0.5
        Dt = min(Dt + Tc + E + Tv * ft, TAWt)
        Db = min(Db + Tv * (1 - ft), TAWb)
        rows[i] = (Dt, Db, 1 - (Dt + Db) / TAW, 1 - Dt / TAWt, Ksv, Tv, Tc, E)
    out = pd.DataFrame(rows, index=idx, columns=["Dt", "Db", "FTSW", "FTSW_top", "Ks_vine", "T_vine", "T_cover", "E"])
    out["theta_top"] = thFC - out["Dt"] / (1000 * Zt)
    return out, TAWt + TAWb


vy_obs = load_ndvi("VINEYARD_06", "S2_10m")
grass_obs = load_ndvi("SMOSMANIA_Condom", "S2_L2A", min_clear=0)
g_nd, _ = daily_ndvi(grass_obs, idx)
kcb_grass, _ = kcb_allen_pereira(g_nd.to_numpy(), 0.3, 1.0, 2.0)

kv, kmid = vine_kcb(vy_obs)
kv_fao, _ = vine_kcb(vy_obs, vigour=False)
print("vine Kcb_mid by year from S-2 Jul-Aug:", {k: round(v, 2) for k, v in kmid.items()})
variants = {
    "dual_S2vigour_grass0.5": (kv, 0.5 * kcb_grass),
    "dual_FAOvine_grass0.5": (kv_fao, 0.5 * kcb_grass),
    "dual_S2vigour_bare": (kv, 0 * kcb_grass),
    "dual_S2vigour_grass1.0": (kv, 1.0 * kcb_grass),
}
res, tabs = {}, {}
for name, (a, b) in variants.items():
    out, taw = run2(a, b)
    rows = []
    for y in range(2016, 2026):
        s = slice(f"{y}-06-01", f"{y}-09-30")
        f = out["FTSW"].loc[s]
        rows.append({"year": y, "days<0.4": int((f < 0.4).sum()), "days<0.2": int((f < 0.2).sum()),
                     "FTSW_mean": round(f.mean(), 2), "first<0.4": f[f < 0.4].index.min().strftime("%m-%d") if (f < 0.4).any() else "-",
                     "T_vine_mm": round(out["T_vine"].loc[s].sum()), "T_cover_mm": round(out["T_cover"].loc[s].sum()),
                     "ISMN_z": round(ins_z.loc[s].mean(), 2) if y <= 2024 else np.nan})
    t = pd.DataFrame(rows).set_index("year")
    tabs[name] = t
    yrs = t.loc[2016:2024]
    zt = z_common(out["theta_top"])
    res[name] = {"TAW_mm": round(taw), "spearman_FTSWmean_vs_ISMNz(9 seasons)": round(yrs["FTSW_mean"].rank().corr(yrs["ISMN_z"].rank()), 2),
                 "R_top0-40_anom_vs_ISMN20-30": round(pd.concat([zt, ins_z], axis=1).dropna().corr().iloc[0, 1], 3),
                 "mean_days<0.4_VI-IX": round(t["days<0.4"].mean(), 1), "range_days<0.4": (int(t["days<0.4"].min()), int(t["days<0.4"].max()))}
    if name == "dual_S2vigour_grass0.5":
        main = out
print(json.dumps(res, indent=1))
pd.set_option("display.width", 250)
for k in ("dual_S2vigour_grass0.5", "dual_FAOvine_grass0.5"):
    print(k)
    print(tabs[k].T.to_string())
# FTSW anomaly (DOY clim 1991-2020) for status use: seasonal mean z per year
fz = z_ref(main["FTSW"])
print("FTSW z (1991-2020 DOY clim), VI-IX mean:", {y: round(fz.loc[f"{y}-06-01":f"{y}-09-30"].mean(), 2) for y in range(2016, 2026)})
# sensitivity of the main variant to TAW and ET0 (season-mean FTSW per year)
sens = {}
for lab, kw in (("Zr=0.9", dict(Zr=0.9)), ("Zr=1.6", dict(Zr=1.6)), ("ET0x0.85", dict(et0_scale=0.85)), ("ET0x1.15", dict(et0_scale=1.15))):
    o, t = run2(kv, 0.5 * kcb_grass, **kw)
    sens[lab + f" (TAW {t:.0f} mm)"] = [int((o["FTSW"].loc[f"{y}-06-01":f"{y}-09-30"] < 0.4).sum()) for y in range(2016, 2026)]
print("days FTSW<0.4 VI-IX 2016..2025 under sensitivity:", json.dumps(sens))
main.to_csv("/tmp/claude-0/-home-user-1-geoworldlook-agriscreen/0b6bc240-34e1-5fd3-a139-3c46967fd603/scratchpad/wb/vineyard_dual.csv")
