"""
Warstwa stresu parowania ERA5-Land (track 'evap', v1.2) — implementacja wzorcowa do przeniesienia do repo.

Docelowo:
  - sekcje I-III -> step_04_metrics_alert.py (ET0, EDDI, SESR, evap_anomalies),
  - sekcja IV    -> step_07_station_pipeline.py (validate_evap: test wstępnie zarejestrowany vs ISMN Condom).

Indeksy:
  ET0   FAO-56 Penman-Monteith (trawa 0,12 m) z dziennych pasm ERA5-Land DAILY_AGGR,
  EDDI  Hobbins i in. 2016: ranga sumy ET0 z `days` dni; znak Hobbinsa (+ = sucho); z = -EDDI (znak projektu, <= -1 = sucho),
  SESR  Christian i in. 2019: standaryzowany ESR = sum(ET)/sum(ET0) (ET = total_evaporation ERA5-Land, NIE potential_evaporation),
  dSESR zmiana SESR w pentadzie, ponownie standaryzowana; flaga szybkiego narastania (kryteria Christian 2019).

Standaryzacja (poprawka względem step_04.clim_anomaly dla krótkich sum): każda wartość z puli ±hw dni roku jest
najpierw centrowana średnią SWOJEGO dnia roku, więc nachylenie cyklu rocznego w oknie ±15 dni nie zawyża rozrzutu puli
(dla sum ET0 14 dni zawyżenie dawało |z| za małe, częstość z <= -1 ~6% zamiast ~16%, test_evap_v2.py).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

# ==============================================================================
# I. PASMA ERA5-LAND (GEE ECMWF/ERA5_LAND/DAILY_AGGR) I JEDNOSTKI
# ==============================================================================
# Nazwy i jednostki sprawdzone w katalogu GEE (STAC: earthengine-stac/catalog/ECMWF/ECMWF_ERA5_LAND_DAILY_AGGR.json,
# 2026-10-09). Pasma *_sum: suma doby UTC (wartość z pierwszej godziny dnia następnego); pozostałe: średnia godzin doby UTC.
# Konwencja ECMWF: strumienie pionowe dodatnie w dół -> parowanie ma znak ujemny [m wody].
ERA5_EVAP_BANDS = {
    "dewpoint_temperature_2m": "td2m_c",                    # K, średnia doby
    "u_component_of_wind_10m": "u10_ms",                    # m/s, średnia doby (składowa!)
    "v_component_of_wind_10m": "v10_ms",
    "surface_pressure": "sp_kpa",                           # Pa
    "surface_solar_radiation_downwards_sum": "ssrd_mj",     # J/m2 na dobę, Rs do FAO-56
    "surface_net_solar_radiation_sum": "ssr_mj",            # J/m2, dodatnie w dół (czułość Rn)
    "surface_net_thermal_radiation_sum": "str_mj",          # J/m2, zwykle ujemne (czułość Rn)
    "total_evaporation_sum": "et_mm",                       # m w.e., ujemne = parowanie
    "potential_evaporation_sum": "pev_mm",                  # m, tylko diagnostyka (znane problemy, nie do indeksu)
}


def era5_convert(name: str, v: pd.Series) -> pd.Series:
    """Jednostki GEE -> jednostki projektu (wg nazwy kolumny); rozszerza konwersję z step_01.fetch_era5_land_daily."""
    if name == "precip_mm":
        return v * 1000.0
    if name.startswith("t2m") or name.startswith("td2m"):
        return v - 273.15
    if name.endswith("_kpa"):
        return v / 1000.0
    if name.endswith("_mj"):
        return v / 1e6                      # J m-2 doba-1 -> MJ m-2 doba-1; znak ECMWF zostaje (str_mj < 0)
    if name in ("et_mm", "pev_mm"):
        return -1000.0 * v                  # m (ujemne = parowanie) -> mm (dodatnie = parowanie, ujemne = rosa)
    return v


def qa_evap_columns(e: pd.DataFrame) -> Dict[str, float]:
    """Kontrola znaków i rzędów wielkości po pobraniu (bez ISMN). Zwraca liczby do logu / run_summary."""
    jja = e[e.index.month.isin([6, 7, 8])]
    out = {
        "et_mm_jja_median": float(jja["et_mm"].median()),
        "pev_mm_jja_median": float(jja["pev_mm"].median()) if "pev_mm" in e else np.nan,
        "et_mm_share_negative": float((e["et_mm"] < 0).mean()),
        "ssrd_mj_jja_median": float(jja["ssrd_mj"].median()),
        "str_mj_median": float(e["str_mj"].median()) if "str_mj" in e else np.nan,
        "sp_kpa_median": float(e["sp_kpa"].median()),
        "td_le_t_share": float((e["td2m_c"] <= e["t2m_c"] + 0.5).mean()),
    }
    ok = (out["et_mm_jja_median"] > 0.5 and out["ssrd_mj_jja_median"] > 10 and 85 < out["sp_kpa_median"] < 105
          and out["td_le_t_share"] > 0.99)
    out["ok"] = float(ok)
    return out


# ==============================================================================
# II. ET0 FAO-56 PENMAN-MONTEITH (krok dobowy)
# ==============================================================================

def _e0(t):
    """Ciśnienie pary nasyconej [kPa], FAO-56 eq. 11."""
    return 0.6108 * np.exp(17.27 * t / (t + 237.3))


def extraterrestrial_radiation(doy: np.ndarray, lat_deg: float) -> np.ndarray:
    """Ra [MJ m-2 doba-1], FAO-56 eq. 21-25."""
    phi = np.radians(lat_deg)
    dr = 1 + 0.033 * np.cos(2 * np.pi * doy / 365)
    dec = 0.409 * np.sin(2 * np.pi * doy / 365 - 1.39)
    ws = np.arccos(np.clip(-np.tan(phi) * np.tan(dec), -1, 1))
    return 24 * 60 / np.pi * 0.0820 * dr * (ws * np.sin(phi) * np.sin(dec) + np.cos(phi) * np.cos(dec) * np.sin(ws))


def fao56_et0(df: pd.DataFrame, lat_deg: float, elev_m: float, reference: str = "short",
              rn_source: str = "fao56", u2_const: Optional[float] = None) -> pd.DataFrame:
    """
    ET0 [mm/doba] z kolumn t2m_max_c, t2m_min_c, td2m_c, ssrd_mj, u10_ms, v10_ms, sp_kpa (indeks = dni).
      reference: 'short' FAO-56 (Cn 900, Cd 0,34) | 'tall' ASCE-EWRI 2005 (Cn 1600, Cd 0,38) — czułość,
      rn_source: 'fao56' Rn = 0,77 Rs - Rnl (eq. 38-39, powierzchnia wzorcowa) | 'era5' Rn = ssr + str (stan modelu) — czułość,
      wiatr: |średnia wektorowa| (u, v) doby — DAILY_AGGR nie ma średniej prędkości, więc u2 jest zaniżone w dni
             ze zmiennym kierunkiem; u2_const (np. 2 m/s, FAO-56 przy braku danych) jako czułość,
      ea = e0(Td średnie doby) (eq. 14), es = [e0(Tmax) + e0(Tmin)]/2 (eq. 12), gamma z ciśnienia ERA5 (eq. 8), G = 0 (eq. 42).
    """
    tmax, tmin = df["t2m_max_c"].to_numpy(float), df["t2m_min_c"].to_numpy(float)
    tmean = (tmax + tmin) / 2
    es = (_e0(tmax) + _e0(tmin)) / 2
    ea = _e0(df["td2m_c"].to_numpy(float))
    vpd = np.clip(es - ea, 0, None)
    delta = 4098 * _e0(tmean) / (tmean + 237.3) ** 2
    gamma = 0.665e-3 * df["sp_kpa"].to_numpy(float)
    if u2_const is None:
        u10 = np.hypot(df["u10_ms"].to_numpy(float), df["v10_ms"].to_numpy(float))
        u2 = u10 * 4.87 / np.log(67.8 * 10 - 5.42)            # eq. 47, z = 10 m -> 0,748
    else:
        u2 = np.full(len(df), float(u2_const))
    rs = df["ssrd_mj"].to_numpy(float)
    if rn_source == "era5":
        rn = (df["ssr_mj"] + df["str_mj"]).to_numpy(float)
    else:
        doy = pd.DatetimeIndex(df.index).dayofyear.to_numpy()
        ra = extraterrestrial_radiation(doy, lat_deg)
        rso = (0.75 + 2e-5 * elev_m) * ra                      # eq. 37
        ratio = np.clip(rs / np.where(rso > 0, rso, np.nan), 0.3, 1.0)
        rnl = 4.903e-9 * ((tmax + 273.16) ** 4 + (tmin + 273.16) ** 4) / 2 * (0.34 - 0.14 * np.sqrt(ea)) \
            * (1.35 * ratio - 0.35)                            # eq. 39
        rn = (1 - 0.23) * rs - rnl
    cn, cd = (900.0, 0.34) if reference == "short" else (1600.0, 0.38)
    et0 = (0.408 * delta * rn + gamma * cn / (tmean + 273.0) * u2 * vpd) / (delta + gamma * (1 + cd * u2))
    return pd.DataFrame({"et0_mm": np.clip(et0, 0, None), "rn_mj": rn, "vpd_kpa": vpd, "u2_ms": u2}, index=df.index)


# ==============================================================================
# III. STANDARYZACJA I INDEKSY (EDDI, SESR, dSESR, flaga szybkiego narastania)
# ==============================================================================

def _circ_doy_dist(a: np.ndarray, b) -> np.ndarray:
    d = np.abs(a - b)
    return np.minimum(d, 366 - d)


def _rolling_sum(s: pd.Series, days: int) -> pd.Series:
    s = s.sort_index().asfreq("D")
    return s.rolling(days, min_periods=int(np.ceil(0.9 * days))).sum()


def _doy_pools(s: pd.Series, ref: Tuple[str, str], half_window: int, min_n: int, exclude_same_year: bool):
    """
    Generator (maska dat, wartości bieżące, pula reszt) dla każdego dnia roku i roku.
    Reszta = wartość - średnia z lat referencyjnych dla JEJ dnia roku (±half_window), więc pula ±half_window dni
    nie jest poszerzona przez nachylenie cyklu rocznego. exclude_same_year: dla dat z okresu odniesienia pula bez
    tego samego roku (sąsiednie sumy kroczące z tego roku są silnie skorelowane z wartością bieżącą).
    """
    s = s.dropna().sort_index()
    r = s.loc[ref[0]:ref[1]]
    rd, ry, rv = r.index.dayofyear.to_numpy(), r.index.year.to_numpy(), r.to_numpy(float)
    mean_by_doy = np.full(367, np.nan)
    for d in range(1, 367):
        pool = rv[_circ_doy_dist(rd, d) <= half_window]
        if len(pool) >= min_n:
            mean_by_doy[d] = pool.mean()
    r_res = rv - mean_by_doy[rd]
    doy, yr = s.index.dayofyear.to_numpy(), s.index.year.to_numpy()
    x_res = s.to_numpy(float) - mean_by_doy[doy]
    for d in np.unique(doy):
        in_win = _circ_doy_dist(rd, d) <= half_window
        for y in np.unique(yr[doy == d]):
            m = in_win & (ry != y) if exclude_same_year else in_win
            pool = r_res[m]
            pool = pool[np.isfinite(pool)]
            sel = (doy == d) & (yr == y)
            yield sel, x_res[sel], pool, mean_by_doy[d]
    return


def doy_standardize(s: pd.Series, ref: Tuple[str, str], half_window: int = 15, min_n: int = 30,
                    exclude_same_year: bool = True, method: str = "rank") -> pd.DataFrame:
    """
    Anomalia względem klimatologii dnia roku (okno ±half_window, lata ref) liczona na resztach (patrz _doy_pools).
      method='rank'   : z = Phi^-1(p), p = (i - 0,33)/(n + 0,33) — ranga wśród puli + wartość bieżąca (Tukey, jak EDDI);
                        odporne na skośność (ESR ograniczony od góry: z momentów częstość z <= -1 wychodzi ~9%, nie ~16%),
      method='moments': z = reszta / odchylenie standardowe puli (jak step_04.clim_anomaly).
    Kolumny jak clim_anomaly: value, clim_mean, clim_std, z, percentile (0-100), n_ref.
    """
    from scipy import stats

    s = s.dropna().sort_index()
    out = pd.DataFrame(index=s.index, data={"value": s.to_numpy(float)})
    cm, cs, z, pc, nr = (np.full(len(s), np.nan) for _ in range(5))
    for sel, xr, pool, mu in _doy_pools(s, ref, half_window, min_n, exclude_same_year):
        if len(pool) < min_n:
            continue
        sp = np.sort(pool)
        sd = sp.std(ddof=1)
        cm[sel], cs[sel], nr[sel] = mu, sd, len(sp)
        if method == "rank":
            lo, hi = np.searchsorted(sp, xr, side="left"), np.searchsorted(sp, xr, side="right")
            rank = lo + 1 + (hi - lo) / 2.0                  # ranga środkowa przy remisach (np. ESR = 1 w okresach mokrych)
            p = (rank - 0.33) / (len(sp) + 1 + 0.33)
            z[sel], pc[sel] = stats.norm.ppf(p), 100.0 * p
        else:
            z[sel] = xr / sd
            pc[sel] = 100.0 * np.searchsorted(sp, xr, side="right") / len(sp)
    out["clim_mean"], out["clim_std"], out["z"], out["percentile"], out["n_ref"] = cm, cs, z, pc, nr
    return out


def eddi(et0: pd.Series, days: int, ref: Tuple[str, str], half_window: int = 15, min_n: int = 30) -> pd.DataFrame:
    """
    EDDI (Hobbins i in. 2016) w wersji projektu: suma ET0 z `days` dni wstecz; ranga reszty względem puli reszt z lat
    referencyjnych (±half_window dni roku, bez tego samego roku) z dołączoną wartością bieżącą; prawdopodobieństwo
    nieprzekroczenia z pozycji Tukeya p = (i - 0,33)/(n + 0,33); EDDI = Phi^-1(p) (+ = większe zapotrzebowanie = sucho).
    Kolumny: value [mm], p, eddi (znak Hobbinsa), z = -eddi (znak projektu: <= -1 = sucho), percentile (ET0), n_ref.
    """
    acc = _rolling_sum(et0, days).dropna()
    st = doy_standardize(acc, ref, half_window, min_n, exclude_same_year=True, method="rank")
    p = st["percentile"].to_numpy() / 100.0                       # nieprzekroczenie (ranga rosnąco, 1 = najmniejsze ET0)
    e = st["z"].to_numpy()
    return pd.DataFrame({"value": acc.to_numpy(float), "p": p, "eddi": e, "z": -e, "percentile": 100 * p,
                         "n_ref": st["n_ref"].to_numpy()}, index=acc.index)


def sesr(et: pd.Series, et0: pd.Series, days: int, ref: Tuple[str, str], half_window: int = 15,
         step_days: int = 5, min_et0_mm_per_day: float = 0.5) -> pd.DataFrame:
    """
    SESR (Christian i in. 2019) z ERA5-Land: ESR = sum(ET)/sum(ET0) z `days` dni (iloraz sum, nie średnia ilorazów),
    pomijany, gdy średnie ET0 < min_et0_mm_per_day (zima: iloraz niestabilny). z = doy_standardize(ESR).
    dSESR = z(t) - z(t - step_days) (pentada), ponownie standaryzowane -> dz, dz_percentile.
    """
    a_et, a_0 = _rolling_sum(et, days), _rolling_sum(et0, days)
    esr = (a_et / a_0).where(a_0 >= min_et0_mm_per_day * days).dropna()
    ca = doy_standardize(esr, ref, half_window)
    zz = ca["z"].asfreq("D")
    d_raw = (zz - zz.shift(step_days)).dropna()
    cd = doy_standardize(d_raw, ref, half_window)
    out = ca[["value", "z", "percentile", "n_ref"]].copy()
    out["dz"] = cd["z"].reindex(out.index)
    out["dz_percentile"] = cd["percentile"].reindex(out.index)
    return out


def sesr_flash_flag(s: pd.DataFrame, step_days: int = 5, n_changes: int = 5) -> pd.Series:
    """
    Szybkie narastanie stresu wg kryteriów Christian i in. 2019 (pentady; liczone przyczynowo na dzień t):
      (1) długość >= n_changes zmian pentadowych (5 zmian = 6 pentad ~ 30 dni),
      (2) percentyl SESR w dniu t <= 20,
      (3) percentyl dSESR <= 40 w każdej zmianie, z jednym dopuszczalnym wyjątkiem (nie w ostatniej zmianie),
      (4) średni percentyl dSESR w całym ciągu <= 25.
    Progi z przeglądu (dostęp do pełnego tekstu: brak — snippet); sprawdzić z PDF przed wdrożeniem.
    """
    pct = s["percentile"].asfreq("D")
    dp = s["dz_percentile"].asfreq("D")
    lagged = np.column_stack([dp.shift(k * step_days).to_numpy() for k in range(n_changes)])
    ok = lagged <= 40
    finite = np.isfinite(lagged).all(axis=1) & np.isfinite(pct.to_numpy())
    flag = finite & ok[:, 0] & ((~ok).sum(axis=1) <= 1) & (np.nanmean(lagged, axis=1) <= 25) & (pct.to_numpy() <= 20)
    return pd.Series(flag, index=pct.index).reindex(s.index)


def evap_indices(e: pd.DataFrame, lat_deg: float, elev_m: float, ref: Tuple[str, str], windows: Sequence[int] = (7, 14, 30),
                 half_window: int = 15, **et0_kw) -> Dict[str, pd.DataFrame]:
    """Wszystkie warstwy z dziennej ramki ERA5-Land (indeks = dni). Klucze jak produkty w gwl_anomalies."""
    et0 = fao56_et0(e, lat_deg, elev_m, **et0_kw)["et0_mm"]
    out: Dict[str, pd.DataFrame] = {"ERA5L_ET0": pd.DataFrame({"value": et0})}
    for w in windows:
        out[f"ERA5L_EDDI{w}"] = eddi(et0, w, ref, half_window)
        out[f"ERA5L_SESR{w}"] = sesr(e["et_mm"], et0, w, ref, half_window)
    return out


# ==============================================================================
# IV. TEST WSTĘPNIE ZAREJESTROWANY (statystyki; dane ISMN wchodzą dopiero tutaj)
# ==============================================================================

def _blocks(idx: pd.DatetimeIndex, how: str) -> np.ndarray:
    if how == "30d":
        return ((idx - idx.min()) / pd.Timedelta(days=30)).astype(int).to_numpy()
    return idx.year.to_numpy()


def _boot_idx(blk: np.ndarray, n_boot: int, seed: int):
    ub = np.unique(blk)
    by = {k: np.flatnonzero(blk == k) for k in ub}
    rng = np.random.default_rng(seed)
    for _ in range(n_boot):
        yield np.concatenate([by[k] for k in rng.choice(ub, len(ub), replace=True)])


def fit_predict(d: pd.DataFrame, xcols: Sequence[str], ycol: str = "y", scheme: str = "forward",
                min_train_years: int = 3) -> pd.Series:
    """
    OLS poza próbą. scheme='forward': współczynniki tylko z lat WCZEŚNIEJSZYCH (>= min_train_years), prognoza roku
    bieżącego (operacyjnie uczciwe); 'loyo': zostaw rok (porównywalność z F4 B V9/V10).
    """
    pred = pd.Series(np.nan, index=d.index)
    yrs = d.index.year.to_numpy()
    uy = np.unique(yrs)
    for k, yv in enumerate(uy):
        if scheme == "forward":
            if k < min_train_years:
                continue
            tr = yrs < yv
        else:
            tr = yrs != yv
        te = yrs == yv
        X = np.column_stack([np.ones(tr.sum()), d.loc[tr, list(xcols)].to_numpy(float)])
        b = np.linalg.lstsq(X, d.loc[tr, ycol].to_numpy(float), rcond=None)[0]
        pred[te] = np.column_stack([np.ones(te.sum()), d.loc[te, list(xcols)].to_numpy(float)]) @ b
    return pred


def paired_delta_r(a: pd.Series, b: pd.Series, y: pd.Series, how: str = "30d", n_boot: int = 2000,
                   seed: int = 42) -> Dict[str, float]:
    """R(a,y) - R(b,y) na tych samych dniach; 95% CI i jednostronne p = P*(delta <= 0) z bootstrapu tych samych bloków."""
    p = pd.concat([a.rename("a"), b.rename("b"), y.rename("y")], axis=1, join="inner")
    p = p.replace([np.inf, -np.inf], np.nan).dropna()
    A, B, Y = p["a"].to_numpy(), p["b"].to_numpy(), p["y"].to_numpy()
    if len(p) < 30:
        return {"r_a": np.nan, "r_b": np.nan, "delta": np.nan, "lo": np.nan, "hi": np.nan, "p_le0": np.nan, "n": len(p)}
    dd = np.array([np.corrcoef(A[i], Y[i])[0, 1] - np.corrcoef(B[i], Y[i])[0, 1]
                   for i in _boot_idx(_blocks(p.index, how), n_boot, seed)])
    ra, rb = np.corrcoef(A, Y)[0, 1], np.corrcoef(B, Y)[0, 1]
    return {"r_a": ra, "r_b": rb, "delta": ra - rb, "lo": float(np.nanpercentile(dd, 2.5)),
            "hi": float(np.nanpercentile(dd, 97.5)), "p_le0": float(np.mean(dd <= 0)), "n": len(p)}


def partial_r(y: np.ndarray, x: np.ndarray, ctrl: np.ndarray) -> float:
    X = np.column_stack([np.ones(len(y)), ctrl])
    ry = y - X @ np.linalg.lstsq(X, y, rcond=None)[0]
    rx = x - X @ np.linalg.lstsq(X, x, rcond=None)[0]
    return float(np.corrcoef(ry, rx)[0, 1])


def partial_r_ci(d: pd.DataFrame, xcol: str, ctrl: Sequence[str], ycol: str = "y", how: str = "30d",
                 n_boot: int = 2000, seed: int = 42) -> Dict[str, float]:
    d = d[[ycol, xcol] + list(ctrl)].replace([np.inf, -np.inf], np.nan).dropna()
    yv, xv, cv = d[ycol].to_numpy(float), d[xcol].to_numpy(float), d[list(ctrl)].to_numpy(float)
    bs = np.array([partial_r(yv[i], xv[i], cv[i]) for i in _boot_idx(_blocks(d.index, how), n_boot, seed)])
    return {"r": partial_r(yv, xv, cv), "lo": float(np.nanpercentile(bs, 2.5)), "hi": float(np.nanpercentile(bs, 97.5)),
            "p_le0": float(np.mean(bs <= 0)), "n": len(d)}


def ccf(x: pd.Series, y: pd.Series, lags: Sequence[int]) -> pd.Series:
    """r(x_t, y_{t+L}); L > 0: x wyprzedza y. Opisowo (autokorelacja obu serii przesuwa maksimum)."""
    out = {}
    for L in lags:
        p = pd.concat([x.rename("x"), y.shift(-L, freq="D").rename("y")], axis=1, join="inner").dropna()
        out[L] = p["x"].corr(p["y"]) if len(p) > 30 else np.nan
    return pd.Series(out)


def ccf_peak_ci(x: pd.Series, y: pd.Series, lags: Sequence[int], n_boot: int = 300, seed: int = 42) -> Dict[str, float]:
    """Opóźnienie maksimum r i 95% CI z bootstrapu całych lat (szybko: macierz [dni x opóźnienia])."""
    x = x.asfreq("D")
    ys = pd.concat({L: y.shift(-L, freq="D") for L in lags}, axis=1).reindex(x.index)
    yrs = x.index.year.to_numpy()
    uy = np.unique(yrs[np.isfinite(x.to_numpy())])
    by = {k: np.flatnonzero(yrs == k) for k in uy}
    X, Y = x.to_numpy(float), ys.to_numpy(float)

    def peak(idx):
        rs = []
        for j in range(Y.shape[1]):
            xv, yv = X[idx], Y[idx, j]
            m = np.isfinite(xv) & np.isfinite(yv)
            rs.append(np.corrcoef(xv[m], yv[m])[0, 1] if m.sum() > 30 else np.nan)
        rs = np.asarray(rs)
        return lags[int(np.nanargmax(rs))], float(np.nanmax(rs))
    pk, pr = peak(np.arange(len(X)))
    rng = np.random.default_rng(seed)
    boots = [peak(np.concatenate([by[k] for k in rng.choice(uy, len(uy), replace=True)]))[0] for _ in range(n_boot)]
    return {"peak_lag": float(pk), "peak_r": pr, "lo": float(np.percentile(boots, 2.5)), "hi": float(np.percentile(boots, 97.5))}


def lead_frame(y: pd.Series, base: pd.DataFrame, x: pd.Series, h: int) -> pd.DataFrame:
    """Ramka testu wyprzedzania: dy = y_{t+h} - y_t, predyktory y_t, baza_t, x_t (dni bez braków)."""
    yf = y.shift(-h, freq="D").rename("yf")
    d = pd.concat([y.rename("y0"), yf, base, x.rename("x")], axis=1, join="inner")
    d = d.replace([np.inf, -np.inf], np.nan).dropna()
    d["dy"] = d["yf"] - d["y0"]
    return d


def granger_lead(y: pd.Series, base: pd.DataFrame, x: pd.Series, h: int, scheme: str = "forward",
                 how: str = "30d", n_boot: int = 2000, months: Optional[Tuple[int, int]] = None) -> Dict[str, float]:
    """Czy x_t poprawia prognozę zmiany y w h dni ponad [y_t, baza_t]? Modele poza próbą; dR na dy (sparowane)."""
    d = lead_frame(y, base, x, h)
    b0 = ["y0"] + list(base.columns)
    p0, p1 = fit_predict(d, b0, "dy", scheme), fit_predict(d, b0 + ["x"], "dy", scheme)
    if months is not None:
        m = (d.index.month >= months[0]) & (d.index.month <= months[1])
        p0, p1, dy = p0[m], p1[m], d["dy"][m]
    else:
        dy = d["dy"]
    return paired_delta_r(p1, p0, dy, how, n_boot)


def placebo_delta_r(d: pd.DataFrame, base_cols: Sequence[str], xcol: str, ycol: str = "y", scheme: str = "forward",
                    n_perm: int = 500, seed: int = 42, months: Optional[Tuple[int, int]] = None) -> np.ndarray:
    """Rozkład dR przy indeksie z innego roku (permutacja lat bez punktów stałych, dopasowanie po dniu roku)."""
    rng = np.random.default_rng(seed)
    yrs = np.unique(d.index.year)
    doy = np.minimum(d.index.dayofyear, 365)
    xs = pd.Series(d[xcol].to_numpy(), index=pd.MultiIndex.from_arrays([d.index.year, doy]))
    xs = xs[~xs.index.duplicated()]
    p0 = fit_predict(d, base_cols, ycol, scheme)
    msk = np.ones(len(d), bool) if months is None else (d.index.month >= months[0]) & (d.index.month <= months[1])
    out = []
    for _ in range(n_perm):
        perm = rng.permutation(yrs)
        while len(yrs) > 1 and np.any(perm == yrs):
            perm = rng.permutation(yrs)
        mp = dict(zip(yrs, perm))
        dd = d.copy()
        dd["xp"] = xs.reindex(pd.MultiIndex.from_arrays([[mp[v] for v in d.index.year], doy])).to_numpy()
        ok = dd["xp"].notna().to_numpy()
        dd = dd[ok]
        p1 = fit_predict(dd, list(base_cols) + ["xp"], ycol, scheme)
        m = msk[ok] & p1.notna().to_numpy() & p0[ok].notna().to_numpy()
        out.append(np.corrcoef(p1[m], dd[ycol][m])[0, 1] - np.corrcoef(p0[ok][m], dd[ycol][m])[0, 1])
    return np.asarray(out)


def onsets(z: pd.Series, thr: float = -1.0, min_days: int = 20, merge_gap: int = 5, quiet_days: int = 30,
           months: Tuple[int, int] = (3, 10), min_quiet_cover: float = 0.8) -> List[pd.Timestamp]:
    """
    Początki epizodów suszy w serii referencyjnej: ciąg dni z z <= thr trwający >= min_days (przerwy <= merge_gap
    scalane), poprzedzony quiet_days dniami bez z <= thr (z pokryciem danych >= min_quiet_cover); początek w months.
    """
    z = z.asfreq("D")
    dry = (z <= thr).to_numpy()
    idx = z.index
    runs, i = [], 0
    while i < len(dry):
        if dry[i]:
            last, j = i, i
            while j < len(dry) and (dry[j] or (j - last) <= merge_gap):
                if dry[j]:
                    last = j
                j += 1
            runs.append((i, last))
            i = last + 1
        else:
            i += 1
    out, prev_end = [], -10 ** 9
    for a, b in runs:
        q = z.iloc[max(0, a - quiet_days):a]
        quiet_ok = (a - prev_end > quiet_days) and len(q) == quiet_days and q.notna().mean() >= min_quiet_cover
        if b - a + 1 >= min_days and quiet_ok and months[0] <= idx[a].month <= months[1]:
            out.append(idx[a])
        prev_end = b
    return out


def _flag(z: pd.Series, thr: float, k: int = 5, m: int = 7) -> pd.Series:
    """Przyczynowy filtr trwałości: z <= thr w >= k z m ostatnich dni."""
    return (z.asfreq("D") <= thr).astype(float).rolling(m, min_periods=m).sum() >= k


def first_crossing(z: pd.Series, start: pd.Timestamp, end: pd.Timestamp, thr: float = -1.0,
                   quiet: int = 14) -> Tuple[Optional[pd.Timestamp], str]:
    """
    Pierwsze NOWE przejście (flaga 0 -> 1) w (start, end]. Jeśli predyktor jest w suchym ciągu już w dniu `start`
    (flaga aktywna), status 'already_dry' (wyprzedzenie >= okno, wartość obcięta). Zwraca (data, status).
    """
    f = _flag(z, thr)
    if start in f.index and bool(f.loc[start]):
        return None, "already_dry"
    w = f.loc[start:end]
    new_on = w & ~w.shift(1, fill_value=False)
    hit = new_on[new_on]
    return (hit.index[0], "hit") if len(hit) else (None, "miss")


def onset_leads(preds: Dict[str, pd.Series], ins_onsets: List[pd.Timestamp], before: int = 60, after: int = 30,
                thr: float = -1.0) -> pd.DataFrame:
    """
    Wyprzedzenie [dni] = T0_ISMN - przejście predyktora (dodatnie = wcześniej). Cenzura: miss -> -(after+1);
    already_dry (predyktor sucho już przed oknem) -> +before (wartość obcięta, status zapisany osobno).
    """
    rows = []
    for t0 in ins_onsets:
        r = {"onset": t0}
        for name, z in preds.items():
            tx, st = first_crossing(z, t0 - pd.Timedelta(days=before), t0 + pd.Timedelta(days=after), thr)
            r[name] = float((t0 - tx).days) if tx is not None else (float(before) if st == "already_dry" else -float(after + 1))
            r[name + "_status"] = st
        rows.append(r)
    return pd.DataFrame(rows)


def false_onsets(z: pd.Series, ins_z: pd.Series, thr: float = -1.0, horizon: int = 60, sep: int = 30,
                 months: Tuple[int, int] = (3, 10)) -> Tuple[int, int]:
    """Nowe przejścia predyktora (odstęp >= sep dni) w months bez dnia ISMN z <= thr w [t, t + horizon]."""
    f = _flag(z, thr)
    starts, last = [], None
    for t, v in f.items():
        if v and (last is None or (t - last).days > sep):
            starts.append(t)
        if v:
            last = t
    starts = [t for t in starts if months[0] <= t.month <= months[1]]
    insd = ins_z.asfreq("D")
    covered = [t for t in starts if insd.loc[t:t + pd.Timedelta(days=horizon)].notna().mean() >= 0.8]
    n_false = sum(1 for t in covered if not (insd.loc[t:t + pd.Timedelta(days=horizon)] <= thr).any())
    return n_false, len(covered)


def holm(pvals: Dict[str, float], alpha: float = 0.05) -> Dict[str, bool]:
    """Korekta Holma-Bonferroniego (krokowo w dół). NaN = nie odrzucona."""
    order = sorted(pvals, key=lambda k: (np.inf if not np.isfinite(pvals[k]) else pvals[k]))
    m, out, stop = len(order), {}, False
    for i, k in enumerate(order):
        ok = (not stop) and np.isfinite(pvals[k]) and pvals[k] <= alpha / (m - i)
        out[k] = bool(ok)
        stop = stop or not ok
    return out


def freq_matched_threshold(z: pd.Series, rate: float, months: Tuple[int, int] = (4, 10),
                           period: Tuple[str, str] = ("2016-01-01", "2024-12-31")) -> float:
    """
    Próg predyktora o tej samej częstości przekroczeń co referencja (rate = udział dni ISMN z <= -1 w months/period).
    Liczony z rozkładu SAMEGO predyktora (bez par z ISMN), żeby porównanie terminów nie nagradzało indeksu, który
    przekracza -1 częściej (trend ET0: EDDI <= -1 w 2016-2024 IV-X ~25-29% dni zamiast ~16%).
    """
    q = z.loc[period[0]:period[1]]
    q = q[(q.index.month >= months[0]) & (q.index.month <= months[1])].dropna()
    return float(np.quantile(q, rate)) if len(q) else np.nan


def year_permuted(x: pd.Series, years: Sequence[int], rng: np.random.Generator) -> pd.Series:
    """Seria x z lat przestawionych losowo (bez punktów stałych), dopasowana po dniu roku — placebo dla terminów epizodów."""
    yrs = np.asarray(sorted(years))
    perm = rng.permutation(yrs)
    while len(yrs) > 1 and np.any(perm == yrs):
        perm = rng.permutation(yrs)
    mp = dict(zip(yrs, perm))
    xs = x.dropna()
    key = pd.Series(xs.to_numpy(), index=pd.MultiIndex.from_arrays([xs.index.year, np.minimum(xs.index.dayofyear, 365)]))
    key = key[~key.index.duplicated()]
    idx = xs.index[np.isin(xs.index.year, yrs)]
    vals = key.reindex(pd.MultiIndex.from_arrays([[mp[v] for v in idx.year], np.minimum(idx.dayofyear, 365)])).to_numpy()
    return pd.Series(vals, index=idx).asfreq("D")
