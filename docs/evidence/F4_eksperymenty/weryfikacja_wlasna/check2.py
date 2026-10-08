import sys, os, numpy as np, pandas as pd
from scipy import stats
sys.path.insert(0, '/home/user/1_geoworldlook-agriscreen')
os.chdir('/home/user/1_geoworldlook-agriscreen')
import step_07_station_pipeline as s7, step_04_metrics_alert as s4
D = '/tmp/claude-0/-home-user-1-geoworldlook-agriscreen/0b6bc240-34e1-5fd3-a139-3c46967fd603/scratchpad/drive_data/'
o = pd.read_csv(D + 'gwl_observations.csv')
o['t'] = pd.to_datetime(o.time_utc).dt.tz_localize(None)
def site(sid):
    v = o[(o.site_id == sid) & (o['product'] == 'S2SR_2.5m')].pivot_table(index='t', columns='variable', values='value').reset_index()
    v = v[v.clear_frac >= 0.9].copy()
    v['track'] = np.where(v.t.dt.hour * 60 + v.t.dt.minute < 11 * 60 + 4, 'early(~10:59)', 'late(~11:09)')
    v['doy'] = v.t.dt.dayofyear; v['yr'] = v.t.dt.year
    return v
def anom(df, col, causal=False):
    z = []
    for _, r in df.iterrows():
        d = np.abs(((df.doy - r.doy + 182) % 365) - 182)
        m = (d <= 15) & (df.yr != r.yr)
        if causal: m &= df.yr < r.yr
        ref = df.loc[m, col]
        z.append((r[col] - ref.mean()) / ref.std(ddof=1) if len(ref) >= 5 else np.nan)
    return np.array(z)
for sid in ('VINEYARD_06', 'SMOSMANIA_Condom'):
    v = site(sid); v['z'] = anom(v, 'ndvi')
    g = v.dropna(subset=['z']).groupby('track').z
    a, b = [x.values for _, x in g]
    print(sid, 'mean z by track', g.mean().round(3).to_dict(), 'n', g.size().to_dict(), 'Welch p=%.2g' % stats.ttest_ind(a, b, equal_var=False).pvalue)
# causal vs all-other-years climatology R vs ISMN 20-30
cfg = s7.build_config()
ism = []
for dd in (0.2, 0.3):
    x = s7.insitu_daily_depth(dd, {'STATION_DIR': 'data/7_isismn_data/SMOSMANIA/Condom'}); ism.append(x)
print(ism[0].columns.tolist()[:6])
sm = pd.concat([ism[0].sm.rename('a'), ism[1].sm.rename('b')], axis=1).mean(axis=1).dropna()
import inspect
za = s4.clim_anomaly(sm, ('2016-01-01', '2024-12-31'), min_n=20)
zs = za['z'] if 'z' in za else za.iloc[:, -1]
v = site('VINEYARD_06'); v['z'] = anom(v, 'ndvi'); v['zc'] = anom(v, 'ndvi', causal=True)
v['d'] = v.t.dt.normalize()
m = v.set_index('d').join(zs.rename('ism'), how='inner').dropna(subset=['z', 'ism'])
print('all-other-years: R=%.3f n=%d' % (m.z.corr(m.ism), len(m)))
mc = m.dropna(subset=['zc'])
print('same days (causal available): all-other R=%.3f, causal R=%.3f, n=%d' % (mc.z.corr(mc.ism), mc.zc.corr(mc.ism), len(mc)))
# detrended (remove linear year trend of NDVI before anomaly) causal
v2 = v.copy(); coef = np.polyfit(v2.yr + v2.doy / 365, v2.ndvi, 1)
v2['ndvi_dt'] = v2.ndvi - np.polyval(coef, v2.yr + v2.doy / 365)
v2['zc_dt'] = anom(v2, 'ndvi_dt', causal=True)
m2 = v2.set_index('d').join(zs.rename('ism'), how='inner').dropna(subset=['zc_dt', 'ism'])
print('causal + detrended (trend fitted on full series, optimistic): R=%.3f n=%d' % (m2.zc_dt.corr(m2.ism), len(m2)))
zz = v.z.dropna()
print('calibration: z<=-1 %.1f%%  |z|>2 %.1f%%  n=%d (normal: 15.9%%, 4.6%%)' % (100 * (zz <= -1).mean(), 100 * (zz.abs() > 2).mean(), len(zz)))
a = pd.read_csv(D + 'gwl_anomalies.csv'); print(a[a.site_id.str.contains('VINEYARD')].groupby('product').z.apply(lambda s: f"{100*(s<=-1).mean():.1f}% <=-1, {100*(s.abs()>2).mean():.1f}% |z|>2, n={s.notna().sum()}").to_dict())
