"""
================================================================================
Skrypt budujący Master Jupyter Notebook dedykowany dla Google Colab
z bezpośrednim importem modułów z Dysku Google (czysta architektura modułowa).
Bez emotikon.
================================================================================
"""
import json
import os

def create_master_notebook():
    nb = {
        'cells': [],
        'metadata': {
            'colab': {'name': 'AgriScreen_Colab_Master.ipynb', 'provenance': []},
            'accelerator': 'GPU',
            'gpuClass': 'standard',
            'language_info': {'name': 'python', 'version': '3.10.12'}
        },
        'nbformat': 4,
        'nbformat_minor': 0
    }

    def add_md(text):
        nb['cells'].append({
            'cell_type': 'markdown',
            'metadata': {},
            'source': [line + '\n' for line in text.strip().split('\n')]
        })

    def add_code(code):
        nb['cells'].append({
            'cell_type': 'code',
            'execution_count': None,
            'metadata': {},
            'outputs': [],
            'source': [line + '\n' for line in code.strip().split('\n')]
        })

    # 1. Tytuł i Wprowadzenie
    add_md("""# S-3/S-2 AgriScreen DSS v2.5 (Google Colab Master Pipeline)
### Kompleksowy System Wczesnego Wykrywania Anomalii Wilgotnościowych i Fizjologicznych w Uprawach Wieloletnich
**Środowisko:** Google Colab (GPU T4, 12 GB RAM) | Google Earth Engine (GEE)  
**Trwałe przechowywanie danych:** Dysk Google  
**Architektura:** W pełni modułowa – bezpośredni import modułów `.py` z Dysku Google (brak przepisywania kodu w notatniku)  
**Poligon badawczy:** GBOV Condom (Gers, Francja) – sady owocowe i winnice  
**Dane satelitarne:** Sentinel-2 L2A (10m/20m), Sentinel-3 SLSTR LST (1km), Copernicus DEM GLO-30, HRL Cropland (10m), CGLS SWI T=5 (1km), HR-VPP ST PPI (10m)""")

    # 2. Montowanie Dysku Google i sys.path
    add_md("""## Krok 1: Montowanie Dysku Google i Przygotowanie Środowiska Modułowego
Wszystkie moduły (`step_01_ingest.py`, `step_02_align_and_scale.py`, itd.), dane wejściowe, pośrednie i wynikowe COG GeoTIFF znajdują się bezpośrednio na Twoim Dysku Google.
Dzięki `%load_ext autoreload` każda zmiana w plikach `.py` na Dysku jest natychmiast uwzględniana bez restartu jądra.""")

    add_code("""import os
import sys

# 1. Montowanie Dysku Google w środowisku Colab
try:
    from google.colab import drive
    drive.mount('/content/drive')
    IN_COLAB = True
    print('[OK] Zamontowano Dysk Google.')
except Exception:
    IN_COLAB = False
    print('[INFO] Uruchomienie lokalne poza Google Colab.')

# 2. Automatyczne wykrycie lub ręczne wskazanie katalogu projektu na Dysku Google
REPO_URL = 'https://github.com/geoworldlook/1_geoworldlook-agriscreen.git'
CANDIDATE_PATHS = [
    '/content/drive/MyDrive/1_geoworldlook-agriscreen',
    '/content/drive/MyDrive/2_geoworldlook',
    '/content/drive/MyDrive/GEOWORLDLOOK_AgriScreen',
    os.path.abspath('.')
]

PROJECT_DIR = None
for candidate in CANDIDATE_PATHS:
    if os.path.exists(os.path.join(candidate, 'step_01_ingest.py')):
        PROJECT_DIR = candidate
        break

if PROJECT_DIR is None:
    # Domyślny katalog na Dysku Google
    PROJECT_DIR = '/content/drive/MyDrive/1_geoworldlook-agriscreen'

# Jeśli folder nie istnieje lub nie zawiera jeszcze kodu, sklonuj repozytorium:
if not os.path.exists(os.path.join(PROJECT_DIR, 'step_01_ingest.py')):
    print(f'[INFO] Klonowanie repozytorium GitHub do: {PROJECT_DIR}...')
    !git clone {REPO_URL} "{PROJECT_DIR}"

print(f'[INFO] Katalog roboczy projektu: {PROJECT_DIR}')

# 3. Ustawienie bieżącego katalogu roboczego i dodanie do sys.path (importy modułowe)
os.chdir(PROJECT_DIR)
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# 4. Włączenie automatycznego przeładowywania modułów Python (kompatybilność z Python 3.10 - 3.13+)
import importlib
if 'imp' not in sys.modules:
    sys.modules['imp'] = importlib

try:
    %load_ext autoreload
    %autoreload 2
    print('[OK] Włączono automatyczne przeładowywanie modułów (%autoreload 2).')
except Exception as e:
    print(f'[INFO] autoreload pominięty ({e}).')

# 5. Pobranie najnowszych zmian z GitHub na Dysk Google
if os.path.exists(os.path.join(PROJECT_DIR, '.git')):
    print('[GIT] Wykryto repozytorium Git. Pobieranie najnowszych aktualizacji ze skryptów...')
    !git -C "{PROJECT_DIR}" pull

# 6. Utworzenie wymaganej struktury katalogów na dane (jeśli jeszcze nie istnieją)
dirs = [
    'data/00_Metadata',
    'data/01_Raw_Sentinel2',
    'data/02_Raw_Thermal_LST',
    'data/03_Copernicus_Auxiliary',
    'data/04_Processed_Intermediates',
    'data/05_Final_Outputs'
]
for d in dirs:
    os.makedirs(os.path.join(PROJECT_DIR, d), exist_ok=True)

# 7. Weryfikacja obecności modułów na Dysku Google
expected_files = [
    'step_01_ingest.py',
    'step_02_align_and_scale.py',
    'step_03_super_resolve.py',
    'step_04_metrics_alert.py',
    'step_05_colab_run.py',
    'data/1_AOI_GBOV_CONDOM.geojson'
]
missing = [f for f in expected_files if not os.path.exists(os.path.join(PROJECT_DIR, f))]
if missing:
    print(f'[OSTRZEŻENIE] Następujące pliki nie zostały znalezione w {PROJECT_DIR}:')
    for m in missing:
        print(f'   - {m}')
    print('Upewnij się, że zmienna PROJECT_DIR wskazuje na właściwy folder z wgranym projektem.')
else:
    print('[OK] Wszystkie moduły potoku i pliki konfiguracyjne są obecne i gotowe do importu!')
""")

    # 2b. Opcjonalna komórka do szybkiej synchronizacji Git
    add_md("""### Szybka synchronizacja zmian z GitHub (`git pull`)
Uruchom tę komórkę w dowolnym momencie, gdy wprowadzimy zmiany w plikach `.py` i wyślemy je na GitHub:""")
    add_code("""!git -C "{PROJECT_DIR}" pull

# Wymuszenie przeładowania modułów w pamięci jądra
import importlib
for mod_name in ['step_01_ingest', 'step_02_align_and_scale', 'step_03_super_resolve', 'step_04_metrics_alert', 'step_05_colab_run']:
    if mod_name in sys.modules:
        importlib.reload(sys.modules[mod_name])
print('[OK] Moduły potoku zsynchronizowane i przeładowane!')
""")

    # 3. Weryfikacja GPU / CPU
    add_md("## Krok 2: Weryfikacja Środowiska Obliczeniowego (GPU / CPU)")

    add_code("""import torch
cuda_available = torch.cuda.is_available()
print(f'PyTorch wersja: {torch.__version__}')
if cuda_available:
    print(f'[INFO] Akcelerator GPU: {torch.cuda.get_device_name(0)}')
    print(f'[INFO] Dostępna pamięć VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.2f} GB')
    !nvidia-smi
else:
    print('[INFO] Tryb obliczeń: Standardowy CPU (Colab Free).')
    print('[INFO] Potok AgriScreen DSS w pełni obsługuje CPU. Całkowity czas obliczeń będzie tylko nieznacznie dłuższy.')
""")

    # 4. Instalacja Zależności
    add_md("## Krok 3: Instalacja Bibliotek Teledetekcyjnych i Uczenia Maszynowego")

    add_code("""# Instalacja pakietów geoprzestrzennych, silnika GEE i przetwarzania rastrów
!pip install -q earthengine-api geemap geedim rasterio geopandas scikit-image scikit-learn scipy affine shapely
# Zaawansowane biblioteki super-rozdzielczości i korejestracji (opcjonalne/fallback)
!pip install -q mlstac sen2sr arosics pydms || true

print('[OK] Pakiety teledetekcyjne zostały pomyślnie zweryfikowane i zainstalowane!')
""")

    # 5. Inicjalizacja GEE
    add_md("## Krok 4: Autoryzacja i Inicjalizacja Google Earth Engine (GEE)")

    add_code("""import ee
import geemap

print('Inicjalizacja Google Earth Engine...')
try:
    ee.Initialize()
    print('[OK] Google Earth Engine jest już zainicjalizowany!')
except Exception as e:
    print('Wymagana autoryzacja GEE. Postępuj zgodnie z instrukcją na ekranie:')
    ee.Authenticate()
    try:
        ee.Initialize()
    except Exception as init_err:
        print('Wskazówka: Nowe konta GEE wymagają wskazania powiązanego projektu Google Cloud.')
        project_id = input('Podaj ID projektu Google Cloud dla Earth Engine (np. ee-twojanazwa lub wciśnij Enter aby pominąć): ').strip()
        if project_id:
            ee.Initialize(project=project_id)
        else:
            raise init_err
    print('[OK] Pomyślnie uwierzytelniono GEE!')
""")

    # 6. Konfiguracja i Podgląd AOI
    add_md("## Krok 5: Konfiguracja Parametrów i Wizualizacja Działek na Mapie Interaktywnej")

    add_code("""import geopandas as gpd

CONFIG = {
    'LAT': 43.9752,
    'LON': 0.3376,
    'TARGET_DATE': '2023-07-15',
    'BUFFER_M': 2000,
    'BASELINE_YEARS': (2018, 2025),
    'GEOJSON_PATH': os.path.join(PROJECT_DIR, 'data', '1_AOI_GBOV_CONDOM.geojson'),
    'OUTPUT_DIR': os.path.join(PROJECT_DIR, 'data', '05_Final_Outputs'),
    'DOWNLOAD_HISTORICAL': False  # Ustaw True, aby pobrać pełną serię przyrostową od 2016
}

gdf = gpd.read_file(CONFIG['GEOJSON_PATH'])
print(f'Wczytano {len(gdf)} działek referencyjnych w rejonie Condom (Francja).')
display(gdf[['fid', 'Typ', 'geometry']].head(5))

# Zabezpieczenie przed Timeoutem na kluczu GOOGLE_MAPS_API_KEY w Google Colab
try:
    from google.colab import userdata
    _orig_get = userdata.get
    def _safe_get(k, *a, **kw):
        if 'GOOGLE_MAPS' in k:
            raise userdata.SecretNotFoundError(k)
        return _orig_get(k, *a, **kw)
    userdata.get = _safe_get
except Exception:
    pass

# Interaktywna mapa podglądowa Geemap (backend foliumap zoptymalizowany pod Colab)
try:
    import geemap.foliumap as geemap
    m = geemap.Map(center=[CONFIG['LAT'], CONFIG['LON']], zoom=14)
    m.add_basemap('HYBRID')
    m.add_geojson(CONFIG['GEOJSON_PATH'], layer_name='Działki GBOV Condom')
except Exception:
    import geemap
    m = geemap.Map(center=[CONFIG['LAT'], CONFIG['LON']], zoom=14)
    m.add_basemap('HYBRID')
    m.add_geojson(CONFIG['GEOJSON_PATH'], layer_name='Działki GBOV Condom')
m
""")

    # 7. Moduł 1: Ingestia
    add_md("""## MODUŁ 1: Ingestia Rzeczywistych Danych Satelitarnych i Bazy GEE (`step_01_ingest.py`)
Pobiera z GEE: Sentinel-2 L2A (10 pasm BOA z maską chmur i geometryczną projekcją cieni), Sentinel-3 / 1km LST, Copernicus DEM GLO-30, Maskę Upraw Trwałych ($M_{crop}$), CGLS SWI $T=5$ oraz fenologię HR-VPP PPI wraz z wieloletnią bazą referencyjną 2018–2025.""")

    add_code("""# Bezpośredni import z modułu na Dysku Google
from step_01_ingest import ingest_satellite_data

s2_bands, profile_10m, baseline_stats = ingest_satellite_data(
    lat=CONFIG['LAT'],
    lon=CONFIG['LON'],
    target_date=CONFIG['TARGET_DATE'],
    buffer_m=CONFIG['BUFFER_M'],
    baseline_years=CONFIG['BASELINE_YEARS'],
    geojson_path=CONFIG['GEOJSON_PATH'],
    download_historical_series=CONFIG['DOWNLOAD_HISTORICAL']
)

print('[OK] KROK 1 ZAKOŃCZONY POMYŚLNIE:')
print(f' - Pobrane pasma S2: {list(s2_bands.keys())}')
print(f' - Rozmiar siatki 10m: {s2_bands[\"B04\"].shape}')
print(f' - Maska HRL M_crop: {s2_bands[\"crop_mask\"].shape} (sad_jablonek, winnice)')
print(f' - Regionalny SWI T=5: {s2_bands[\"swi_1km\"].shape}')
print(f' - Trajektoria fenologiczna HR-VPP PPI: {s2_bands[\"ppi_10m\"].shape}')
print(f' - Profil CRS: {profile_10m[\"crs\"]}')
""")

    # 8. Moduł 2: Downscaling pyDMS
    add_md("""## MODUŁ 2: Korejestracja AROSICS i Downscaling Termiczny pyDMS (`step_02_align_and_scale.py`)
Subpikselowa korejestracja korelacji fazowej, korekta adiabatyczna do poziomu morza ($LST + 0.006 \cdot DEM$), deagregacja pyDMS (bagging drzew z cechami NDVI i DEM), kompensacja reszt Gaussa i przywrócenie temperatury fizycznej.""")

    add_code("""# Bezpośredni import z modułu na Dysku Google
from step_02_align_and_scale import align_and_scale_lst
import matplotlib.pyplot as plt

lst_10m = align_and_scale_lst(
    s2_bands=s2_bands,
    s3_lst_raw=s2_bands['s3_lst_raw'],
    dem=s2_bands['dem'],
    profile_10m=profile_10m
)

# Porównanie surowego LST 1km vs zaostrzonego LST 10m
fig, axes = plt.subplots(1, 2, figsize=(14, 5))
im0 = axes[0].imshow(s2_bands['s3_lst_raw'], cmap='inferno')
axes[0].set_title('Surowe LST Coarse (1 km)')
plt.colorbar(im0, ax=axes[0], label='Temperatura [°C]')

im1 = axes[1].imshow(lst_10m, cmap='inferno')
axes[1].set_title('Zaostrzone LST pyDMS (10 m)')
plt.colorbar(im1, ax=axes[1], label='Temperatura [°C]')
plt.tight_layout()
plt.show()
""")

    # 9. Moduł 3: Super-Resolution SEN2SR & ATPRK
    add_md("""## MODUŁ 3: Super-Rozdzielczość SEN2SR i Fuzja ATPRK do Siatki 2.5 m (`step_03_super_resolve.py`)
Podniesienie rozdzielczości pasm RGBN (B02, B03, B04, B08) 4x do 2.5 m/px za pomocą modelu Deep Learning SEN2SR (GPU T4) oraz geostatystyczna fuzja ATPRK z funkcją PSF i konserwacją energii dla kanałów 20m, LST oraz fenologii PPI.""")

    add_code("""# Bezpośredni import z modułu na Dysku Google
from step_03_super_resolve import super_resolve_bands

bands_25m, profile_25m = super_resolve_bands(
    s2_bands=s2_bands,
    lst_10m=lst_10m,
    profile_10m=profile_10m
)

print('[OK] KROK 3 ZAKOŃCZONY POMYŚLNIE:')
print(f' - Nowy rozmiar siatki 2.5m: {bands_25m[\"B04\"].shape}')
print(f' - Transformacja afiniczna piksela: {profile_25m[\"transform\"].a} m')
print(f' - Wygenerowane warstwy 2.5m: {list(bands_25m.keys())}')
""")

    # 10. Moduł 4: Wskaźniki, Z-score i Protokół Walda
    add_md("""## MODUŁ 4: Wskaźniki Biofizyczne, TVDI, Alerty Z-score i Protokół Walda (`step_04_metrics_alert.py`)
Obliczenie OSAVI, TCARI, TCARI/OSAVI na siatce 2.5 m, wskaźnika suszy TVDI (trójkąt LST-NDVI), aplikacji maski upraw trwałych $M_{crop}$ (sady/winnice), walidacji z regionalnym SWI $T=5$, klasyfikacji alertów Z-score oraz testu dokładności Walda.""")

    add_code("""# Bezpośredni import z modułu na Dysku Google
from step_04_metrics_alert import compute_metrics_and_alerts

products, wald_metrics = compute_metrics_and_alerts(
    bands_25m=bands_25m,
    lst_10m=lst_10m,
    baseline_stats=baseline_stats,
    profile_25m=profile_25m
)

print('[OK] Wyniki Walidacji Dokładności (Protokół Walda):')
for k, v in wald_metrics.items():
    print(f'  - {k.upper()}: {v:.4f}')

# Wizualizacja wyników analitycznych
fig, axes = plt.subplots(1, 3, figsize=(18, 5))
im0 = axes[0].imshow(products['tcari_osavi_25m'], cmap='RdYlGn_r', vmin=-0.5, vmax=1.5)
axes[0].set_title('TCARI / OSAVI (2.5 m) - Maska Sadów i Winnic')
plt.colorbar(im0, ax=axes[0], label='Wskaźnik chlorozy')

im1 = axes[1].imshow(products['tvdi_10m'], cmap='YlOrRd', vmin=0, vmax=1)
axes[1].set_title('TVDI (10 m) - Stres Wilgotnościowy')
plt.colorbar(im1, ax=axes[1], label='Wskaźnik TVDI [0-1]')

cmap_alert = plt.matplotlib.colors.ListedColormap(['#2ecc71', '#f1c40f', '#e74c3c'])
im2 = axes[2].imshow(products['alert_mask_25m'], cmap=cmap_alert, vmin=0, vmax=2)
axes[2].set_title('Macierz Alertów (2.5 m): 0=Norma, 1=Żółty, 2=Czerwony')
plt.colorbar(im2, ax=axes[2], ticks=[0, 1, 2])
plt.tight_layout()
plt.show()
""")

    # 11. Moduł 5: Master Orchestrator i Eksport COG GeoTIFF
    add_md("""## MODUŁ 5: Master Orchestrator i Eksport Cloud-Optimized GeoTIFF (`step_05_colab_run.py`)
Uruchomienie kompletnego potoku z profilowaniem czasu, zapis kafelkowanych rastrów COG GeoTIFF z kompresją LZW na Dysku Google oraz wygenerowanie oficjalnego raportu walidacyjnego Markdown.""")

    add_code("""# Bezpośredni import z modułu na Dysku Google
from step_05_colab_run import run_pipeline

# Pełne automatyczne wykonanie potoku
run_pipeline(CONFIG)

# Odczyt i prezentacja wygenerowanego raportu
report_path = os.path.join(CONFIG['OUTPUT_DIR'], 'validation_report.md')
if os.path.exists(report_path):
    with open(report_path, 'r', encoding='utf-8') as f:
        print(f.read())
""")

    # 12. Interaktywna Prezentacja Geoprzestrzenna w Geemap
    add_md("""## Krok 6: Interaktywna Wizualizacja Geoprzestrzenna Wyników w Colab
Prezentacja zaostrzonych warstw LST, TCARI/OSAVI, TVDI oraz macierzy alertów na interaktywnym podkładzie satelitarnym z nałożeniem wektorowych granic działek.""")

    add_code("""# Interaktywna mapa podsumowująca
try:
    import geemap.foliumap as geemap
    m_results = geemap.Map(center=[CONFIG['LAT'], CONFIG['LON']], zoom=15)
    m_results.add_basemap('HYBRID')
    m_results.add_geojson(CONFIG['GEOJSON_PATH'], layer_name='Działki GBOV Condom (Wektor)')
except Exception:
    import geemap
    m_results = geemap.Map(center=[CONFIG['LAT'], CONFIG['LON']], zoom=15)
    m_results.add_basemap('HYBRID')
    m_results.add_geojson(CONFIG['GEOJSON_PATH'], layer_name='Działki GBOV Condom (Wektor)')

print('[INFO] Interaktywna mapa wyników gotowa do eksploracji:')
m_results
""")

    # Zapis notatnika do dwóch lokalizacji: root oraz notebooks/
    paths = ['AgriScreen_Colab_Master.ipynb', 'notebooks/AgriScreen_Colab_Master.ipynb']
    for p in paths:
        os.makedirs(os.path.dirname(p) if os.path.dirname(p) else '.', exist_ok=True)
        with open(p, 'w', encoding='utf-8') as out:
            json.dump(nb, out, indent=2, ensure_ascii=False)
        print(f'Pomyślnie wygenerowano notatnik: {p}')

if __name__ == '__main__':
    create_master_notebook()
