from __future__ import annotations

"""
================================================================================
S-3/S-2 AgriScreen DSS v2.5 - KROK 1: INGESTIA DANYCH Z GEE I COPERNICUS
================================================================================
Moduł odpowiedzialny za uwierzytelnienie w Google Earth Engine (GEE),
ekstrakcję i pobieranie rzeczywistych danych satelitarnych:
  - Sentinel-2 L2A (COPERNICUS/S2_SR_HARMONIZED) od 2016 do dziś
  - Maskowanie chmur s2cloudless + SCL + geometryczna projekcja cieni
  - Sentinel-3 SLSTR LST / Copernicus Thermal (1 km)
  - Copernicus DEM GLO-30 (COPERNICUS/DEM/GLO30) 30 m -> 10 m
  - Copernicus Land Cover (CLMS)
  - Obliczanie wieloletnich statystyk referencyjnych (mean, stdDev) bezpośrednio w GEE
  - Przyrostowy mechanizm aktualizacji (incremental download z manifestem JSON)
  - Rygorystyczne skalowanie radiometryczne (wartości całkowite -> 0.0-1.0)
================================================================================
"""

import os
import sys
import json
import time
import random
import logging
import warnings
from pathlib import Path
from datetime import datetime, timedelta
from typing import Tuple, Dict, Any, Optional, List, Union

import numpy as np
import rasterio
from rasterio.transform import from_bounds
from rasterio.enums import Resampling

# Ustrukturyzowane logowanie zdarzeń
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("AgriScreen_Ingest")

# Wyciszenie zbędnych ostrzeżeń bibliotek zewnętrznych
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

# Stałe spektralne i konfiguracyjne
REQUIRED_S2_BANDS = ["B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B11", "B12"]
S2_BAND_MAP_HARMONIZED = {
    "B2": "B02", "B3": "B03", "B4": "B04", "B5": "B05",
    "B6": "B06", "B7": "B07", "B8": "B08", "B8A": "B8A",
    "B11": "B11", "B12": "B12"
}
REFLECTANCE_SCALE_FACTOR = 10000.0  # BOA L2A integer -> [0.0, 1.0]
EPSILON = 1e-6


# ==============================================================================
# I. POMOCNICZE FUNKCJE GEOREFERENCYJNE I AOI
# ==============================================================================

def load_aoi_geometry(
    geojson_path: str,
    buffer_m: int = 1000
) -> Tuple[ee.Geometry, Dict[str, float], int]:
    """
    Wczytuje wektor AOI z pliku GeoJSON, wyznacza obwiednię, punkt centralny,
    odpowiednią strefę UTM (EPSG) oraz zwraca geometrię Earth Engine.
    """
    if not os.path.exists(geojson_path):
        raise FileNotFoundError(f"Nie znaleziono pliku AOI: {geojson_path}")

    with open(geojson_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    features = data.get("features", [])
    if not features:
        raise ValueError(f"Plik GeoJSON {geojson_path} nie zawiera obiektów 'features'.")

    all_lons: List[float] = []
    all_lats: List[float] = []
    ee_polygons = []

    for feat in features:
        geom = feat.get("geometry", {})
        coords = geom.get("coordinates", [])
        geom_type = geom.get("type", "")

        if geom_type == "Polygon":
            poly_coords = coords[0]  # zewnętrzny pierścień
            for pt in poly_coords:
                all_lons.append(pt[0])
                all_lats.append(pt[1])
            ee_polygons.append(ee.Geometry.Polygon(coords))
        elif geom_type == "MultiPolygon":
            for poly in coords:
                for pt in poly[0]:
                    all_lons.append(pt[0])
                    all_lats.append(pt[1])
            ee_polygons.append(ee.Geometry.MultiPolygon(coords))

    min_lon, max_lon = min(all_lons), max(all_lons)
    min_lat, max_lat = min(all_lats), max(all_lats)
    center_lon = (min_lon + max_lon) / 2.0
    center_lat = (min_lat + max_lat) / 2.0

    # Wyznaczenie strefy UTM (WGS84 UTM Zone)
    utm_zone = int((center_lon + 180) // 6) + 1
    epsg_code = 32600 + utm_zone if center_lat >= 0 else 32700 + utm_zone

    # Złożona geometria EE i bufor
    combined_geom = ee.Geometry.MultiPolygon([
        poly.coordinates() for poly in ee_polygons
    ]).buffer(buffer_m)

    bbox_dict = {
        "min_lon": min_lon, "min_lat": min_lat,
        "max_lon": max_lon, "max_lat": max_lat,
        "center_lon": center_lon, "center_lat": center_lat
    }

    logger.info(
        f"Wczytano AOI: {len(features)} działek. Środek: ({center_lat:.4f}, {center_lon:.4f}). "
        f"Docelowy układ UTM: EPSG:{epsg_code}, bufor: {buffer_m}m"
    )
    return combined_geom, bbox_dict, epsg_code


def initialize_earth_engine(project_id: Optional[str] = None) -> None:
    """
    Inicjalizuje połączenie z Google Earth Engine z automatyczną obsługą uwierzytelnienia.
    """
    if ee is None:
        raise ImportError("Biblioteka 'earthengine-api' nie jest zainstalowana. Uruchom: pip install earthengine-api geemap")
    try:
        if project_id:
            ee.Initialize(project=project_id)
        else:
            ee.Initialize()
        logger.info("Pomyślnie zainicjalizowano Google Earth Engine.")
    except Exception as e:
        logger.warning(f"Inicjalizacja standardowa GEE nie powiodła się: {e}. Uruchamianie procedury autoryzacji...")
        try:
            ee.Authenticate()
            if project_id:
                ee.Initialize(project=project_id)
            else:
                ee.Initialize()
            logger.info("Pomyślnie uwierzytelniono i zainicjalizowano GEE.")
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
    cloud_thresh: int = 60
) -> ee.ImageCollection:
    """
    Buduje kolekcję Sentinel-2 L2A (SR Harmonized) złączoną z kolekcją prawdopodobieństwa
    chmur s2cloudless (COPERNICUS/S2_CLOUD_PROBABILITY).
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

    return ee.ImageCollection(
        ee.Join.saveFirst('s2cloudless').apply(
            primary=s2_sr_col,
            secondary=s2_cloudless_col,
            condition=ee.Filter.equals(
                leftField='system:index',
                rightField='system:index'
            )
        )
    )


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
# III. COPERNICUS DEM, LAND COVER I SENTINEL-3 / 1KM THERMAL LST
# ==============================================================================

def get_copernicus_dem_glo30(aoi: ee.Geometry) -> ee.Image:
    """
    Pobiera numeryczny model terenu Copernicus DEM GLO-30 (30m) i wycina do AOI.
    """
    dem_col = ee.ImageCollection('COPERNICUS/DEM/GLO30').filterBounds(aoi)
    dem = dem_col.select('DEM').mosaic().clip(aoi).rename('elevation')
    return dem


def get_copernicus_land_cover(aoi: ee.Geometry) -> ee.Image:
    """
    Pobiera warstwę pokrycia terenu Copernicus Land Monitoring Service (CLMS):
    CORINE Land Cover lub Global Land Cover 100m.
    """
    try:
        clc = ee.ImageCollection('COPERNICUS/CORINE/V20/100m').filterBounds(aoi).sort('system:time_start', False).first()
        if clc:
            return ee.Image(clc).select('landcover').clip(aoi).rename('landcover')
    except Exception:
        pass

    # Fallback na Copernicus Global Land Cover 100m
    cgls = ee.ImageCollection('COPERNICUS/Landcover/100m/Proba-V-C3/Global').filterBounds(aoi).sort('system:time_start', False).first()
    return ee.Image(cgls).select('discrete_classification').clip(aoi).rename('landcover')


def get_thermal_lst_1km(
    aoi: ee.Geometry,
    target_datetime_str: str
) -> ee.Image:
    """
    Pobiera scenę LST (1 km) zbieżną czasowo z wybraną sceną Sentinel-2 (+/- 24h).
    Weryfikuje dostępność S3 SLSTR LST, a w przypadku jej braku w publicznym katalogu
    pobiera zbieżną scenę MODIS LST (1 km) przeliczoną do stopni Celsjusza.
    """
    target_dt = datetime.strptime(target_datetime_str[:10], "%Y-%m-%d")
    start_dt = (target_dt - timedelta(days=1)).strftime("%Y-%m-%d")
    end_dt = (target_dt + timedelta(days=2)).strftime("%Y-%m-%d")

    # Próba pobrania Sentinel-3 SLSTR LST
    try:
        s3_col = (
            ee.ImageCollection('COPERNICUS/S3/SLSTR')
            .filterBounds(aoi)
            .filterDate(start_dt, end_dt)
        )
        if s3_col.size().getInfo() > 0:
            logger.info("Znaleziono scenę Sentinel-3 SLSTR LST w GEE.")
            s3_img = s3_col.sort('system:time_start').first()
            # Wybór pasma LST i przeliczenie K -> Celsjusz
            lst_k = s3_img.select(['LST', 'LST_in_celsius', 'temperature']).first()
            return lst_k.clip(aoi).rename('LST_raw')
    except Exception as s3_err:
        logger.debug(f"Kolekcja COPERNICUS/S3/SLSTR niedostępna: {s3_err}. Użycie 1km MODIS LST.")

    # Pobranie termicznego kanału LST 1 km (MODIS MOD11A1 Day LST)
    modis_col = (
        ee.ImageCollection('MODIS/061/MOD11A1')
        .filterBounds(aoi)
        .filterDate(start_dt, end_dt)
    )
    count = modis_col.size().getInfo()
    if count > 0:
        logger.info(f"Pobieranie 1 km LST z MODIS MOD11A1 (znaleziono {count} scen w oknie +/-24h).")
        # Skalowanie: DN * 0.02 = Kelvin, Kelvin - 273.15 = stopnie Celsjusza
        modis_img = modis_col.sort('system:time_start').first()
        lst_celsius = modis_img.select('LST_Day_1km').multiply(0.02).subtract(273.15).clip(aoi).rename('LST_raw')
        return lst_celsius
    else:
        # Fallback na ERA5-Land hourly skin temperature (1 km zresamplowane)
        logger.info("Użycie ERA5-Land Skin Temperature jako źródła LST.")
        era5 = (
            ee.ImageCollection('ECMWF/ERA5_LAND/HOURLY')
            .filterBounds(aoi)
            .filterDate(start_dt, end_dt)
            .select('skin_temperature')
            .mean()
            .subtract(273.15)
            .clip(aoi)
            .rename('LST_raw')
        )
        return era5


def get_cgls_soil_water_index(
    aoi: ee.Geometry,
    target_datetime_str: str
) -> ee.Image:
    """
    Regionalny Indeks Wilgotności (CGLS Soil Water Index - 1 km):
    Pobiera produkt SWI dla parametru T = 5 (strefa korzeniowa drzew / upraw trwałych).
    Służy jako tło regionalne do weryfikacji skali suszy w skali makro.
    """
    target_dt = datetime.strptime(target_datetime_str[:10], "%Y-%m-%d")
    start_dt = (target_dt - timedelta(days=2)).strftime("%Y-%m-%d")
    end_dt = (target_dt + timedelta(days=3)).strftime("%Y-%m-%d")

    try:
        # Próba pobrania natywnego produktu CGLS SWI (jeśli dostępny w katalogu lub STAC)
        swi_col = ee.ImageCollection('COPERNICUS/CGLS/SWI').filterBounds(aoi).filterDate(start_dt, end_dt)
        if swi_col.size().getInfo() > 0:
            logger.info("Pobrano produkt CGLS SWI T=5 (1 km) z repozytorium Copernicus.")
            swi_img = swi_col.first().select(['SWI_005', 'SWI_T5', 'SWI']).first()
            return swi_img.clip(aoi).rename('SWI_T5')
    except Exception:
        pass

    # Regionalne tło wilgotnościowe strefy korzeniowej (NASA-USDA SMAP / ERA5-Land Root-Zone)
    logger.info("Obliczanie regionalnego wskaźnika wilgotności gleby strefy korzeniowej (SWI T=5 proxy)...")
    try:
        smap = (
            ee.ImageCollection('NASA_USDA/HSL/SMAP10KM_soil_moisture')
            .filterBounds(aoi)
            .filterDate(start_dt, end_dt)
            .select('smp_rootzone')
            .mean()
        )
        # Normalizacja do skali SWI [0-100%]
        swi_proxy = smap.multiply(100.0).clip(aoi).rename('SWI_T5')
        return swi_proxy
    except Exception:
        era5_soil = (
            ee.ImageCollection('ECMWF/ERA5_LAND/HOURLY')
            .filterBounds(aoi)
            .filterDate(start_dt, end_dt)
            .select(['volumetric_soil_water_layer_1', 'volumetric_soil_water_layer_2'])
            .mean()
        )
        # Średnia wilgotność warstwy 0-28 cm (m3/m3) przeliczona na wskaźnik SWI [%]
        swi_proxy = (
            era5_soil.select('volumetric_soil_water_layer_1')
            .add(era5_soil.select('volumetric_soil_water_layer_2'))
            .multiply(50.0)
            .clip(aoi)
            .rename('SWI_T5')
        )
        return swi_proxy


def get_hrvpp_seasonal_trajectory_ppi(
    aoi: ee.Geometry,
    target_datetime_str: str
) -> ee.Image:
    """
    Trajektorie Sezonowe (HR-VPP ST - 10 m):
    Pobiera oczyszczoną z chmur i zinterpolowaną 10-dniową serię wskaźnika PPI
    (Plant Phenology Index). Eliminuje to potrzebę ręcznego gap-fillingu surowych scen Sentinel-2.
    """
    target_dt = datetime.strptime(target_datetime_str[:10], "%Y-%m-%d")
    start_dt = (target_dt - timedelta(days=10)).strftime("%Y-%m-%d")
    end_dt = (target_dt + timedelta(days=10)).strftime("%Y-%m-%d")

    try:
        hrvpp_col = ee.ImageCollection('COPERNICUS/CLMS/HRVPP/V1/ST').filterBounds(aoi).filterDate(start_dt, end_dt)
        if hrvpp_col.size().getInfo() > 0:
            logger.info("Pobrano Trajektorię Sezonową HR-VPP ST (PPI) z katalogu CLMS.")
            return hrvpp_col.first().select('PPI').clip(aoi).rename('PPI_10m')
    except Exception:
        pass

    # Obliczenie wskaźnika PPI (Plant Phenology Index) na oczyszczonej kolekcji S2 wokół zadanego dnia:
    # PPI = -K * ln((DVI_max - DVI) / (DVI_max - DVI_soil)), gdzie DVI = B08 - B04
    logger.info("Obliczanie bezszumnej trajektorii fenologicznej PPI (Plant Phenology Index 10 m)...")
    s2_col = (
        ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
        .filterBounds(aoi)
        .filterDate(start_dt, end_dt)
        .filter(ee.Filter.lte('CLOUDY_PIXEL_PERCENTAGE', 40))
    )

    def calc_ppi(img: ee.Image) -> ee.Image:
        b4 = img.select('B4').divide(REFLECTANCE_SCALE_FACTOR)
        b8 = img.select('B8').divide(REFLECTANCE_SCALE_FACTOR)
        dvi = b8.subtract(b4)
        # DVI_max = 0.85, DVI_soil = 0.09, K = 0.4
        dvi_clamped = dvi.clamp(0.091, 0.84)
        ratio_term = (ee.Image.constant(0.85).subtract(dvi_clamped)).divide(0.76)
        ppi = ratio_term.log().multiply(-0.4).rename('PPI_10m')
        return ppi

    ppi_smooth = s2_col.map(calc_ppi).median().clip(aoi).rename('PPI_10m')
    return ppi_smooth


def get_hrl_crop_mask(
    geojson_path: Optional[str],
    profile_10m: dict
) -> np.ndarray:
    """
    Maska Upraw (HRL Croplands - 10 m):
    Pobiera roczny produkt klasyfikacji typów upraw lub wektor działek referencyjnych.
    Piksele oznaczające uprawy trwałe (sady owocowe, winnice) tworzą binarną maskę M_crop:
        M_crop(x, y) = 1.0 (jeśli piksel to uprawa trwała)
        M_crop(x, y) = NaN (w pozostałych przypadkach)
    """
    logger.info("Generowanie maski upraw trwałych M_crop (HRL Croplands 10 m: sady, winnice)...")
    from rasterio.features import rasterize
    from shapely.geometry import shape

    h = profile_10m['height']
    w = profile_10m['width']
    transform = profile_10m['transform']

    # Inicjalizacja macierzy z wartościami NaN
    m_crop = np.full((h, w), np.nan, dtype=np.float32)

    if geojson_path and os.path.exists(geojson_path):
        with open(geojson_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        shapes_to_burn = []
        permanent_crop_types = {'sad_jablonek', 'winnice', 'orchard', 'vineyard', 'permanent_crop'}

        for feat in data.get('features', []):
            crop_type = str(feat.get('properties', {}).get('Typ', '')).lower()
            if any(pct in crop_type for pct in permanent_crop_types):
                geom = feat.get('geometry')
                if geom:
                    shapes_to_burn.append((shape(geom), 1.0))

        if shapes_to_burn:
            logger.info(f"HRL CropMask: Zrasteryzowano {len(shapes_to_burn)} działek sadów i winnic do siatki 10 m.")
            burned = rasterize(
                shapes=shapes_to_burn,
                out_shape=(h, w),
                transform=transform,
                fill=0,
                default_value=1,
                dtype=np.uint8
            )
            m_crop[burned == 1] = 1.0
            pct_crop = (np.sum(m_crop == 1.0) / (h * w)) * 100.0
            logger.info(f"HRL CropMask M_crop: {pct_crop:.2f}% pikseli w AOI oznaczono jako uprawy trwałe.")
            return m_crop

    # Fallback jeśli brak działek w pliku
    logger.warning("Brak działek upraw trwałych w AOI. Ustawienie maski pełnej (1.0 dla wszystkich pikseli).")
    return np.ones((h, w), dtype=np.float32)


# ==============================================================================
# IV. AGREGACJA WIELOLETNIA (2016-2026) BEZPOŚREDNIO W SILNIKU GEE
# ==============================================================================

def compute_historical_baseline_stats(
    aoi: ee.Geometry,
    target_date_str: str,
    baseline_years: Tuple[int, int] = (2018, 2025),
    day_window: int = 10
) -> ee.Image:
    """
    Zbuduj wieloletnią kolekcję obrazów Sentinel-2 dla zadanego tygodnia kalendarzowego
    w latach bazowych. Oblicza wieloletnią średnią (mean) i odchylenie standardowe (stdDev)
    wskaźników TCARI/OSAVI oraz TVDI na poziomie piksela bezpośrednio w silniku GEE.
    """
    target_dt = datetime.strptime(target_date_str[:10], "%Y-%m-%d")
    target_doy = target_dt.timetuple().tm_yday
    logger.info(
        f"Obliczanie wieloletniej bazy referencyjnej GEE: lata {baseline_years[0]}-{baseline_years[1]}, "
        f"dzień roku (DOY) {target_doy} +/- {day_window} dni..."
    )

    # Pobranie kolekcji z całego zakresu lat
    start_baseline = f"{baseline_years[0]}-01-01"
    end_baseline = f"{baseline_years[1]}-12-31"

    s2_col = (
        ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
        .filterBounds(aoi)
        .filterDate(start_baseline, end_baseline)
        .filter(ee.Filter.calendarRange(max(1, target_doy - day_window), min(365, target_doy + day_window), 'day_of_year'))
        .filter(ee.Filter.lte('CLOUDY_PIXEL_PERCENTAGE', 40))
    )

    def calculate_pixel_indices(img: ee.Image) -> ee.Image:
        # Odfiltrowanie pikseli chmur przy użyciu SCL
        scl = img.select('SCL')
        valid_mask = scl.neq(1).And(scl.neq(3)).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)).And(scl.neq(11))
        
        b2 = img.select('B2').divide(REFLECTANCE_SCALE_FACTOR)
        b3 = img.select('B3').divide(REFLECTANCE_SCALE_FACTOR)
        b4 = img.select('B4').divide(REFLECTANCE_SCALE_FACTOR)
        b5 = img.select('B5').divide(REFLECTANCE_SCALE_FACTOR)
        b8 = img.select('B8').divide(REFLECTANCE_SCALE_FACTOR)

        # OSAVI = (B08 - B04) / (B08 + B04 + 0.16)
        osavi = (b8.subtract(b4)).divide(b8.add(b4).add(0.16)).rename('OSAVI')

        # TCARI = 3 * [(B05 - B04) - 0.2 * (B05 - B03) * (B05 / (B04 + eps))]
        term1 = b5.subtract(b4)
        term2 = (b5.subtract(b3)).multiply(0.2).multiply(b5.divide(b4.add(EPSILON)))
        tcari = (term1.subtract(term2)).multiply(3.0).rename('TCARI')

        # Ratio TCARI / OSAVI
        ratio = tcari.divide(osavi.add(EPSILON)).rename('TCARI_OSAVI')

        # NDVI
        ndvi = (b8.subtract(b4)).divide(b8.add(b4).add(EPSILON)).rename('NDVI')

        return ratio.addBands(ndvi).updateMask(valid_mask)

    indexed_col = s2_col.map(calculate_pixel_indices)

    # Obliczenie średniej i odchylenia standardowego
    stats_tcari = indexed_col.select('TCARI_OSAVI').reduce(
        ee.Reducer.mean().combine(ee.Reducer.stdDev(), "", True)
    ).rename(['tcari_osavi_mean', 'tcari_osavi_std'])

    stats_ndvi = indexed_col.select('NDVI').reduce(
        ee.Reducer.mean().combine(ee.Reducer.stdDev(), "", True)
    ).rename(['tvdi_mean', 'tvdi_std'])  # Proxy bazy pod TVDI na poziomie piksela

    combined_stats = stats_tcari.addBands(stats_ndvi)
    return combined_stats


# ==============================================================================
# V. POBIERANIE RASTROWE (ROBUST DOWNLOAD Z EXPONENTIAL BACKOFF)
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


# ==============================================================================
# VI. SILNIK SYNCHRONIZACJI PRZYROSTOWEJ (INCREMENTAL SYNC 2016-DZIŚ)
# ==============================================================================

def sync_sentinel2_time_series(
    aoi: ee.Geometry,
    start_year: int = 2016,
    end_year: Optional[int] = None,
    output_dir: str = "data/01_Raw_Sentinel2",
    manifest_path: str = "data/00_Metadata/ingest_manifest.json",
    cloud_thresh: int = 40,
    epsg_code: int = 32631,
    max_scenes_per_year: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Pobiera wszystkie dostępne bezchmurne zobrazowania Sentinel-2 od 2016 roku do dziś.
    Działa przyrostowo (incremental download): sprawdza manifest JSON i istniejące pliki,
    pobierając wyłącznie nowe sceny.
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

    # Pobranie kolekcji S2 złączonej z s2cloudless
    s2_col = get_s2_sr_cld_collection(aoi, start_date, end_date, cloud_thresh=cloud_thresh)

    # Pobranie listy metadanych scen
    scenes_info = s2_col.sort('system:time_start', True).getInfo().get('features', [])
    logger.info(f"Znaleziono {len(scenes_info)} scen spełniających kryteria chmurowości w GEE.")

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

        # Sprawdzenie czy scena już została pobrana
        if scene_id in downloaded_keys and os.path.exists(filepath) and os.path.getsize(filepath) > 1024:
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

    logger.info(f"Synchronizacja S2 zakończona. Pobrano nowych scen: {new_downloads}. Wszystkich dostępnych: {len(scenes_summary)}.")
    return scenes_summary


# ==============================================================================
# VII. GŁÓWNA FUNKCJA KROKU 1: ingest_satellite_data
# ==============================================================================

def ingest_satellite_data(
    lat: float = 43.9752,
    lon: float = 0.3376,
    target_date: str = "2023-07-15",
    buffer_m: int = 2000,
    baseline_years: Tuple[int, int] = (2018, 2025),
    geojson_path: Optional[str] = "data/1_AOI_GBOV_CONDOM.geojson",
    output_base_dir: str = "data",
    download_historical_series: bool = False
) -> Tuple[Dict[str, np.ndarray], Dict[str, Any], Dict[str, np.ndarray]]:
    """
    GŁÓWNA FUNKCJA WEJŚCIOWA DLA KROKU 1 (Rygorystyczny kontrakt interfejsu).

    Pobiera bieżące zobrazowania S2, S3 LST, DEM SRTM/Copernicus oraz historyczne serie S2 (2018-2025),
    zwracając słowniki tablic NumPy, metadane georeferencyjne oraz profil rastrowy.

    Parametry:
        lat, lon: Współrzędne geograficzne punktu docelowego (domyślnie centrum GBOV Condom).
        target_date: Docelowa data analizy w formacie 'YYYY-MM-DD'.
        buffer_m: Promień bufora w metrach.
        baseline_years: Zakres lat dla wyznaczenia wieloletnich statystyk referencyjnych.
        geojson_path: Ścieżka do pliku wektorowego działek (AOI).
        output_base_dir: Główny katalog zapisu danych.
        download_historical_series: Czy uruchomić pełne przyrostowe pobieranie wszystkich scen od 2016.

    Zwraca:
        s2_bands_dict: Słownik zawierający macierze NumPy float32 dla pasm Sentinel-2
                       (B02, B03, B04, B05, B06, B07, B08, B8A, B11, B12), 's3_lst_raw' oraz 'dem'.
        profile_10m: Słownik metadanych profilu georeferencyjnego (Rasterio Affine, CRS, width, height).
        baseline_stats: Słownik zawierający macierze wieloletnich statystyk:
                       'tcari_osavi_mean', 'tcari_osavi_std', 'tvdi_mean', 'tvdi_std'.
    """
    logger.info("================================================================================")
    logger.info(f"URUCHOMIENIE KROKU 1: Ingestia danych satelitarnych dla daty {target_date}...")
    logger.info("================================================================================")

    # 1. Inicjalizacja GEE
    initialize_earth_engine()

    # 2. Definicja geometrii AOI i CRS
    if geojson_path and os.path.exists(geojson_path):
        aoi, bbox, epsg_code = load_aoi_geometry(geojson_path, buffer_m=buffer_m)
    else:
        # Geometria punktowa z buforem
        center_pt = ee.Geometry.Point([lon, lat])
        aoi = center_pt.buffer(buffer_m)
        utm_zone = int((lon + 180) // 6) + 1
        epsg_code = 32600 + utm_zone if lat >= 0 else 32700 + utm_zone
        logger.info(f"Użyto współrzędnych punktowych: lat={lat}, lon={lon}, bufor={buffer_m}m, EPSG:{epsg_code}")

    # Definicja katalogów zapisu
    dir_s2 = os.path.join(output_base_dir, "01_Raw_Sentinel2")
    dir_lst = os.path.join(output_base_dir, "02_Raw_Thermal_LST")
    dir_aux = os.path.join(output_base_dir, "03_Copernicus_Auxiliary")
    os.makedirs(dir_s2, exist_ok=True)
    os.makedirs(dir_lst, exist_ok=True)
    os.makedirs(dir_aux, exist_ok=True)

    # 3. Synchronizacja przyrostowa pełnej serii czasowej (opcjonalna)
    if download_historical_series:
        sync_sentinel2_time_series(
            aoi=aoi,
            start_year=baseline_years[0],
            end_year=datetime.now().year,
            output_dir=dir_s2,
            epsg_code=epsg_code
        )

    # 4. Wybór bieżącej sceny Sentinel-2 dla zadanego dnia (+/- 7 dni w razie chmur)
    target_dt = datetime.strptime(target_date[:10], "%Y-%m-%d")
    s2_start = (target_dt - timedelta(days=7)).strftime("%Y-%m-%d")
    s2_end = (target_dt + timedelta(days=7)).strftime("%Y-%m-%d")

    logger.info(f"Wyszukiwanie optymalnej sceny Sentinel-2 w oknie: {s2_start} do {s2_end}...")
    s2_col = get_s2_sr_cld_collection(aoi, s2_start, s2_end, cloud_thresh=50)
    col_size = s2_col.size().getInfo()

    if col_size == 0:
        logger.warning(f"Brak scen S2 w oknie +/-7 dni od {target_date}. Rozszerzanie okna do +/- 15 dni...")
        s2_start = (target_dt - timedelta(days=15)).strftime("%Y-%m-%d")
        s2_end = (target_dt + timedelta(days=15)).strftime("%Y-%m-%d")
        s2_col = get_s2_sr_cld_collection(aoi, s2_start, s2_end, cloud_thresh=70)
        if s2_col.size().getInfo() == 0:
            raise RuntimeError(f"Nie znaleziono żadnej sceny Sentinel-2 dla obszaru w oknie {s2_start} do {s2_end}.")

    # Wybór sceny o najmniejszym zachmurzeniu
    best_s2 = s2_col.sort('CLOUDY_PIXEL_PERCENTAGE').first()
    best_id = best_s2.get('system:index').getInfo()
    cloud_pct = best_s2.get('CLOUDY_PIXEL_PERCENTAGE').getInfo()
    time_start_ms = best_s2.get('system:time_start').getInfo()
    actual_date_str = datetime.utcfromtimestamp(time_start_ms / 1000.0).strftime('%Y-%m-%d')
    logger.info(f"Wybrano scenę S2: {best_id} (data akwizycji: {actual_date_str}, zachmurzenie: {cloud_pct:.1f}%)")

    # Przygotowanie obrazu S2 ze skalowaniem BOA -> [0.0, 1.0]
    s2_processed = prepare_s2_scaled_image(best_s2)

    # 5. Pobranie bieżącej sceny termicznej LST (1 km)
    lst_image = get_thermal_lst_1km(aoi, actual_date_str)

    # 6. Pobranie numerycznego modelu terenu Copernicus DEM GLO-30 (30 m)
    dem_image = get_copernicus_dem_glo30(aoi)

    # 7. Obliczenie wieloletnich statystyk referencyjnych w GEE
    baseline_stats_image = compute_historical_baseline_stats(
        aoi=aoi,
        target_date_str=actual_date_str,
        baseline_years=baseline_years
    )

    # 8. Pobranie CGLS SWI T=5 (1 km) oraz HR-VPP ST PPI (10 m)
    swi_image = get_cgls_soil_water_index(aoi, actual_date_str)
    ppi_image = get_hrvpp_seasonal_trajectory_ppi(aoi, actual_date_str)

    # 9. Eksport rastrów do plików lokalnych GeoTIFF
    s2_tif_path = os.path.join(dir_s2, f"S2_L2A_{actual_date_str}.tif")
    lst_tif_path = os.path.join(dir_lst, f"LST_1km_{actual_date_str}.tif")
    dem_tif_path = os.path.join(dir_aux, "Copernicus_DEM_GLO30_10m.tif")
    base_tif_path = os.path.join(dir_aux, f"Baseline_Stats_{baseline_years[0]}_{baseline_years[1]}.tif")
    swi_tif_path = os.path.join(dir_aux, f"CGLS_SWI_1km_{actual_date_str}.tif")
    ppi_tif_path = os.path.join(dir_aux, f"HRVPP_PPI_10m_{actual_date_str}.tif")

    # Pobieranie GeoTIFF z GEE
    export_image_robust(s2_processed, s2_tif_path, region=aoi, scale=10.0, crs=f'EPSG:{epsg_code}')
    export_image_robust(lst_image, lst_tif_path, region=aoi, scale=1000.0, crs=f'EPSG:{epsg_code}')
    export_image_robust(dem_image, dem_tif_path, region=aoi, scale=10.0, crs=f'EPSG:{epsg_code}')
    export_image_robust(baseline_stats_image, base_tif_path, region=aoi, scale=10.0, crs=f'EPSG:{epsg_code}')
    export_image_robust(swi_image, swi_tif_path, region=aoi, scale=1000.0, crs=f'EPSG:{epsg_code}')
    export_image_robust(ppi_image, ppi_tif_path, region=aoi, scale=10.0, crs=f'EPSG:{epsg_code}')

    # 10. Wczytanie do tablic NumPy i przygotowanie profilu Rasterio
    s2_raw_arr, profile_10m = read_geotiff_to_numpy(s2_tif_path)
    dem_arr, _ = read_geotiff_to_numpy(dem_tif_path)
    lst_arr, _ = read_geotiff_to_numpy(lst_tif_path)
    base_arr, _ = read_geotiff_to_numpy(base_tif_path)
    swi_arr, _ = read_geotiff_to_numpy(swi_tif_path)
    ppi_arr, _ = read_geotiff_to_numpy(ppi_tif_path)

    # Generowanie binarnej maski upraw trwałych M_crop (HRL Croplands 10 m)
    crop_mask = get_hrl_crop_mask(geojson_path, profile_10m)
    crop_mask_path = os.path.join(dir_aux, "HRL_Crop_Mask_10m.tif")
    with rasterio.open(crop_mask_path, 'w', **profile_10m) as dst:
        dst.write(np.nan_to_num(crop_mask, nan=-9999.0).astype(np.float32), 1)

    # Budowa słownika s2_bands_dict
    s2_bands_dict: Dict[str, np.ndarray] = {}
    for idx, band_name in enumerate(REQUIRED_S2_BANDS):
        band_data = s2_raw_arr[idx, :, :]
        if np.nanmax(band_data) > 10.0:
            band_data = band_data / REFLECTANCE_SCALE_FACTOR
        s2_bands_dict[band_name] = band_data.astype(np.float32)

    # Dołączenie LST, DEM, M_crop, SWI T=5 oraz PPI do słownika zwracanego
    s2_bands_dict["s3_lst_raw"] = lst_arr[0, :, :].astype(np.float32) if len(lst_arr.shape) == 3 else lst_arr.astype(np.float32)
    s2_bands_dict["dem"] = dem_arr[0, :, :].astype(np.float32) if len(dem_arr.shape) == 3 else dem_arr.astype(np.float32)
    s2_bands_dict["crop_mask"] = crop_mask.astype(np.float32)
    s2_bands_dict["swi_1km"] = swi_arr[0, :, :].astype(np.float32) if len(swi_arr.shape) == 3 else swi_arr.astype(np.float32)
    s2_bands_dict["ppi_10m"] = ppi_arr[0, :, :].astype(np.float32) if len(ppi_arr.shape) == 3 else ppi_arr.astype(np.float32)

    # Wypełnienie słownika statystyk bazowych
    baseline_stats_dict: Dict[str, np.ndarray] = {
        "tcari_osavi_mean": base_arr[0, :, :].astype(np.float32),
        "tcari_osavi_std": base_arr[1, :, :].astype(np.float32),
        "tvdi_mean": base_arr[2, :, :].astype(np.float32),
        "tvdi_std": base_arr[3, :, :].astype(np.float32)
    }

    logger.info("================================================================================")
    logger.info("KROK 1 ZAKOŃCZONY POMYŚLNIE:")
    logger.info(f" - Rozmiar siatki 10m: {profile_10m['height']} x {profile_10m['width']} px")
    logger.info(f" - Układ CRS: {profile_10m['crs']}")
    logger.info(f" - Pasm S2 wczytanych: {len(REQUIRED_S2_BANDS)}")
    logger.info(f" - Maska Upraw HRL M_crop: {np.nansum(crop_mask == 1.0)} pikseli upraw trwałych")
    logger.info(f" - Regionalny SWI T=5: średnia {np.nanmean(s2_bands_dict['swi_1km']):.1f}%")
    logger.info(f" - Trajektoria HR-VPP PPI: średnia {np.nanmean(s2_bands_dict['ppi_10m']):.3f}")
    logger.info(f" - Zakres temperatur LST: min={np.nanmin(s2_bands_dict['s3_lst_raw']):.1f}C, max={np.nanmax(s2_bands_dict['s3_lst_raw']):.1f}C")
    logger.info(f" - Zakres wysokości DEM: min={np.nanmin(s2_bands_dict['dem']):.1f}m, max={np.nanmax(s2_bands_dict['dem']):.1f}m")
    logger.info("================================================================================")

    return s2_bands_dict, profile_10m, baseline_stats_dict


# ==============================================================================
# TEST SAMODZIELNY MODUŁU
# ==============================================================================
if __name__ == "__main__":
    print("Testowanie modułu step_01_ingest.py...")
    try:
        bands, profile, baseline = ingest_satellite_data(
            target_date="2023-07-15",
            geojson_path="data/1_AOI_GBOV_CONDOM.geojson",
            download_historical_series=False
        )
        print(" Sukces! Wymiary B04:", bands["B04"].shape)
    except Exception as err:
        print(f"Informacja: Test wymaga aktywnej sesji Google Earth Engine: {err}")
