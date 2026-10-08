"""A6: SPI vs SPEI (Hargreaves, Tmax~2*Tmean-Tmin), FTSW bucket as pseudo-reference, alert vs warning skill."""
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.metrics import roc_auc_score
from common import COMMON, era5, insitu_rz, zclim, s4, veg_obs

e = era5()
LAT = np.radians(43.97)
doy = e.index.dayofyear.to_numpy()
dr = 1 + 0.033 * np.cos(2 * np.pi * doy / 365)
dec = 0.409 * np.sin(2 * np.pi * doy / 365 - 1.39)
ws = np.arccos(-np.tan(LAT) * np.tan(dec))
Ra = 24 * 60 / np.pi * 0.0820 * dr * (ws * np.sin(LAT) * np.sin(dec) + np.cos(LAT) * np.cos(dec) * np.sin(ws))  # MJ m-2 d-1
tmin = e["t2m_min_c"]; tmean = e["t2m_c"]
tmax = 2 * tmean - tmin            # approximation (ERA5-Land DAILY_AGGR has temperature_2m_max: ingest it instead)
et0 = (0.0023 * 0.408 * Ra * (tmean + 17.8) * np.sqrt((tmax - tmin).clip(lower=0))).clip(lower=0)
e["et0"] = et0
print("Mean annual ET0 (Hargreaves, approx Tmax) 1991-2020:", round(et0.loc["1991":"2020"].groupby(et0.loc["1991":"2020"].index.year).sum().mean(), 0), "mm")
print("Mean annual P:", round(e["precip_mm"].loc["1991":"2020"].groupby(e.loc["1991":"2020"].index.year).sum().mean(), 0), "mm")

REF = ("1991-01-01", "2020-12-31")


def spei(wb: pd.Series, days: int, dist="fisk", hw=15):
    acc = wb.asfreq("D").rolling(days, min_periods=int(0.9 * days)).sum().dropna()
    r = acc.loc[REF[0]:REF[1]]
    rd, rv = r.index.dayofyear.to_numpy(), r.to_numpy(float)
    dd = acc.index.dayofyear.to_numpy(); z = np.full(len(acc), np.nan); pvals = []
    for d in np.unique(dd):
        pool = rv[s4._circ_doy_dist(rd, d) <= hw]
        sel = dd == d
        if dist == "fisk":
            c, loc, sc = stats.fisk.fit(pool)
            cdf = stats.fisk.cdf(acc.to_numpy()[sel], c, loc, sc)
            if d % 30 == 0:
                pvals.append(stats.kstest(pool, "fisk", args=(c, loc, sc)).pvalue)
        elif dist == "genextreme":
            c, loc, sc = stats.genextreme.fit(pool)
            cdf = stats.genextreme.cdf(acc.to_numpy()[sel], c, loc, sc)
        else:  # empirical (Gringorten) non-parametric
            x = acc.to_numpy()[sel]
            cdf = np.array([(np.sum(pool <= xi) - 0.44) / (len(pool) + 0.12) for xi in x])
        z[sel] = stats.norm.ppf(np.clip(cdf, 1e-4, 1 - 1e-4))
    return pd.Series(z, index=acc.index), pvals


wb = e["precip_mm"] - e["et0"]
SP = {}
for days in (30, 90):
    SP[f"SPI{days//30}"] = s4.spi(e["precip_mm"], days, REF, 15)["z"]
    SP[f"SPEI{days//30}_fisk"], pv = spei(wb, days, "fisk")
    print(f"SPEI-{days//30} fisk KS p-values (sample of DOYs): min {np.min(pv):.3f}, share<0.05 {np.mean(np.array(pv)<0.05):.2f}")
    SP[f"SPEI{days//30}_emp"], _ = spei(wb, days, "emp")

# FTSW bucket (vineyard): TTSW 150 mm, Ks/ET = ET0*Kc*Ks, Kc grows IV->VII (row crop ~0.2-0.5), Ks linear below FTSW 0.4
TTSW = 150.0
kc = pd.Series(0.25, index=e.index)
m = e.index.month
kc[(m >= 5) & (m <= 9)] = 0.45
kc[(m == 4) | (m == 10)] = 0.3
store = TTSW; ftsw = []
for p, et, k in zip(e["precip_mm"].to_numpy(), e["et0"].to_numpy(), kc.to_numpy()):
    f = store / TTSW
    ks = min(1.0, f / 0.4)
    store = min(TTSW, max(0.0, store + p - et * k * ks))
    ftsw.append(store / TTSW)
e["ftsw"] = ftsw
SP["FTSW"] = s4.clim_anomaly(e["ftsw"], REF, 15)["z"]
SP["ERA5_RZ"] = s4.clim_anomaly(s4.rootzone(e), REF, 15)["z"]
SP["ERA5_L3"] = s4.clim_anomaly(e["sm_l3"], REF, 15)["z"]

ins = zclim(insitu_rz("Condom"))
print("\nDaily R with ISMN 20-30 cm anomaly (2016-2024), all months and IV-X:")
for k, v in SP.items():
    p = pd.concat([v.rename("x"), ins.rename("y")], axis=1).dropna()
    q = p[p.index.month.isin(range(4, 11))]
    print(f"  {k:14s} all R={p.corr().iloc[0,1]:.3f} (n={len(p)})  IV-X R={q.corr().iloc[0,1]:.3f}")

# vs vineyard NDVI anomaly (SR) — scene days
import a2_veg_anomaly as a2  # noqa: E402
g = a2.w[(a2.w.site_id == "VINEYARD_06") & (a2.w["product"] == "S2SR_2.5m")]
vz = a2.scene_z(g, "ndvi")
print("\nR with vineyard SR NDVI anomaly (scene days):")
for k, v in list(SP.items()) + [("ISMN_20_30", ins)]:
    p = pd.concat([vz.rename("x"), v.rename("y")], axis=1).dropna()
    print(f"  {k:14s} R={p.corr().iloc[0,1]:.3f} n={len(p)}")

# Event AUC for ISMN dekad z<=-1 in IV-X
st = pd.DataFrame(SP)
st = st.loc["2016":"2024"]
dk = s4.dekad_end(pd.Series(st.index)).to_numpy()
st_dk = st.groupby(dk).agg(["mean", "last"])
tmp = pd.DataFrame({"z": ins.to_numpy(), "dk": s4.dekad_end(pd.Series(ins.index)).to_numpy()})
ins_dk = tmp.groupby("dk")["z"].mean()
J = pd.concat([st_dk, ins_dk.rename(("ins", "z"))], axis=1).dropna()
J = J[J.index.month.isin(range(4, 11))]
obs = J[("ins", "z")] <= -1
print(f"\nIV-X dekads n={len(J)}, base rate {obs.mean():.3f}; ROC AUC for ISMN z<=-1:")
for k in SP:
    agg = "mean" if k.startswith(("ERA5", "FTSW")) else "last"
    print(f"  {k:14s} AUC={roc_auc_score(obs, -J[(k, agg)]):.3f}")

# Alert vs warning precision against ISMN dekad dryness (IV-X)
S = pd.read_csv(a2.__dict__.get("DD", "/tmp/claude-0/-home-user-1-geoworldlook-agriscreen/0b6bc240-34e1-5fd3-a139-3c46967fd603/scratchpad/drive_data") + "/gwl_status.csv")
S = S[S.site_id == "VINEYARD_06"].copy(); S["date"] = pd.to_datetime(S["date"])
S = S.set_index("date").join(ins_dk.rename("ins_z"), how="inner")
S = S[S.index.month.isin(range(4, 11))]
for lab, prd in (("warning-or-alert (level>=2)", S.cdi_level >= 2), ("alert (level 3)", S.cdi_level == 3),
                 ("any (level>=1)", S.cdi_level >= 1)):
    o = S.ins_z <= -1
    a = int((o & prd).sum()); b = int((~o & prd).sum()); c = int((o & ~prd).sum())
    print(f"  {lab:28s} n_flag={a+b:3d} hits={a} FA={b} miss={c} precision={a/(a+b) if a+b else np.nan:.2f} POD={a/(a+c):.2f}")
print("alert dekads by year:", S[S.cdi_level == 3].index.year.value_counts().sort_index().to_dict())
