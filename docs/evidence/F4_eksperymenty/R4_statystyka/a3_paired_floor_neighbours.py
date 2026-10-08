"""A3: paired dR with year-block bootstrap + power; summer floor effect of probe; neighbour stations & triple collocation."""
import numpy as np
import pandas as pd
from common import COMMON, era5, insitu, insitu_rz, zclim, s4, veg_obs
import a2_veg_anomaly as a2  # reuses helpers (re-runs a2 prints; acceptable)

w = a2.w
y = a2.y_full


def paired(z1, z2, ref, lab, B=2000):
    p = pd.concat([z1.rename("a"), z2.rename("b"), ref.rename("y")], axis=1).dropna()
    ra, rb = p[["a", "y"]].corr().iloc[0, 1], p[["b", "y"]].corr().iloc[0, 1]
    rng = np.random.default_rng(1); yrs = p.index.year.to_numpy(); uy = np.unique(yrs); d = []
    for _ in range(B):
        pick = rng.choice(uy, len(uy), replace=True)
        idx = np.concatenate([np.flatnonzero(yrs == k) for k in pick])
        q = p.iloc[idx]
        d.append(q[["b", "y"]].corr().iloc[0, 1] - q[["a", "y"]].corr().iloc[0, 1])
    lo, hi = np.percentile(d, [2.5, 97.5]); lo90, hi90 = np.percentile(d, [5, 95])
    print(f"{lab:50s} n={len(p)} R_a={ra:.3f} R_b={rb:.3f} dR={rb-ra:+.3f} 95%CI[{lo:+.3f},{hi:+.3f}] 90%CI[{lo90:+.3f},{hi90:+.3f}]")


print("\n######## A3 paired comparisons (year-block bootstrap) ########")
gsr = w[(w.site_id == "VINEYARD_06") & (w["product"] == "S2SR_2.5m")]
g10 = w[(w.site_id == "VINEYARD_06") & (w["product"] == "S2_10m")]
base = a2.scene_z(gsr, "ndvi")
paired(a2.scene_z(g10, "ndvi"), base, y, "SR NDVI vs 10 m NDVI")
paired(base, a2.scene_z(gsr, "ndvi", robust=True), y, "robust z vs mean/sd z (SR NDVI)")
paired(base, a2.scene_z(gsr, "ndmi"), y, "NDMI vs NDVI (SR)")
paired(base, -a2.scene_z(gsr, "crswir"), y, "-CRSWIR vs NDVI (SR)")
paired(base, a2.scene_z(g10, "ndvi"), a2.x_era, "ref=ERA5: 10m vs SR NDVI")

print("\n######## A4 summer floor effect of ISMN 20-30 cm ########")
rz = insitu_rz("Condom")
clim_min = rz.quantile(0.02)
z = zclim(rz)
df = pd.DataFrame({"sm": rz, "z": z}).dropna()
print("2% quantile of 20-30 cm SM:", round(clim_min, 3))
print(df.groupby(df.index.month).agg(sm_mean=("sm", "mean"), sm_sd=("sm", "std"), z_sd=("z", "std"),
                                      near_floor=("sm", lambda s: (s <= clim_min + 0.02).mean())).round(3).to_string())
e = era5()
for lay in ("sm_l1", "sm_l2", "sm_l3"):
    print(lay, "monthly sd (2016-2024):", e.loc["2016":"2024", lay].groupby(e.loc["2016":"2024"].index.month).std().round(3).to_dict())

print("\n######## A5 neighbour stations (anomaly R vs Condom, 20-30 cm and 5 cm) ########")
stations = ["Condom", "PeyrusseGrande", "Lahas", "CreondArmagnac", "Savenes", "SaintFelixdeLauragais", "Montaut",
            "Urgons", "Sabres"]
coords = {"Condom": (43.9744, 0.3361), "PeyrusseGrande": (43.6664, 0.2217), "Lahas": (43.5472, 0.8878),
          "CreondArmagnac": (43.9936, -0.0469), "Savenes": (43.825, 1.1767), "SaintFelixdeLauragais": (43.4417, 1.88),
          "Montaut": (43.1922, 1.6436), "Urgons": (43.6397, -0.435), "Sabres": (44.1475, -0.8456)}
Z = {}
for s in stations:
    try:
        Z[s] = zclim(insitu_rz(s))
    except Exception as ex:  # noqa
        print(s, "failed", ex)
ZZ = pd.DataFrame(Z)
era_z = zclim(s4.rootzone(e.loc[COMMON[0]:COMMON[1]]))


def dist(a, b):
    la1, lo1 = np.radians(coords[a]); la2, lo2 = np.radians(coords[b])
    return 6371 * np.arccos(np.sin(la1) * np.sin(la2) + np.cos(la1) * np.cos(la2) * np.cos(lo1 - lo2))


for s in ZZ.columns:
    p = ZZ[["Condom", s]].dropna()
    pe = pd.concat([ZZ[s], era_z], axis=1).dropna()
    print(f"{s:24s} d={dist('Condom', s):5.0f} km  n={len(p):4d}  R(Condom insitu)={p.corr().iloc[0,1]:.3f}  "
          f"R(ERA5 Condom cell)={pe.corr().iloc[0,1]:.3f}")
gers = [c for c in ("PeyrusseGrande", "Lahas", "CreondArmagnac", "Savenes") if c in ZZ]
comp = ZZ[gers].mean(axis=1, skipna=False)
comp_all = ZZ[gers + ["Condom"]].mean(axis=1, skipna=False)
p = pd.concat([era_z.rename("era"), ZZ["Condom"].rename("condom"), comp.rename("neigh")], axis=1).dropna()
print("n triplets:", len(p), "\ncorr matrix:\n", p.corr().round(3))
# Classical TC (covariance notation, McColl et al. 2014): R_i^2 = Q_ij Q_ik / (Q_ii Q_jk)
Q = p.cov().to_numpy()
names = list(p.columns)
for i in range(3):
    j, k = [m for m in range(3) if m != i]
    r2 = Q[i, j] * Q[i, k] / (Q[i, i] * Q[j, k])
    print(f"ETC: R({names[i]} vs unknown truth) = {np.sqrt(r2):.3f}")
pa = pd.concat([era_z.rename("era"), comp_all.rename("comp5")], axis=1).dropna()
print("ERA5 vs 5-station Gers composite R =", round(pa.corr().iloc[0, 1], 3), "n=", len(pa))
# Year-block bootstrap of TC R for ERA5
rng = np.random.default_rng(2); yrs = p.index.year.to_numpy(); uy = np.unique(yrs); out = {n: [] for n in names}
for _ in range(1000):
    pick = rng.choice(uy, len(uy), replace=True)
    idx = np.concatenate([np.flatnonzero(yrs == k) for k in pick])
    Qb = p.iloc[idx].cov().to_numpy()
    for i in range(3):
        j, k = [m for m in range(3) if m != i]
        out[names[i]].append(np.sqrt(max(Qb[i, j] * Qb[i, k] / (Qb[i, i] * Qb[j, k]), 0)))
print({n: np.percentile(v, [2.5, 97.5]).round(3) for n, v in out.items()})
