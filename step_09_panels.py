"""
================================================================================
AgriWatch - KROK 9: PANELE PREZENTACJI v1.2
================================================================================
Trzy elementy dashboardu (step_06) i biuletynu (step_05.task_bulletin), liczone wyłącznie z wyników zadań step_05
(veg_anomalies.csv, status_dekads.csv, validation_anomalies.csv) i z dziennej serii ERA5-Land:

  1. „Kondycja winnicy” — najnowsza anomalia NDVI, NDRE i NDMI winnicy (z wobec 5 poprzednich lat, zwykle ten sam
                           tor orbity), klasa słowna, ostatnie dni ze sceną, zgodność (R) z czujnikiem gleby ISMN.
  2. Krzywa sezonu       — NDVI bieżącego sezonu na tle pasma 10–90% z lat Y−5..Y−1 (wzór: ASAP JRC, CLMS NDVI LTS);
                           wilgotność gleby 0–100 cm na tle normy statusu 1991–2020 (ta sama norma, z której liczony
                           jest próg „Sucho”), z cienkimi liniami dwóch poprzednich lat.
  3. Matryca sygnałów    — wiersze w kolejności kaskady EDO CDI (opad -> gleba -> roślinność), kolumny = ostatnie
                           dekady, kolor = z; pod spodem pasek statusu. Roślinność wybierana tak jak w build_status
                           (ostatnia scena <= VEG_MAX_AGE_DAYS przed końcem dekady, tylko S2_MONTHS), więc kolor NDVI
                           zgadza się z paskiem statusu.

Zasady (wszystko stałe a priori, nic nie strojone na ISMN):
  - klasy z jak progi CDI: −1 (próg THR_VEG, SMA, SPI-3) i −1,5 (granica „poważnej” suszy w klasach SPI),
  - pasmo NDVI tylko z lat ŚCIŚLE wcześniejszych niż oglądany sezon (assert; test wycieku w _selftest_panels),
  - punkty bieżącego sezonu bez wygładzania (wygładzanie przepisywałoby przeszłe punkty), wygładzane jest tylko pasmo,
  - jedna wartość na dzień ze sceną (dwie sceny jednego dnia — dwa tory albo dwie granule jednego przelotu —
    nie liczą się podwójnie); kolor punktu = z ostatniej sceny dnia, ta sama reguła co w build_status,
  - jedna paleta klas z roślinności (brązy jak w matrycy), inna niż kolory klas statusu.
Spośród wskaźników roślinności status (alarm) używa tylko NDVI, wybranego z góry; NDRE i NDMI są informacyjne.
Test v1.2 (sparowane ΔR wobec NDVI na tych samych dniach, bootstrap blokami 30 dni): NDMI w granicach niepewności,
NDRE wyraźnie niższe; reguły „kilka wskaźników naraz” nie zmniejszyły liczby fałszywych alarmów. Na tej działce
z trzech wskaźników zmieniają się niemal razem (korelacja z NDVI–NDRE 0,98), więc ich zgodność nie jest niezależnym
potwierdzeniem.
================================================================================
"""

from __future__ import annotations

import html
import logging
import os
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

import step_04_metrics_alert as s4

logger = logging.getLogger("AgriWatch_Panels")

MONTHS_PL = ["sty", "lut", "mar", "kwi", "maj", "cze", "lip", "sie", "wrz", "paź", "lis", "gru"]
PRODUCT_PL = {"S2SR_2.5m": "SR 2,5 m", "S2_10m": "10 m"}

# Co mierzy wskaźnik i co może znaczyć jego spadek (bez diagnozy: średnia działki obejmuje też międzyrzędzia)
INDEX_PL: Dict[str, Dict[str, str]] = {
    "ndvi": {"label": "NDVI — wigor",
             "meaning": "ile zielonych liści widzi satelita (winorośl i zielone międzyrzędzia)",
             "drop_hint": "mniej zieleni niż zwykle o tej porze: susza, wcześniejsze starzenie liści, ale też koszenie "
                          "lub uprawa międzyrzędzi"},
    "ndre": {"label": "NDRE — chlorofil",
             "meaning": "zieloność liści winorośli i okrywy międzyrzędzi (kanał red-edge, średnia działki)",
             "drop_hint": "liście bledsze lub starsze niż zwykle (niedobór wody lub azotu, choroby, wcześniejsze "
                          "przebarwienie), ale też koszenie lub uprawa międzyrzędzi; na tej działce NDRE zmienia się "
                          "prawie tak samo jak NDVI"},
    "ndmi": {"label": "NDMI — woda w liściach",
             "meaning": "zawartość wody w liściach (podczerwień krótkofalowa SWIR)",
             "drop_hint": "mniej wody w liściach lub mniej liści; reaguje też na suchą okrywę międzyrzędzi"},
}

# Klasy z roślinności dla kafelków, mini-wykresu i krzywej sezonu (stałe a priori, zgodne z THR_VEG = −1 i klasami
# SPI). Jedna paleta: brązy / morski jak w matrycy (BrBG), celowo INNA niż kolory klas statusu (czerwień „Sprawdź
# winnicę”, pomarańcz „Sucho”, niebieski „Powrót do normy”), bo NDRE i NDMI są tylko informacyjne.
VEG_Z_COLORS = {"well_below": "#6e4007", "below": "#b0731f", "normal": "#333333", "above": "#21847c"}
Z_NONE = ("none", "brak oceny (za krótka historia)", "#888888")
Z_STALE = ("stale", "brak aktualnej sceny", "#888888")
Z_NOT_COMPUTED = ("not_computed", "wskaźnik niepoliczony — uruchom task_anomalies", "#888888")
# Wynik testu v1.2 (scratchpad agreement/scene_r_diff.csv): sparowane ΔR wobec NDVI na tych samych dniach ze sceną,
# 2018–2024, bootstrap blokami 30 dni. SR 2,5 m: NDRE −0,09 [−0,16; −0,04], NDMI +0,02 [−0,05; +0,08];
# 10 m: NDRE −0,08 [−0,14; −0,04], NDMI +0,00 [−0,07; +0,06]. Ustalone raz; nie przeliczane przy każdym biegu,
# więc w tekście podajemy R z tego testu (wskaźnik, NDVI), a nie R z bieżącej walidacji (inny zbiór dni).
R_VS_STATUS_V12 = {"ndre": ("lower", 0.29, 0.38), "ndmi": ("similar", 0.40, 0.38)}
R_TEST_V12_YEARS = "2018–2024"
# Siła zgodności R z czujnikiem (a priori, |R| < 0,5 = mniej niż 25% wspólnej zmienności)
R_STRENGTH = ((0.5, "słaba zgodność"), (0.7, "umiarkowana zgodność"), (np.inf, "dobra zgodność"))
STATUS_SHORT_PL = {"normal": "Norma", "watch": "Obserwuj", "warning": "Sucho", "alert": "Sprawdź winnicę",
                   "recovery": "Powrót do normy"}
REF_MODE_PL = {"same_track": "ten sam tor orbity", "all_tracks": "oba tory orbity (za mało scen z tego samego toru)"}

# Matryca: (klucz, etykieta, źródło, znak). Znak +1: ujemne z = „sucho / gorzej niż zwykle”.
# Źródło None = wiersz-zaślepka (dane w przygotowaniu, v1.2 B), pokazywany tylko przy MATRIX_SHOW_PLACEHOLDERS.
# CRSWIR (gdyby został dodany) dostaje znak −1: wyższa wartość = mniej wody.
MATRIX_ROWS = (
    ("spi1", "Opad 30 dni (SPI-1)", "status", 1),
    ("spi3", "Opad 90 dni (SPI-3)", "status", 1),
    ("sma_l1", "Gleba 0–7 cm", "status", 1),
    ("sma_rz", "Gleba 0–100 cm", "status", 1),
    ("et_stress", "Stres parowania (ERA5-Land)", None, 1),
    ("ndvi", "NDVI — wigor", "veg", 1),
    ("ndre", "NDRE — chlorofil", "veg", 1),
    ("ndmi", "NDMI — woda w liściach", "veg", 1),
    ("s1", "Radar S-1 (VV)", None, 1),
    ("s3_lst", "Temperatura S-3 (LST)", None, -1),
)
# Granice klas koloru: progi klas SPI (−1, −1,5, −2) i próg CDI −1; skrajne = ±MATRIX_CLIP_Z
MATRIX_BINS = (-2.5, -2.0, -1.5, -1.0, -0.5, 0.5, 1.0, 1.5, 2.0, 2.5)
MX_OFF_SEASON = "#efefef"        # roślinność poza sezonem (kreskowanie)
MX_MISSING = "#d9d9d9"           # brak bezchmurnej sceny / danych w sezonie, zaślepka
SOIL_PREV_YEARS = 2              # cienkie linie gleby: lata Y−1 i Y−2


def z_class(z: Any) -> tuple:
    """(kod, etykieta PL, kolor) klasy z: ≤ −1,5 | (−1,5; −1] | (−1; 1) | ≥ 1 | brak."""
    try:
        z = float(z)
    except (TypeError, ValueError):
        return Z_NONE
    if not np.isfinite(z):
        return Z_NONE
    if z <= -1.5:
        return ("well_below", "wyraźnie poniżej normy", VEG_Z_COLORS["well_below"])
    if z <= -1.0:
        return ("below", "poniżej normy", VEG_Z_COLORS["below"])
    if z < 1.0:
        return ("normal", "w normie", VEG_Z_COLORS["normal"])
    return ("above", "powyżej normy", VEG_Z_COLORS["above"])


def _num(x: Any, nd: int = 2) -> str:
    """Liczba z przecinkiem dziesiętnym i typograficznym minusem; brak = „—”."""
    try:
        if x is None or not np.isfinite(float(x)):
            return "—"
        v = round(float(x), nd) or 0.0              # bez „−0,00”
        return f"{v:.{nd}f}".replace(".", ",").replace("-", "−")
    except (TypeError, ValueError):
        return "—"


def axis_fmt(nd: Optional[int] = None):
    """Formatter osi matplotlib: przecinek dziesiętny i „−” (nd=None: tyle miejsc, ile potrzeba)."""
    from matplotlib.ticker import FuncFormatter

    def f(x, pos=None):
        s = f"{x:.{nd}f}" if nd is not None else f"{x:.6g}"
        return s.replace(".", ",").replace("-", "−")
    return FuncFormatter(f)


def days_pl(n: int) -> str:
    """„1 dzień”, „5 dni” (odmiana liczebnika dla dni)."""
    return f"{n} dzień" if abs(int(n)) == 1 else f"{n} dni"


def days_ago_pl(n: int) -> str:
    """„dziś”, „wczoraj”, „5 dni temu”."""
    n = int(n)
    return "dziś" if n == 0 else "wczoraj" if n == 1 else f"{days_pl(n)} temu"


def r_strength(r: Any) -> str:
    """Słowna siła zgodności R z czujnikiem (progi R_STRENGTH, ustalone z góry)."""
    r = _float(r)
    if not np.isfinite(r):
        return ""
    return next(lab for lim, lab in R_STRENGTH if abs(r) < lim)


def month_label(d: Any) -> str:
    """Etykieta miesiąca osi matrycy: „paź 25” (nie „10.25”, które wygląda jak liczba)."""
    d = pd.Timestamp(d)
    return f"{MONTHS_PL[d.month - 1]} {d:%y}"


def _float(x: Any) -> float:
    """Liczba albo NaN (brak kolumny w starszym CSV, pusta komórka)."""
    try:
        return float(x)
    except (TypeError, ValueError):
        return np.nan


def _year(x: Any) -> str:
    try:
        return "" if x is None or pd.isna(x) else str(pd.Timestamp(x).year)
    except (TypeError, ValueError):
        return ""


def _site_veg(veg: pd.DataFrame, site_id: str, product: str, idx: str, need_z: bool = True) -> pd.DataFrame:
    """Sceny jednego obiektu, produktu i wskaźnika, posortowane w czasie (domyślnie tylko z policzalnym z)."""
    if veg is None or not len(veg):
        return pd.DataFrame(columns=["time", "value", "z"])
    v = veg[(veg["site_id"] == site_id) & (veg["product"] == product) & (veg["index"] == idx)].copy()
    v["time"] = pd.to_datetime(v["time"])
    if need_z:
        v = v.dropna(subset=["z"])
    return v.sort_values("time")


def _per_day(v: pd.DataFrame) -> pd.DataFrame:
    """
    Jedna wartość na dzień ze sceną (dwa tory orbity albo dwie granule jednego przelotu, np. 10:59:04 i 10:59:11):
      value    — średnia scen z tego dnia (położenie punktu na krzywej),
      z        — z OSTATNIEJ sceny dnia z policzalnym z (ta sama reguła co build_status i duża liczba kafelka;
                 średnia dwóch z z różnych torów nie jest już z-score),
      ref_mode — odniesienie tej sceny (same_track / all_tracks), n_scenes, track (tory dnia, np. „0+1”).
    """
    cols = ["value", "z", "n_scenes", "track", "ref_mode"]
    if v is None or not len(v):
        return pd.DataFrame(columns=cols, index=pd.DatetimeIndex([], name="day"))
    d = v.assign(day=pd.to_datetime(v["time"]).dt.normalize()).sort_values("time")
    if "track" not in d:
        d["track"] = np.nan
    if "ref_mode" not in d:
        d["ref_mode"] = ""
    d["z"] = pd.to_numeric(d["z"], errors="coerce")
    g = d.groupby("day")
    last_z = d.dropna(subset=["z"]).groupby("day").tail(1).set_index("day")[["z", "ref_mode"]]
    out = pd.DataFrame({
        "value": g["value"].mean(), "n_scenes": g.size(),
        "track": g["track"].agg(lambda s: "+".join(str(int(t)) for t in sorted(set(s.dropna())))),
    })
    out["z"] = last_z["z"].reindex(out.index)
    out["ref_mode"] = last_z["ref_mode"].reindex(out.index).where(lambda s: s.notna(), "").astype(str)
    out.index.name = "day"
    return out[cols]


# ==============================================================================
# I. PANEL „KONDYCJA WINNICY”
# ==============================================================================

def _validation_r(val: pd.DataFrame, product: str, idx: str, site_id: str) -> Dict[str, Any]:
    """R anomalii wskaźnika winnicy vs anomalia ISMN 20–30 cm (validate_anomalies, segment anomaly_clim)."""
    if val is None or not len(val):
        return {}
    sub = val["subset"].astype(str)
    q = val[(val["product"] == f"{product}_{idx.upper()}") & (val["segment"] == "anomaly_clim")
            & (val["metric"] == "pearson_r") & sub.str.contains(f"vineyard {site_id}", regex=False)]
    if q.empty:
        return {}
    r = q.iloc[0]
    n = pd.to_numeric(r.get("n"), errors="coerce")
    return {"r": float(r["value"]), "r_lo": float(r["ci_low"]), "r_hi": float(r["ci_high"]),
            "r_n": int(n) if np.isfinite(n) else None,
            "r_from": _year(r.get("date_from")), "r_to": _year(r.get("date_to"))}


def condition_panel(veg: pd.DataFrame, val: pd.DataFrame, cfg: Dict[str, Any], site_id: str,
                    today: Optional[Any] = None, status_row: Optional[Any] = None) -> List[Dict[str, Any]]:
    """
    Jeden słownik na wskaźnik z CONDITION_INDICES: najnowsza scena produktu CONDITION_PRODUCT (domyślnie VEG_PRODUCT),
    jej z, klasa, wiek, ostatnie 8 dni ze sceną (spark) i R wobec czujnika ISMN 20–30 cm.
    Zapasowo 10 m: gdy najnowsza scena S2_10m tego wskaźnika jest nowsza niż najnowsza z SR 2,5 m (kontrola SR
    odrzuciła wskaźnik dla tej sceny albo scena czeka w kolejce SR) — pokazujemy 10 m z dopiskiem.
    in_status = wskaźnik VEG_INDEX z produktu VEG_PRODUCT (tylko taka scena wchodzi do statusu; kafelek z 10 m
    nie jest wartością statusu). status_row (ostatni wiersz status_dekads) — dla VEG_INDEX zapisujemy scenę i z,
    których użył status (status_scene), żeby kafelek mógł je pokazać, gdy różnią się od najnowszej sceny.
    Wskaźnika, którego w ogóle nie ma w veg (stary veg_anomalies.csv sprzed v1.2), nie opisujemy jako „krótkiej
    historii” — dostaje klasę not_computed.
    """
    today = pd.Timestamp(today if today is not None else pd.Timestamp.now()).normalize()
    prod = cfg.get("CONDITION_PRODUCT") or cfg["VEG_PRODUCT"]
    max_age = cfg["VEG_MAX_AGE_DAYS"]
    known = set(veg["index"].astype(str)) if veg is not None and len(veg) and "index" in veg else set()
    out = []
    for idx in cfg.get("CONDITION_INDICES", ("ndvi", "ndre", "ndmi")):
        txt = INDEX_PL.get(idx, {"label": idx.upper(), "meaning": "", "drop_hint": ""})
        v, used, note = _site_veg(veg, site_id, prod, idx), prod, ""
        if prod != "S2_10m":
            v10 = _site_veg(veg, site_id, "S2_10m", idx)
            if len(v10) and (v.empty or v10["time"].max().normalize() > v["time"].max().normalize()):
                v, used = v10, "S2_10m"
                note = (f"z 10 m — dla najnowszej sceny brak tego wskaźnika z {PRODUCT_PL.get(prod, prod)} "
                        f"(odrzucony przez kontrolę SR lub jeszcze nieprzetworzony)")
        rec: Dict[str, Any] = {"index": idx, **txt, "product": used, "note": note,
                               "in_status": idx == cfg["VEG_INDEX"] and used == cfg["VEG_PRODUCT"],
                               "status_index": idx == cfg["VEG_INDEX"], "status_scene": None,
                               "date": None, "age_days": None, "value": np.nan, "clim_mean": np.nan, "z": np.nan,
                               "n_ref": None, "ref_mode": "", "track": None, "spark": [], "spark_dates": []}
        if len(v):
            last = v.iloc[-1]
            age = int((today - last["time"].normalize()).days)
            n_ref, trk, mode = _float(last.get("n_ref")), _float(last.get("track")), last.get("ref_mode")
            rec.update(date=last["time"], age_days=age, value=_float(last["value"]),
                       clim_mean=_float(last["clim_mean"]), z=_float(last["z"]),
                       n_ref=int(n_ref) if np.isfinite(n_ref) else None,
                       ref_mode=str(mode) if isinstance(mode, str) else "",
                       track=int(trk) if np.isfinite(trk) else None)
            days = _per_day(v).tail(8)              # ostatnie 8 DNI ze sceną (jedna wartość na dzień, z ostatniej sceny)
            rec["spark"] = [float(z) for z in days["z"]]
            rec["spark_dates"] = [d.strftime("%d.%m.%Y") for d in days.index]
        cls = z_class(rec["z"])
        if rec["age_days"] is not None and rec["age_days"] > max_age:
            cls = Z_STALE
        elif idx not in known:
            cls = Z_NOT_COMPUTED
        rec["cls"], rec["cls_label"], rec["color"] = cls
        if rec["status_index"] and status_row is not None:
            sz, age = _float(status_row.get("veg_z")), _float(status_row.get("veg_age_days"))
            if np.isfinite(sz) and np.isfinite(age):
                dk = pd.Timestamp(status_row["date"]).normalize()
                rec["status_scene"] = {"dekad": dk, "date": dk - pd.Timedelta(days=int(age)), "z": sz,
                                       "product": str(status_row.get("veg_source") or cfg["VEG_PRODUCT"])}
        rec.update(_validation_r(val, used, idx, site_id))
        out.append(rec)
    return out


def condition_footer(cond: List[Dict[str, Any]], cfg: Dict[str, Any], status_date: Optional[Any] = None) -> str:
    """
    Stopka panelu: dlaczego status używa tylko NDVI, jak wypadły pozostałe wskaźniki w teście v1.2 (R_VS_STATUS_V12,
    z liczbami R z tego testu), opóźnienie reakcji roślin i to, że wskaźniki roślinności nie są niezależnym
    potwierdzeniem. Bez tezy o przewadze NDVI z F4 (krytyka v1.2).
    """
    vi = cfg["VEG_INDEX"]
    others = [c["index"].upper() for c in cond if c["index"] != vi]
    txt = f"Spośród wskaźników roślinności status (alarm) używa tylko {vi.upper()}, wybranego z góry"
    if others:
        txt += f"; {' i '.join(others) if len(others) <= 2 else ', '.join(others)} pokazujemy informacyjnie"
    cmp_parts = []
    for c in cond:
        res = R_VS_STATUS_V12.get(c["index"])
        if c["index"] == vi or res is None:
            continue
        verdict, r_idx, r_vi = res
        nums = f"{_num(r_idx)} wobec {_num(r_vi)}"
        cmp_parts.append(f"{c['index'].upper()} ma R podobne do {vi.upper()} ({nums}, różnica w granicach "
                         f"niepewności)" if verdict == "similar" else
                         f"{c['index'].upper()} ma wyraźnie niższe R ({nums})")
    if cmp_parts:
        txt += f". W teście z 2026 r. (te same dni ze sceną {R_TEST_V12_YEARS}) " + "; ".join(cmp_parts)
    txt += ". "
    txt += ("Reguły „kilka wskaźników naraz” nie zmniejszyły tam" if cmp_parts else
            "Test z 2026 r. (reguły „kilka wskaźników naraz”) nie zmniejszył")
    txt += (" liczby fałszywych alarmów — dlatego nie zmieniamy wskaźnika na podstawie tych samych danych. "
            "Roślinność reaguje na przesychanie gleby z opóźnieniem (na tej działce ok. 1–1,5 miesiąca, ocena po "
            "fakcie), a R liczymy dla tego samego dnia")
    txt += ("; wskaźniki roślinności zmieniają się tu niemal razem, więc ich zgodność nie jest niezależnym "
            "potwierdzeniem. " if len(cond) > 1 else ". ")
    txt += (f"R liczone pośrednio (stacja ISMN {cfg.get('STATION', 'Condom')} 136 m od winnicy, pod trawą). "
            f"Norma: {int(cfg.get('VEG_REF_YEARS') or 5)} poprzednich lat, zwykle ten sam tor orbity "
            f"(gdy za mało scen — oba tory).")
    dates = [c["date"] for c in cond if c.get("date") is not None]
    if status_date is not None and dates and max(dates).normalize() > pd.Timestamp(status_date):
        txt += (f" Panel pokazuje najnowszą scenę; status — sceny do końca dekady "
                f"{pd.Timestamp(status_date):%d.%m.%Y}.")
    return txt


# ==============================================================================
# II. KRZYWA SEZONU NA TLE LAT POPRZEDNICH
# ==============================================================================
# Oś „dnia sezonu”: każdą datę przenosimy na ten sam dzień i miesiąc roku 2001 (365 dni; 29.02 odpada),
# więc sezony różnych lat leżą na jednej osi, a okno ±N dni liczymy po obwodzie roku.

_CUM_DAYS = np.cumsum([0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30])
_AXIS0 = pd.Timestamp("2001-01-01")


def ref_doy(t: Any) -> np.ndarray:
    """Dzień osi roku 2001 (1–365) dla dat dowolnego roku; 29.02 -> NaN."""
    t = pd.DatetimeIndex(pd.to_datetime(t))
    mo, dy = np.asarray(t.month, int), np.asarray(t.day, int)
    d = (_CUM_DAYS[mo - 1] + dy).astype(float)
    d[(mo == 2) & (dy == 29)] = np.nan
    return d


def ref_date(doy: Any) -> pd.DatetimeIndex:
    """Dzień osi (1–365) -> data w roku 2001 (do rysowania)."""
    return pd.DatetimeIndex(_AXIS0 + pd.to_timedelta(np.asarray(doy, float) - 1, unit="D"))


def _qname(q: float) -> str:
    return f"p{int(round(100 * q))}"


def _envelope(doy: np.ndarray, vals: np.ndarray, years: np.ndarray, grid_doy: np.ndarray, half_window: int,
              qs: tuple, min_n: int, min_years: int) -> pd.DataFrame:
    """Kwantyle wartości z puli lat odniesienia w oknie ±half_window dni wokół każdego dnia siatki."""
    ok = np.isfinite(vals) & np.isfinite(doy)
    dp, vp, yp = doy[ok], vals[ok], years[ok]
    rows = []
    for d in grid_doy:
        dist = np.abs(dp - d)
        sel = np.minimum(dist, 365 - dist) <= half_window
        pool, ny = vp[sel], len(np.unique(yp[sel]))
        good = len(pool) >= min_n and ny >= min_years
        rows.append([float(np.quantile(pool, q)) if good else np.nan for q in qs] + [int(len(pool)), int(ny)])
    return pd.DataFrame(rows, index=ref_date(grid_doy), columns=[_qname(q) for q in qs] + ["n", "n_years"])


def season_trajectory(veg: pd.DataFrame, era5: pd.DataFrame, cfg: Dict[str, Any], site_id: str,
                      year: Optional[int] = None) -> Dict[str, Any]:
    """
    Dane krzywej sezonu Y (domyślnie: rok najnowszej sceny VEG_PRODUCT):
      ndvi_env  — pasmo kwantyli TRAJ_QUANTILES z dni ze sceną lat Y−TRAJ_REF_YEARS..Y−1 (ściśle < Y), okno
                  ±TRAJ_HALF_WINDOW_DAYS, oba tory razem; NaN przy < TRAJ_MIN_N dniach lub < TRAJ_MIN_YEARS latach;
                  wygładzone średnią kroczącą TRAJ_SMOOTH_DAYS (tylko pasmo),
      ndvi_cur  — dni ze sceną sezonu Y (średnia scen dnia, bez wygładzania), z i tryb odniesienia,
      soil_env  — pasmo wilgotności 0–100 cm z normy statusu CLIM_REF (±CLIM_HALF_WINDOW_DAYS),
      soil_cur, soil_prev — dzienne wartości roku Y i lat Y−1, Y−2,
      soil_thr  — orientacyjny próg „Sucho”: clim_mean − clim_std (dzienne z = −1; status liczy średnią z dekady).
    """
    idx, prod = cfg["VEG_INDEX"], cfg["VEG_PRODUCT"]
    v = _site_veg(veg, site_id, prod, idx, need_z=False)
    v = v[np.isfinite(pd.to_numeric(v["value"], errors="coerce"))] if len(v) else v
    e = era5.set_index(pd.to_datetime(era5["time"]).dt.floor("D")).sort_index()
    e = e[~e.index.duplicated(keep="last")]
    rz = s4.rootzone(e).dropna()

    if year is not None:
        Y = int(year)
    elif len(v):
        Y = int(v["time"].dt.year.max())
    else:
        Y = int(rz.index.max().year)
    ref_years = list(range(Y - int(cfg.get("TRAJ_REF_YEARS", 5)), Y))
    assert ref_years and max(ref_years) < Y, "Pasmo tylko z lat wcześniejszych niż oglądany sezon"
    m0, m1 = cfg.get("TRAJ_MONTHS") or cfg["S2_MONTHS"]
    grid = pd.date_range(f"2001-{m0:02d}-01", pd.Timestamp(f"2001-{m1:02d}-01") + pd.offsets.MonthEnd(0), freq="D")
    grid_doy = ref_doy(grid)
    qs = tuple(cfg.get("TRAJ_QUANTILES", (0.1, 0.5, 0.9)))
    qcols = [_qname(q) for q in qs]

    # --- NDVI: pasmo z lat wcześniejszych, punkty bieżącego sezonu ---
    days = _per_day(v)
    pool = days[np.isin(days.index.year, ref_years)]
    assert (pool.index.year < Y).all(), "Wyciek: w puli pasma są dni z sezonu Y lub późniejsze"
    env = _envelope(ref_doy(pool.index), pool["value"].to_numpy(float), np.asarray(pool.index.year),
                    grid_doy, int(cfg.get("TRAJ_HALF_WINDOW_DAYS", 15)), qs,
                    int(cfg.get("TRAJ_MIN_N", 8)), int(cfg.get("TRAJ_MIN_YEARS", 3)))
    k = int(cfg.get("TRAJ_SMOOTH_DAYS", 7) or 1)
    if k > 1:                                  # wygładzamy tylko statystyki odniesienia; braki zostają brakami
        env[qcols] = env[qcols].rolling(k, center=True, min_periods=1).mean().where(env[qcols].notna())
    cur = days[days.index.year == Y].copy()
    cur["doy"] = ref_doy(cur.index)
    cur = cur[np.isfinite(cur["doy"]) & (cur.index.month >= m0) & (cur.index.month <= m1)]
    cur["x"] = ref_date(cur["doy"])

    # --- Gleba 0–100 cm: norma statusu (CLIM_REF), lata poprzednie, bieżący rok, orientacyjny próg ---
    r0, r1 = cfg["CLIM_REF"]
    hw = int(cfg["CLIM_HALF_WINDOW_DAYS"])
    ref = rz.loc[r0:r1]
    soil_env = _envelope(ref_doy(ref.index), ref.to_numpy(float), np.asarray(ref.index.year), grid_doy, hw, qs,
                         30, 3)

    def season_days(s: pd.Series) -> pd.DataFrame:
        s = s[(s.index.month >= m0) & (s.index.month <= m1)]
        d = pd.DataFrame({"value": s.to_numpy(float), "doy": ref_doy(s.index)}, index=s.index)
        d = d[np.isfinite(d["doy"])]
        d["x"] = ref_date(d["doy"])
        return d

    soil_cur = season_days(rz[rz.index.year == Y])
    soil_prev = {y: season_days(rz[rz.index.year == y]) for y in range(Y - 1, Y - 1 - SOIL_PREV_YEARS, -1)
                 if (rz.index.year == y).any()}
    rz_sub = rz[(rz.index.year == Y) | ((rz.index >= pd.Timestamp(r0)) & (rz.index <= pd.Timestamp(r1)))]
    clim = s4.clim_anomaly(rz_sub, (r0, r1), hw)
    thr = (clim["clim_mean"] - clim["clim_std"])[clim.index.year == Y]
    soil_thr = season_days(thr)

    return {"year": Y, "ref_years": ref_years, "index": idx, "product": prod, "site_id": site_id,
            # lata, które faktycznie mają dni ze sceną w puli pasma (może ich być mniej niż TRAJ_REF_YEARS:
            # pasmo wymaga tylko TRAJ_MIN_YEARS lat w oknie — np. początek archiwum albo niepełna historia SR)
            "ref_years_used": sorted(int(y) for y in set(pool.index.year)),
            "clim_ref": (str(r0)[:4], str(r1)[:4]), "soil_ref_has_Y": Y <= pd.Timestamp(r1).year,
            "quantiles": qs, "grid": grid,
            "ndvi_env": env, "ndvi_cur": cur, "soil_env": soil_env, "soil_cur": soil_cur, "soil_prev": soil_prev,
            "soil_thr": soil_thr, "thr_veg": float(cfg["THR_VEG"]),
            "last_veg": v["time"].max() if len(v) else None, "last_era5": rz.index.max() if len(rz) else None}


def _below_lo(cur: pd.DataFrame, env: pd.DataFrame, qcol: str) -> pd.Series:
    """Dla każdego dnia bieżącego: wartość < dolny kwantyl pasma tego dnia osi (NaN, gdy pasma brak)."""
    lo = env[qcol].reindex(pd.DatetimeIndex(cur["x"])).to_numpy(float) if len(cur) else np.array([])
    out = pd.Series(np.where(np.isfinite(lo), cur["value"].to_numpy(float) < lo, np.nan), index=cur.index)
    return out


def ref_years_label(traj: Dict[str, Any], short: bool = False) -> str:
    """Lata pasma roślinności, które naprawdę mają dane: „2021–2025” albo „2016–2018 (3 z 5 lat z danymi)”."""
    ry, used = traj["ref_years"], traj.get("ref_years_used") or []
    if not used:
        return f"{ry[0]}–{ry[-1]}"
    lab = f"{used[0]}–{used[-1]}" if len(used) > 1 else str(used[0])
    if len(used) < len(ry) and not short:
        lab += f" ({len(used)} z {len(ry)} lat z danymi)"
    return lab


def season_summary(traj: Dict[str, Any]) -> str:
    """
    Zdanie pod wykresem: ile dni ze sceną sezonu leży poniżej dolnego kwantyla pasma NDVI oraz od kiedy gleba
    0–100 cm jest nieprzerwanie poniżej dolnego kwantyla normy (część o glebie pomijana, gdy ostatni dzień nie jest
    poniżej). Liczymy dni, nie sceny (dwie sceny jednego dnia = jeden dzień). Dolny kwantyl (P10, z ≈ −1,3) jest
    ostrzejszy niż próg „Sucho” statusu (z ≤ −1 ze średniej dekady), więc data „od” bywa późniejsza niż w statusie.
    """
    ry = ref_years_label(traj)
    qlo = _qname(min(traj["quantiles"]))
    pct = qlo[1:]
    b = _below_lo(traj["ndvi_cur"], traj["ndvi_env"], qlo)
    m, k = int(b.notna().sum()), int((b == 1).sum())
    name = traj["index"].upper()
    parts = [f"{name}: {k} z {m} dni ze sceną poniżej {pct}. percentyla lat {ry}" if m else
             f"{name}: brak pasma odniesienia (za mało scen z lat {ry})"]
    sb = _below_lo(traj["soil_cur"], traj["soil_env"], qlo).dropna()
    if len(sb) and sb.iloc[-1] == 1:
        start = sb.index[-1]
        for d, flag in zip(sb.index[::-1], sb.to_numpy()[::-1]):
            if flag != 1:
                break
            start = d
        c0, c1 = traj["clim_ref"]
        txt = f"gleba 0–100 cm poniżej {pct}. percentyla normy {c0}–{c1} nieprzerwanie od "
        txt += ("co najmniej " if start == sb.index[0] else "") + f"{start:%d.%m}"
        if traj.get("last_era5") is not None and sb.index[-1] < pd.Timestamp(traj["last_era5"]).normalize():
            txt += f" do {sb.index[-1]:%d.%m}"
        parts.append(txt + " (próg ostrzejszy niż „Sucho” w statusie: z ≤ −1 ze średniej dekady)")
    return "; ".join(parts) + "."


def season_caption(traj: Dict[str, Any], cfg: Dict[str, Any]) -> str:
    """Podpis wykresu: skąd pasma, co znaczą kolory punktów (puste kółka — tylko gdy są na wykresie)."""
    (c0, c1), Y = traj["clim_ref"], traj["year"]
    prev = sorted(traj["soil_prev"])
    thr = _num(cfg["THR_VEG"], 0)
    hollow = len(traj["ndvi_cur"]) and (traj["ndvi_cur"]["ref_mode"].astype(str) == "all_tracks").any()
    return (f"Pasmo {traj['index'].upper()}: 10–90% wartości z poprzednich lat {ref_years_label(traj)}, "
            f"±{cfg.get('TRAJ_HALF_WINDOW_DAYS', 15)} dni, oba tory orbity razem (norma krótka, bo międzyrzędzia "
            f"zmieniają się z roku na rok). Punkty: jedna wartość na dzień ze sceną sezonu {Y} (średnia scen z tego "
            f"dnia), bez wygładzania. Kolor punktu = anomalia z ostatniej sceny dnia (jak w statusie), liczona zwykle "
            f"wobec tego samego toru orbity: brązowy = z ≤ {thr} (ok. 16. percentyl), ciemnobrązowy = z ≤ −1,5. "
            f"Brzeg pasma to 10. percentyl, a z liczone jest wobec innego zbioru scen, więc punkt tuż w paśmie może "
            f"być brązowy" + ("; puste kółka = odniesienie z obu torów (za mało scen z tego samego toru)"
                              if hollow else "") +
            f". Pasmo gleby: 10–90% normy {c0}–{c1} (±{cfg['CLIM_HALF_WINDOW_DAYS']} dni, ta sama norma co status"
            + (f"; norma obejmuje też sezon {Y}" if traj.get("soil_ref_has_Y") else "") + ")"
            + (f"; cienkie linie: lata {', '.join(str(y) for y in prev)}" if prev else "") +
            ". Próg „Sucho” orientacyjny: dzienna wartość dla z = −1, a status liczy średnie z dekady.")


def plot_season_trajectory(traj: Dict[str, Any], cfg: Dict[str, Any], out_png: str) -> str:
    """Wykres dwupanelowy (NDVI na górze, gleba 0–100 cm na dole), oś miesięcy po polsku. Zwraca ścieżkę PNG."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter

    Y, (c0, c1) = traj["year"], traj["clim_ref"]
    ry_lab, n_used = ref_years_label(traj, short=True), len(traj.get("ref_years_used") or traj["ref_years"])
    qn = [_qname(q) for q in traj["quantiles"]]
    lo, mid, hi = qn[0], qn[len(qn) // 2], qn[-1]
    thr_veg = traj["thr_veg"]
    fig, ax = plt.subplots(2, 1, figsize=(11, 6.4), sharex=True, gridspec_kw={"hspace": 0.12})

    env = traj["ndvi_env"]
    ax[0].fill_between(env.index, env[lo], env[hi], color="#9bb7d4", alpha=0.45, lw=0,
                       label=f"{ry_lab}: 10–90%")
    ax[0].plot(env.index, env[mid], color="#4a6f96", lw=1.2, ls="--",
               label=f"mediana {n_used} {'roku' if n_used == 1 else 'lat'}")
    cur = traj["ndvi_cur"]
    if len(cur):
        z = cur["z"].to_numpy(float)
        hollow = (cur["ref_mode"].astype(str) == "all_tracks").to_numpy()
        ax[0].plot(cur["x"], cur["value"], color="#2b2b2b", lw=0.8, alpha=0.6)
        thr_txt = _num(thr_veg, 0)
        for sel, kw, lab in (     # kolory klas jak w kafelkach i matrycy (VEG_Z_COLORS), nie kolory statusu
                (np.isfinite(z) & (z > thr_veg), {"s": 22, "color": VEG_Z_COLORS["normal"]},
                 f"{Y}: dzień ze sceną (z > {thr_txt})"),
                (np.isfinite(z) & (z <= thr_veg) & (z > -1.5), {"s": 30, "color": VEG_Z_COLORS["below"]},
                 f"{Y}: −1,5 < z ≤ {thr_txt}"),
                (np.isfinite(z) & (z <= min(thr_veg, -1.5)), {"s": 30, "color": VEG_Z_COLORS["well_below"]},
                 f"{Y}: z ≤ −1,5"),
                (~np.isfinite(z), {"s": 18, "color": "#9a9a9a"}, f"{Y}: bez oceny z (krótka historia)")):
            if not sel.any():
                continue
            full, empty = sel & ~hollow, sel & hollow
            if full.any():
                ax[0].scatter(cur["x"][full], cur["value"][full], zorder=3, label=lab, **kw)
            if empty.any():
                ax[0].scatter(cur["x"][empty], cur["value"][empty], s=kw["s"], facecolors="none",
                              edgecolors=kw["color"], lw=1.2, zorder=3, label=lab + ", odniesienie z obu torów")
    ax[0].set_ylabel(f"{traj['index'].upper()} winnicy\n({PRODUCT_PL.get(traj['product'], traj['product'])}, "
                     "średnia działki)")

    senv = traj["soil_env"]
    ax[1].fill_between(senv.index, senv[lo], senv[hi], color="#9bb7d4", alpha=0.45, lw=0, label=f"{c0}–{c1}: 10–90%")
    ax[1].plot(senv.index, senv[mid], color="#4a6f96", lw=1.2, ls="--", label=f"mediana {c0}–{c1}")
    for (y, d), col in zip(sorted(traj["soil_prev"].items(), reverse=True), ("#a6761d", "#cdb48a", "#e3d5bb")):
        ax[1].plot(d["x"], d["value"], color=col, lw=0.9, alpha=0.9, label=str(y))
    sc = traj["soil_cur"]
    if len(sc):
        ax[1].plot(sc["x"], sc["value"], color="#8c510a", lw=2, label=f"{Y} (ERA5-Land)")
    st = traj["soil_thr"]
    if len(st):
        ax[1].plot(st["x"], st["value"], color="#f08a24", ls=":", lw=1.1,
                   label=f"próg „Sucho” orientacyjny (z = −1, norma {c0}–{c1})")
    ax[1].set_ylabel("Wilgotność gleby\n0–100 cm [m³/m³]")

    for a, last, lab in ((ax[0], traj.get("last_veg"), "ostatnia scena"),
                         (ax[1], traj.get("last_era5"), "ostatni dzień ERA5-Land")):
        a.grid(alpha=0.25)
        a.yaxis.set_major_formatter(axis_fmt())
        if last is not None and pd.Timestamp(last).year == Y:
            d = ref_doy([pd.Timestamp(last)])
            if np.isfinite(d[0]):
                a.axvline(ref_date(d)[0], color="0.5", lw=0.6, label=f"{lab} ({pd.Timestamp(last):%d.%m})")
        if a.get_legend_handles_labels()[0]:            # legenda obok wykresu: nie zasłania danych sezonu
            a.legend(fontsize=8, loc="upper left", bbox_to_anchor=(1.01, 1.0), frameon=False)
    grid = traj["grid"]
    ax[1].set_xlim(grid[0], grid[-1])
    ax[1].xaxis.set_major_locator(mdates.MonthLocator())
    ax[1].xaxis.set_major_formatter(FuncFormatter(lambda x, pos: MONTHS_PL[mdates.num2date(x).month - 1]))
    fig.suptitle(f"Sezon {Y} na tle lat {ry_lab} (roślinność) i normy {c0}–{c1} (gleba)", fontsize=11)
    os.makedirs(os.path.dirname(out_png) or ".", exist_ok=True)
    fig.savefig(out_png, dpi=110, bbox_inches="tight")
    plt.close(fig)
    return out_png


# ==============================================================================
# III. MATRYCA SYGNAŁÓW
# ==============================================================================

def _veg_at_dekads(v: pd.DataFrame, dekads: List[pd.Timestamp], cfg: Dict[str, Any]) -> List[tuple]:
    """
    Wybór sceny dla dekady DOKŁADNIE jak w s4.build_status: ostatnia scena z czasem <= koniec dekady + 1 dzień
    i >= koniec dekady − VEG_MAX_AGE_DAYS, tylko w miesiącach S2_MONTHS. Zwraca (z, czas sceny, wiek, flaga,
    odniesienie sceny) z flagą "ok" | "missing" (sezon, brak sceny) | "off_season".
    """
    m0, m1 = cfg["S2_MONTHS"]
    out = []
    for dk in dekads:
        if not (m0 <= dk.month <= m1):
            out.append((np.nan, None, np.nan, "off_season", ""))
            continue
        cand = v[(v["time"] <= dk + pd.Timedelta(days=1)) &
                 (v["time"] >= dk - pd.Timedelta(days=cfg["VEG_MAX_AGE_DAYS"]))] if len(v) else v
        if len(cand):
            last = cand.iloc[-1]
            mode = last.get("ref_mode")
            out.append((float(last["z"]), last["time"], float((dk - last["time"].normalize()).days), "ok",
                        mode if isinstance(mode, str) else ""))
        else:
            out.append((np.nan, None, np.nan, "missing", ""))
    return out


def signal_matrix(status: pd.DataFrame, veg: pd.DataFrame, cfg: Dict[str, Any], site_id: str,
                  n_dekads: Optional[int] = None) -> Dict[str, Any]:
    """
    Matryca z (wiersze MATRIX_ROWS × ostatnie n dekad statusu; ostatnia dekada = ostatnia pełna dekada ERA5).
    Zwraca słownik: z (DataFrame, NaN = brak wartości), flag (ok | missing | off_season | placeholder |
    not_computed — wskaźnika nie ma w veg, np. stary plik sprzed v1.2), scene (czas sceny roślinności), age (wiek
    sceny w dniach), ref (odniesienie sceny: same_track / all_tracks), cls (klasa statusu dekady), rows (pokazane
    wiersze), newest_scene (najnowsza scena VEG_INDEX, jeśli późniejsza niż ostatnia dekada).
    """
    n = int(n_dekads or cfg.get("MATRIX_DEKADS", 36))
    st = status[status["site_id"] == site_id].copy()
    if st.empty:
        raise ValueError(f"Brak statusu dla {site_id}")
    st["date"] = pd.to_datetime(st["date"])
    st = st.sort_values("date").drop_duplicates("date", keep="last").set_index("date")
    cols = list(st.index[-n:])
    rows = [r for r in cfg.get("MATRIX_ROWS", MATRIX_ROWS) if r[2] is not None or cfg.get("MATRIX_SHOW_PLACEHOLDERS")]
    keys = [r[0] for r in rows]
    Z = pd.DataFrame(np.nan, index=keys, columns=cols)
    F = pd.DataFrame("missing", index=keys, columns=cols, dtype=object)
    S = pd.DataFrame(None, index=keys, columns=cols, dtype=object)
    A = pd.DataFrame(np.nan, index=keys, columns=cols)
    R = pd.DataFrame("", index=keys, columns=cols, dtype=object)
    prod = cfg["VEG_PRODUCT"]
    known = set(veg["index"].astype(str)) if veg is not None and len(veg) and "index" in veg else set()
    for key, _, src, sign in rows:
        if src is None:
            F.loc[key] = "placeholder"
        elif src == "veg" and key not in known:
            F.loc[key] = "not_computed"
        elif src == "status":
            vals = pd.to_numeric(st.loc[cols, key], errors="coerce").to_numpy(float) if key in st else np.full(len(cols), np.nan)
            Z.loc[key] = sign * vals
            F.loc[key] = np.where(np.isfinite(vals), "ok", "missing")
        elif src == "veg":
            sel = _veg_at_dekads(_site_veg(veg, site_id, prod, key), cols, cfg)
            Z.loc[key] = [sign * s[0] for s in sel]
            S.loc[key] = [s[1] for s in sel]
            A.loc[key] = [s[2] for s in sel]
            F.loc[key] = [s[3] for s in sel]
            R.loc[key] = [s[4] for s in sel]
    newest = None
    vi = _site_veg(veg, site_id, prod, cfg["VEG_INDEX"])
    if len(vi) and cols and vi["time"].max().normalize() > cols[-1]:
        newest = vi["time"].max()
    return {"z": Z, "flag": F, "scene": S, "age": A, "ref": R, "cls": st.loc[cols, "cdi_class"].astype(str),
            "rows": rows,
            "product": prod, "newest_scene": newest}


def matrix_caption(mx: Dict[str, Any], cfg: Dict[str, Any]) -> str:
    r0, r1 = cfg["CLIM_REF"]
    txt = ("Kolejność jak w europejskim wskaźniku suszy EDO (CDI): opad → gleba → roślinność. Kolor = odchylenie "
           f"od normy w odchyleniach standardowych (gleba i opad: norma {str(r0)[:4]}–{str(r1)[:4]}; roślinność: "
           f"{int(cfg.get('VEG_REF_YEARS') or 5)} poprzednich lat, zwykle ten sam tor orbity, gdy za mało scen — "
           f"oba tory). Roślinność jak w statusie: ostatnia bezchmurna scena do {cfg['VEG_MAX_AGE_DAYS']} dni przed "
           f"końcem dekady (jedna scena może więc wypełnić do 3 dekad), tylko w sezonie (miesiące "
           f"{cfg['S2_MONTHS'][0]}–{cfg['S2_MONTHS'][1]}). Pasek „Status” pod matrycą: klasa statusu dekady.")
    if (mx["flag"] == "not_computed").any().any():
        txt += " Wiersz „wskaźnik niepoliczony”: brak tego wskaźnika w veg_anomalies.csv (uruchom task_anomalies)."
    if mx.get("newest_scene") is not None:
        txt += f" Najnowsza scena po ostatniej pełnej dekadzie: {pd.Timestamp(mx['newest_scene']):%d.%m.%Y}."
    return txt


def _mx_cmap(cfg: Dict[str, Any]):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import BoundaryNorm, ListedColormap

    c = float(cfg.get("MATRIX_CLIP_Z", 2.5))
    bins = [-c] + list(MATRIX_BINS[1:-1]) + [c]
    cmap = ListedColormap(plt.get_cmap("BrBG")(np.linspace(0.05, 0.95, len(bins) - 1)))
    cmap.set_bad((0, 0, 0, 0))
    return cmap, BoundaryNorm(bins, cmap.N), bins, c


def matrix_table(mx: Dict[str, Any]) -> pd.DataFrame:
    """Postać długa matrycy (do signal_matrix.csv): wiersz, dekada, z, flaga, scena, wiek, odniesienie, status."""
    recs = []
    labels = {r[0]: r[1] for r in mx["rows"]}
    ref = mx.get("ref")
    for key in mx["z"].index:
        for dk in mx["z"].columns:
            sc = mx["scene"].at[key, dk]
            recs.append({"row": key, "label": labels[key], "dekad": dk.strftime("%Y-%m-%d"),
                         "z": mx["z"].at[key, dk], "flag": mx["flag"].at[key, dk],
                         "scene_time": "" if sc is None or pd.isna(sc) else pd.Timestamp(sc).strftime("%Y-%m-%dT%H:%M:%S"),
                         "scene_age_days": mx["age"].at[key, dk],
                         "ref_mode": "" if ref is None else ref.at[key, dk], "status": mx["cls"].get(dk, "")})
    return pd.DataFrame(recs)


def _status_labels(status_labels: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    return {**STATUS_SHORT_PL, **(status_labels or {})}


def plot_signal_matrix(mx: Dict[str, Any], cfg: Dict[str, Any], out_png: str, csv_path: Optional[str] = None,
                       status_labels: Optional[Dict[str, str]] = None) -> str:
    """Matryca jako PNG (do biuletynu) + signal_matrix.csv obok (postać długa). Zwraca ścieżkę PNG."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch, Rectangle

    Z, F, rows = mx["z"], mx["flag"], mx["rows"]
    nr, nc = Z.shape
    cmap, norm, bins, clip = _mx_cmap(cfg)
    fig, (ax, axs) = plt.subplots(2, 1, figsize=(12, 1.4 + 0.33 * nr), sharex=True,
                                  gridspec_kw={"height_ratios": [nr, 1], "hspace": 0.05})
    zz = np.ma.masked_invalid(np.clip(Z.to_numpy(float), -clip, clip))
    ax.pcolormesh(np.arange(nc + 1), np.arange(nr + 1), zz, cmap=cmap, norm=norm, edgecolors="white", linewidth=0.6)
    for i, key in enumerate(Z.index):
        for j in range(nc):
            f, z = F.iat[i, j], Z.iat[i, j]
            if f == "off_season":
                ax.add_patch(Rectangle((j, i), 1, 1, facecolor=MX_OFF_SEASON, edgecolor="#c4c4c4", hatch="//", lw=0))
            elif f in ("missing", "placeholder", "not_computed") or not np.isfinite(z):
                ax.add_patch(Rectangle((j, i), 1, 1, facecolor=MX_MISSING, lw=0))
            elif abs(z) >= 1:
                ax.text(j + 0.5, i + 0.5, _num(z, 1), ha="center", va="center", fontsize=5.5,
                        color="white" if abs(z) >= 2 else "#222")
        if rows[i][2] is None:
            ax.text(nc / 2, i + 0.5, "w przygotowaniu (v1.2 B)", ha="center", va="center", fontsize=7, color="#666")
        elif (F.iloc[i] == "not_computed").all():
            ax.text(nc / 2, i + 0.5, "wskaźnik niepoliczony — uruchom task_anomalies", ha="center", va="center",
                    fontsize=7, color="#666")
    for i in range(nr + 1):
        ax.axhline(i, color="white", lw=0.8)
    for j in range(nc + 1):
        ax.axvline(j, color="white", lw=0.8)
    ax.set_xlim(0, nc)
    ax.set_ylim(0, nr)
    ax.set_yticks(np.arange(nr) + 0.5, [r[1] for r in rows], fontsize=8)
    ax.invert_yaxis()
    ax.set_title(f"Matryca sygnałów — ostatnie {nc} dekad", loc="left", fontsize=10)
    ax.legend(handles=[Patch(facecolor=MX_OFF_SEASON, edgecolor="#c4c4c4", hatch="//", label="poza sezonem"),
                       Patch(facecolor=MX_MISSING, label="brak bezchmurnej sceny / danych")],
              loc="lower right", bbox_to_anchor=(1.0, 1.0), ncol=2, fontsize=7, frameon=False)
    for j, c in enumerate(mx["cls"]):
        axs.add_patch(Rectangle((j, 0), 1, 1, facecolor=s4._COLORS.get(c, "#cccccc"), edgecolor="white", lw=0.6))
    axs.set_ylim(0, 1)
    axs.set_yticks([0.5], ["Status"], fontsize=8)
    first = [k for k, d in enumerate(Z.columns) if d.day <= 10]
    axs.set_xticks(np.array(first) + 0.5, [month_label(Z.columns[k]) for k in first], fontsize=7)
    labs = _status_labels(status_labels)
    present = [c for c in ("normal", "watch", "warning", "alert", "recovery") if c in set(mx["cls"])]
    if present:                                    # klucz kolorów paska statusu (tylko klasy obecne na pasku)
        axs.legend(handles=[Patch(facecolor=s4._COLORS.get(c, "#cccccc"), label=labs.get(c, c)) for c in present],
                   loc="upper left", bbox_to_anchor=(0.0, -0.9), ncol=len(present), fontsize=7, frameon=False,
                   title="Status dekady:", title_fontsize=7)
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    cb = fig.colorbar(sm, ax=[ax, axs], fraction=0.025, pad=0.01, ticks=bins)
    cb.ax.tick_params(labelsize=7)
    cb.ax.yaxis.set_major_formatter(axis_fmt(1))
    cb.set_label("z (≤ −1: sucho / gorzej niż zwykle)", fontsize=7)
    os.makedirs(os.path.dirname(out_png) or ".", exist_ok=True)
    fig.savefig(out_png, dpi=120, bbox_inches="tight")
    plt.close(fig)
    matrix_table(mx).to_csv(csv_path or os.path.splitext(out_png)[0] + ".csv", index=False)
    return out_png


def matrix_html(mx: Dict[str, Any], cfg: Dict[str, Any], status_labels: Optional[Dict[str, str]] = None) -> str:
    """
    Matryca jako tabela HTML (do dashboardu): kolory jak w PNG, wartość wpisana przy |z| ≥ 1, dymek z dokładnym z,
    dekadą i źródłem (dla roślinności: data i wiek sceny, odniesienie tej sceny). Pod tabelą pasek statusu z kluczem
    kolorów, legenda i podpis.
    """
    from matplotlib.colors import to_hex

    esc = html.escape
    Z, F, S, A, rows = mx["z"], mx["flag"], mx["scene"], mx["age"], mx["rows"]
    REF = mx.get("ref")
    cmap, norm, bins, clip = _mx_cmap(cfg)
    labels = _status_labels(status_labels)
    r0, r1 = cfg["CLIM_REF"]
    nref = int(cfg.get("VEG_REF_YEARS") or 5)
    src_txt = {"spi1": f"ERA5-Land, norma {str(r0)[:4]}–{str(r1)[:4]}, stan na koniec dekady",
               "spi3": f"ERA5-Land, norma {str(r0)[:4]}–{str(r1)[:4]}, stan na koniec dekady",
               "sma_l1": f"ERA5-Land, średnia z dekady, norma {str(r0)[:4]}–{str(r1)[:4]}",
               "sma_rz": f"ERA5-Land, średnia z dekady, norma {str(r0)[:4]}–{str(r1)[:4]}"}
    prod = PRODUCT_PL.get(mx.get("product", ""), mx.get("product", ""))
    nc = Z.shape[1]

    def color(z):
        return to_hex(cmap(norm(np.clip(z, -clip, clip))))

    def age_txt(age):
        if not np.isfinite(age):
            return ""
        return ", w ostatnim dniu dekady" if int(age) <= 0 else f", {days_pl(int(age))} przed końcem dekady"

    head = "".join(f'<th>{month_label(d) if d.day <= 10 else ""}</th>' for d in Z.columns)
    body = []
    for i, (key, label, src, _) in enumerate(rows):
        cells = []
        if src is None:
            cells.append(f'<td class="ph" colspan="{nc}">w przygotowaniu (v1.2 B)</td>')
        elif (F.loc[key] == "not_computed").all():
            cells.append(f'<td class="ph" colspan="{nc}">wskaźnik niepoliczony — uruchom task_anomalies</td>')
        else:
            for dk in Z.columns:
                z, f = Z.at[key, dk], F.at[key, dk]
                dtxt = f"{label} · dekada do {dk:%d.%m.%Y}"
                if f == "off_season":
                    cells.append(f'<td class="off" title="{esc(dtxt)}: poza sezonem"></td>')
                    continue
                if not np.isfinite(z):
                    why = "brak bezchmurnej sceny" if src == "veg" else "brak danych"
                    cells.append(f'<td class="na" title="{esc(dtxt)}: {why}"></td>')
                    continue
                if src == "veg":
                    sc = S.at[key, dk]
                    mode = "" if REF is None else REF.at[key, dk]
                    vref = f"norma: {nref} poprzednich lat" + (f", {REF_MODE_PL[mode]}" if mode in REF_MODE_PL else "")
                    source = f"Sentinel-2 {prod}, scena {pd.Timestamp(sc):%d.%m.%Y}{age_txt(A.at[key, dk])}; {vref}"
                else:
                    source = src_txt.get(key, "")
                txt = _num(z, 1) if abs(z) >= 1 else ""
                fg = "#fff" if abs(z) >= 2 else "#222"
                cells.append(f'<td style="background:{color(z)};color:{fg}" '
                             f'title="{esc(dtxt)}: z = {_num(z, 2)} ({esc(source)})">{txt}</td>')
        body.append(f'<tr><th class="lbl">{esc(label)}</th>{"".join(cells)}</tr>')
    strip = "".join(f'<td style="background:{s4._COLORS.get(c, "#ccc")}" '
                    f'title="Status · dekada do {dk:%d.%m.%Y}: {esc(labels.get(c, c))}"></td>'
                    for dk, c in zip(Z.columns, mx["cls"]))
    body.append(f'<tr class="st"><th class="lbl">Status</th>{strip}</tr>')
    chips = "".join(f'<span class="chip" style="background:{color((a + b) / 2)}"></span>'
                    for a, b in zip(bins[:-1], bins[1:]))
    present = [c for c in ("normal", "watch", "warning", "alert", "recovery") if c in set(mx["cls"])]
    st_chips = "".join(f'<span class="chip" style="margin-left:8px;background:{s4._COLORS.get(c, "#ccc")}"></span>'
                       f'<span>{esc(labels.get(c, c))}</span>' for c in present)
    legend = (f'<div class="aw-mx-leg"><span>{_num(-clip, 1)}</span>{chips}<span>{_num(clip, 1)}</span>'
              f'<span style="margin-left:8px">z ≤ −1: sucho / gorzej niż zwykle</span>'
              f'<span class="chip off"></span><span>poza sezonem</span>'
              f'<span class="chip na"></span><span>brak bezchmurnej sceny / danych</span></div>'
              + (f'<div class="aw-mx-leg"><span>Pasek „Status”:</span>{st_chips}</div>' if present else ""))
    style = ("<style>.aw-mx{border-collapse:separate;border-spacing:1px;table-layout:fixed;width:100%;font-size:9px}"
             ".aw-mx td{padding:0;height:20px;text-align:center;font-size:9px}"
             ".aw-mx thead th{font-weight:400;color:#666;text-align:left;font-size:9px;padding:0;white-space:nowrap;"
             "overflow:visible}"
             ".aw-mx th.lbl{width:170px;text-align:right;padding-right:6px;font-size:11px;font-weight:400;color:#333;"
             "white-space:nowrap}"
             ".aw-mx td.off{background:#efefef repeating-linear-gradient(45deg,transparent 0 3px,#cfcfcf 3px 4px)}"
             ".aw-mx td.na{background:#d9d9d9} .aw-mx td.ph{background:#d9d9d9;color:#666;font-size:10px}"
             ".aw-mx tr.st td{height:12px} .aw-mx tr.st th{padding-top:4px}"
             ".aw-mx-leg{display:flex;align-items:center;gap:2px;font-size:11px;color:#666;margin-top:6px;"
             "flex-wrap:wrap}.aw-mx-leg .chip{display:inline-block;width:18px;height:10px}"
             ".aw-mx-leg .chip.off{margin-left:10px;background:#efefef repeating-linear-gradient(45deg,transparent 0 3px,"
             "#cfcfcf 3px 4px)}.aw-mx-leg .chip.na{margin-left:10px;background:#d9d9d9}</style>")
    return (f'{style}<div style="overflow-x:auto"><table class="aw-mx"><thead><tr><th class="lbl"></th>{head}</tr>'
            f'</thead><tbody>{"".join(body)}</tbody></table></div>{legend}'
            f'<div class="src" style="margin-top:4px">{esc(matrix_caption(mx, cfg))}</div>')


# ==============================================================================
# IV. TESTY (wywoływane z selftestu step_05)
# ==============================================================================

def _selftest_panels(veg: pd.DataFrame, status: pd.DataFrame, era5: pd.DataFrame, cfg: Dict[str, Any],
                     site_id: str) -> None:
    """
    1. Brak wycieku: zaburzenie wartości roku Y i lat późniejszych nie zmienia pasma NDVI sezonu Y; sprawdzane dla
       Y = najnowszy rok oraz Y − 1. Pasmo gleby sprawdzane tak samo tylko dla Y późniejszego niż koniec CLIM_REF:
       dla Y w okresie CLIM_REF norma gleby celowo obejmuje Y (ta sama norma co status, decyzja 4; mówi to podpis).
    2. Matryca: komórka roślinności poza sezonem = NaN z flagą off_season; wiersz NDVI = veg_z statusu w każdej
       dekadzie, w której status ma veg_z (ta sama reguła wyboru sceny), a NaN tam, gdzie status go nie ma.
    3. Kafelki na przypadkach, których zwykły selftest nie tworzy: „dziś” = ostatnia scena + 3 dni (klasy z zamiast
       „brak aktualnej sceny”); zapas 10 m (najnowsza scena SR bez NDRE, potem bez NDVI) — kafelek 10 m z dopiskiem,
       a NDVI z 10 m NIE jest „używany w statusie” i pokazuje scenę statusu.
    4. Zdanie podsumowania z częścią o glebie (gleba sezonu Y obniżona do 30%: „nieprzerwanie od co najmniej …”).
    5. Zaślepki matrycy (MATRIX_SHOW_PLACEHOLDERS) i stare pliki wyników (veg bez track/ref_mode i bez NDRE, status
       bez sma_l1): żaden panel nie rzuca wyjątku, brak NDRE opisany jako „wskaźnik niepoliczony”.
    """
    import tempfile

    v = veg[(veg["site_id"] == site_id) & (veg["product"] == cfg["VEG_PRODUCT"]) & (veg["index"] == cfg["VEG_INDEX"])]
    y_last = int(pd.to_datetime(v["time"]).dt.year.max())
    years = [y_last] + ([y_last - 1] if (pd.to_datetime(v["time"]).dt.year == y_last - 1).any() else [])
    clim_end = pd.Timestamp(cfg["CLIM_REF"][1]).year
    soil_checked = []
    for Y in years:
        base = season_trajectory(veg, era5, cfg, site_id, year=Y)
        vp = veg.copy()
        vp.loc[pd.to_datetime(vp["time"]).dt.year >= Y, "value"] += 10.0
        ep = era5.copy()
        late = pd.to_datetime(ep["time"]).dt.year >= Y
        for c in ("sm_l1", "sm_l2", "sm_l3"):
            ep.loc[late, c] += 1.0
        pert = season_trajectory(vp, ep, cfg, site_id, year=Y)
        pd.testing.assert_frame_equal(base["ndvi_env"], pert["ndvi_env"])
        if Y > clim_end:
            pd.testing.assert_frame_equal(base["soil_env"], pert["soil_env"])
            soil_checked.append(Y)
        for y in base["soil_prev"]:
            pd.testing.assert_frame_equal(base["soil_prev"][y], pert["soil_prev"][y])
        assert base["ndvi_env"]["p50"].notna().any(), f"Pasmo NDVI {Y} puste"
        assert not np.allclose(base["ndvi_cur"]["value"], pert["ndvi_cur"]["value"]), "Zaburzenie nie dotarło do roku Y"
        assert base["ref_years_used"] and max(base["ref_years_used"]) < Y, base["ref_years_used"]
    print(f"[OK] Krzywa sezonu: pasma NDVI lat {years} (gleby: {soil_checked}) niezależne od wartości sezonu Y "
          f"i lat późniejszych (brak wycieku).")

    st = status[status["site_id"] == site_id].copy()
    mx = signal_matrix(status, veg, cfg, site_id, n_dekads=len(st))
    m0, m1 = cfg["S2_MONTHS"]
    off = [d for d in mx["z"].columns if not (m0 <= d.month <= m1)]
    assert off, "Test matrycy wymaga dekad poza sezonem"
    for key in ("ndvi", "ndre", "ndmi"):
        if key in mx["z"].index:
            assert mx["z"].loc[key, off].isna().all() and (mx["flag"].loc[key, off] == "off_season").all(), key
    st["date"] = pd.to_datetime(st["date"])
    sz = st.set_index("date")["veg_z"].astype(float).reindex(mx["z"].columns)
    mz = mx["z"].loc[cfg["VEG_INDEX"]].astype(float)
    assert (sz.notna() == mz.notna()).all(), "Matryca i status różnią się dostępnością roślinności"
    assert sz.notna().sum() > 0 and np.allclose(sz.dropna(), mz[sz.notna()]), "NDVI w matrycy ≠ veg_z statusu"
    print(f"[OK] Matryca: {int(sz.notna().sum())} dekad z NDVI = veg_z statusu, {len(off)} dekad poza sezonem "
          f"(NaN z flagą).")

    # --- 3. Kafelki: aktualna scena i zapas 10 m ---
    import step_06_dashboard as s6
    prod, vi = cfg["VEG_PRODUCT"], cfg["VEG_INDEX"]
    t = pd.to_datetime(veg["time"])
    site_sr = (veg["site_id"] == site_id) & (veg["product"] == prod) & veg["z"].notna()
    t_new = t[site_sr].max()
    today = t_new.normalize() + pd.Timedelta(days=3)
    srow = status[status["site_id"] == site_id].sort_values("date").iloc[-1]
    cond = {c["index"]: c for c in condition_panel(veg, pd.DataFrame(), cfg, site_id, today=today, status_row=srow)}
    assert cond[vi]["product"] == prod and cond[vi]["in_status"] and cond[vi]["age_days"] == 3, cond[vi]
    assert all(c["cls"] in ("well_below", "below", "normal", "above") for c in cond.values()), \
        [c["cls"] for c in cond.values()]
    for drop_idx in ("ndre", vi):
        vf = veg[~(site_sr & (veg["index"].isin(["ndre", drop_idx])) & (t == t_new))]
        cf = {c["index"]: c for c in condition_panel(vf, pd.DataFrame(), cfg, site_id, today=today, status_row=srow)}
        assert cf["ndre"]["product"] == "S2_10m" and cf["ndre"]["note"] and not cf["ndre"]["in_status"], cf["ndre"]
        if drop_idx == vi:
            assert cf[vi]["product"] == "S2_10m" and not cf[vi]["in_status"], cf[vi]
            assert cf[vi]["status_scene"] is not None or not np.isfinite(_float(srow.get("veg_z")))
            h = s6._condition_html(list(cf.values()), cfg, srow["date"])
            assert h.count("używany w statusie") == 0 and "status używa" in h, "Kafelek 10 m oznaczony jako status"
        else:
            assert cf[vi]["product"] == prod and cf[vi]["in_status"], cf[vi]
    h = s6._condition_html(list(cond.values()), cfg, srow["date"])
    assert h.count("używany w statusie") == 1 and "brak aktualnej sceny" not in h, "Kafelki: status / klasy z"
    print("[OK] Kondycja winnicy: klasy z przy aktualnej scenie, zapas 10 m (NDRE, NDVI) poza statusem.")

    # --- 4. Podsumowanie z częścią o glebie ---
    ep = era5.copy()
    yr = pd.to_datetime(ep["time"]).dt.year == y_last
    for c in ("sm_l1", "sm_l2", "sm_l3"):
        ep.loc[yr, c] *= 0.3
    summ = season_summary(season_trajectory(veg, ep, cfg, site_id, year=y_last))
    assert "gleba 0–100 cm poniżej" in summ and "nieprzerwanie od co najmniej" in summ, summ
    print(f"[OK] Podsumowanie sezonu z glebą: {summ}")

    # --- 5. Zaślepki i stare pliki wyników ---
    with tempfile.TemporaryDirectory() as tmp:
        cph = dict(cfg, MATRIX_SHOW_PLACEHOLDERS=True)
        mxp = signal_matrix(status, veg, cph, site_id)
        assert (mxp["flag"].loc["s1"] == "placeholder").all() and "w przygotowaniu" in matrix_html(mxp, cph)
        plot_signal_matrix(mxp, cph, os.path.join(tmp, "mx_ph.png"))
        vold = veg[veg["index"] != "ndre"].drop(columns=["track", "ref_mode"])
        stold = status.drop(columns=["sma_l1"])
        co = {c["index"]: c for c in condition_panel(vold, pd.DataFrame(), cfg, site_id, today=today,
                                                     status_row=stold.sort_values("date").iloc[-1])}
        assert co["ndre"]["cls"] == "not_computed", co["ndre"]["cls"]
        ho = s6._condition_html(list(co.values()), cfg, srow["date"])
        assert "niepoliczony" in ho and "scen, oba tory" not in ho and "krótka historia" not in ho, ho
        tro = season_trajectory(vold, era5, cfg, site_id)
        season_summary(tro), season_caption(tro, cfg)
        plot_season_trajectory(tro, cfg, os.path.join(tmp, "traj_old.png"))
        mxo = signal_matrix(stold, vold, cfg, site_id)
        assert (mxo["flag"].loc["ndre"] == "not_computed").all() and (mxo["flag"].loc["sma_l1"] == "missing").all()
        assert "niepoliczony" in matrix_html(mxo, cfg)
        plot_signal_matrix(mxo, cfg, os.path.join(tmp, "mx_old.png"))
    print("[OK] Zaślepki matrycy i stare pliki wyników (bez NDRE, track, ref_mode, sma_l1): panele bez błędu.")
