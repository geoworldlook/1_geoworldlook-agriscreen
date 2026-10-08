import numpy as np, pandas as pd
import a6_spei_wb_alert as a6
vz = a6.vz
cols = {k: v for k, v in a6.SP.items()}
cols["ISMN_20_30"] = a6.ins
P = pd.concat([vz.rename("ndvi")] + [v.rename(k) for k, v in cols.items()], axis=1).dropna()
print("\nSAME DAYS n=", len(P), "(2016-2024 scenes)")
rng = np.random.default_rng(5); yrs = P.index.year.to_numpy(); uy = np.unique(yrs)
for k in cols:
    r = P[["ndvi", k]].corr().iloc[0, 1]
    bs = []
    for _ in range(1000):
        pick = rng.choice(uy, len(uy), replace=True); idx = np.concatenate([np.flatnonzero(yrs == y) for y in pick])
        q = P.iloc[idx]; bs.append(q[["ndvi", k]].corr().iloc[0, 1] - q[["ndvi", "ISMN_20_30"]].corr().iloc[0, 1])
    print(f"  {k:12s} R(NDVI)={r:.3f}  dR vs ISMN target {r - P[['ndvi','ISMN_20_30']].corr().iloc[0,1]:+.3f} CI {np.percentile(bs,[2.5,97.5]).round(3)}")
S = a6.S
o = S.ins_z <= -1
for lab, prd in (("level>=2 (warn|alert)", S.cdi_level >= 2), ("level==3 alert", S.cdi_level == 3)):
    a = int((o & prd).sum()); b = int((~o & prd).sum()); c = int((o & ~prd).sum())
    print(f"  {lab:24s} n_flag={a+b:3d} hits={a} FA={b} miss={c} precision={a/(a+b):.2f} POD={a/(a+c):.2f}")
# ERA5 SMA <=-1 vs alert in IV-X: what fraction of SMA-warn dekads become alerts?
print(S.groupby(S.index.year).agg(alert=("cdi_level", lambda s: (s == 3).sum()), warn=("cdi_level", lambda s: (s == 2).sum()), ins_dry=("ins_z", lambda s: (s <= -1).sum())).to_string())
