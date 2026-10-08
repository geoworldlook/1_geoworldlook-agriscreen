"""Can better Sentinel-1 processing (per-orbit references, vegetation correction) make S-1 a useful surface observation?"""
import os, sys, numpy as np, pandas as pd
REPO = '/home/user/1_geoworldlook-agriscreen'; SP = os.path.dirname(os.getcwd())
sys.path.insert(0, REPO); os.chdir(REPO)
import step_07_station_pipeline as s7
cfg = s7.build_config(); D = SP + '/drive_data/'
ism = s7.insitu_daily_depth(0.05, {}); ism.index = pd.to_datetime(ism.index).normalize()
o = pd.read_csv(D + 'gwl_observations.csv'); o['t'] = pd.to_datetime(o.time_utc).dt.tz_localize(None)
g = o[(o.site_id == 'SMOSMANIA_Condom') & (o['product'] == 'S1_GRD')].pivot_table(index='t', columns='variable', values='value')
g['orb'] = g.angle.round(0)   # incidence angle identifies the relative orbit at a fixed point
print('angles:', g.orb.value_counts().to_dict())
g['d'] = g.index.normalize()
train = g.index.year <= 2020
def cd(x, mask):  # change detection: position between dry (p5) and wet (p95) reference from training years
    lo, hi = x[mask].quantile(0.05), x[mask].quantile(0.95); return ((x - lo) / (hi - lo)).clip(0, 1)
g['vv_cd_all'] = cd(g.vv_db, train)
g['vv_cd_orb'] = np.nan; g['vvveg_cd_orb'] = np.nan
for a, h in g.groupby('orb'):
    m = train[g.orb.values == a]
    g.loc[h.index, 'vv_cd_orb'] = cd(h.vv_db, m)
    # vegetation correction: remove part of VV explained by cross-pol ratio (fitted on training years per orbit)
    k = np.polyfit((h.vh_db - h.vv_db)[m], h.vv_db[m], 1)[0]
    g.loc[h.index, 'vvveg_cd_orb'] = cd(h.vv_db - k * (h.vh_db - h.vv_db), m)
rows = []
for col in ('vv_cd_all', 'vv_cd_orb', 'vvveg_cd_orb'):
    x = g.groupby('d')[col].mean()
    for seg, s in ism.groupby('segment'):
        j = pd.concat([x.rename('x'), s.sm.rename('y')], axis=1, join='inner').dropna()
        j = j[j.index.year >= 2021] if True else j   # evaluate only on test years (references from <=2020)
        if len(j) < 30: continue
        r, lo, hi = s7._r_with_ci(pd.Series(j.index), j.x.values, j.y.values, cfg)
        rows.append(dict(method=col, segment=seg, n=len(j), R=round(r, 3), CI=f'[{lo:.2f},{hi:.2f}]'))
print(pd.DataFrame(rows).to_string(index=False))
rows = []
e = pd.read_csv(D + 'era5_land_daily.csv', parse_dates=['time']).set_index('time').sm_l1
s = ism[ism.segment == 'seg2_ML2x'].sm
for a, h in g.groupby('orb'):
    x = h.groupby('d').vv_cd_orb.mean()
    j = pd.concat([x.rename('x'), s.rename('y'), e.rename('e')], axis=1, join='inner').dropna()
    j = j[j.index.year >= 2021]
    rows.append(dict(angle=a, n=len(j), R_S1=round(j.x.corr(j.y), 3), R_ERA5_same_days=round(j.e.corr(j.y), 3)))
print(pd.DataFrame(rows).to_string(index=False))
