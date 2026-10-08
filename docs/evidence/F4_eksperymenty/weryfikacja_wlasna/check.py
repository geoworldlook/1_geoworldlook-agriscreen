import sys, numpy as np, pandas as pd
from scipy import stats
sys.path.insert(0, '/home/user/1_geoworldlook-agriscreen')
import step_07_station_pipeline as s7
D = 'drive_data/'
o = pd.read_csv(D + 'gwl_observations.csv')
o['t'] = pd.to_datetime(o.time_utc).dt.tz_localize(None)
v = o[(o.site_id == 'VINEYARD_06') & (o['product'] == 'S2SR_2.5m')].pivot_table(index=['t', 'orbit'], columns='variable', values='value').reset_index()
v = v[v.clear_frac >= 0.9].copy()
print('orbits:', v.orbit.value_counts().to_dict())
v['doy'] = v.t.dt.dayofyear; v['yr'] = v.t.dt.year

def anom(df, col, causal=False):
    z = []
    for _, r in df.iterrows():
        d = np.abs(((df.doy - r.doy + 182) % 365) - 182)
        m = (d <= 15) & (df.yr != r.yr)
        if causal: m &= df.yr < r.yr
        ref = df.loc[m, col]
        z.append((r[col] - ref.mean()) / ref.std(ddof=1) if len(ref) >= 5 else np.nan)
    return np.array(z)

v['z'] = anom(v, 'ndvi')
v['zc'] = anom(v, 'ndvi', causal=True)
g = v.dropna(subset=['z']).groupby('orbit').z
print('mean z by orbit:', g.mean().round(3).to_dict(), 'n', g.size().to_dict())
orbs = [x for x in v.orbit.unique() if x != 0]
if len(orbs) >= 2:
    a, b = [v.loc[v.orbit == x, 'z'].dropna() for x in orbs[:2]]
    print('Welch t p =', stats.ttest_ind(a, b, equal_var=False).pvalue)
# yearly NDVI trend (April)
print('April NDVI by year:', v[v.t.dt.month == 4].groupby('yr').ndvi.mean().round(2).to_dict())
# ISMN 20-30 cm z
cfg = s7.build_config()
ism = pd.concat([s7.insitu_daily_depth(dd, {}) for dd in (0.2, 0.3)])
print(ism.head(2)); 
