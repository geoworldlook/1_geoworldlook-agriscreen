import sys, numpy as np, pandas as pd
sys.path.insert(0, ".")
from wb_proto import load_era5, z_common, insitu_daily_depth, OVR, rootzone, CFG7
e = load_era5()
d20, d30 = (insitu_daily_depth(z, OVR)["sm"] for z in (0.20, 0.30))
ins = z_common(pd.concat([d20, d30], axis=1, sort=True).dropna().mean(axis=1))
cand = {"ERA5L_RZ": z_common(rootzone(e)), "ERA5L_0-28": z_common((7*e.sm_l1+21*e.sm_l2)/28),
        "WB_station_S2": z_common(pd.read_csv("station_wb_s2.csv", index_col=0, parse_dates=True)["theta_rz"]),
        "WB_vine_dual_top": z_common(pd.read_csv("vineyard_dual.csv", index_col=0, parse_dates=True)["theta_top"])}
j = pd.concat([ins.rename("y")] + [v.rename(k) for k, v in cand.items()], axis=1, sort=True).dropna()
rng = np.random.default_rng(42)
blk = ((j.index - j.index.min()).days // 30).to_numpy(); ub = np.unique(blk); ib = {b: np.flatnonzero(blk == b) for b in ub}
def r(a, b): return np.corrcoef(a, b)[0, 1]
for k in ("ERA5L_0-28", "WB_station_S2", "WB_vine_dual_top"):
    d0 = r(j[k], j.y) - r(j["ERA5L_RZ"], j.y); bs = []
    for _ in range(2000):
        idx = np.concatenate([ib[b] for b in rng.choice(ub, len(ub))]); s = j.iloc[idx]
        bs.append(r(s[k], s.y) - r(s["ERA5L_RZ"], s.y))
    print(f"{k} - ERA5L_RZ: dR={d0:+.3f} 95% CI [{np.percentile(bs,2.5):+.3f}, {np.percentile(bs,97.5):+.3f}] n={len(j)}")
d0 = r(j["WB_station_S2"], j.y) - r(j["ERA5L_0-28"], j.y); bs=[]
for _ in range(2000):
    idx = np.concatenate([ib[b] for b in rng.choice(ub, len(ub))]); s = j.iloc[idx]
    bs.append(r(s["WB_station_S2"], s.y) - r(s["ERA5L_0-28"], s.y))
print(f"WB_station_S2 - ERA5L_0-28: dR={d0:+.3f} 95% CI [{np.percentile(bs,2.5):+.3f}, {np.percentile(bs,97.5):+.3f}]")
