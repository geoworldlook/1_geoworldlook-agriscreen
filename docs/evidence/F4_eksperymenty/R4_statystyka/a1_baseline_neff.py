"""A1: reproduce ERA5 RZ vs ISMN 20-30 cm anomaly R; effective N; block-length sensitivity; event skill set."""
import numpy as np
import pandas as pd
from common import COMMON, era5, insitu_rz, zclim, neff_bretherton, fisher_ci, s4

e = era5().loc[COMMON[0]:COMMON[1]]
rz_era = s4.rootzone(e)
rz_ins = insitu_rz("Condom")
x = zclim(rz_era)
y = zclim(rz_ins)
p = pd.concat([x.rename("x"), y.rename("y")], axis=1).dropna()
r = p.corr().iloc[0, 1]
print(f"ERA5 RZ vs ISMN 20-30 anomaly R = {r:.3f}, n = {len(p)}")
for k in (1, 10, 30, 60, 90, 120, 180):
    print(f"  ACF lag {k:3d}: ERA5 {x.asfreq('D').autocorr(k):.2f}  ISMN {y.asfreq('D').autocorr(k):.2f}")
n, ne = neff_bretherton(x, y)
print(f"N = {n}, N_eff (Bretherton) = {ne:.1f}; Fisher CI with N_eff: {fisher_ci(r, ne)}")


# Moving-block bootstrap with different block lengths
def mbb(px, py, block, B=2000, seed=1):
    rng = np.random.default_rng(seed)
    n = len(px)
    nb = int(np.ceil(n / block))
    out = []
    for _ in range(B):
        starts = rng.integers(0, n - block + 1, nb)
        idx = np.concatenate([np.arange(s, s + block) for s in starts])[:n]
        out.append(np.corrcoef(px[idx], py[idx])[0, 1])
    return np.percentile(out, [2.5, 97.5])


# Make contiguous daily (drop NaN rows -> approximately contiguous)
px, py = p["x"].to_numpy(), p["y"].to_numpy()
for b in (1, 30, 90, 180, 365):
    lo, hi = mbb(px, py, b)
    print(f"  MBB block {b:3d} d: CI [{lo:.3f}, {hi:.3f}]")

# Year-level jackknife (leave-one-year-out) R
yrs = sorted(set(p.index.year))
loyo = {yy: p[p.index.year != yy].corr().iloc[0, 1] for yy in yrs}
print("LOYO R:", {k: round(v, 3) for k, v in loyo.items()})
nj = len(yrs)
rj = np.array(list(loyo.values()))
se_j = np.sqrt((nj - 1) / nj * np.sum((rj - rj.mean()) ** 2))
print(f"Jackknife(year) SE = {se_j:.3f} -> approx CI [{r - 1.96 * se_j:.3f}, {r + 1.96 * se_j:.3f}]")

# Spearman
print("Spearman rho:", round(p.corr(method="spearman").iloc[0, 1], 3))

# ---------- Dekad events ----------
st = pd.read_csv("/tmp/claude-0/-home-user-1-geoworldlook-agriscreen/0b6bc240-34e1-5fd3-a139-3c46967fd603/scratchpad/drive_data/gwl_status.csv")
st = st[st.site_id == "VINEYARD_06"].copy()
st["date"] = pd.to_datetime(st["date"])
tmp = pd.DataFrame({"z": y.to_numpy(), "dk": s4.dekad_end(pd.Series(y.index)).to_numpy()})
ins_dk = tmp.groupby("dk")["z"].mean()
j = st.set_index("date").join(ins_dk.rename("ins_z"), how="inner").dropna(subset=["ins_z", "sma_rz"])
print("dekads joined:", len(j))


def table(obs, prd):
    a = int((obs & prd).sum()); b = int((~obs & prd).sum()); c = int((obs & ~prd).sum()); d = int((~obs & ~prd).sum())
    n = a + b + c + d
    pod = a / (a + c); far = b / (a + b); pofd = b / (b + d); csi = a / (a + b + c)
    ar = (a + b) * (a + c) / n
    ets = (a - ar) / (a + b + c - ar)
    hss = 2 * (a * d - b * c) / ((a + c) * (c + d) + (a + b) * (b + d))
    pss = pod - pofd
    F, H = pofd, pod
    sedi = (np.log(F) - np.log(H) - np.log(1 - F) + np.log(1 - H)) / (np.log(F) + np.log(H) + np.log(1 - F) + np.log(1 - H))
    bias = (a + b) / (a + c)
    return dict(a=a, b=b, c=c, d=d, base=(a + c) / n, POD=pod, FAR=far, POFD=pofd, CSI=csi, ETS=ets, HSS=hss, PSS=pss,
                SEDI=sedi, freq_bias=bias)


obs = j["ins_z"] <= -1
for thr in (-0.5, -0.8, -1.0, -1.2, -1.5):
    prd = j["sma_rz"] <= thr
    t = table(obs, prd)
    print(f"thr {thr}: " + ", ".join(f"{k}={v:.3f}" if isinstance(v, float) else f"{k}={v}" for k, v in t.items()))

from sklearn.metrics import roc_auc_score, average_precision_score
auc = roc_auc_score(obs, -j["sma_rz"])
ap = average_precision_score(obs, -j["sma_rz"])
print(f"ROC AUC (SMA_RZ as score for ISMN z<=-1) = {auc:.3f}; AP = {ap:.3f} (base rate {obs.mean():.3f})")

# Year-block bootstrap of AUC & PSS
rng = np.random.default_rng(3)
yrs_dk = j.index.year.to_numpy()
uy = np.unique(yrs_dk)
aucs, psss, hsss = [], [], []
for _ in range(2000):
    pick = rng.choice(uy, len(uy), replace=True)
    idx = np.concatenate([np.flatnonzero(yrs_dk == k) for k in pick])
    o, s = obs.to_numpy()[idx], j["sma_rz"].to_numpy()[idx]
    if o.all() or (~o).all():
        continue
    aucs.append(roc_auc_score(o, -s))
    t = table(pd.Series(o), pd.Series(s <= -1))
    psss.append(t["PSS"]); hsss.append(t["HSS"])
print("Year-block bootstrap 95% CI: AUC", np.percentile(aucs, [2.5, 97.5]).round(3), "PSS", np.percentile(psss, [2.5, 97.5]).round(3),
      "HSS", np.percentile(hsss, [2.5, 97.5]).round(3))

# Season stratification (growing season IV-X vs rest)
for name, m in (("IV-X", j.index.month.isin(range(4, 11))), ("XI-III", ~j.index.month.isin(range(4, 11)))):
    t = table(obs[m], (j["sma_rz"] <= -1)[m])
    print(name, {k: round(v, 3) if isinstance(v, float) else v for k, v in t.items()})

# Event (run) level: consecutive dekads with ISMN z<=-1 (>=2 dekads)
def runs(b):
    ev, cur = [], None
    for t, v in b.items():
        if v and cur is None:
            cur = [t, t]
        elif v:
            cur[1] = t
        elif cur is not None:
            ev.append(tuple(cur)); cur = None
    if cur is not None:
        ev.append(tuple(cur))
    return ev


ev_obs = [e_ for e_ in runs(obs) if (e_[1] - e_[0]).days >= 10]
ev_prd = [e_ for e_ in runs(j["sma_rz"] <= -1) if (e_[1] - e_[0]).days >= 10]
hit = 0; lags = []
for a0, a1 in ev_obs:
    ov = [(b0, b1) for b0, b1 in ev_prd if b0 <= a1 and b1 >= a0]
    if ov:
        hit += 1; lags.append((ov[0][0] - a0).days)
fa = sum(1 for b0, b1 in ev_prd if not any(b0 <= a1 and b1 >= a0 for a0, a1 in ev_obs))
print(f"Event-level (>=2 dekads): obs events {len(ev_obs)}, pred events {len(ev_prd)}, hits {hit}, false events {fa}, "
      f"onset lag (pred-obs) days median {np.median(lags) if lags else np.nan}, list {lags}")
