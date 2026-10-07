"""
================================================================================
AgriWatch - KROK 7: PIPELINE STACYJNY (JEDNA STACJA, END-TO-END)
================================================================================
Samodzielny potok dla jednej stacji ISMN (domyślnie SMOSMANIA / Condom):

  1. In situ     : odczyt plików ISMN (.stm) i kontrola jakości ponad flagi ISMN
                   (flaga G, zakres fizyczny, zamrożone wartości, okresy wykluczone,
                   segmenty czujników). Uzasadnienie: docs/evidence/Condom_QC.md
  2. Satelita    : serie czasowe w buforze wokół stacji pobierane z Google Earth Engine
                   (Sentinel-1 GRD, Sentinel-2 L2A + maska chmur z kroku 1, ERA5-Land),
                   z cache CSV na Dysku (kolejne uruchomienia pobierają tylko brakujące okresy).
  3. Wilgotność  : change detection Sentinel-1 per orbita względna
                   (odniesienia suche/mokre = percentyle w okresie kalibracji),
                   konwersja do m3/m3 przez porowatość z HWSD (niezależną od czujnika).
  4. Walidacja   : kolokacja z pomiarami in situ (+/- 60 min), metryki pytesmo
                   (R, rho, bias, RMSD, ubRMSD, R anomalii 35-dniowych) z 95% CI
                   z bootstrapu blokowego; benchmark ERA5-Land na tych samych datach;
                   wyniki per segment czujnika, okres i rok.
  5. Raport      : CSV, wykresy PNG i raport Markdown generowany wyłącznie z liczb.
  6. Rejestr     : wyniki jako wiersze tabel gwl_* (zapis przez step_05.run_task na Dysk Google).

Moduł nie zależy od kroków 2-5. Z kroku 1 używa tylko inicjalizacji GEE i maski chmur S2.

Punkty rozbudowy (kolejne wersje): OPTRAM z SEN2SR 2.5 m, LST (pyDMS), kolejne stacje,
wilgotność strefy korzeniowej (filtr wykładniczy), model ML.

Uruchomienie:
    from step_07_station_pipeline import run_station_pipeline
    results = run_station_pipeline({"PROJECT_DIR": PROJECT_DIR})

Test bez GEE (prawdziwe dane in situ + syntetyczne dane satelitarne):
    python step_07_station_pipeline.py --selftest
================================================================================
"""

from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger("AgriWatch_Station")

PIPELINE_VERSION = "0.2.0"

# ==============================================================================
# KONFIGURACJA STACJI
# ==============================================================================
# Ścieżki względne są liczone względem PROJECT_DIR. Nazwy kluczy nie kolidują z CONFIG z notatnika,
# więc można przekazać cały CONFIG notatnika: używane są tylko klucze znane temu modułowi.
STATION_CONFIG: Dict[str, Any] = {
    "PROJECT_DIR": ".",
    "NETWORK": "SMOSMANIA",
    "STATION": "Condom",
    "ISMN_DIR": "data/7_isismn_data",
    "STATION_OUTPUT_DIR": "data/08_Station_Validation",
    "GEE_PROJECT": "ee-geoworldlook",

    "START_DATE": "2016-01-01",
    "END_DATE": "2024-12-31",
    "DEPTH_M": 0.05,                 # warstwa powierzchniowa porównywalna z S-1
    "STATION_BUFFER_M": 50,          # promień bufora wokół stacji (S-1 wymaga wielu pikseli)

    # --- Kontrola jakości in situ (docs/evidence/Condom_QC.md) ---
    "SM_VALID_RANGE": (0.0, 0.60),   # m3/m3
    "STUCK_MIN_HOURS": 168,          # identyczna wartość przez >= 7 dni = zamrożony czujnik
    "EXCLUDE_PERIODS": [
        # (od, do, głębokość [m] lub None = wszystkie, powód)
        ("2019-02-06", "2019-02-21", 0.05, "QC-1: artefakt wymiany czujnika 5 cm (ML3 -> ML2x)"),
    ],
    "DAILY_MIN_HOURS": 18,           # minimalna liczba godzin do średniej dobowej

    # --- Sentinel-1 change detection ---
    "CD_CALIBRATION": ("2016-01-01", "2021-12-31"),
    "CD_PERCENTILES": (5, 95),
    "CD_MIN_OBS_PER_ORBIT": 30,
    "S1_MIN_PIXEL_FRACTION": 0.5,    # min. udział pikseli bufora z danymi
    "POROSITY": None,                # None = odczyt z HWSD (static_variables.csv)

    # --- Flagi ---
    "S2_MIN_CLEAR_FRACTION": 0.9,
    "NDVI_TOLERANCE_DAYS": 15,
    "NDVI_DENSE_VEGETATION": 0.7,
    "FROZEN_T2M_MIN_C": 0.0,

    # --- Walidacja ---
    "MATCH_TOLERANCE_MIN": 60,
    "ANOMALY_WINDOW_DAYS": 35,
    "TEST_PERIOD": ("2022-01-01", "2024-12-31"),
    "MIN_N_METRICS": 10,
    "BOOTSTRAP_N": 1000,
    "BOOTSTRAP_BLOCK_DAYS": 30,
    "RANDOM_SEED": 42,

    # --- Pobieranie z GEE (długość fragmentów zapytań w miesiącach) ---
    "CHUNK_MONTHS": {"s1": 12, "s2": 6, "era5": 12},
}


def build_config(overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Łączy konfigurację domyślną z nadpisaniami i rozwiązuje ścieżki względne."""
    cfg = dict(STATION_CONFIG)
    if overrides:
        cfg.update({k: v for k, v in overrides.items() if k in STATION_CONFIG})
    root = cfg["PROJECT_DIR"]
    for key in ("ISMN_DIR", "STATION_OUTPUT_DIR"):
        if not os.path.isabs(cfg[key]):
            cfg[key] = os.path.join(root, cfg[key])
    cfg["STATION_DIR"] = os.path.join(cfg["ISMN_DIR"], cfg["NETWORK"], cfg["STATION"])
    cfg["RUN_DIR"] = os.path.join(cfg["STATION_OUTPUT_DIR"], cfg["STATION"])
    cfg["CACHE_DIR"] = os.path.join(cfg["RUN_DIR"], "cache")
    return cfg


# ==============================================================================
# I. DANE IN SITU: ODCZYT ISMN I KONTROLA JAKOŚCI
# ==============================================================================

_STM_NAME = re.compile(r"_sm_(?P<dfrom>[0-9.]+)_(?P<dto>[0-9.]+)_(?P<sensor>.+?)_\d+_\d+_\d{8}_\d{8}\.stm$")


def read_ismn_stm(path: str) -> pd.DataFrame:
    """
    Czyta plik ISMN w formacie Header+values (.stm).
    Wiersz 1: nagłówek stacji; kolejne: 'YYYY/MM/DD HH:MM wartość flaga_ISMN flaga_źródła'.
    Zwraca DataFrame z indeksem czasu UTC oraz kolumnami: sm, flag, sensor, depth_from, depth_to.
    """
    m = _STM_NAME.search(os.path.basename(path))
    if m is None:
        raise ValueError(f"Nierozpoznana nazwa pliku ISMN: {os.path.basename(path)}")
    df = pd.read_csv(
        path, sep=r"\s+", skiprows=1, header=None,
        names=["date", "time", "sm", "flag", "origin"],
        dtype={"flag": str, "origin": str},
    )
    df.index = pd.to_datetime(df["date"] + " " + df["time"], format="%Y/%m/%d %H:%M")
    df.index.name = "time"
    out = df[["sm", "flag"]].copy()
    out["sensor"] = m.group("sensor")
    out["depth_from"] = float(m.group("dfrom"))
    out["depth_to"] = float(m.group("dto"))
    return out


def read_station_metadata(station_dir: str) -> Dict[str, Any]:
    """Odczytuje współrzędne (z nagłówka .stm) i porowatość HWSD (z static_variables.csv)."""
    stm_files = sorted(glob.glob(os.path.join(station_dir, "*_sm_*.stm")))
    if not stm_files:
        raise FileNotFoundError(f"Brak plików *_sm_*.stm w {station_dir}")
    with open(stm_files[0], "r", encoding="utf-8") as f:
        header = f.readline().split()
    meta: Dict[str, Any] = {"lat": float(header[3]), "lon": float(header[4]), "elevation_m": float(header[5])}

    static = glob.glob(os.path.join(station_dir, "*static_variables.csv"))
    meta["porosity_hwsd"] = None
    meta["land_cover"] = None
    if static:
        sv = pd.read_csv(static[0], sep=";")
        sat = sv[(sv["quantity_name"] == "saturation") & (sv["quantity_source_name"] == "HWSD")
                 & (sv["depth_from[m]"] == 0.0)]
        if not sat.empty:
            meta["porosity_hwsd"] = float(sat["value"].iloc[0])
        lc = sv[sv["quantity_name"] == "land cover classification"]
        if not lc.empty:
            meta["land_cover"] = str(lc["description"].iloc[-1])
    return meta


def load_insitu(cfg: Dict[str, Any]) -> pd.DataFrame:
    """Wczytuje wszystkie czujniki dla zadanej głębokości i nadaje identyfikatory segmentów."""
    files = sorted(glob.glob(os.path.join(cfg["STATION_DIR"], "*_sm_*.stm")))
    frames = [read_ismn_stm(p) for p in files]
    frames = [f for f in frames if np.isclose(f["depth_from"].iloc[0], cfg["DEPTH_M"])]
    if not frames:
        raise FileNotFoundError(f"Brak czujników na głębokości {cfg['DEPTH_M']} m w {cfg['STATION_DIR']}")

    # Segment = jeden czujnik; kolejność według początku pomiarów
    frames.sort(key=lambda f: f.index.min())
    for k, f in enumerate(frames, start=1):
        short = f["sensor"].iloc[0].replace("DeltaT-ThetaProbe-", "")
        f["segment"] = f"seg{k}_{short}"
    df = pd.concat(frames).sort_index()
    # Nakładające się znaczniki czasu przy wymianie czujnika: zostaje nowszy czujnik
    df = df[~df.index.duplicated(keep="last")]
    df = df.loc[cfg["START_DATE"]:pd.Timestamp(cfg["END_DATE"]) + pd.Timedelta(days=1)]
    logger.info(f"In situ: {len(df)} rekordów, segmenty: {df['segment'].unique().tolist()}")
    return df


def _stuck_mask(sm: pd.Series, min_hours: int) -> pd.Series:
    """Oznacza serie identycznych wartości trwające >= min_hours (zamrożony czujnik)."""
    s = sm.dropna()
    if s.empty:
        return pd.Series(False, index=sm.index)
    run_id = (s.diff() != 0).cumsum().to_numpy()
    t = s.index.to_series()
    grp = t.groupby(run_id)
    span_h = (grp.transform("max") - grp.transform("min")) / pd.Timedelta(hours=1)
    return (span_h >= min_hours).reindex(sm.index, fill_value=False)


def qc_insitu(df: pd.DataFrame, cfg: Dict[str, Any]) -> pd.DataFrame:
    """
    Kontrola jakości ponad flagi ISMN. Dodaje kolumny:
      qc_ok (bool) i qc_reason (pierwszy powód odrzucenia).
    Rekordy odrzucone nie są usuwane — raport pokazuje ich liczbę per powód.
    """
    out = df.copy()
    reason = pd.Series("", index=out.index, dtype=object)

    def mark(mask: pd.Series, code: str) -> None:
        nonlocal reason
        reason = reason.where(~(mask & (reason == "")), code)

    lo, hi = cfg["SM_VALID_RANGE"]
    mark(out["flag"] != "G", "FLAG_NOT_G")
    mark(out["sm"].isna() | (out["sm"] < lo) | (out["sm"] > hi), "OUT_OF_RANGE")
    for seg, g in out.groupby("segment"):
        mark(_stuck_mask(g["sm"], cfg["STUCK_MIN_HOURS"]).reindex(out.index, fill_value=False), "STUCK_VALUE")
    for start, end, depth, why in cfg["EXCLUDE_PERIODS"]:
        in_period = (out.index >= pd.Timestamp(start)) & (out.index < pd.Timestamp(end) + pd.Timedelta(days=1))
        depth_ok = np.ones(len(out), bool) if depth is None else np.isclose(out["depth_from"], depth)
        mark(pd.Series(in_period & depth_ok, index=out.index), "EXCLUDED_PERIOD")

    out["qc_reason"] = reason
    out["qc_ok"] = reason == ""
    summary = out["qc_reason"].replace("", "OK").value_counts()
    logger.info("QC in situ: " + ", ".join(f"{k}={v}" for k, v in summary.items()))
    return out


def insitu_daily(df_qc: pd.DataFrame, cfg: Dict[str, Any]) -> pd.DataFrame:
    """Średnie dobowe z rekordów qc_ok (min. DAILY_MIN_HOURS godzin) z segmentem dnia."""
    ok = df_qc[df_qc["qc_ok"]]
    g = ok.groupby(ok.index.floor("D"))
    daily = pd.DataFrame({"sm": g["sm"].mean(), "n_hours": g["sm"].count(), "segment": g["segment"].last()})
    daily = daily[daily["n_hours"] >= cfg["DAILY_MIN_HOURS"]]
    daily.index.name = "date"
    return daily


# ==============================================================================
# II. DANE SATELITARNE Z GOOGLE EARTH ENGINE (SERIE CZASOWE W BUFORZE STACJI)
# ==============================================================================

def _month_chunks(start: str, end: str, months: int) -> List[Tuple[pd.Timestamp, pd.Timestamp]]:
    """Dzieli [start, end] na przedziały [a, b) o długości `months` miesięcy."""
    chunks = []
    a = pd.Timestamp(start)
    stop = pd.Timestamp(end) + pd.Timedelta(days=1)
    while a < stop:
        b = min(a + pd.DateOffset(months=months), stop)
        chunks.append((a, b))
        a = b
    return chunks


def _cached_extract(
    cfg: Dict[str, Any],
    source: str,
    fetch: Callable[[str, str], pd.DataFrame],
) -> pd.DataFrame:
    """
    Pobiera dane fragmentami i zapisuje każdy fragment jako CSV w cache.
    Fragmenty zakończone ponad 7 dni temu są odczytywane z cache; bieżący jest pobierany ponownie.
    """
    os.makedirs(cfg["CACHE_DIR"], exist_ok=True)
    frames = []
    now = pd.Timestamp.now(tz="UTC").tz_localize(None)
    for a, b in _month_chunks(cfg["START_DATE"], cfg["END_DATE"], cfg["CHUNK_MONTHS"][source]):
        path = os.path.join(cfg["CACHE_DIR"], f"{source}_{a:%Y%m%d}_{b:%Y%m%d}.csv")
        final = b < now - pd.Timedelta(days=7)
        if final and os.path.exists(path):
            frames.append(pd.read_csv(path, parse_dates=["time"]))
            continue
        logger.info(f"GEE {source}: pobieranie {a:%Y-%m-%d} -> {b:%Y-%m-%d}...")
        df = fetch(f"{a:%Y-%m-%d}", f"{b:%Y-%m-%d}")
        df.to_csv(path, index=False)
        frames.append(df)
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame(columns=["time"])
    return pd.concat(frames, ignore_index=True).sort_values("time").reset_index(drop=True)


def _ee_init(cfg: Dict[str, Any]):
    """Inicjalizuje GEE przez funkcję z kroku 1 i zwraca moduł ee."""
    from step_01_ingest import initialize_earth_engine
    import ee
    initialize_earth_engine(project_id=cfg["GEE_PROJECT"])
    return ee


def _features_to_df(fc_info: Dict[str, Any]) -> pd.DataFrame:
    rows = [f["properties"] for f in fc_info.get("features", [])]
    return pd.DataFrame(rows)


def fetch_s1(ee, geom, start: str, end: str) -> pd.DataFrame:
    """
    Sentinel-1 GRD IW (VV+VH): średnia sigma0 w buforze liczona w skali liniowej
    (GEE dostarcza dB), liczba pikseli, kąt padania, orbita względna i kierunek.
    """
    col = (
        ee.ImageCollection("COPERNICUS/S1_GRD")
        .filterBounds(geom)
        .filterDate(start, end)
        .filter(ee.Filter.eq("instrumentMode", "IW"))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
    )

    def to_feature(img):
        lin = ee.Image(10).pow(img.select(["VV", "VH"]).divide(10))
        stats = lin.addBands(img.select("angle")).reduceRegion(
            reducer=ee.Reducer.mean().combine(ee.Reducer.count(), sharedInputs=True),
            geometry=geom, scale=10, maxPixels=1e7,
        )
        return ee.Feature(None, stats).set({
            "time_ms": img.get("system:time_start"),
            "rel_orbit": img.get("relativeOrbitNumber_start"),
            "pass": img.get("orbitProperties_pass"),
            "platform": img.get("platform_number"),
            "image_id": img.get("system:index"),
        })

    df = _features_to_df(ee.FeatureCollection(col.map(to_feature)).getInfo())
    if df.empty:
        return pd.DataFrame(columns=["time"])
    df["time"] = pd.to_datetime(df["time_ms"], unit="ms")
    df = df.rename(columns={"VV_mean": "vv_lin", "VH_mean": "vh_lin", "angle_mean": "angle", "VV_count": "n_px"})
    return df[["time", "vv_lin", "vh_lin", "angle", "n_px", "rel_orbit", "pass", "platform", "image_id"]]


def fetch_s2(ee, geom, start: str, end: str) -> pd.DataFrame:
    """
    Sentinel-2 L2A (harmonized) w buforze: udział pikseli bezchmurnych (maska chmur i cieni
    z kroku 1: s2cloudless + SCL + projekcja cieni), NDVI i STR (OPTRAM, z B12) dla pikseli czystych.
    """
    from step_01_ingest import add_cloud_and_shadow_mask

    s2 = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(geom).filterDate(start, end)
    cld = ee.ImageCollection("COPERNICUS/S2_CLOUD_PROBABILITY").filterBounds(geom).filterDate(start, end)
    joined = ee.ImageCollection(ee.Join.saveFirst("s2cloudless").apply(
        primary=s2, secondary=cld,
        condition=ee.Filter.equals(leftField="system:index", rightField="system:index"),
    ))

    def to_feature(img):
        clear = add_cloud_and_shadow_mask(img).select("cloudmask").Not().rename("clear")
        refl = img.select(["B4", "B8", "B11", "B12"]).divide(10000)
        ndvi = refl.normalizedDifference(["B8", "B4"]).rename("NDVI")
        b12 = refl.select("B12")
        str_swir = ee.Image(1).subtract(b12).pow(2).divide(b12.multiply(2)).rename("STR")
        clear_stats = clear.reduceRegion(ee.Reducer.mean(), geom, scale=10, maxPixels=1e7)
        veg_stats = ndvi.addBands(str_swir).updateMask(clear).reduceRegion(
            ee.Reducer.mean(), geom, scale=10, maxPixels=1e7)
        return ee.Feature(None, veg_stats).set({
            "clear_frac": clear_stats.get("clear"),
            "time_ms": img.get("system:time_start"),
            "image_id": img.get("system:index"),
        })

    df = _features_to_df(ee.FeatureCollection(joined.map(to_feature)).getInfo())
    if df.empty:
        return pd.DataFrame(columns=["time"])
    df["time"] = pd.to_datetime(df["time_ms"], unit="ms")
    df = df.rename(columns={"NDVI": "ndvi", "STR": "str"})
    for c in ("ndvi", "str", "clear_frac"):
        if c not in df:
            df[c] = np.nan
    return df[["time", "ndvi", "str", "clear_frac", "image_id"]]


def fetch_era5(ee, point, start: str, end: str) -> pd.DataFrame:
    """ERA5-Land w punkcie stacji (pobieranie: step_01.fetch_era5_land_daily); sm_era5 = warstwa 1 (0-7 cm)."""
    from step_01_ingest import fetch_era5_land_daily
    lon, lat = point.coordinates().getInfo()
    df = fetch_era5_land_daily(lat, lon, start, end)
    return df.rename(columns={"sm_l1": "sm_era5"})


def extract_satellite(cfg: Dict[str, Any], lat: float, lon: float) -> Dict[str, pd.DataFrame]:
    """Pobiera (lub czyta z cache) serie S-1, S-2 i ERA5-Land dla stacji."""
    ee = _ee_init(cfg)
    point = ee.Geometry.Point([lon, lat])
    geom = point.buffer(cfg["STATION_BUFFER_M"])
    return {
        "s1": _cached_extract(cfg, "s1", lambda a, b: fetch_s1(ee, geom, a, b)),
        "s2": _cached_extract(cfg, "s2", lambda a, b: fetch_s2(ee, geom, a, b)),
        "era5": _cached_extract(cfg, "era5", lambda a, b: fetch_era5(ee, point, a, b)),
    }


# ==============================================================================
# III. PRZYGOTOWANIE SERII SATELITARNYCH
# ==============================================================================

def prepare_s1(s1: pd.DataFrame, cfg: Dict[str, Any]) -> pd.DataFrame:
    """Konwersja do dB, filtr pokrycia bufora, usunięcie duplikatów (nakładające się sceny)."""
    df = s1.dropna(subset=["vv_lin", "rel_orbit"]).copy()
    expected_px = np.pi * cfg["STATION_BUFFER_M"] ** 2 / 100.0
    df = df[df["n_px"] >= cfg["S1_MIN_PIXEL_FRACTION"] * expected_px]
    df["vv_db"] = 10.0 * np.log10(df["vv_lin"])
    df["vh_db"] = 10.0 * np.log10(df["vh_lin"])
    df["rel_orbit"] = df["rel_orbit"].astype(int)
    # Ta sama akwizycja w dwóch sąsiednich scenach (slice'ach): dana orbita względna przelatuje
    # nad punktem najwyżej raz na dobę, więc klucz = doba + orbita; zostaje scena z większym pokryciem
    df["acq_key"] = df["time"].dt.floor("D").astype(str) + "_" + df["rel_orbit"].astype(str)
    df = df.sort_values("n_px", ascending=False).drop_duplicates("acq_key").sort_values("time")
    return df.drop(columns="acq_key").reset_index(drop=True)


def prepare_s2(s2: pd.DataFrame, cfg: Dict[str, Any]) -> pd.DataFrame:
    """Tylko sceny bezchmurne nad buforem; jedna wartość na dzień (sąsiednie kafle S2)."""
    df = s2.dropna(subset=["ndvi"]).copy()
    df = df[df["clear_frac"] >= cfg["S2_MIN_CLEAR_FRACTION"]]
    df["date"] = df["time"].dt.floor("D")
    df = df.groupby("date", as_index=False).agg(time=("time", "first"), ndvi=("ndvi", "mean"), str=("str", "mean"))
    return df.sort_values("time").reset_index(drop=True)


# ==============================================================================
# IV. WILGOTNOŚĆ Z SENTINEL-1: CHANGE DETECTION PER ORBITA
# ==============================================================================

def s1_change_detection(s1: pd.DataFrame, porosity: float, cfg: Dict[str, Any]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Change detection (TU Wien, Bauer-Marschallinger et al. 2019) w wersji per orbita względna:
      SM_rel = (sigma0_VV - sigma0_dry) / (sigma0_wet - sigma0_dry), przycięte do [0, 1]
      SM_vol = SM_rel * porowatość
    Odniesienia suche/mokre = percentyle VV [dB] w okresie kalibracji (tylko dane satelitarne,
    bez użycia pomiarów in situ). Każda orbita ma stały kąt padania w danym miejscu,
    więc osobne odniesienia per orbita zastępują normalizację kąta.
    """
    c0, c1 = pd.Timestamp(cfg["CD_CALIBRATION"][0]), pd.Timestamp(cfg["CD_CALIBRATION"][1]) + pd.Timedelta(days=1)
    p_lo, p_hi = cfg["CD_PERCENTILES"]
    refs, parts = [], []
    for orbit, g in s1.groupby("rel_orbit"):
        cal = g[(g["time"] >= c0) & (g["time"] < c1)]["vv_db"]
        ref = {"rel_orbit": int(orbit), "pass": g["pass"].mode().iat[0], "n_total": len(g), "n_calibration": len(cal),
               "angle_mean": float(g["angle"].mean())}
        if len(cal) < cfg["CD_MIN_OBS_PER_ORBIT"]:
            ref.update({"dry_db": np.nan, "wet_db": np.nan, "status": "SKIPPED_TOO_FEW_OBS"})
            refs.append(ref)
            continue
        dry, wet = np.percentile(cal, p_lo), np.percentile(cal, p_hi)
        ref.update({"dry_db": float(dry), "wet_db": float(wet), "status": "OK"})
        refs.append(ref)
        part = g.copy()
        part["sm_rel"] = np.clip((part["vv_db"] - dry) / (wet - dry), 0.0, 1.0)
        parts.append(part)
    refs_df = pd.DataFrame(refs)
    if not parts:
        raise RuntimeError("Żadna orbita nie ma wystarczającej liczby obserwacji w okresie kalibracji.")
    sm = pd.concat(parts).sort_values("time").reset_index(drop=True)
    sm["sm_s1"] = sm["sm_rel"] * porosity
    logger.info(f"Change detection: {len(sm)} obserwacji z {int((refs_df['status'] == 'OK').sum())} orbit.")
    return sm, refs_df


# ==============================================================================
# V. KOLOKACJA, FLAGI I ANOMALIE
# ==============================================================================

def _moving_anomaly(series: pd.Series, window_days: int, min_periods: int) -> pd.Series:
    """Anomalia krótkoterminowa: wartość minus wyśrodkowana średnia ruchoma (jak w QA4SM)."""
    s = series.dropna().sort_index()
    s = s[~s.index.duplicated(keep="first")]
    ma = s.rolling(f"{window_days}D", center=True, min_periods=min_periods).mean()
    return s - ma


def build_matchups(
    sm: pd.DataFrame,
    insitu_qc: pd.DataFrame,
    daily: pd.DataFrame,
    s2: pd.DataFrame,
    era5: pd.DataFrame,
    cfg: Dict[str, Any],
) -> pd.DataFrame:
    """Łączy obserwacje S-1 z in situ (+/- MATCH_TOLERANCE_MIN), NDVI, ERA5-Land i anomaliami."""
    w = cfg["ANOMALY_WINDOW_DAYS"]
    sat = sm[["time", "rel_orbit", "pass", "vv_db", "vh_db", "angle", "sm_rel", "sm_s1"]].sort_values("time").copy()

    # Anomalia satelitarna z całej serii S-1 (przed kolokacją)
    sat_anom = _moving_anomaly(sat.set_index("time")["sm_s1"], w, min_periods=3)
    sat["sm_s1_anom"] = sat["time"].map(sat_anom)

    # In situ: najbliższy pomiar godzinowy qc_ok
    ins = insitu_qc[insitu_qc["qc_ok"]][["sm", "segment"]].rename(columns={"sm": "sm_insitu"})
    ins = ins.reset_index().rename(columns={"time": "insitu_time"}).sort_values("insitu_time")
    mu = pd.merge_asof(sat, ins, left_on="time", right_on="insitu_time", direction="nearest",
                       tolerance=pd.Timedelta(minutes=cfg["MATCH_TOLERANCE_MIN"]))

    # Anomalia in situ: pomiar minus średnia ruchoma serii dobowej w dniu obserwacji
    ma_ins = daily["sm"].rolling(f"{w}D", center=True, min_periods=15).mean()
    mu["date"] = mu["time"].dt.floor("D")
    mu["sm_insitu_anom"] = mu["sm_insitu"] - mu["date"].map(ma_ins)

    # ERA5-Land dnia obserwacji (benchmark) i jego anomalia z serii dobowej
    if not era5.empty:
        e = era5.copy()
        e["date"] = e["time"].dt.floor("D")
        e = e.drop_duplicates("date").set_index("date")
        e_anom = _moving_anomaly(e["sm_era5"], w, min_periods=15)
        mu["sm_era5"] = mu["date"].map(e["sm_era5"])
        mu["sm_era5_anom"] = mu["date"].map(e_anom)
        mu["t2m_min_c"] = mu["date"].map(e["t2m_min_c"])
        mu["precip_prev_day_mm"] = mu["date"].map(e["precip_mm"].shift(1, freq="D"))
    else:
        for c in ("sm_era5", "sm_era5_anom", "t2m_min_c", "precip_prev_day_mm"):
            mu[c] = np.nan

    # NDVI z najbliższej bezchmurnej sceny S-2 (+/- NDVI_TOLERANCE_DAYS)
    if not s2.empty:
        nd = s2[["time", "ndvi"]].rename(columns={"time": "s2_time"}).sort_values("s2_time")
        mu = pd.merge_asof(mu.sort_values("time"), nd, left_on="time", right_on="s2_time", direction="nearest",
                           tolerance=pd.Timedelta(days=cfg["NDVI_TOLERANCE_DAYS"]))
    else:
        mu["ndvi"], mu["s2_time"] = np.nan, pd.NaT

    # Flagi (reason codes)
    def flags(r) -> str:
        f = []
        if pd.isna(r["ndvi"]):
            f.append("NO_NDVI")
        elif r["ndvi"] > cfg["NDVI_DENSE_VEGETATION"]:
            f.append("DENSE_VEGETATION")
        if pd.notna(r["t2m_min_c"]) and r["t2m_min_c"] < cfg["FROZEN_T2M_MIN_C"]:
            f.append("POSSIBLE_FROZEN")
        if pd.isna(r["sm_insitu"]):
            f.append("NO_INSITU_MATCH")
        return ";".join(f)

    mu["flags"] = mu.apply(flags, axis=1)
    t0, t1 = pd.Timestamp(cfg["TEST_PERIOD"][0]), pd.Timestamp(cfg["TEST_PERIOD"][1]) + pd.Timedelta(days=1)
    mu["period"] = np.where((mu["time"] >= t0) & (mu["time"] < t1), "test", "calibration")
    return mu.sort_values("time").reset_index(drop=True)


# ==============================================================================
# VI. METRYKI I WALIDACJA
# ==============================================================================

def _block_bootstrap_ci(
    times: pd.Series, x: np.ndarray, y: np.ndarray, func: Callable[[np.ndarray, np.ndarray], float], cfg: Dict[str, Any]
) -> Tuple[float, float]:
    """95% CI z bootstrapu blokowego (bloki kalendarzowe BOOTSTRAP_BLOCK_DAYS) — uwzględnia autokorelację."""
    rng = np.random.default_rng(cfg["RANDOM_SEED"])
    block = ((times - times.min()) / pd.Timedelta(days=cfg["BOOTSTRAP_BLOCK_DAYS"])).astype(int).to_numpy()
    uniq = np.unique(block)
    if len(uniq) < 5:
        return np.nan, np.nan
    idx_by_block = {b: np.flatnonzero(block == b) for b in uniq}
    stats = []
    for _ in range(cfg["BOOTSTRAP_N"]):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        idx = np.concatenate([idx_by_block[b] for b in pick])
        if len(idx) < 3:
            continue
        with np.errstate(all="ignore"):
            stats.append(func(x[idx], y[idx]))
    stats = np.asarray(stats, float)
    stats = stats[np.isfinite(stats)]
    if len(stats) < 50:
        return np.nan, np.nan
    return float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5))


def compute_metrics(df: pd.DataFrame, product: str, cfg: Dict[str, Any], with_ci: bool = True) -> Dict[str, Any]:
    """
    Metryki produktu vs in situ (pytesmo). Bias = produkt - in situ.
    R anomalii liczone na parach z dostępnymi anomaliami obu serii.
    """
    import pytesmo.metrics as pm

    res: Dict[str, Any] = {"product": product}
    d = df.dropna(subset=[product, "sm_insitu"])
    res["n"] = len(d)
    if len(d) < cfg["MIN_N_METRICS"]:
        res["note"] = f"n<{cfg['MIN_N_METRICS']}"
        return res
    x, y, t = d[product].to_numpy(float), d["sm_insitu"].to_numpy(float), d["time"]
    res["pearson_r"] = float(pm.pearson_r(x, y))
    if with_ci:
        res["pearson_r_ci"] = _block_bootstrap_ci(t, x, y, lambda a, b: np.corrcoef(a, b)[0, 1], cfg)
    res["spearman_rho"] = float(pm.spearman_r(x, y))
    res["bias"] = float(pm.bias(x, y))
    res["rmsd"] = float(pm.rmsd(x, y))
    res["ubrmsd"] = float(pm.ubrmsd(x, y))
    if with_ci:
        res["ubrmsd_ci"] = _block_bootstrap_ci(t, x, y, lambda a, b: float(np.std((a - a.mean()) - (b - b.mean()))), cfg)

    anom_col = f"{product}_anom"
    da = d.dropna(subset=[anom_col, "sm_insitu_anom"])
    res["n_anom"] = len(da)
    if len(da) >= cfg["MIN_N_METRICS"]:
        xa, ya = da[anom_col].to_numpy(float), da["sm_insitu_anom"].to_numpy(float)
        res["anomaly_r"] = float(pm.pearson_r(xa, ya))
        if with_ci:
            res["anomaly_r_ci"] = _block_bootstrap_ci(da["time"], xa, ya, lambda a, b: np.corrcoef(a, b)[0, 1], cfg)
    return res


PRODUCTS = {"sm_s1": "Sentinel-1 change detection (buffer)", "sm_era5": "ERA5-Land layer 1 (~9 km)"}


def evaluate(matchups: pd.DataFrame, cfg: Dict[str, Any]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Walidacja per segment czujnika x okres x podzbiór roślinności.
    Oba produkty oceniane na TYCH SAMYCH parach (uczciwe porównanie z benchmarkiem).
    Zwraca: tabelę główną i tabelę per rok.
    """
    base = matchups.dropna(subset=["sm_insitu", "sm_s1", "sm_era5"])
    base = base[~base["flags"].str.contains("POSSIBLE_FROZEN")]
    rows, yearly = [], []
    subsets = {
        "all": lambda d: d,
        "ndvi<=0.7": lambda d: d[~d["flags"].str.contains("DENSE_VEGETATION") & ~d["flags"].str.contains("NO_NDVI")],
    }
    for seg, dseg in base.groupby("segment"):
        for period in ("all", "calibration", "test"):
            dp = dseg if period == "all" else dseg[dseg["period"] == period]
            for sub_name, sub in subsets.items():
                ds = sub(dp)
                for prod, label in PRODUCTS.items():
                    m = compute_metrics(ds, prod, cfg)
                    m.update({"segment": seg, "period": period, "subset": sub_name, "product_label": label,
                              "date_from": ds["time"].min(), "date_to": ds["time"].max()})
                    rows.append(m)
        for year, dy in dseg.groupby(dseg["time"].dt.year):
            for prod, label in PRODUCTS.items():
                m = compute_metrics(dy, prod, cfg, with_ci=False)
                m.update({"segment": seg, "year": int(year), "product_label": label})
                yearly.append(m)
    return pd.DataFrame(rows), pd.DataFrame(yearly)


# ==============================================================================
# VII. WYKRESY I RAPORT
# ==============================================================================

def plot_results(daily: pd.DataFrame, matchups: pd.DataFrame, era5: pd.DataFrame, cfg: Dict[str, Any], out_png: str) -> str:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig = plt.figure(figsize=(16, 9))
    ax = fig.add_subplot(2, 1, 1)
    seg_colors = ["tab:blue", "tab:green", "tab:purple", "tab:cyan"]
    for k, (seg, g) in enumerate(daily.groupby("segment")):
        ax.plot(g.index, g["sm"], lw=0.9, c=seg_colors[k % len(seg_colors)],
                label=f"In situ {int(cfg['DEPTH_M']*100)} cm ({seg})")
    ok = matchups[~matchups["flags"].str.contains("DENSE_VEGETATION|POSSIBLE_FROZEN")]
    dense = matchups[matchups["flags"].str.contains("DENSE_VEGETATION")]
    ax.scatter(ok["time"], ok["sm_s1"], s=7, c="k", label="Sentinel-1 CD", zorder=3)
    ax.scatter(dense["time"], dense["sm_s1"], s=7, c="0.65", label="Sentinel-1 CD (NDVI>0.7)", zorder=2)
    if not era5.empty:
        ax.plot(era5["time"], era5["sm_era5"], lw=0.8, c="tab:orange", alpha=0.8, label="ERA5-Land L1")
    for start, end, depth, why in cfg["EXCLUDE_PERIODS"]:
        ax.axvspan(pd.Timestamp(start), pd.Timestamp(end), color="red", alpha=0.15)
    ax.set_ylabel("m³/m³")
    ax.set_title(f"{cfg['NETWORK']} {cfg['STATION']} — surface soil moisture: in situ vs Sentinel-1 vs ERA5-Land")
    ax.legend(ncol=3, fontsize=8, loc="upper right")

    base = matchups.dropna(subset=["sm_insitu", "sm_s1", "sm_era5"])
    for k, (prod, label) in enumerate(PRODUCTS.items()):
        a = fig.add_subplot(2, 3, 4 + k)
        for j, (seg, g) in enumerate(base.groupby("segment")):
            a.scatter(g["sm_insitu"], g[prod], s=6, alpha=0.6, c=seg_colors[j % len(seg_colors)], label=seg)
        lim = [0, max(0.55, float(np.nanmax(base[[prod, "sm_insitu"]].to_numpy())) if len(base) else 0.55)]
        a.plot(lim, lim, "k--", lw=0.8)
        a.set_xlim(lim); a.set_ylim(lim)
        a.set_xlabel("in situ [m³/m³]"); a.set_ylabel(f"{label.split(' (')[0]} [m³/m³]")
        a.set_title(label, fontsize=9); a.legend(fontsize=7)

    a = fig.add_subplot(2, 3, 6)
    da = base.dropna(subset=["sm_s1_anom", "sm_insitu_anom"])
    a.scatter(da["sm_insitu_anom"], da["sm_s1_anom"], s=6, alpha=0.6, c="k")
    a.axhline(0, c="0.6", lw=0.5); a.axvline(0, c="0.6", lw=0.5)
    a.set_xlabel("in situ anomaly (35 d)"); a.set_ylabel("S-1 anomaly (35 d)")
    a.set_title("Short-term anomalies", fontsize=9)
    fig.tight_layout()
    fig.savefig(out_png, dpi=130)
    plt.close(fig)
    return out_png


def _fmt(v: Any, nd: int = 3) -> str:
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "—"
    if isinstance(v, tuple):
        if any(not np.isfinite(x) for x in v):
            return "—"
        return f"[{v[0]:.{nd}f}, {v[1]:.{nd}f}]"
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    return f"{v:.{nd}f}"


def _fmt_int(v: Any) -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else str(int(v))


def _metrics_table(df: pd.DataFrame) -> str:
    cols = ["segment", "product_label", "n", "pearson_r", "pearson_r_ci", "spearman_rho", "bias", "ubrmsd",
            "ubrmsd_ci", "n_anom", "anomaly_r", "anomaly_r_ci"]
    head = "| Segment | Product | n | R | R 95% CI | ρ | Bias | ubRMSD | ubRMSD 95% CI | n anom | R anom | R anom 95% CI |"
    lines = [head, "|" + "---|" * len(cols)]
    for _, r in df[df["n"] > 0].iterrows():
        cells = []
        for c in cols:
            if c in ("segment", "product_label"):
                cells.append(str(r[c]))
            elif c in ("n", "n_anom"):
                cells.append(_fmt_int(r.get(c)))
            else:
                cells.append(_fmt(r.get(c)))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def write_report(
    cfg: Dict[str, Any], meta: Dict[str, Any], insitu_qc: pd.DataFrame, sat: Dict[str, pd.DataFrame],
    refs: pd.DataFrame, matchups: pd.DataFrame, metrics: pd.DataFrame, yearly: pd.DataFrame, png: str, out_md: str,
) -> str:
    """Raport Markdown (EN) generowany wyłącznie z wyliczonych wartości."""
    qc_counts = insitu_qc["qc_reason"].replace("", "OK").value_counts()
    main = metrics[(metrics["period"] == "all") & (metrics["subset"] == "all")]
    veg = metrics[(metrics["period"] == "all") & (metrics["subset"] == "ndvi<=0.7")]
    test = metrics[(metrics["period"] == "test") & (metrics["subset"] == "all")]

    def verdict(seg_df: pd.DataFrame) -> List[str]:
        out = []
        for seg, g in seg_df.groupby("segment"):
            s1 = g[g["product"] == "sm_s1"].iloc[0]
            e5 = g[g["product"] == "sm_era5"].iloc[0]
            for metric, label in (("anomaly_r", "short-term anomaly R"), ("pearson_r", "R")):
                a, b = s1.get(metric), e5.get(metric)
                if pd.notna(a) and pd.notna(b):
                    rel = "higher" if a > b else "lower"
                    out.append(f"- **{seg}**: Sentinel-1 {label} = {a:.2f} is {rel} than ERA5-Land ({b:.2f}) on the same {int(s1['n'])} pairs.")
        return out

    yr = yearly[yearly["product"] == "sm_s1"][["segment", "year", "n", "pearson_r", "ubrmsd", "anomaly_r"]]
    yr_lines = ["| Segment | Year | n | R | ubRMSD | R anom |", "|---|---|---|---|---|---|"]
    for _, r in yr.iterrows():
        yr_lines.append(f"| {r['segment']} | {int(r['year'])} | {_fmt_int(r['n'])} | {_fmt(r.get('pearson_r'))} | "
                        f"{_fmt(r.get('ubrmsd'))} | {_fmt(r.get('anomaly_r'))} |")

    ref_lines = ["| Rel. orbit | Pass | Mean incidence [°] | n total | n calibration | Dry [dB] | Wet [dB] | Status |",
                 "|---|---|---|---|---|---|---|---|"]
    for _, r in refs.iterrows():
        ref_lines.append(f"| {r['rel_orbit']} | {r['pass']} | {r['angle_mean']:.1f} | {r['n_total']} | {r['n_calibration']} | "
                         f"{_fmt(r['dry_db'], 2)} | {_fmt(r['wet_db'], 2)} | {r['status']} |")

    n_pairs = int(matchups["sm_insitu"].notna().sum())
    clip_dry = float((matchups["sm_rel"] <= 0.0).mean() * 100)
    clip_wet = float((matchups["sm_rel"] >= 1.0).mean() * 100)
    txt = f"""# Station validation report — {cfg['NETWORK']} / {cfg['STATION']}

Generated: {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC · pipeline `step_07_station_pipeline.py` v{PIPELINE_VERSION}

![results]({os.path.basename(png)})

## 1. Setup

| Item | Value |
|---|---|
| Station | {cfg['STATION']} ({meta['lat']:.4f} N, {meta['lon']:.4f} E, {meta['elevation_m']:.0f} m) |
| Land cover (ESA CCI) | {meta.get('land_cover') or '—'} |
| Reference depth | {cfg['DEPTH_M']*100:.0f} cm (ThetaProbe), hourly |
| Period | {cfg['START_DATE']} → {cfg['END_DATE']} |
| Satellite footprint | circular buffer r = {cfg['STATION_BUFFER_M']} m around the station |
| Porosity used for SM conversion | {meta['porosity_used']:.2f} m³/m³ ({meta['porosity_source']}) |
| Change-detection calibration | {cfg['CD_CALIBRATION'][0]} → {cfg['CD_CALIBRATION'][1]} (satellite data only) |
| Temporal matching | nearest in situ hour within ±{cfg['MATCH_TOLERANCE_MIN']} min of the S-1 acquisition |
| Anomalies | value minus centred {cfg['ANOMALY_WINDOW_DAYS']}-day moving average (QA4SM convention) |
| Confidence intervals | 95 %, moving-block bootstrap ({cfg['BOOTSTRAP_BLOCK_DAYS']}-day blocks, {cfg['BOOTSTRAP_N']} resamples) |

## 2. Data volume and quality control

- In situ records: {len(insitu_qc)}; QC outcome: {', '.join(f'{k} = {v}' for k, v in qc_counts.items())}.
- Sentinel-1 acquisitions used: {len(sat['s1'])}; clear-sky Sentinel-2 dates: {len(sat['s2'])}; ERA5-Land days: {len(sat['era5'])}.
- Matched S-1 / in situ pairs: {n_pairs}.
- Sentinel-1 retrievals clipped at the dry reference: {clip_dry:.1f} %; at the wet reference: {clip_wet:.1f} % (expected ≈ {cfg['CD_PERCENTILES'][0]} % each in the calibration period).
- Each in situ sensor is evaluated as a separate segment, because a sensor replacement can change the absolute level.
- Excluded periods: {'; '.join(f'{a} → {b} ({why})' for a, b, _, why in cfg['EXCLUDE_PERIODS']) or 'none'}.

### Sentinel-1 reference levels per relative orbit

{chr(10).join(ref_lines)}

## 3. Results — all matched pairs (frozen days excluded)

{_metrics_table(main)}

{chr(10).join(verdict(main))}

## 4. Results — low vegetation only (NDVI ≤ {cfg['NDVI_DENSE_VEGETATION']})

{_metrics_table(veg)}

## 5. Results — test period {cfg['TEST_PERIOD'][0]} → {cfg['TEST_PERIOD'][1]}

{_metrics_table(test)}

## 6. Sentinel-1 metrics per year

{chr(10).join(yr_lines)}

## 7. Interpretation limits

- One point sensor vs a {cfg['STATION_BUFFER_M']} m buffer: part of the disagreement is spatial representativeness, not retrieval error.
- Bias and RMSD depend on the in situ sensor calibration, which changed between segments; correlations and anomaly correlations are the primary metrics.
- Sentinel-1 senses roughly the top 1–5 cm; under dense vegetation (NDVI > {cfg['NDVI_DENSE_VEGETATION']}) the signal is dominated by the canopy.
- The station is in an open rainfed field; results do not transfer automatically to vineyards or orchards.
"""
    with open(out_md, "w", encoding="utf-8") as f:
        f.write(txt)
    return out_md


# ==============================================================================
# VIII. TABELE REJESTRU (schemat: step_05_colab_run.REGISTRY_SCHEMA)
# ==============================================================================
# Nazwy produktów w rejestrze:
#   ISMN      — in situ, średnia dobowa po QC (variable sm_5cm)
#   S1_GRD    — sigma0 VV/VH [dB] w obszarze stacji (dane surowe do ponownej kalibracji)
#   S1_CD_A   — wilgotność z change detection, wariant A (bazowy)
#   S2_L2A    — NDVI i STR (OPTRAM) ze scen bezchmurnych
#   ERA5L     — ERA5-Land: wilgotność warstwy 1, opad, T2m min

def _iso(t: pd.Series) -> pd.Series:
    return pd.to_datetime(t).dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def site_id(cfg: Dict[str, Any]) -> str:
    return f"{cfg['NETWORK']}_{cfg['STATION']}"


def calib_id(cfg: Dict[str, Any]) -> str:
    """Identyfikator zamrożonej kalibracji change detection (zmienia się tylko przy świadomej rekalibracji)."""
    c0, c1 = cfg["CD_CALIBRATION"]
    lo, hi = cfg["CD_PERCENTILES"]
    return f"S1CD_A_{c0[:4]}-{c1[:4]}_p{lo}-{hi}_b{cfg['STATION_BUFFER_M']}"


def _long(df: pd.DataFrame, sid: str, product: str, variables: Dict[str, str], time_col: str = "time",
          orbit_col: Optional[str] = None, n_px_col: Optional[str] = None, flags_col: Optional[str] = None,
          calib: str = "") -> pd.DataFrame:
    """Serie szerokie -> wiersze gwl_observations (jedna zmienna = jeden wiersz)."""
    parts = []
    for col, unit in variables.items():
        if col not in df.columns:
            continue
        d = df.dropna(subset=[col])
        if d.empty:
            continue
        parts.append(pd.DataFrame({
            "site_id": sid, "product": product, "variable": col, "time_utc": _iso(d[time_col]).to_numpy(),
            "orbit": d[orbit_col].astype(int).to_numpy() if orbit_col else 0,
            "value": d[col].astype(float).to_numpy(), "unit": unit,
            "n_pixels": d[n_px_col].to_numpy() if n_px_col else np.nan,
            "qc_flags": d[flags_col].fillna("").to_numpy() if flags_col else "",
            "calib_id": calib,
        }))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def registry_tables(
    cfg: Dict[str, Any], meta: Dict[str, Any], daily: pd.DataFrame, sat: Dict[str, pd.DataFrame],
    sm: pd.DataFrame, refs: pd.DataFrame, matchups: pd.DataFrame, metrics: pd.DataFrame, yearly: pd.DataFrame,
) -> Dict[str, pd.DataFrame]:
    """Zamienia wyniki potoku stacyjnego na wiersze tabel rejestru (bez run_id — nadaje go run_task)."""
    sid, cal = site_id(cfg), calib_id(cfg)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    depth_cm = int(round(cfg["DEPTH_M"] * 100))
    r = cfg["STATION_BUFFER_M"]

    sites = pd.DataFrame([{
        "site_id": sid, "site_type": "station", "name": cfg["STATION"], "network": cfg["NETWORK"],
        "land_use": meta.get("land_cover"), "lat": meta["lat"], "lon": meta["lon"],
        "geometry_wkt": f"POINT ({meta['lon']} {meta['lat']})", "footprint": f"buffer_{r}m",
        "area_m2": round(np.pi * r ** 2, 1), "source": "ISMN", "updated_at": now,
    }])

    # Flagi produktu S-1 (bez flagi walidacyjnej NO_INSITU_MATCH)
    fl = matchups[["time", "rel_orbit", "flags"]].copy()
    fl["flags"] = fl["flags"].str.split(";").map(lambda xs: ";".join(x for x in xs if x and x != "NO_INSITU_MATCH"))
    s1 = sm.merge(fl, on=["time", "rel_orbit"], how="left")

    ins = daily.reset_index().rename(columns={"date": "time", "sm": f"sm_{depth_cm}cm"})
    ins["segment"] = "segment=" + ins["segment"].astype(str)
    era5 = sat["era5"].rename(columns={"sm_era5": "sm_l1"})
    obs = pd.concat([
        _long(ins, sid, "ISMN", {f"sm_{depth_cm}cm": "m3/m3"}, flags_col="segment"),
        _long(sat["s1"], sid, "S1_GRD", {"vv_db": "dB", "vh_db": "dB", "angle": "deg"},
              orbit_col="rel_orbit", n_px_col="n_px"),
        _long(s1, sid, "S1_CD_A", {"sm_s1": "m3/m3", "sm_rel": "1"}, orbit_col="rel_orbit",
              n_px_col="n_px", flags_col="flags", calib=cal),
        _long(sat["s2"], sid, "S2_L2A", {"ndvi": "1", "str": "1"}),
        _long(era5, sid, "ERA5L", {"sm_l1": "m3/m3", "precip_mm": "mm", "t2m_min_c": "degC"}),
    ], ignore_index=True)
    obs["ingested_at"] = now

    # Kalibracja change detection per orbita + porowatość
    c0, c1 = cfg["CD_CALIBRATION"]
    cal_rows = [{"calib_id": cal, "site_id": sid, "product": "S1_CD_A", "orbit": 0, "param": "porosity",
                 "value": meta["porosity_used"], "period_start": c0, "period_end": c1}]
    for _, ref in refs.iterrows():
        for p in ("dry_db", "wet_db", "n_calibration", "angle_mean"):
            cal_rows.append({"calib_id": cal, "site_id": sid, "product": "S1_CD_A", "orbit": int(ref["rel_orbit"]),
                             "param": p, "value": ref[p], "period_start": c0, "period_end": c1})
    calibrations = pd.DataFrame(cal_rows)

    # Metryki: tabela główna + per rok (period = year_YYYY), format długi
    product_names = {"sm_s1": "S1_CD_A", "sm_era5": "ERA5L"}
    metric_defs = [("pearson_r", "pearson_r_ci", "n"), ("spearman_rho", None, "n"), ("bias", None, "n"),
                   ("rmsd", None, "n"), ("ubrmsd", "ubrmsd_ci", "n"), ("anomaly_r", "anomaly_r_ci", "n_anom")]
    yearly = yearly.assign(period="year_" + yearly["year"].astype(str), subset="all") if len(yearly) else yearly
    mrows = []
    for _, row in pd.concat([metrics, yearly], ignore_index=True).iterrows():
        for metric, ci_col, n_col in metric_defs:
            v = row.get(metric)
            if v is None or pd.isna(v):
                continue
            ci = row.get(ci_col) if ci_col else None
            ci = ci if isinstance(ci, tuple) else (np.nan, np.nan)
            mrows.append({
                "site_id": sid, "product": product_names.get(row["product"], row["product"]),
                "reference": f"ISMN_sm_{depth_cm}cm", "segment": row["segment"], "period": row["period"],
                "subset": row["subset"], "metric": metric, "value": float(v), "ci_low": ci[0], "ci_high": ci[1],
                "n": row.get(n_col), "date_from": row.get("date_from"), "date_to": row.get("date_to"),
            })
    vm = pd.DataFrame(mrows)
    for c in ("date_from", "date_to"):
        if c in vm:
            vm[c] = pd.to_datetime(vm[c]).dt.strftime("%Y-%m-%d")

    return {"gwl_sites": sites, "gwl_observations": obs, "gwl_calibrations": calibrations,
            "gwl_validation_metrics": vm}


# ==============================================================================
# IX. GŁÓWNA FUNKCJA: run_station_pipeline
# ==============================================================================

def run_station_pipeline(
    config: Optional[Dict[str, Any]] = None,
    satellite_data: Optional[Dict[str, pd.DataFrame]] = None,
) -> Dict[str, Any]:
    """
    Uruchamia cały potok stacyjny. Każdy etap zapisuje wynik w RUN_DIR:
      insitu_qc.csv, s1_sm.csv, s1_orbit_refs.csv, matchups.csv, metrics.csv, metrics_yearly.csv,
      station_results.png, station_report.md, run_manifest.json

    satellite_data: opcjonalnie gotowe serie {"s1", "s2", "era5"} (np. testy bez GEE);
                    domyślnie pobierane z GEE z cache.
    """
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    cfg = build_config(config)
    os.makedirs(cfg["RUN_DIR"], exist_ok=True)
    logger.info(f"=== PIPELINE STACYJNY {cfg['NETWORK']}/{cfg['STATION']} (v{PIPELINE_VERSION}) ===")

    # 1. In situ + QC
    meta = read_station_metadata(cfg["STATION_DIR"])
    if cfg["POROSITY"] is not None:
        meta["porosity_used"], meta["porosity_source"] = float(cfg["POROSITY"]), "config"
    elif meta["porosity_hwsd"] is not None:
        meta["porosity_used"], meta["porosity_source"] = meta["porosity_hwsd"], "HWSD v1.1, 0–30 cm"
    else:
        raise ValueError("Brak porowatości w static_variables.csv — ustaw POROSITY w konfiguracji.")
    insitu = qc_insitu(load_insitu(cfg), cfg)
    daily = insitu_daily(insitu, cfg)
    insitu.to_csv(os.path.join(cfg["RUN_DIR"], "insitu_qc.csv"))

    # 2. Satelita
    raw = satellite_data if satellite_data is not None else extract_satellite(cfg, meta["lat"], meta["lon"])
    sat = {"s1": prepare_s1(raw["s1"], cfg), "s2": prepare_s2(raw["s2"], cfg), "era5": raw["era5"]}
    if sat["s1"].empty:
        raise RuntimeError("Brak obserwacji Sentinel-1 dla stacji.")

    # 3. Wilgotność S-1
    sm, refs = s1_change_detection(sat["s1"], meta["porosity_used"], cfg)
    sm.to_csv(os.path.join(cfg["RUN_DIR"], "s1_sm.csv"), index=False)
    refs.to_csv(os.path.join(cfg["RUN_DIR"], "s1_orbit_refs.csv"), index=False)

    # 4. Kolokacja i walidacja
    matchups = build_matchups(sm, insitu, daily, sat["s2"], sat["era5"], cfg)
    matchups.to_csv(os.path.join(cfg["RUN_DIR"], "matchups.csv"), index=False)
    metrics, yearly = evaluate(matchups, cfg)
    metrics.to_csv(os.path.join(cfg["RUN_DIR"], "metrics.csv"), index=False)
    yearly.to_csv(os.path.join(cfg["RUN_DIR"], "metrics_yearly.csv"), index=False)

    # 5. Raport
    png = plot_results(daily, matchups, sat["era5"], cfg, os.path.join(cfg["RUN_DIR"], "station_results.png"))
    md = write_report(cfg, meta, insitu, sat, refs, matchups, metrics, yearly, png,
                      os.path.join(cfg["RUN_DIR"], "station_report.md"))

    manifest = {
        "pipeline_version": PIPELINE_VERSION,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "station": f"{cfg['NETWORK']}/{cfg['STATION']}",
        "satellite_source": "provided" if satellite_data is not None else "GEE",
        "n_s1": len(sat["s1"]), "n_s2_clear": len(sat["s2"]), "n_era5_days": len(sat["era5"]),
        "n_matchups": int(matchups["sm_insitu"].notna().sum()),
        "config": {k: v for k, v in cfg.items() if k not in ("CACHE_DIR",)},
    }
    with open(os.path.join(cfg["RUN_DIR"], "run_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, default=str)

    logger.info(f"Raport: {md}")
    return {"config": cfg, "metrics": metrics, "metrics_yearly": yearly, "matchups": matchups,
            "orbit_refs": refs, "report_path": md, "plot_path": png, "run_dir": cfg["RUN_DIR"],
            "pipeline_version": PIPELINE_VERSION,
            "registry": registry_tables(cfg, meta, daily, sat, sm, refs, matchups, metrics, yearly)}


# ==============================================================================
# IX-b. WALIDACJA ANOMALII PRODUKTU MONITORINGU (krok 4) NA PROFILU GLEBOWYM CONDOM
# ==============================================================================
# Zasady (Gruber i in. 2020; protokół CEOS LPV; QA4SM):
#  - walidujemy ANOMALIE (klimatologiczne i krótkoterminowe 35 dni), nie wartości bezwzględne,
#  - klimatologia porównywanych serii z tego samego, wspólnego okresu (2016-2024),
#  - każda metryka z 95% CI (bootstrap blokowy, autokorelacja) i liczbą par,
#  - 5 cm: tylko anomalie krótkoterminowe w obrębie segmentu czujnika (zmiana ML3 -> ML2x w 2019),
#  - strefa korzeni: średnia 20 i 30 cm (jeden czujnik ML3 przez cały okres).

def insitu_daily_depth(depth_m: float, overrides: Dict[str, Any]) -> pd.DataFrame:
    """Średnie dobowe po QC dla jednej głębokości (kolumny: sm, segment)."""
    c = build_config({**overrides, "DEPTH_M": depth_m})
    return insitu_daily(qc_insitu(load_insitu(c), c), c)


def _r_with_ci(t: pd.Series, x: np.ndarray, y: np.ndarray, cfg: Dict[str, Any]) -> Tuple[float, float, float]:
    if len(x) < cfg["MIN_N_METRICS"]:
        return np.nan, np.nan, np.nan
    r = float(np.corrcoef(x, y)[0, 1])
    lo, hi = _block_bootstrap_ci(t.reset_index(drop=True), x, y, lambda a, b: np.corrcoef(a, b)[0, 1], cfg)
    return r, lo, hi


def validate_anomalies(
    era5_daily: pd.DataFrame, veg: pd.DataFrame, status: pd.DataFrame, overrides: Dict[str, Any],
    monitor_cfg: Dict[str, Any], vineyard_ids: List[str],
) -> pd.DataFrame:
    """
    Zwraca wiersze gwl_validation_metrics (bez run_id):
      1. ERA5-Land 0-7 cm vs czujnik 5 cm — R anomalii 35 dni (per segment czujnika),
      2. ERA5-Land 0-100 cm vs czujniki 20-30 cm — R anomalii klimatologicznych i 35-dniowych,
      3. anomalia NDVI/NDMI S-2 (10 m i SR 2,5 m; stacja i winnica) vs anomalia 20-30 cm w dniu sceny,
      4. wykrywanie susz: dekady z SMA <= -1 (produkt) vs dekady z anomalią 20-30 cm <= -1 (POD, FAR).
    """
    from step_04_metrics_alert import clim_anomaly, rootzone

    cfg = build_config(overrides)
    sid = site_id(cfg)
    common = (cfg["START_DATE"], cfg["END_DATE"])
    hw = monitor_cfg["CLIM_HALF_WINDOW_DAYS"]
    rows: List[Dict[str, Any]] = []

    def add(product, reference, kind, footprint, metric, value, lo, hi, n, d0=None, d1=None):
        rows.append({"site_id": sid, "product": product, "reference": reference, "segment": kind,
                     "period": f"{common[0][:4]}-{common[1][:4]}", "subset": footprint, "metric": metric,
                     "value": value, "ci_low": lo, "ci_high": hi, "n": n,
                     "date_from": d0, "date_to": d1})

    e = era5_daily.set_index(pd.to_datetime(era5_daily["time"]).dt.floor("D")).sort_index()
    e = e[~e.index.duplicated(keep="last")].loc[common[0]:common[1]]
    era_l1, era_rz = e["sm_l1"], rootzone(e)

    # In situ
    d05 = insitu_daily_depth(0.05, overrides)
    d20 = insitu_daily_depth(0.20, overrides)["sm"]
    d30 = insitu_daily_depth(0.30, overrides)["sm"]
    rz = pd.concat([d20, d30], axis=1).dropna().mean(axis=1)

    # 1. 0-7 cm vs 5 cm: anomalie 35 dni w obrębie segmentu
    for seg, g in d05.groupby("segment"):
        a_ins = _moving_anomaly(g["sm"], cfg["ANOMALY_WINDOW_DAYS"], 15)
        a_era = _moving_anomaly(era_l1, cfg["ANOMALY_WINDOW_DAYS"], 15)
        p = pd.concat([a_ins.rename("y"), a_era.rename("x")], axis=1).dropna()
        r, lo, hi = _r_with_ci(pd.Series(p.index), p["x"].to_numpy(), p["y"].to_numpy(), cfg)
        add("ERA5L_SM_L1", f"ISMN_5cm_{seg}", "anomaly_35d", "ERA5 cell", "pearson_r", r, lo, hi, len(p),
            p.index.min(), p.index.max())

    # 2. 0-100 cm vs 20-30 cm: anomalie klimatologiczne (wspólny okres) i 35 dni
    ins_z = clim_anomaly(rz, common, hw, min_n=20)["z"]
    era_z = clim_anomaly(era_rz, common, hw, min_n=20)["z"]
    for kind, x_s, y_s in (("anomaly_clim", era_z, ins_z),
                           ("anomaly_35d", _moving_anomaly(era_rz, cfg["ANOMALY_WINDOW_DAYS"], 15),
                            _moving_anomaly(rz, cfg["ANOMALY_WINDOW_DAYS"], 15))):
        p = pd.concat([x_s.rename("x"), y_s.rename("y")], axis=1).dropna()
        r, lo, hi = _r_with_ci(pd.Series(p.index), p["x"].to_numpy(), p["y"].to_numpy(), cfg)
        add("ERA5L_SM_RZ", "ISMN_20_30cm", kind, "ERA5 cell", "pearson_r", r, lo, hi, len(p), p.index.min(), p.index.max())

    # 3. Roślinność S-2 vs anomalia 20-30 cm w dniu sceny (sezon wegetacyjny)
    #    anomaly_clim        — wszystkie sceny danego produktu,
    #    anomaly_clim_paired — tylko dni, w których są oba produkty (10 m i SR 2,5 m): porównanie 10 m vs SR
    #                          na tych samych scenach (SR liczony jest partiami, więc obejmuje krótszy okres).
    if len(veg):
        foot = {f"{sid}_poly": "station plot", sid: f"station buffer {cfg['STATION_BUFFER_M']} m",
                **{v: f"vineyard {v} (indirect, 136 m)" for v in vineyard_ids}}
        days: Dict[Tuple[str, str, str], pd.Series] = {}
        for (site, prod, idx), g in veg.groupby(["site_id", "product", "index"]):
            if site not in foot:
                continue
            g = g.dropna(subset=["z"]).copy()
            g["day"] = g["time"].dt.floor("D")
            days[(site, prod, idx)] = g.set_index("day")["z"].groupby(level=0).mean()

        def add_veg(site, prod, idx, z, kind):
            p = z.to_frame("x").join(ins_z.rename("y")).dropna()
            r, lo, hi = _r_with_ci(pd.Series(p.index), p["x"].to_numpy(), p["y"].to_numpy(), cfg)
            add(f"{prod}_{idx.upper()}", "ISMN_20_30cm", kind, foot[site], "pearson_r", r, lo, hi, len(p),
                p.index.min() if len(p) else None, p.index.max() if len(p) else None)

        for (site, prod, idx), z in days.items():
            add_veg(site, prod, idx, z, "anomaly_clim")
        for (site, prod, idx), z_sr in days.items():
            z10 = days.get((site, "S2_10m", idx))
            if prod != "S2SR_2.5m" or z10 is None:
                continue
            common_days = z10.index.intersection(z_sr.index)
            if len(common_days):
                add_veg(site, "S2_10m", idx, z10.loc[common_days], "anomaly_clim_paired")
                add_veg(site, prod, idx, z_sr.loc[common_days], "anomaly_clim_paired")

    # 4. Wykrywanie susz w dekadach (SMA produktu vs anomalia 20-30 cm)
    if len(status):
        st = status.drop_duplicates("date").copy()
        st["date"] = pd.to_datetime(st["date"])
        ins_dk = ins_z.groupby(ins_z.index.to_period("D").to_timestamp()).mean()
        from step_04_metrics_alert import dekad_end
        tmp = pd.DataFrame({"z": ins_dk.to_numpy(), "dk": dekad_end(pd.Series(ins_dk.index)).to_numpy()})
        ins_by_dk = tmp.groupby("dk")["z"].mean()
        j = st.set_index("date").join(ins_by_dk.rename("ins_z"), how="inner").dropna(subset=["ins_z", "sma_rz"])
        obs = j["ins_z"] <= monitor_cfg["THR_SMA"]
        prd = j["sma_rz"] <= monitor_cfg["THR_SMA"]
        hits, misses, fa = int((obs & prd).sum()), int((obs & ~prd).sum()), int((~obs & prd).sum())
        pod = hits / (hits + misses) if hits + misses else np.nan
        far = fa / (hits + fa) if hits + fa else np.nan
        add("ERA5L_SM_RZ<=-1", "ISMN_20_30cm<=-1", "events_dekad", "ERA5 cell", "pod", pod, np.nan, np.nan, len(j))
        add("ERA5L_SM_RZ<=-1", "ISMN_20_30cm<=-1", "events_dekad", "ERA5 cell", "far", far, np.nan, np.nan, len(j))

    out = pd.DataFrame(rows)
    for c in ("date_from", "date_to"):
        out[c] = pd.to_datetime(out[c]).dt.strftime("%Y-%m-%d")
    return out


# ==============================================================================
# X. TEST BEZ GEE: PRAWDZIWE DANE IN SITU + SYNTETYCZNE SERIE SATELITARNE
# ==============================================================================

def _synthetic_satellite_data(cfg: Dict[str, Any], seed: int = 0) -> Dict[str, pd.DataFrame]:
    """
    Syntetyczne serie o schemacie identycznym z pobieraniem z GEE (tylko do testów).
    S-1: 3 orbity co 6 dni, sigma0 zależne liniowo od wilgotności in situ + szum;
    S-2: NDVI sezonowe; ERA5: wygładzona wilgotność in situ + szum.
    """
    rng = np.random.default_rng(seed)
    ins = qc_insitu(load_insitu(cfg), cfg)
    daily = insitu_daily(ins, cfg)["sm"]
    days = pd.date_range(cfg["START_DATE"], cfg["END_DATE"], freq="D")
    truth = daily.reindex(days).interpolate(limit_direction="both")
    s1_rows = []
    for orbit, hour, offset, first in ((30, 6.1, 0.0, 0), (132, 17.8, 1.5, 2), (59, 6.2, -1.0, 4)):
        for d in days[first::6]:
            sm_true = truth.loc[d]
            vv_db = -17.0 + offset + 18.0 * sm_true + rng.normal(0, 0.8)
            vh_db = vv_db - 6.0 + rng.normal(0, 0.5)
            s1_rows.append({"time": d + pd.Timedelta(hours=hour), "vv_lin": 10 ** (vv_db / 10), "vh_lin": 10 ** (vh_db / 10),
                            "angle": 38.0 + offset, "n_px": 78, "rel_orbit": orbit,
                            "pass": "DESCENDING" if hour < 12 else "ASCENDING", "platform": "A", "image_id": f"syn_{orbit}_{d:%Y%m%d}"})
    doy = days.dayofyear.to_numpy()
    ndvi = 0.45 + 0.3 * np.sin(2 * np.pi * (doy - 80) / 365.0)
    s2 = pd.DataFrame({"time": days + pd.Timedelta(hours=10.8), "ndvi": ndvi, "str": 2.0, "clear_frac": 1.0, "image_id": "syn"})
    s2 = s2.iloc[::5]
    era5 = pd.DataFrame({"time": days, "sm_era5": truth.rolling(5, center=True, min_periods=1).mean().to_numpy() * 0.9 + 0.05
                         + rng.normal(0, 0.02, len(days)), "precip_mm": 0.0, "t2m_min_c": 5.0, "t2m_c": 12.0})
    return {"s1": pd.DataFrame(s1_rows), "s2": s2, "era5": era5}


def _selftest(out_dir: str) -> None:
    import shutil
    from step_05_colab_run import run_task, registry_read

    overrides = {"PROJECT_DIR": os.path.dirname(os.path.abspath(__file__)), "STATION_OUTPUT_DIR": out_dir,
                 "BOOTSTRAP_N": 200}
    reg_dir = os.path.join(out_dir, "_selftest_registry")
    shutil.rmtree(reg_dir, ignore_errors=True)
    rt = {"REGISTRY_DIR": reg_dir, "GIT_COMMIT": "selftest"}
    res = run_task(rt, "selftest_station", run_station_pipeline, overrides,
                   satellite_data=_synthetic_satellite_data(build_config(overrides)), raise_errors=True)

    # Rejestr: pierwsze uruchomienie dopisuje wiersze, powtórzenie tych samych danych nie dopisuje nic
    obs = registry_read(rt, "gwl_observations")
    assert set(obs["product"]) == {"ISMN", "S1_GRD", "S1_CD_A", "S2_L2A", "ERA5L"}, set(obs["product"])
    assert len(registry_read(rt, "gwl_validation_metrics")) > 0
    run_task(rt, "selftest_repeat", lambda: res, raise_errors=True)
    assert len(registry_read(rt, "gwl_observations")) == len(obs), "Powtórzenie zmieniło liczbę wierszy"
    runs = registry_read(rt, "gwl_runs").sort_values("started_at")
    assert list(runs["status"]) == ["ok", "ok"] and int(runs["n_new_rows"].iat[-1]) == 0, runs.to_string()
    print(f"[OK] Rejestr: {len(obs)} obserwacji; powtórne uruchomienie: 0 nowych wierszy.")

    m = res["metrics"]
    s1 = m[(m["product"] == "sm_s1") & (m["period"] == "all") & (m["subset"] == "all")]
    assert len(s1) >= 2, "Oczekiwano >= 2 segmentów czujnika 5 cm"
    assert (s1["n"] > 100).all(), "Za mało par w segmentach"
    assert (s1["pearson_r"] > 0.7).all(), f"Syntetyczny sygnał powinien dawać wysokie R: {s1['pearson_r'].tolist()}"
    for p in (res["report_path"], res["plot_path"]):
        assert os.path.exists(p), p
    print("[OK] Selftest zakończony. Wyniki:", res["run_dir"])
    print(s1[["segment", "n", "pearson_r", "ubrmsd", "anomaly_r"]].round(3).to_string(index=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Pipeline stacyjny (jedna stacja ISMN)")
    ap.add_argument("--selftest", action="store_true", help="test bez GEE na syntetycznych danych satelitarnych")
    ap.add_argument("--out", default="data/08_Station_Validation", help="katalog wyników")
    ap.add_argument("--project-dir", default=os.path.dirname(os.path.abspath(__file__)))
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    if args.selftest:
        _selftest(args.out)
    else:
        run_station_pipeline({"PROJECT_DIR": args.project_dir, "STATION_OUTPUT_DIR": args.out})
