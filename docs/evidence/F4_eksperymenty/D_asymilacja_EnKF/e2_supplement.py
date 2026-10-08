"""E2 - supplementary diagnostics (descriptive; nothing here is used to choose a setting).

1. R by year (ERA5 0-100, V0, V1, V3, V4, V1*), to see whether any gain/loss is concentrated in single years;
2. paired Brier-score differences (dekads, by-year block bootstrap, 2000 draws): V1 - V0, V0 - climatology,
   V1 - ERA5 deterministic (0/1), V0 - ERA5 deterministic;
3. persistence of the root-zone analysis increment: lag autocorrelation of (V1 - V0) theta2;
4. sensitivity of the open loop to the process-noise scale alpha (V0 with alpha = 1 a priori vs 2 / 4 used).
"""
import json

import numpy as np
import pandas as pd

import common as K
import config as C

meta = json.load(open(f"{K.OUT}/runs_meta.json"))["meta"]
ec = K.era5().loc[C.COMMON[0]:C.COMMON[1]]
z_ins = K.z_common(K.ismn_ref())
ins_dk = K.to_dekad(z_ins)
z_era = K.z_common(K.s4.rootzone(ec))


def load(name):
    d = np.load(f"{K.OUT}/run_{name}.npz")
    idx = pd.DatetimeIndex(d["index"].astype("datetime64[ns]"))
    keep = (idx >= C.COMMON[0]) & (idx <= C.COMMON[1])
    return idx[keep], d["th2"][keep].astype(float)


def zprod(name):
    idx, th2 = load(name)
    return K.z_common(pd.Series(th2.mean(axis=1), index=idx))


def pdk(name):
    idx, th2 = load(name)
    mu, sd = K.pooled_member_clim(th2, idx, C.COMMON)
    return (K.dekad_frame((th2 - mu[:, None]) / sd[:, None], idx) <= C.THR).mean(axis=1)


# 1. R by year
ser = {"ERA5_0_100": z_era, "V0": zprod(meta["V1"]["matched_V0"]), "V1": zprod("V1"), "V3": zprod("V3"),
       "V4": zprod("V4"), "V1star": zprod("V1star")}
by = pd.DataFrame({k: K.pair(v, z_ins, names=["x", "y"]).groupby(lambda t: t.year).apply(
    lambda g: g["x"].corr(g["y"])) for k, v in ser.items()})
by.to_csv(f"{K.OUT}/r_by_year.csv")
print("R by year:\n", by.round(3).to_string())
print("V1 - V0 by year:", (by["V1"] - by["V0"]).round(3).to_dict())

# 2. paired Brier differences, by-year block bootstrap
base_rate = float((ins_dk[ins_dk.index.year.isin(C.TRAIN_YEARS)] <= C.THR).mean())
P = pd.DataFrame({"V0": pdk(meta["V1"]["matched_V0"]), "V1": pdk("V1"), "V1star": pdk("V1star"),
                  "ERA5det": (K.to_dekad(z_era) <= C.THR).astype(float), "obs": (ins_dk <= C.THR).astype(float)}
                 ).dropna()
P["clim"] = base_rate
se = {c: (P[c] - P["obs"]) ** 2 for c in ("V0", "V1", "V1star", "ERA5det", "clim")}
yrs = P.index.year.to_numpy()
uy = np.unique(yrs)
ib = {y: np.flatnonzero(yrs == y) for y in uy}
rng = np.random.default_rng(42)
draws = [np.concatenate([ib[y] for y in rng.choice(uy, len(uy))]) for _ in range(2000)]
rows = []
for a, b in (("V1", "V0"), ("V0", "clim"), ("V1", "clim"), ("V1", "ERA5det"), ("V0", "ERA5det"),
             ("V1star", "V0"), ("ERA5det", "clim")):
    d = (se[a] - se[b]).to_numpy()
    bs = np.array([d[i].mean() for i in draws])
    rows.append(dict(a=a, b=b, dBS=d.mean(), lo=np.percentile(bs, 2.5), hi=np.percentile(bs, 97.5), n=len(d)))
bt = pd.DataFrame(rows)
bt.to_csv(f"{K.OUT}/brier_paired.csv", index=False)
print(f"\nBrier (dekads n={len(P)}, base rate train={base_rate:.3f}):",
      {c: round(float(v.mean()), 4) for c, v in se.items()})
print(bt.to_string(index=False, float_format=lambda x: f"{x:.4f}"))

# 3. increment persistence
i1, a1 = load("V1")
i0, a0 = load(meta["V1"]["matched_V0"])
diff = pd.Series(a1.mean(axis=1) - a0.mean(axis=1), index=i1)
ac = {lag: float(diff.autocorr(lag)) for lag in (1, 5, 10, 30, 60, 90)}
print("\nV1-V0 root-zone difference autocorrelation by lag (days):", {k: round(v, 3) for k, v in ac.items()})

# 4. open loop vs alpha
ol = {}
for name in sorted({m["matched_V0"] for m in meta.values() if "matched_V0" in m} | {"V0_a1.0"}):
    ol[name] = K.r_ci(zprod(name), z_ins)
    print(f"{name}: R={ol[name]['r']:.3f} [{ol[name]['lo']:.3f},{ol[name]['hi']:.3f}]")
json.dump(dict(increment_autocorr=ac, openloop_alpha=ol), open(f"{K.OUT}/e2_supplement.json", "w"), indent=1,
          default=float)
