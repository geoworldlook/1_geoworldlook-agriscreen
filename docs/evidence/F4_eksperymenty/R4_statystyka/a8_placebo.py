import numpy as np, pandas as pd, itertools
import a2_veg_anomaly as a2
g = a2.w[(a2.w.site_id == "VINEYARD_06") & (a2.w["product"] == "S2SR_2.5m")]
vz = a2.scene_z(g, "ndvi"); y = a2.y_full
p = vz.to_frame("x").join(y.rename("y")).dropna()
r0 = p.corr().iloc[0, 1]
yrs = sorted(set(p.index.year))
# placebo: veg anomaly of year A paired with the SM anomaly of year B at the same DOY (+-3 d nearest)
ydf = y.dropna()
def r_perm(perm):
    xs, ys = [], []
    for a, b in zip(yrs, perm):
        pa = p[p.index.year == a]
        for t, xv in pa["x"].items():
            try:
                tb = t.replace(year=b)
            except ValueError:
                continue
            if tb in ydf.index:
                xs.append(xv); ys.append(ydf.loc[tb])
    return np.corrcoef(xs, ys)[0, 1]
rng = np.random.default_rng(0); rs = []
for _ in range(3000):
    perm = list(rng.permutation(yrs))
    if any(a == b for a, b in zip(yrs, perm)):
        continue  # derangements only
    rs.append(r_perm(perm))
rs = np.array(rs)
print(f"observed R={r0:.3f}; placebo (year-deranged) R: mean {rs.mean():.3f}, 95th pct {np.percentile(rs,95):.3f}, "
      f"99th {np.percentile(rs,99):.3f}; one-sided p={np.mean(rs >= r0):.4f}; n_perm={len(rs)}")
# without 2022
q = p[p.index.year != 2022]; print("R without 2022:", round(q.corr().iloc[0,1], 3), "n", len(q))
q = p[~p.index.year.isin([2017, 2022])]; print("R without 2017 & 2022:", round(q.corr().iloc[0,1], 3), "n", len(q))
