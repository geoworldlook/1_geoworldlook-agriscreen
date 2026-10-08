import sys; sys.dont_write_bytecode=True
sys.path.insert(0,"."); 
import numpy as np, pandas as pd
from v0_core import dr_boot
exec(open("v1_events.py").read().split("def dk(")[0])
from step_04_metrics_alert import clim_anomaly
from v0_core import zclim
zi=zclim(ref)
Z={}
for lab,s in (("rz",rz),("l2",e.sm_l2),("w028",(7*e.sm_l1+21*e.sm_l2)/28)):
    Z[lab]=clim_anomaly(s,("1991-01-01","2020-12-31"),15,min_n=30)["z"].loc["2016":"2024"]
D=pd.DataFrame(Z).join(zi.rename("y"),how="inner").dropna()
for sn,ms in (("all",range(1,13)),("IV-X",range(4,11)),("VII-X",range(7,11)),("XI-III",[11,12,1,2,3])):
    S=D[D.index.month.isin(list(ms))]
    (lo,hi),_=dr_boot(S.l2.to_numpy(),S.rz.to_numpy(),S.y.to_numpy(),S.index,90,n=2000)
    print(f"op-base {sn:6s} n={len(S)} R_rz={S.rz.corr(S.y):.3f} R_l2={S.l2.corr(S.y):.3f} R_w028={S.w028.corr(S.y):.3f} dR(l2-rz)={S.l2.corr(S.y)-S.rz.corr(S.y):+.3f} [{lo:.3f},{hi:.3f}] (90d blocks)")
# lagged RZ? maximum cross-corr lag of rz vs y
for lag in (-30,-15,0,15,30):
    print("lag",lag, round(D.rz.shift(lag).corr(D.y),3), round(D.l2.shift(lag).corr(D.y),3))
