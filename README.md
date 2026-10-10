# AgriWatch — monitoring suszy dla winnicy (Condom, Gers)

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/geoworldlook/1_geoworldlook-agriscreen/blob/main/notebooks/AgriWatch_Monitor.ipynb)

Monitoring anomalii suszy dla jednej winnicy (`VINEYARD_06`, 2,9 ha, 136 m od stacji ISMN SMOSMANIA Condom)
z otwartych danych: ERA5-Land i Sentinel-2 po super-resolution SEN2SR do 2,5 m (rozdzielczość detekcji), plus
przymrozki i upały walidowane na stacjach Météo-France. Dane satelitarne wyłącznie z programu Copernicus.
Status dekadowy wzorowany na Combined Drought Indicator (CDI) Europejskiego Obserwatorium Suszy (EDO):

| Status | Warunek | Akcja |
|---|---|---|
| `watch` | SPI-1 ≤ −2 lub SPI-3 ≤ −1 (deficyt opadu) | watch |
| `warning` | anomalia wilgotności strefy korzeni (ERA5-Land 0–100 cm) ≤ −1 | watch |
| `alert` | `warning` oraz anomalia NDVI winnicy ≤ −1 | inspect |
| `recovery` | po `warning`/`alert` spadek poniżej progów, anomalie nadal ujemne | normal |

Anomalia NDVI liczona jest wobec 5 poprzednich lat (bez lat przyszłych), z tego samego toru orbity Sentinel-2.
Do statusu dołączone jest prawdopodobieństwo suszy w glebie p = Φ((−1 − ρz)/√(1−ρ²)), ρ = 0,58.
Błąd anomalii jest walidowany na profilu glebowym stacji ISMN Condom (5–30 cm); alarm `alert` (gleba + roślinność)
nie jest jeszcze zwalidowany na stanie wodnym winorośli. Wyniki i ich ocena: [`docs/MIGRACJA_PODSUMOWANIE.md`](docs/MIGRACJA_PODSUMOWANIE.md), sekcja 5.

**Architektura:** kod na GitHub → obliczenia w Google Colab (GPU, Google Earth Engine) → Dysk Google jako baza danych
(`MyDrive/GeoWorldLook/agriwatch`, tabele CSV `data/registry/gwl_*`). Szczegóły: [`docs/ARCHITEKTURA.md`](docs/ARCHITEKTURA.md).

## Struktura repozytorium

```text
├── step_01_ingest.py            # GEE: Sentinel-2 L2A (przyrostowo, manifest) + maska chmur, ERA5-Land w punkcie, GeoTIFF I/O
├── step_03_super_resolve.py     # SEN2SRLite 10 m -> 2,5 m z kontrolą H-SR0/H-SR1 (bez zastępstwa interpolacją)
├── step_04_metrics_alert.py     # indeksy obiektów, anomalie (klimatologia przyczynowa), SPI, status dekadowy, biuletyn
├── step_05_colab_run.py         # sterowanie z notatnika: setup_runtime, run_task, rejestr gwl_*, zadania monitoringu
├── step_06_dashboard.py         # dashboard winnicy (wzór: panel Wago, ESA WineEO): mapa NDVI, status, ryzyko, pogoda
├── step_07_station_pipeline.py  # stacja ISMN Condom: QC in situ, walidacja anomalii z CI; eksperymentalny potok S-1
├── step_08_weather.py           # przymrozki i upały, walidacja ERA5-Land na stacjach Météo-France
├── step_09_panels.py            # panele v1.2: kondycja winnicy, krzywa sezonu, matryca sygnałów
├── build_colab_master.py        # generator notatnika (notatnika nie edytujemy ręcznie)
├── notebooks/AgriWatch_Monitor.ipynb
├── data/
│   ├── 1_AOI_GBOV_CONDOM.geojson         # działki (winnice, sady, poligon stacji)
│   ├── 1_AOI_GBOV_CONDOM_ZASIEG.geojson  # zasięg pobierania
│   └── 7_isismn_data/                    # pomiary ISMN SMOSMANIA 2016–2024 (21 stacji)
├── docs/                        # architektura, plany, dowody (evidence), podsumowanie projektu
└── legacy/                      # poprzednia wersja (AgriScreen v2.5): LST, ATPRK, TCARI/OSAVI, TVDI — nieużywana
```

Numeracja kroków nie jest ciągła: krok 2 z v2.5 jest w `legacy/`.

## Uruchomienie

1. Otwórz `notebooks/AgriWatch_Monitor.ipynb` w Colab **z GitHuba** (przycisk powyżej albo Plik → Otwórz → GitHub),
   nie z kopii na Dysku. Środowisko z GPU jest potrzebne tylko przy nowych scenach (SR).
2. `Uruchom wszystko`. Notatnik montuje Dysk, klonuje lub aktualizuje repozytorium w `MyDrive/GeoWorldLook/agriwatch`,
   instaluje pakiety, inicjalizuje GEE (projekt `ee-geoworldlook`) i wykonuje zadania:
   `ingest_s2 → ingest_era5 → scene_stats → anomalies → validate → weather → bulletin → dashboard → summary`.
3. Wyniki: `data/05_Final_Outputs/agriwatch/` (**`dashboard.html`**, biuletyn, wykresy, `agriwatch_latest.json`)
   i tabele `data/registry/gwl_*.csv`. Dashboard wyświetla się w notatniku (sekcja 6).
4. Po uruchomieniu prześlij `run_summary.md` (sekcja 7 notatnika): wersje, konfiguracja, kontrola SR, status, walidacja, błędy.

## Stan wersji

| Wersja | Zakres |
|---|---|
| 1.0 (2026-10-07) | status EDO z SPI, wilgotności gleby ERA5-Land i NDVI 2,5 m, walidacja ISMN, dashboard w Colab |
| 1.1 (2026-10-09) | Plan v7, etap A: klimatologia roślinności tylko z lat wcześniejszych, ten sam tor orbity, z predykcyjne, prawdopodobieństwo suszy gleby; przymrozki i upały z walidacją Météo-France |
| 1.2 (2026-10-09) | prezentacja: panel kondycji winnicy (NDVI, NDRE, NDMI), krzywa sezonu, matryca sygnałów; okres ISMN z plików (`END_DATE = "auto"`) |

Otwarte: QC czujników ISMN (A4) i protokół walidacji z Brierem w kodzie (A5) — `docs/plans/Plan_v7_precyzja.md`.
Stan projektu, audyt wyników i kolejność dalszych prac: [`docs/MIGRACJA_PODSUMOWANIE.md`](docs/MIGRACJA_PODSUMOWANIE.md).
Architektura i metoda: [`docs/ARCHITEKTURA.md`](docs/ARCHITEKTURA.md).

Testy offline (bez GEE i GPU; prawdziwe dane ISMN i działki, syntetyczne dane satelitarne i Météo-France):

```bash
python step_05_colab_run.py --selftest --out <katalog>   # ok. 6 min
python step_08_weather.py
python step_07_station_pipeline.py --selftest             # potok S-1 (wymaga pytesmo)
```

## Zależności

`earthengine-api geemap geedim rasterio geopandas numpy pandas scipy matplotlib pytesmo ismn`;
dla super-resolution dodatkowo `sen2sr mlstac torch` (wymagane do detekcji; środowisko Colab z GPU —
na CPU około 1 min na scenę). Bez SR status liczy się bez warstwy roślinności.
