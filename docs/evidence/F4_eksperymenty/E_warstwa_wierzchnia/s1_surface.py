"""Surface (5 cm) soil moisture at ISMN Condom: which product / method tracks it best?"""
import os, sys, numpy as np, pandas as pd
REPO = '/home/user/1_geoworldlook-agriscreen'; SP = os.path.dirname(os.getcwd())
sys.path.insert(0, REPO); os.chdir(REPO)
import step_07_station_pipeline as s7
D = SP + '/drive_data/'
cfg = s7.build_config()

ism = s7.insitu_daily_depth(0.05, {})             # columns sm, n_hours, segment
ism.index = pd.to_datetime(ism.index).normalize()
print('ISMN 5cm segments:', ism.segment.value_counts().to_dict())

e = pd.read_csv(D + 'era5_land_daily.csv', parse_dates=['time']).set_index('time')
o = pd.read_csv(D + 'gwl_observations.csv'); o['t'] = pd.to_datetime(o.time_utc).dt.tz_localize(None)
st = o[o.site_id == 'SMOSMANIA_Condom']
s1 = st[(st['product'] == 'S1_CD_A') & (st.variable == 'sm_s1')].set_index('t').value
s1.index = s1.index.normalize(); s1 = s1.groupby(level=0).mean()
s2 = st[st['product'] == 'S2_L2A'].pivot_table(index='t', columns='variable', values='value')
s2.index = s2.index.normalize()

da = {}
for name in ('V0_a1.0', 'V1', 'V1star'):
    f = f'{SP}/exp_da/out/run_{name}.npz'
    if os.path.exists(f):
        z = np.load(f); da[name] = pd.Series(z['th1'].mean(1), index=pd.to_datetime(z['index']))

def anom35(s):
    return s - s.rolling(35, center=True, min_periods=10).mean()

def evaluate(x, label, days=None):
    rows = []
    for seg, g in ism.groupby('segment'):
        ref = g.sm
        if days is not None: ref = ref[ref.index.isin(days)]
        j = pd.concat([x.rename('x'), ref.rename('y')], axis=1, join='inner').dropna()
        # 35-day anomalies computed on the full daily series of each (product series daily or sparse)
        xa = anom35(x.reindex(pd.date_range(x.index.min(), x.index.max())).interpolate(limit=12))
        ya = anom35(g.sm.reindex(pd.date_range(g.index.min(), g.index.max())))
        ja = pd.concat([xa.rename('x'), ya.rename('y')], axis=1, join='inner').loc[j.index].dropna()
        if len(j) < 30: continue
        r_raw, lo_raw, hi_raw = s7._r_with_ci(pd.Series(j.index), j.x.values, j.y.values, cfg)
        r_an, lo_an, hi_an = s7._r_with_ci(pd.Series(ja.index), ja.x.values, ja.y.values, cfg)
        rows.append(dict(product=label, segment=seg, n=len(j), R_raw=round(r_raw, 3), CI_raw=f'[{lo_raw:.2f},{hi_raw:.2f}]',
                         R_anom35=round(r_an, 3), CI_anom35=f'[{lo_an:.2f},{hi_an:.2f}]'))
    return rows

rows = []
s1_days = s1.index
rows += evaluate(e.sm_l1, 'ERA5-Land L1 0-7 cm (all days)')
rows += evaluate(e.sm_l1, 'ERA5-Land L1 (S-1 days only)', s1_days)
rows += evaluate(s1, 'Sentinel-1 change detection (raw)')
for k, v in da.items():
    rows += evaluate(v, f'model 0-10 cm {k} (all days)')
    rows += evaluate(v, f'model 0-10 cm {k} (S-1 days only)', s1_days)
# OPTRAM: STR vs NDVI trapezoid fitted on the station time series (dry/wet edges from 5th/95th pct per NDVI bin)
if {'str', 'ndvi'} <= set(s2.columns):
    q = s2[['ndvi', 'str']].dropna()
    bins = pd.cut(q.ndvi, 8); env = q.groupby(bins, observed=True).str.quantile([0.05, 0.95]).unstack()
    mid = np.array([b.mid for b in env.index])
    sd, id_ = np.polyfit(mid, env[0.05].values, 1); sw, iw = np.polyfit(mid, env[0.95].values, 1)
    W = (id_ + sd * q.ndvi - q['str']) / (id_ - iw + (sd - sw) * q.ndvi)
    rows += evaluate((1 - W).clip(-0.5, 1.5) * -1 + 1, 'Sentinel-2 OPTRAM (STR-NDVI trapezoid)')  # W already wetness
    rows += evaluate(q['str'], 'Sentinel-2 STR alone')
res = pd.DataFrame(rows); pd.set_option('display.width', 200)
print(res.to_string(index=False)); res.to_csv('surface_results.csv', index=False)
