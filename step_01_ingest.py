"""
================================================================================
AgriWatch - KROK 1: POBIERANIE DANYCH (GOOGLE EARTH ENGINE)
================================================================================
  - Sentinel-2 L2A (COPERNICUS/S2_SR_HARMONIZED) od 2016 r., przyrostowo z manifestem JSON:
    10 pasm reflektancji [0, 1] (L2A / 10 000; pasma 20 m próbkowane do 10 m) + maska chmur + SCL,
  - maska chmur: s2cloudless + SCL + geometryczna projekcja cieni,
  - ERA5-Land: dzienne serie w punkcie (wilgotność 3 warstw, opad, temperatura), z cache CSV,
  - odczyt i zapis GeoTIFF.

Używają go step_05 (zadania ingest_s2, ingest_era5, scene_stats) i step_07 (GEE, maska chmur, ERA5).
Poprzednia wersja (AgriScreen v2.5: LST, CDSE SWI/HR-VPP, DEM, statystyki wieloletnie w GEE):
legacy/step_01_ingest_v1.py.
================================================================================
"""

from __future__ import annotations

import glob
import json
import logging
import os
import random
import time
import warnings
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import rasterio

logger = logging.getLogger("AgriWatch_Ingest")

warnings.filterwarnings("ignore")
logging.getLogger("rasterio").setLevel(logging.ERROR)
logging.getLogger("googleapiclient.http").setLevel(logging.ERROR)
os.environ['CPL_LOG'] = '/dev/null'

try:
    import ee
    import geemap
except ImportError:
    logger.warning("Brak wymaganych bibliotek: earthengine-api lub geemap w bieżącym środowisku.")
    logger.warning("Zainstaluj je poleceniem: pip install earthengine-api geemap rasterio")
    ee = None
    geemap = None

# Stałe spektralne
REQUIRED_S2_BANDS = ["B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B11", "B12"]
REFLECTANCE_SCALE_FACTOR = 10000.0  # BOA L2A integer -> [0.0, 1.0]


# ==============================================================================
# I. POMOCNICZE FUNKCJE GEOREFERENCYJNE I AOI
# ==============================================================================

def load_aoi_geometry(
    geojson_path: str,
    buffer_m: int = 0
) -> Tuple[ee.Geometry, Dict[str, float], int]:
    """
    Wczytuje wektor AOI z pliku GeoJSON, wyznacza obwiednię, punkt centralny,
    odpowiednią strefę UTM (EPSG) oraz zwraca geometrię Earth Engine.
    Obsługuje zarówno pojedynczy zasięg bufora (MultiPolygon), jak i kolekcję działek.
    """
    if not os.path.exists(geojson_path):
        raise FileNotFoundError(f"Nie znaleziono pliku AOI: {geojson_path}")

    with open(geojson_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    features = data.get("features", [])
    if not features:
        raise ValueError(f"Plik GeoJSON {geojson_path} nie zawiera obiektów 'features'.")

    # Bezpośrednie wczytanie geometrii do Earth Engine
    try:
        ee_fc = ee.FeatureCollection(data)
        combined_geom = ee_fc.geometry()
        if buffer_m > 0:
            combined_geom = combined_geom.buffer(buffer_m)
    except Exception as ee_err:
        logger.warning(f"FeatureCollection fallback: {ee_err}. Konstruowanie geometrii z elementów.")
        geoms = [ee.Geometry(feat["geometry"]) for feat in features if "geometry" in feat]
        combined_geom = ee.Geometry.MultiPolygon([g.coordinates() for g in geoms]) if len(geoms) > 1 else geoms[0]
        if buffer_m > 0:
            combined_geom = combined_geom.buffer(buffer_m)

    # Wyznaczenie współrzędnych obwiedni w WGS84
    bounds_info = combined_geom.bounds().getInfo()
    coords = bounds_info["coordinates"][0]
    lons = [pt[0] for pt in coords]
    lats = [pt[1] for pt in coords]

    min_lon, max_lon = min(lons), max(lons)
    min_lat, max_lat = min(lats), max(lats)
    center_lon = (min_lon + max_lon) / 2.0
    center_lat = (min_lat + max_lat) / 2.0

    # Wyznaczenie strefy UTM (WGS84 UTM Zone)
    utm_zone = int((center_lon + 180) // 6) + 1
    epsg_code = 32600 + utm_zone if center_lat >= 0 else 32700 + utm_zone

    bbox_dict = {
        "min_lon": min_lon, "min_lat": min_lat,
        "max_lon": max_lon, "max_lat": max_lat,
        "center_lon": center_lon, "center_lat": center_lat
    }

    logger.info(
        f"Wczytano AOI: {len(features)} obiektów z {os.path.basename(geojson_path)}. "
        f"Środek: ({center_lat:.4f}, {center_lon:.4f}). Docelowy układ UTM: EPSG:{epsg_code}, bufor: {buffer_m}m"
    )
    return combined_geom, bbox_dict, epsg_code


def initialize_earth_engine(project_id: Optional[str] = "ee-geoworldlook") -> None:
    """
    Inicjalizuje połączenie z Google Earth Engine z automatyczną obsługą uwierzytelnienia i projektu.
    """
    if ee is None:
        raise ImportError("Biblioteka 'earthengine-api' nie jest zainstalowana. Uruchom: pip install earthengine-api geemap")
    
    if not project_id:
        project_id = os.environ.get("EE_PROJECT", "ee-geoworldlook")

    try:
        ee.Initialize(project=project_id)
        logger.info(f"Pomyślnie zainicjalizowano Google Earth Engine (projekt: {project_id}).")
    except Exception as e:
        logger.warning(f"Inicjalizacja GEE z projektem {project_id} wymaga autoryzacji ({e}). Uruchamianie procedury autoryzacji...")
        try:
            ee.Authenticate()
            ee.Initialize(project=project_id)
            logger.info(f"Pomyślnie uwierzytelniono i zainicjalizowano GEE (projekt: {project_id}).")
        except Exception as auth_err:
            logger.error(f"Krytyczny błąd autoryzacji Google Earth Engine: {auth_err}")
            raise


# ==============================================================================
# II. MASKOWANIE CHMUR I PRZETWARZANIE SENTINEL-2 W GEE
# ==============================================================================

def get_s2_sr_cld_collection(
    aoi: ee.Geometry,
    start_date: str,
    end_date: str,
    cloud_thresh: int = 90
) -> ee.ImageCollection:
    """
    Buduje kolekcję Sentinel-2 L2A (SR Harmonized) złączoną z kolekcją prawdopodobieństwa
    chmur s2cloudless (COPERNICUS/S2_CLOUD_PROBABILITY).
    Oblicza średnie zachmurzenie s2cloudless wyłącznie nad obwiednią działek AOI
    i przypisuje je do właściwości 'AOI_CLOUD_PERCENTAGE'.
    """
    s2_sr_col = (
        ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
        .filterBounds(aoi)
        .filterDate(start_date, end_date)
        .filter(ee.Filter.lte('CLOUDY_PIXEL_PERCENTAGE', cloud_thresh))
    )

    s2_cloudless_col = (
        ee.ImageCollection('COPERNICUS/S2_CLOUD_PROBABILITY')
        .filterBounds(aoi)
        .filterDate(start_date, end_date)
    )

    joined = ee.ImageCollection(
        ee.Join.saveFirst('s2cloudless').apply(
            primary=s2_sr_col,
            secondary=s2_cloudless_col,
            condition=ee.Filter.equals(
                leftField='system:index',
                rightField='system:index'
            )
        )
    )

    def compute_aoi_cloud(img: ee.Image) -> ee.Image:
        cld = ee.Image(img.get('s2cloudless'))
        cld_prob = cld.select('probability')
        stats = cld_prob.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=aoi,
            scale=20,
            maxPixels=1e6
        )
        val = ee.Algorithms.If(stats.contains('probability'), stats.get('probability'), 100.0)
        return img.set('AOI_CLOUD_PERCENTAGE', val)

    return joined.map(compute_aoi_cloud)


def add_cloud_and_shadow_mask(img: ee.Image) -> ee.Image:
    """
    Tworzy precyzyjną maskę chmur i cieni chmur za pomocą prawdopodobieństwa s2cloudless,
    warstwy SCL (Scene Classification Layer) oraz geometrycznej projekcji cieni.
    """
    # 1. Prawdopodobieństwo chmur s2cloudless
    cld_prb = ee.Image(img.get('s2cloudless')).select('probability')
    is_cloud = cld_prb.gt(40).rename('clouds')

    # 2. Filtracja warstwy klasyfikacji sceny SCL (L2A):
    # 1=Defective/Saturated, 3=Cloud Shadow, 8=Cloud Medium, 9=Cloud High, 10=Cirrus, 11=Snow
    scl = img.select('SCL')
    scl_mask = (
        scl.eq(1)
        .Or(scl.eq(3))
        .Or(scl.eq(8))
        .Or(scl.eq(9))
        .Or(scl.eq(10))
        .Or(scl.eq(11))
    ).rename('scl_invalid')

    # 3. Geometryczna projekcja cieni chmur (wektor kąta słońca)
    dark_pixels = img.select('B8').lt(0.15 * REFLECTANCE_SCALE_FACTOR).rename('dark_pixels')
    solar_azimuth = ee.Number(img.get('MEAN_SOLAR_AZIMUTH_ANGLE'))
    shadow_azimuth = ee.Number(90).subtract(solar_azimuth)

    cld_proj = (
        is_cloud.directionalDistanceTransform(shadow_azimuth, 30)
        .reproject(crs=img.select('B8').projection(), scale=20)
        .select('distance')
        .mask()
        .rename('cloud_transform')
    )
    geometric_shadows = cld_proj.multiply(dark_pixels).rename('geometric_shadows')

    # Łączna maska niepożądanych pikseli (1 = chmura/cień/błąd, 0 = czysty piksel)
    combined_mask = is_cloud.Or(scl_mask).Or(geometric_shadows).rename('cloudmask')
    return img.addBands(combined_mask)


def prepare_s2_scaled_image(img: ee.Image) -> ee.Image:
    """
    Przeskalowuje kanały Sentinel-2 BOA do zakresu fizycznego [0.0, 1.0],
    zmienia nazwy pasm na standardowe i nakłada maskę jakościową.
    """
    img_with_mask = add_cloud_and_shadow_mask(img)
    cloudmask = img_with_mask.select('cloudmask')

    # Wybór i przeskalowanie pasm 10m i 20m
    scaled_bands = (
        img.select(['B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B8A', 'B11', 'B12'])
        .divide(REFLECTANCE_SCALE_FACTOR)
        .select(
            ['B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B8A', 'B11', 'B12'],
            REQUIRED_S2_BANDS
        )
    )

    # Dołączenie maski chmur oraz surowego SCL
    return (
        scaled_bands
        .addBands(cloudmask)
        .addBands(img.select('SCL').rename('SCL'))
        .set('system:time_start', img.get('system:time_start'))
        .set('system:index', img.get('system:index'))
    )


# ==============================================================================
# III. POBIERANIE RASTROWE (ROBUST DOWNLOAD Z EXPONENTIAL BACKOFF)
# ==============================================================================

def export_image_robust(
    image: ee.Image,
    path: str,
    region: ee.Geometry,
    scale: float = 10.0,
    crs: str = 'EPSG:32631',
    max_retries: int = 5
) -> bool:
    """
    Pobiera raster z GEE z mechanizmem ponawiania prób (Exponential Backoff).
    Sprawdza, czy plik już istnieje i jest nieuszkodzony.
    """
    if os.path.exists(path) and os.path.getsize(path) > 1024:
        logger.info(f"Plik już istnieje na dysku: {os.path.basename(path)} (pomijanie pobierania).")
        return True

    os.makedirs(os.path.dirname(path), exist_ok=True)
    wait_time = 4.0

    for attempt in range(max_retries):
        try:
            logger.info(f"Rozpoczynanie pobierania -> {os.path.basename(path)} (skala={scale}m, CRS={crs}, próba {attempt+1}/{max_retries})...")
            geemap.download_ee_image(
                image=image,
                filename=path,
                scale=scale,
                region=region,
                crs=crs,
                overwrite=True,
                num_threads=4
            )
            if os.path.exists(path) and os.path.getsize(path) > 1024:
                logger.info(f"Pomyślnie pobrano: {os.path.basename(path)} ({os.path.getsize(path)/1024:.1f} KB)")
                return True
            else:
                raise IOError("Pobrany plik jest pusty lub uszkodzony.")
        except Exception as e:
            if attempt < max_retries - 1:
                sleep_seconds = wait_time * (2 ** attempt) + random.uniform(1.0, 3.0)
                logger.warning(f"Błąd pobierania ({e}). Czekam {sleep_seconds:.1f}s przed ponowną próbą...")
                time.sleep(sleep_seconds)
            else:
                logger.error(f"Nie udało się pobrać pliku po {max_retries} próbach: {os.path.basename(path)}")
                return False
    return False


def read_geotiff_to_numpy(path: str) -> Tuple[np.ndarray, Dict[str, Any]]:
    """
    Wczytuje wielokanałowy plik GeoTIFF do tablicy NumPy float32 wraz z profilem Rasterio.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Nie znaleziono pliku GeoTIFF: {path}")

    with rasterio.open(path) as src:
        data = src.read().astype(np.float32)
        profile = src.profile.copy()
        if src.nodata is not None:
            data[data == src.nodata] = np.nan
        # Zamiana wartości inf na nan
        data[np.isinf(data)] = np.nan

    return data, profile


def write_geotiff(data: np.ndarray, profile: Dict[str, Any], path: str, nodata: float = np.nan) -> str:
    """Zapisuje tablicę (H, W) lub (C, H, W) jako GeoTIFF float32 z kompresją (kafle 256)."""
    arr = data[np.newaxis] if data.ndim == 2 else data
    prof = profile.copy()
    prof.update(driver="GTiff", count=arr.shape[0], height=arr.shape[1], width=arr.shape[2],
                dtype="float32", nodata=nodata, compress="deflate", tiled=True, blockxsize=256, blockysize=256)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with rasterio.open(path, "w", **prof) as dst:
        dst.write(arr.astype(np.float32))
    return path


# ==============================================================================
# IV. ERA5-LAND: DZIENNE SERIE W PUNKCIE (WILGOTNOŚĆ 3 WARSTW, OPAD, TEMPERATURA)
# ==============================================================================
# Całe AOI mieści się w jednym oczku ERA5-Land (~9 km), więc pobieramy serię punktową, nie raster.
# Warstwy CHTESSEL: 1 = 0-7 cm, 2 = 7-28 cm, 3 = 28-100 cm (Muñoz-Sabater i in. 2021, ESSD 13:4349).

ERA5_LAND_BANDS = {
    "volumetric_soil_water_layer_1": "sm_l1",
    "volumetric_soil_water_layer_2": "sm_l2",
    "volumetric_soil_water_layer_3": "sm_l3",
    "total_precipitation_sum": "precip_mm",
    "temperature_2m_min": "t2m_min_c",
    "temperature_2m": "t2m_c",
    "temperature_2m_max": "t2m_max_c",
}


def fetch_era5_land_daily(lat: float, lon: float, start: str, end: str) -> "pd.DataFrame":
    """ERA5-Land DAILY_AGGR (GEE) w punkcie [start, end): wilgotność 3 warstw [m3/m3], opad [mm], T, Tmin, Tmax [°C]."""
    import pandas as pd
    col = ee.ImageCollection("ECMWF/ERA5_LAND/DAILY_AGGR").filterDate(start, end).select(list(ERA5_LAND_BANDS))
    rows = col.getRegion(ee.Geometry.Point([lon, lat]), 11132).getInfo()
    if len(rows) <= 1:
        return pd.DataFrame(columns=["time"] + list(ERA5_LAND_BANDS.values()))
    df = pd.DataFrame(rows[1:], columns=rows[0])
    out = pd.DataFrame({"time": pd.to_datetime(df["time"], unit="ms")})
    for band, name in ERA5_LAND_BANDS.items():
        v = pd.to_numeric(df[band], errors="coerce")
        if name == "precip_mm":
            v = v * 1000.0
        elif name.startswith("t2m"):
            v = v - 273.15
        out[name] = v.to_numpy()
    return out.sort_values("time").reset_index(drop=True)


def sync_era5_land_point(
    lat: float, lon: float, start: str, end: str, cache_dir: str, chunk_months: int = 12,
    refetch_days: int = 120,
) -> "pd.DataFrame":
    """
    Przyrostowe pobieranie ERA5-Land do cache CSV (jeden plik na fragment).
    Fragmenty kończące się ponad `refetch_days` dni temu są czytane z cache; nowsze są pobierane ponownie,
    bo ERA5-Land dochodzi z opóźnieniem (wersja wstępna ~5 dni, finalna 2-3 miesiące).
    """
    import pandas as pd
    os.makedirs(cache_dir, exist_ok=True)
    now = pd.Timestamp.now(tz="UTC").tz_localize(None)
    a, stop = pd.Timestamp(start), pd.Timestamp(end) + pd.Timedelta(days=1)
    frames = []
    while a < stop:
        b = min(a + pd.DateOffset(months=chunk_months), stop)
        path = os.path.join(cache_dir, f"era5land_{a:%Y%m%d}_{b:%Y%m%d}.csv")
        cached = pd.read_csv(path, parse_dates=["time"]) if os.path.exists(path) else None
        # fragment z cache bez którejś zmiennej (np. dodanej później Tmax) jest pobierany ponownie
        if (cached is not None and b < now - pd.Timedelta(days=refetch_days)
                and set(ERA5_LAND_BANDS.values()) <= set(cached.columns)):
            frames.append(cached)
        else:
            logger.info(f"ERA5-Land: pobieranie {a:%Y-%m-%d} -> {b:%Y-%m-%d}")
            df = fetch_era5_land_daily(lat, lon, f"{a:%Y-%m-%d}", f"{b:%Y-%m-%d}")
            df.to_csv(path, index=False)
            # bieżący fragment kończy się "jutro", więc co dzień ma inną nazwę: starsze wersje są zbędne
            for old in glob.glob(os.path.join(cache_dir, f"era5land_{a:%Y%m%d}_*.csv")):
                if os.path.abspath(old) != os.path.abspath(path):
                    os.remove(old)
            frames.append(df)
        a = b
    frames = [f for f in frames if not f.empty]
    if not frames:
        raise RuntimeError("ERA5-Land: brak danych w zadanym okresie.")
    out = pd.concat(frames, ignore_index=True).drop_duplicates("time").sort_values("time").reset_index(drop=True)
    logger.info(f"ERA5-Land: {len(out)} dni, {out['time'].min():%Y-%m-%d} -> {out['time'].max():%Y-%m-%d}")
    return out


# ==============================================================================
# IV-b. KLUCZE Z DYSKU I SATELITARNY SOIL WATER INDEX 1 km (CLMS) — SONDA DOSTĘPU (Plan v9 W3a)
# ==============================================================================
# Klucze tylko z folderu SECRETS_DIR na Dysku (MyDrive/GeoWorldLook/secrets), plik KEY=VALUE `cdse.env`.
# Treść kluczy nigdy nie trafia do logów, rejestru ani raportów (D-074): secrets_status podaje tylko nazwy plików
# i nazwy pól. Sonda sprawdza dostęp do SWI 1 km przez Copernicus Data Space (Sentinel Hub Statistical API, D-078)
# na jednym miesiącu dla piksela winnicy — bez analizy; pełne pobieranie powstaje po wyniku sondy.
# Metoda: docs/evidence/W3a_SWI_1km_satelita.md. Adresy jak w ETL strony GeoWorldLook (scripts/backfill_copernicus.py).

CDSE_TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
CDSE_STATS_URL = "https://sh.dataspace.copernicus.eu/api/v1/statistics"
CDSE_CATALOG_URL = "https://sh.dataspace.copernicus.eu/api/v1/catalog/1.0.0/collections"
SWI_COLLECTION = "byoc-bd02588b-7236-4b1e-9480-aeae7dce3c7a"   # z legacy/step_01_ingest_v1.py — potwierdza sonda
SWI_BANDS = ("SWI002", "SWI005", "SWI010", "SWI015", "SWI020", "SWI040", "SWI060", "SWI100")
SWI_SCALE = 0.5                                                 # pasmo × 0,5 = % nasycenia (legacy) — potwierdza sonda


def read_secret_env(secrets_dir: str, filename: str = "cdse.env") -> Dict[str, str]:
    """Plik KEY=VALUE z folderu kluczy (komentarze #, cudzysłowy zdejmowane). Zwraca słownik — nie wypisywać."""
    path = os.path.join(secrets_dir, filename)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Brak pliku z kluczami: {path}")
    out: Dict[str, str] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def secrets_status(secrets_dir: str) -> Dict[str, Any]:
    """Co jest w folderze kluczy: nazwy plików i — dla plików .env — nazwy pól. Bez wartości (bezpieczne do wypisania)."""
    if not os.path.isdir(secrets_dir):
        return {"folder": secrets_dir, "exists": False}
    files = sorted(os.listdir(secrets_dir))
    fields = {}
    for name in files:
        if name.endswith(".env"):
            try:
                fields[name] = sorted(read_secret_env(secrets_dir, name))
            except Exception as e:
                fields[name] = f"nieczytelny ({type(e).__name__})"
    return {"folder": secrets_dir, "exists": True, "files": files, "env_fields": fields}


def cdse_token(secrets_dir: str, session: Any = None, timeout: int = 30) -> str:
    """Token OAuth2 Copernicus Data Space (client credentials) z `cdse.env` (CDSE_CLIENT_ID/SECRET lub
    COPERNICUS_CLIENT_ID/SECRET jak w ETL strony). Błąd podaje tylko kod HTTP i kod błędu serwera."""
    import requests
    s = session or requests
    env = read_secret_env(secrets_dir)
    cid = env.get("CDSE_CLIENT_ID") or env.get("COPERNICUS_CLIENT_ID")
    sec = env.get("CDSE_CLIENT_SECRET") or env.get("COPERNICUS_CLIENT_SECRET")
    if not (cid and sec):
        raise ValueError("W cdse.env brakuje CDSE_CLIENT_ID lub CDSE_CLIENT_SECRET")
    r = s.post(CDSE_TOKEN_URL, data={"grant_type": "client_credentials", "client_id": cid, "client_secret": sec},
               timeout=timeout)
    if r.status_code != 200:
        try:
            code = r.json().get("error", "")
        except Exception:
            code = ""
        raise RuntimeError(f"CDSE: logowanie nieudane (HTTP {r.status_code} {code})")
    return r.json()["access_token"]


def _swi_evalscript(bands: Tuple[str, ...] = SWI_BANDS, scale: float = SWI_SCALE) -> str:
    vals = ", ".join(f"s.{b} * {scale}" for b in bands)
    return ("//VERSION=3\nfunction setup() {\n  return {input: [{bands: [" + ", ".join(f'"{b}"' for b in bands)
            + ', "dataMask"]}],\n          output: [{id: "swi", bands: ' + str(len(bands))
            + ', sampleType: "FLOAT32"}, {id: "dataMask", bands: 1}]};\n}\n'
            "function evaluatePixel(s) {\n  return {swi: [" + vals + "], dataMask: [s.dataMask]};\n}\n")


def parse_swi_stats(js: Dict[str, Any], bands: Tuple[str, ...] = SWI_BANDS) -> "pd.DataFrame":
    """Odpowiedź Statistical API -> dzienna tabela: date, swi002…swi100 (średnia w obszarze), n_valid."""
    import pandas as pd
    rows = []
    for entry in js.get("data", []):
        out = entry.get("outputs", {}).get("swi", {}).get("bands", {})
        if not out:
            continue
        row = {"date": pd.Timestamp(entry["interval"]["from"][:10])}
        n_valid = None
        for i, b in enumerate(bands):
            st = out.get(f"B{i}", {}).get("stats", {})
            row[b.lower()] = st.get("mean", np.nan) if st.get("sampleCount", 0) > st.get("noDataCount", 0) else np.nan
            if n_valid is None and st:
                n_valid = int(st.get("sampleCount", 0) - st.get("noDataCount", 0))
        row["n_valid"] = n_valid if n_valid is not None else 0
        rows.append(row)
    cols = ["date"] + [b.lower() for b in bands] + ["n_valid"]
    return pd.DataFrame(rows, columns=cols).sort_values("date").reset_index(drop=True) if rows else pd.DataFrame(columns=cols)


def fetch_swi_point(token: str, lat: float, lon: float, start: str, end: str, half_deg: float = 0.0045,
                    collection: str = SWI_COLLECTION, session: Any = None, timeout: int = 120) -> "pd.DataFrame":
    """Dzienny SWI (8 wartości T) dla piksela ~1 km wokół punktu (bbox ±half_deg w EPSG:4326, 1 × 1 piksel wyjścia)."""
    import requests
    s = session or requests
    payload = {
        "input": {"bounds": {"bbox": [lon - half_deg, lat - half_deg, lon + half_deg, lat + half_deg],
                             "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"}},
                  "data": [{"type": collection}]},
        "aggregation": {"timeRange": {"from": f"{start}T00:00:00Z", "to": f"{end}T23:59:59Z"},
                        "aggregationInterval": {"of": "P1D"}, "width": 1, "height": 1,
                        "evalscript": _swi_evalscript()},
    }
    r = s.post(CDSE_STATS_URL, json=payload, headers={"Authorization": f"Bearer {token}"}, timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"CDSE Statistical API: HTTP {r.status_code}: {r.text[:300]}")
    return parse_swi_stats(r.json())


def probe_swi(secrets_dir: str, lat: float, lon: float, days: int = 31, session: Any = None) -> Dict[str, Any]:
    """
    Sonda dostępu do SWI 1 km (jednorazowo, bez analizy): klucze w folderze (tylko nazwy), logowanie, kolekcje
    w katalogu z „swi”/„soil water” w nazwie, dzienny SWI z ostatnich `days` dni dla piksela winnicy (liczba dni,
    zakres dat, zakres wartości — czy skala 0–100). Każdy etap ma własny wynik; błąd jednego nie ukrywa pozostałych.
    """
    import pandas as pd
    import requests
    s = session or requests
    res: Dict[str, Any] = {"secrets": secrets_status(secrets_dir), "collection": SWI_COLLECTION}
    try:
        token = cdse_token(secrets_dir, session=s)
        res["login"] = "ok"
    except Exception as e:
        res["login"] = f"błąd: {type(e).__name__}: {e}"
        return res
    try:
        r = s.get(CDSE_CATALOG_URL, headers={"Authorization": f"Bearer {token}"}, timeout=60)
        cols = r.json().get("collections", []) if r.status_code == 200 else []
        res["catalog"] = ([{"id": c.get("id"), "title": c.get("title")} for c in cols
                           if any(k in f"{c.get('id', '')} {c.get('title', '')}".lower()
                                  for k in ("swi", "soil water", "soil moisture"))]
                          if r.status_code == 200 else f"HTTP {r.status_code}")
    except Exception as e:
        res["catalog"] = f"błąd: {type(e).__name__}: {e}"
    end = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
    start = end - pd.Timedelta(days=days)
    try:
        df = fetch_swi_point(token, lat, lon, f"{start:%Y-%m-%d}", f"{end:%Y-%m-%d}", session=s)
        vals = df[[b.lower() for b in SWI_BANDS]].to_numpy(float) if len(df) else np.array([])
        fin = vals[np.isfinite(vals)] if vals.size else vals
        res["stats"] = {"days_with_data": int(df.dropna(subset=["swi020"]).shape[0]) if len(df) else 0,
                        "first": str(df["date"].min().date()) if len(df) else None,
                        "last": str(df["date"].max().date()) if len(df) else None,
                        "min": float(fin.min()) if fin.size else None, "max": float(fin.max()) if fin.size else None,
                        "scale_0_100": bool(fin.size and fin.min() >= 0 and fin.max() <= 100)}
        res["sample"] = df.tail(5).round(2).astype({"date": str}).to_dict("records") if len(df) else []
    except Exception as e:
        res["stats"] = f"błąd: {type(e).__name__}: {e}"
    return res


def _selftest_swi() -> None:
    """Klucze z pliku (komentarze, cudzysłowy, nazwy pól bez wartości), parsowanie odpowiedzi Statistical API
    i przebieg sondy na atrapie sieci (logowanie, katalog, statystyki)."""
    import tempfile
    import pandas as pd

    class Resp:
        def __init__(self, code, js):
            self.status_code, self._js, self.text = code, js, json.dumps(js)

        def json(self):
            return self._js

    def stats_js(days):
        data = []
        for i, d in enumerate(days):
            bands = {f"B{k}": {"stats": {"mean": 40.0 + k + i, "sampleCount": 1, "noDataCount": 0}} for k in range(8)}
            data.append({"interval": {"from": f"{d}T00:00:00Z", "to": f"{d}T23:59:59Z"},
                         "outputs": {"swi": {"bands": bands}}})
        return {"data": data}

    class FakeSession:
        def post(self, url, data=None, json=None, headers=None, timeout=None):
            if url == CDSE_TOKEN_URL:
                ok = data["client_id"] == "abc" and data["client_secret"] == "s3cr3t"
                return Resp(200, {"access_token": "T"}) if ok else Resp(401, {"error": "unauthorized_client"})
            assert headers["Authorization"] == "Bearer T" and json["input"]["data"][0]["type"] == SWI_COLLECTION
            return Resp(200, stats_js(["2026-10-01", "2026-10-02"]))

        def get(self, url, headers=None, timeout=None):
            return Resp(200, {"collections": [{"id": SWI_COLLECTION, "title": "CLMS Soil Water Index 1km"},
                                              {"id": "sentinel-2-l2a", "title": "Sentinel-2 L2A"}]})

    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "cdse.env"), "w") as f:
            f.write('# klucze\nCDSE_CLIENT_ID="abc"\nCDSE_CLIENT_SECRET=s3cr3t\n')
        st = secrets_status(d)
        assert st["env_fields"]["cdse.env"] == ["CDSE_CLIENT_ID", "CDSE_CLIENT_SECRET"] and "s3cr3t" not in str(st), st
        res = probe_swi(d, 43.97, 0.34, session=FakeSession())
        assert res["login"] == "ok" and res["catalog"] == [{"id": SWI_COLLECTION, "title": "CLMS Soil Water Index 1km"}]
        assert res["stats"]["days_with_data"] == 2 and res["stats"]["scale_0_100"] and "s3cr3t" not in str(res), res
        with open(os.path.join(d, "cdse.env"), "w") as f:
            f.write("CDSE_CLIENT_ID=abc\nCDSE_CLIENT_SECRET=zle\n")
        bad = probe_swi(d, 43.97, 0.34, session=FakeSession())
        assert bad["login"].startswith("błąd") and "401" in bad["login"] and "zle" not in str(bad), bad
    df = parse_swi_stats(stats_js(["2026-10-02", "2026-10-01"]))
    assert list(df["date"]) == [pd.Timestamp("2026-10-01"), pd.Timestamp("2026-10-02")] and df["swi020"].iat[0] == 45.0
    print("[OK] Klucze z Dysku i sonda SWI: pola bez wartości, logowanie, katalog, parsowanie odpowiedzi.")


# ==============================================================================
# V. SYNCHRONIZACJA PRZYROSTOWA SENTINEL-2 (INCREMENTAL SYNC 2016-DZIŚ)
# ==============================================================================

def sync_sentinel2_time_series(
    aoi: ee.Geometry,
    start_year: int = 2016,
    end_year: Optional[int] = None,
    output_dir: str = "data/01_Raw_Sentinel2",
    manifest_path: str = "data/00_Metadata/ingest_manifest.json",
    cloud_thresh: int = 40,
    epsg_code: int = 32631,
    max_scenes_per_year: Optional[int] = None,
    months: Optional[Tuple[int, int]] = None
) -> List[Dict[str, Any]]:
    """
    Pobiera wszystkie dostępne bezchmurne zobrazowania Sentinel-2 od 2016 roku do dziś.
    Działa przyrostowo (incremental download): sprawdza manifest JSON i istniejące pliki,
    pobierając wyłącznie nowe sceny.

    months: opcjonalny zakres miesięcy (np. (4, 10) = sezon wegetacyjny winorośli).
    Plik: 10 pasm reflektancji [0-1] (B02…B12, 20 m próbkowane do 10 m) + cloudmask + SCL.
    """
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)

    if end_year is None:
        end_year = datetime.now().year

    # Wczytanie manifestu
    manifest: Dict[str, Any] = {"downloaded_scenes": {}}
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, 'r', encoding='utf-8') as mf:
                manifest = json.load(mf)
        except Exception:
            manifest = {"downloaded_scenes": {}}

    downloaded_keys = set(manifest.get("downloaded_scenes", {}).keys())

    start_date = f"{start_year}-01-01"
    end_date = datetime.now().strftime("%Y-%m-%d")

    logger.info(f"--- SYNCHRONIZACJA PRZYROSTOWA S2: {start_date} do {end_date} (AOI Condom) ---")

    # Pobranie kolekcji S2 złączonej z s2cloudless z zachmurzeniem liczonym ściśle nad działkami
    s2_col = get_s2_sr_cld_collection(aoi, start_date, end_date, cloud_thresh=90)
    s2_col_clear = s2_col.filter(ee.Filter.lte('AOI_CLOUD_PERCENTAGE', cloud_thresh))
    if months is not None:
        s2_col_clear = s2_col_clear.filter(ee.Filter.calendarRange(int(months[0]), int(months[1]), 'month'))

    # Pobranie listy metadanych scen
    scenes_info = s2_col_clear.sort('system:time_start', True).getInfo().get('features', [])
    logger.info(f"Znaleziono {len(scenes_info)} scen spełniających kryterium bezchmurności nad działkami (<= {cloud_thresh}%).")

    new_downloads = 0
    scenes_summary: List[Dict[str, Any]] = []

    for feat in scenes_info:
        props = feat.get('properties', {})
        scene_id = feat.get('id', '')
        time_start_ms = props.get('system:time_start', 0)
        dt_str = datetime.utcfromtimestamp(time_start_ms / 1000.0).strftime('%Y%m%d_%H%M%S')
        cloud_pct = props.get('CLOUDY_PIXEL_PERCENTAGE', 0.0)

        filename = f"S2_L2A_{dt_str}.tif"
        filepath = os.path.join(output_dir, filename)

        scene_meta = {
            "scene_id": scene_id,
            "date": dt_str,
            "cloud_percentage": cloud_pct,
            "filepath": filepath
        }
        scenes_summary.append(scene_meta)

        # Sprawdzenie czy scena juz istnieje na dysku (pamiec podreczna)
        if os.path.exists(filepath) and os.path.getsize(filepath) > 1024:
            if scene_id not in downloaded_keys:
                manifest["downloaded_scenes"][scene_id] = {
                    "filepath": filepath,
                    "timestamp": dt_str,
                    "cloud_percentage": cloud_pct,
                    "downloaded_at": datetime.now().isoformat()
                }
                downloaded_keys.add(scene_id)
                with open(manifest_path, 'w', encoding='utf-8') as mf:
                    json.dump(manifest, mf, indent=2)
            continue

        # Przygotowanie obrazu ze wszystkimi 10 pasmami + maska chmur
        raw_img = ee.Image(scene_id)
        # Pobranie odpowiadającego s2cloudless
        cld_img = ee.Image(
            ee.ImageCollection('COPERNICUS/S2_CLOUD_PROBABILITY')
            .filter(ee.Filter.equals('system:index', props.get('system:index')))
            .first()
        )
        raw_img = raw_img.set('s2cloudless', cld_img)
        processed_img = prepare_s2_scaled_image(raw_img)

        # Eksport GeoTIFF
        success = export_image_robust(
            image=processed_img,
            path=filepath,
            region=aoi,
            scale=10.0,
            crs=f'EPSG:{epsg_code}',
            max_retries=4
        )

        if success:
            manifest["downloaded_scenes"][scene_id] = {
                "filepath": filepath,
                "timestamp": dt_str,
                "cloud_percentage": cloud_pct,
                "downloaded_at": datetime.now().isoformat()
            }
            # Zapis manifestu na bieżąco
            with open(manifest_path, 'w', encoding='utf-8') as mf:
                json.dump(manifest, mf, indent=2)
            new_downloads += 1

    cached_count = len(scenes_summary) - new_downloads
    logger.info(
        f"Synchronizacja S2 zakonczona. Wszystkich scen: {len(scenes_summary)} "
        f"({cached_count} juz na dysku, {new_downloads} nowo pobranych)."
    )
    return scenes_summary
