import numpy as np, pandas as pd, sys
sys.argv=["x"]
from common import veg_obs, s4
w = veg_obs(); w = w[w.time.dt.month.between(4,10)]
g = w[(w.site_id=="VINEYARD_06")&(w["product"]=="S2SR_2.5m")]
cfg={"VEG_HALF_WINDOW_DAYS":15,"VEG_MIN_REF":5,"VEG_MIN_CLEAR_FRAC":0.9}
a = s4.scene_anomaly(g,"ndvi",cfg)
d = a.dropna(subset=["z"]).copy()
yrs_in_pool=[]
doy=d.time.dt.dayofyear.to_numpy(); yr=d.time.dt.year.to_numpy()
for i in range(len(d)):
    m=(yr!=yr[i])&(s4._circ_doy_dist(doy,doy[i])<=15)
    yrs_in_pool.append(len(set(yr[m])))
d["n_years"]=yrs_in_pool
print("n_ref scenes: median", d.n_ref.median(), "IQR", d.n_ref.quantile([.25,.75]).tolist(), "; distinct years in pool: median", np.median(yrs_in_pool), "min", min(yrs_in_pool))
print("clear scenes per season:", d.groupby(d.time.dt.year).size().to_dict())
# clim_std variability: day-to-day relative change (sampling noise in sigma)
d=d.sort_values("time")
print("clim_std: median", round(d.clim_std.median(),4), "CV across scenes", round(d.clim_std.std()/d.clim_std.mean(),2))
print("z distribution: sd", round(d.z.std(),2), "share |z|>2:", round((d.z.abs()>2).mean(),3), "(normal 0.046)", "share z<=-1:", round((d.z<=-1).mean(),3), "(normal 0.159)")
from scipy import stats
print("theory P(|t8|>2/sqrt(1+1/9)) =", round(2*stats.t.sf(2/np.sqrt(1+1/9), 8), 3))
# Year-weighted climatology + predictive-t calibration
def yw_z(g, col="ndvi", hw=15):
    dd = g[(g.clear_frac>=0.9)&g[col].notna()].sort_values("time").copy()
    doy=dd.time.dt.dayofyear.to_numpy(); yr=dd.time.dt.year.to_numpy(); v=dd[col].to_numpy(float)
    zc=[]; zraw=[]
    for i in range(len(dd)):
        m=(yr!=yr[i])&(s4._circ_doy_dist(doy,doy[i])<=hw)
        ym = pd.Series(v[m]).groupby(yr[m]).mean()   # one value per year
        n=len(ym)
        if n<5: zc.append(np.nan); zraw.append(np.nan); continue
        z=(v[i]-ym.mean())/ym.std(ddof=1)
        zraw.append(z)
        p=stats.t.cdf(z/np.sqrt(1+1/n), n-1)
        zc.append(stats.norm.ppf(np.clip(p,1e-4,1-1e-4)))
    idx=dd.time.dt.floor("D").to_numpy()
    return pd.Series(zraw,index=idx).groupby(level=0).mean(), pd.Series(zc,index=idx).groupby(level=0).mean()
zr, zc = yw_z(g)
for lab, z in (("year-weighted raw z", zr), ("year-weighted + predictive-t", zc)):
    z=z.dropna()
    print(f"{lab:32s} sd={z.std():.2f} |z|>2={np.mean(np.abs(z)>2):.3f} z<=-1={np.mean(z<=-1):.3f}")
import a2_veg_anomaly as a2
a2.r_with(zr, label="NDVI year-weighted z")
a2.r_with(zc, label="NDVI year-weighted + predictive-t z")
