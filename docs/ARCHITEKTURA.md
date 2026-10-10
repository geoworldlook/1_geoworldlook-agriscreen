# AgriWatch — architektura (stan kodu v1.2)

> Opis tego, co jest zaimplementowane w `step_01…09` (stan na 2026-10-10, po wdrożeniu v1.1 „precyzja” i v1.2 „prezentacja”).
> Nie jest to plan ani zapis decyzji — plany są w `docs/plans/` (patrz „Dokumenty” na końcu). Stan projektu, wyniki
> i lista otwartych spraw: [`docs/MIGRACJA_PODSUMOWANIE.md`](MIGRACJA_PODSUMOWANIE.md).

## 1. Przepływ

```text
GitHub (kod) ──git pull──▶ Dysk Google: MyDrive/GeoWorldLook/agriwatch ◀──── Colab (GPU, GEE)
                                     │
notebooks/AgriWatch_Monitor.ipynb ──▶ step_05.setup_runtime ──▶ run_task(...) dla każdego zadania
                                                                   │
  ingest_s2 ─▶ ingest_era5 ─▶ scene_stats ─▶ anomalies ─▶ validate ─▶ weather ─▶ bulletin ─▶ dashboard ─▶ summary
  (step_01)    (step_01)      (step_03/04)   (step_04)    (step_07)   (step_08)  (step_04/09) (step_06/09)  (step_05)
                                                                   │
                                     data/registry/gwl_*.csv  +  data/05_Final_Outputs/agriwatch/
```

Każde zadanie jest wywoływane przez `run_task`, który zapisuje wiersz w `gwl_runs` (czas, status, commit gita
z flagą `+dirty`, parametry, liczba nowych wierszy). Błąd zadania jest zapisywany i nie zatrzymuje kolejnych.

## 2. Moduły

| Moduł | Odpowiedzialność | Główne funkcje |
|---|---|---|
| `step_01_ingest.py` | Pobieranie z Google Earth Engine | `initialize_earth_engine`, `load_aoi_geometry`, `add_cloud_and_shadow_mask`, `sync_sentinel2_time_series` (10 pasm L2A [0–1] + `cloudmask` + SCL, manifest `data/00_Metadata/ingest_manifest.json`, filtr miesięcy), `sync_era5_land_point` (ERA5-Land DAILY_AGGR w punkcie: wilgotność 3 warstw, opad, T, Tmin, Tmax; cache CSV w fragmentach 12-miesięcznych, ponowne pobieranie ostatnich 120 dni), `read_geotiff_to_numpy`, `write_geotiff` |
| `step_03_super_resolve.py` | SEN2SRLite „main” 10 m → 2,5 m | `load_sen2sr`, `super_resolve` (dopełnienie do kwadratu ≥ 128 px — obejście błędów `predict_large` w sen2sr 0.8.5), `sr_checks` (H-SR0, H-SR1, decyzja per wskaźnik), `plot_sr_comparison` |
| `step_04_metrics_alert.py` | Indeksy, anomalie, status, biuletyn | `compute_indices` (NDVI, NDMI, NDRE, CRSWIR), `site_stats`, `clim_anomaly`, `spi`, `era5_anomalies`, `track_ids`, `scene_anomaly`, `soil_drought_probability`, `build_status`, `build_bulletin` |
| `step_05_colab_run.py` | Sterowanie i rejestr | `setup_runtime`, `run_task`, `registry_read/upsert`, `MONITOR_CONFIG`, `monitor_config`, zadania `task_*`, `run_monitoring`, `--selftest` |
| `step_06_dashboard.py` | Dashboard winnicy (HTML, wzór: panel Wago z ESA WineEO) | `save_site_ndvi` (wycinki NDVI działki z `task_scene_stats`), `build_dashboard` (mapa NDVI na zdjęciu satelitarnym z wyborem daty, status, ryzyko suszy z prawdopodobieństwem, przyczyny, panele v1.2, pogoda ERA5 + prognoza Open-Meteo, przymrozki i upały, wiarygodność), `show_dashboard` |
| `step_07_station_pipeline.py` | Stacja ISMN: QC i walidacja anomalii; eksperymentalny potok S-1 | `qc_insitu`, `validate_anomalies` (używana w monitoringu); `extract_satellite`, `s1_change_detection`, `evaluate`, `run_station_pipeline` (potok S-1, poza statusem) |
| `step_08_weather.py` | Przymrozki, upały i walidacja ERA5-Land na stacjach Météo-France | `download_mf`, `read_mf`, `select_stations`, `validate_weather` (Tmin, Tmax, opad, SPI), `calibrated_thresholds`, `weather_hazards`, `hazard_summary` |
| `step_09_panels.py` | Panele prezentacji v1.2 (dashboard i biuletyn) | `condition_panel` („Kondycja winnicy”: NDVI, NDRE, NDMI), `season_trajectory` + `plot_season_trajectory` (krzywa sezonu), `signal_matrix` + `matrix_html` / `plot_signal_matrix` (matryca sygnałów), `_selftest_panels` |
| `build_colab_master.py` | Generator `notebooks/AgriWatch_Monitor.ipynb` (notatnika nie edytujemy ręcznie) | `create_monitor_notebook` |

Zależności między modułami: `step_05` importuje pozostałe moduły leniwie (wewnątrz zadań); `step_09` importuje `step_04`;
`step_06` używa `step_09` (błąd panelu daje kartę „Element niedostępny”, reszta dashboardu powstaje);
`step_07` używa z `step_01` tylko GEE, maski chmur i ERA5, a z `step_04` funkcji `clim_anomaly`, `rootzone`, `dekad_end`;
`step_08` używa `step_04.spi` i `dekad_end`.

## 3. Zadania monitoringu (`step_05`)

| Zadanie | Wejście | Wyjście |
|---|---|---|
| `task_ingest_s2` | AOI + bufor 320 m, sezon IV–X, ≤ 40% chmur nad AOI | `data/01_Raw_Sentinel2/S2_L2A_*.tif` |
| `task_ingest_era5` | centroid winnicy, 1991 → dziś | `data/02_ERA5_Land/era5_land_daily.csv` |
| `task_scene_stats` | nowe sceny (brak w `gwl_observations`), od najnowszej | statystyki obiektów 10 m i 2,5 m (tylko wskaźniki, których pasma przeszły H-SR0/H-SR1); QC SR jako `product = SR_QC` z wersją kontroli w `calib_id`; limit `SR_MAX_SCENES_PER_RUN` na uruchomienie; pokrycie SR w komunikacie (`sr_coverage`); zapis co 25 scen (wznawianie po przerwanej sesji); wycinki NDVI działki dla mapy |
| `task_anomalies` | ERA5, obserwacje roślinności | `gwl_anomalies`, `gwl_status` (z `p_soil_drought`), `era5_daily_anomalies.csv`, `veg_anomalies.csv` (NDVI, NDRE, NDMI, CRSWIR; kolumny `track`, `ref_mode`), `status_dekads.csv` |
| `task_validate` | anomalie i status | `gwl_validation_metrics`, `validation_anomalies.csv` (R anomalii vs ISMN 5 cm i 20–30 cm z CI, POD/FAR suchych dekad) |
| `task_weather` | pliki dobowe Météo-France (Gers, Lot-et-Garonne), ERA5-Land w punktach stacji | `validation_weather.csv`, `mf_stations.csv`, `hazard_thresholds.json`, `weather_hazards.csv`, `hazard_summary.csv`; metryki do `gwl_validation_metrics` |
| `task_bulletin` | status, anomalie, walidacja | `bulletin.md` (EN; panele v1.2 z podpisami PL), `season_*.png`, `last_12_months.png`, `last_5_years.png`, `season_trajectory.png`, `signal_matrix.png/.csv`, `agriwatch_latest.json` |
| `task_dashboard` | wyniki powyżej + wycinki NDVI działki (`SR_DIR/site_ndvi/`) | `dashboard.html` |
| `task_summary` | rejestr i wyniki | `run_summary.md` / `.json` — wersje, konfiguracja, kontrola SR, status per rok, walidacja, pogoda, ostatnie uruchomienia |

## 4. Metoda

- **Anomalie ERA5-Land** (`clim_anomaly`): z-score i percentyl względem klimatologii dnia roku 1991–2020 (okno ±15 dni,
  konwencja WMO; obejmuje lata 2016–2020, więc dla nich nie jest przyczynowa).
  Wilgotność strefy korzeni = średnia warstw 0–7, 7–28, 28–100 cm ważona grubością; warstwa 0–7 cm informacyjnie.
- **SPI-1, SPI-3** (`spi`): sumy 30 i 90 dni, rozkład gamma dopasowany dla pory roku, z prawdopodobieństwem zera.
- **Anomalie roślinności** (`scene_anomaly`, Plan v7 A1–A3): dla sceny z roku Y odniesieniem są sceny tylko z lat
  **wcześniejszych** (`VEG_CAUSAL`), najwyżej `VEG_REF_YEARS` = 5 (zmiana gospodarki międzyrzędziem daje trend NDVI),
  ±15 dni roku, z **tego samego toru orbity** S-2 (`VEG_BY_TRACK`; tor rozpoznawany z godziny przelotu, `track_ids`;
  gdy scen z toru za mało — oba tory, `ref_mode = all_tracks`), min. 5 scen odniesienia, tylko sceny z ≥ 90% czystych
  pikseli. z predykcyjne z rozkładu t-Studenta (`VEG_PREDICTIVE_Z`), żeby częstość z ≤ −1 odpowiadała rozkładowi
  normalnemu przy krótkiej historii. Liczone dla NDVI, NDRE, NDMI i CRSWIR; status używa tylko NDVI (`VEG_INDEX`).
- **Status** (`build_status`): na koniec każdej dekady; obserwuj = SPI-1 ≤ −2 lub SPI-3 ≤ −1; sucho = anomalia gleby
  0–100 cm ≤ −1; sprawdź winnicę = sucho oraz anomalia NDVI winnicy ≤ −1 (roślinność tylko w IV–X i nie starsza niż
  30 dni); powrót do normy = po „sucho”/„sprawdź” anomalie nadal ujemne. `confidence` = high / medium / low zależnie od
  dostępności i wieku sceny.
- **Prawdopodobieństwo suszy gleby** (`soil_drought_probability`, Plan v7 A7 w wersji jednoźródłowej):
  p = P(anomalia ISMN 20–30 cm ≤ −1 | anomalia ERA5-Land z) = Φ((−1 − ρz)/√(1−ρ²)), ρ = `PSMA_RHO` = 0,58
  (korelacja ERA5-Land z ISMN Condom). Kolumna `p_soil_drought` w statusie, pokazywana na dashboardzie.
  Ocena Brierem jest na razie poza potokiem (Plan v7, krok A5).
- **Walidacja** (`step_07.validate_anomalies`): R anomalii klimatologicznych i 35-dniowych z 95% CI z bootstrapu
  blokowego (30 dni); 5 cm osobno dla każdego czujnika (wymiana w 2019 r.); 20–30 cm jako strefa korzeni; roślinność
  w dniu sceny (10 m i SR 2,5 m, także sparowane); POD/FAR suchych dekad (z ≤ −1). Okres ISMN z nazw plików
  (`END_DATE = "auto"`). QC czujników: flaga ISMN, zakres, zamrożone wartości, okres wymiany czujnika 5 cm;
  flagi utraty kontaktu 20/30 cm (QC-4 z `docs/evidence/Condom_QC.md`) jeszcze nie ma (Plan v7, krok A4).
- **Pogoda** (`step_08`): przymrozki wiosenne (Tmin ≤ próg, 15 III – 15 V) i upały (Tmax ≥ próg, VI–VIII) z ERA5-Land
  w punkcie winnicy. Progi kalibrowane tylko na stacji Météo-France w promieniu 5 km (Condom, 0,2 km), na latach
  < 2021, i tylko gdy jest ≥ 10 zdarzeń i CSI rośnie o ≥ 0,05; inaczej próg nominalny (0 °C, 35 °C). POD/FAR na
  latach ≥ 2021 dla progu używanego w produkcie (D-049).
- **Panele v1.2** (`step_09`): kondycja winnicy (najnowsze z NDVI, NDRE, NDMI z klasą słowną i R wobec ISMN; NDRE
  i NDMI informacyjnie, D-051), krzywa sezonu (pasmo 10–90% NDVI z 5 lat ściśle wcześniejszych; gleba na tle normy
  1991–2020), matryca sygnałów (kaskada CDI, ostatnie 36 dekad, wybór sceny jak w statusie).
- **Rozdzielczość detekcji: SR 2,5 m** (`VEG_PRODUCT = "S2SR_2.5m"`, decyzja 2026-10-07). Każda scena wchodząca do
  detekcji jest po SEN2SR; scena, która nie przeszła kontroli pasm 10 m, nie wchodzi do detekcji (bez zastępstwa 10 m).
  NDVI 10 m jest liczony dalej jako odniesienie (segment `anomaly_clim_paired`). Wynik walidacji: SR 2,5 m jest
  równoważny 10 m dla sygnału (ΔR +0,004 [0,000; 0,009], Plan v7 ustalenie 14), więc SR zostaje do map.
- **Kontrola SR:** H-SR0 — `std(SR − bikubika) / std(SR) ≥ 0,02` (model faktycznie działał);
  H-SR1 — RMSE(SR uśredniony do natywnej rozdzielczości pasma, wejście) w reflektancji (spójność radiometryczna):
  pasma 10 m (B02, B03, B04, B08) w blokach 4×4, próg stały 0,01; pasma 20 m (B05–B07, B8A, B11, B12) w blokach 8×8
  względem pikseli 20 m (przesunięcie siatki wykrywane z powielonych pikseli), próg = specyfikacja dokładności L2A
  `SR_20M_SPEC_FACTOR · (0,05·ρ + 0,005)` (Vermote 2008), ρ = średnia reflektancja pasma w scenie.
  **Decyzja per wskaźnik** (`step_03.INDEX_BANDS`): NDVI (B04, B08), NDMI (B8A, B11), NDRE (B8A, B05),
  CRSWIR (B8A, B11, B12) z 2,5 m tylko, gdy przeszły wszystkie ich pasma. Szacowany błąd wskaźnika z SR
  (`{idx}_sr_err`) zapisywany w `SR_QC` dla każdej sceny. Brak modelu = błąd zgłoszony, bez zastępstwa interpolacją.
  Wersja kontroli: `SR_QC_VERSION = "qc4"`, `SR_20M_SPEC_FACTOR = 1,5`. W przebiegu 2026-10-09: 414 scen ocenionych,
  NDVI z 2,5 m przyjęte w 98,3%; mediana błędu NDVI z SR 0,009, NDMI 0,04, NDRE 0,035, CRSWIR 0,085.
- **Ryzyko przyjęte świadomie (2026-10-07):** pasma 20 m po SR mają błąd spójności kilkunastokrotnie większy niż pasma
  10 m; NDMI, NDRE i CRSWIR z 2,5 m mają błąd ~0,03–0,09 na piksel, porównywalny z typową zmiennością międzyroczną.
  Dlatego nie wchodzą do logiki statusu.

## 5. Rejestr `gwl_*` (Dysk Google, `data/registry/`)

Pliki CSV o nazwach i kolumnach przyszłej bazy danych. `registry_upsert` dopisuje wiersze według klucza głównego:
nowy klucz → dopisany, zmieniona wartość → zastąpiony, bez zmian → zostaje stary wiersz. Zapis atomowy.

| Tabela | Klucz |
|---|---|
| `gwl_sites` | `site_id` |
| `gwl_observations` | `site_id, product, variable, time_utc, orbit` |
| `gwl_anomalies` | `site_id, product, date` |
| `gwl_validation_metrics` | `site_id, product, reference, segment, period, subset, metric` |
| `gwl_calibrations` | `calib_id, site_id, product, orbit, param` |
| `gwl_status` | `site_id, date` |
| `gwl_runs` | `run_id` |

Pełny schemat: `REGISTRY_SCHEMA` w `step_05_colab_run.py`.

## 6. Konfiguracja

Jedno miejsce: `MONITOR_CONFIG` w `step_05_colab_run.py` (ścieżki względne liczone od `PROJECT_DIR`).
Kolejna winnica = nowy wpis w `VINEYARDS` (`{"site_id": fid}` z `data/1_AOI_GBOV_CONDOM.geojson`).
Konfiguracja stacji ISMN: `STATION_CONFIG` w `step_07_station_pipeline.py`.

## 7. Testy offline

```bash
python step_05_colab_run.py --selftest --out <katalog>   # cały monitoring (~6 min): syntetyczne S-2, ERA5 i Météo-France,
                                                         # prawdziwe ISMN i działki, atrapa SEN2SR; panele v1.2 i test wycieku
python step_08_weather.py                                # pogoda: odczyt MF, kalibracja progów, walidacja
python step_07_station_pipeline.py --selftest            # potok S-1 stacji (wymaga pytesmo)
python -m pyflakes step_0*.py step_09_panels.py          # znane: 2× undefined name 'pd' w step_01 (adnotacje)
```

## 8. Dokumenty

| Dokument | Status |
|---|---|
| `docs/MIGRACJA_PODSUMOWANIE.md` | stan projektu, audyt wyników, następne kroki (2026-10-10) |
| `docs/plans/Plan_v7_precyzja.md` | `PROPOSED` (2026-10-08), etap A wdrożony poza A4/A5; decyzje D-040…D-051 |
| `docs/evidence/F4_eksperymenty/`, `F5_asymilacja_danych.md`, `F7_v12/` | dowody do Planu v7 i v1.2 (eksperymenty offline z recenzjami) |
| `docs/evidence/F6_alerty_strefowe.md` | przegląd i projekt alertów w obrębie działki (niewdrożone) |
| `docs/plans/Plan_v3_monitoring_winnic_SR.md` | `APPROVED` (2026-10-06); część A = przegląd literatury, z którego korzysta kod (EDO CDI, walidacja anomalii, SR) |
| `docs/plans/Plan_v6_platforma_anomalii_wilgotnosci.md` | `PROPOSED` (2026-10-07) — platforma na wzór WineEO dla 15 winnic; przegląd i propozycje Z1–Z8 w `docs/evidence/F3_przeglad_literatury_platforma.md` |
| `docs/plans/Plan_v5_bilans_wodny_winnic.md` | `PROPOSED` (bilans wodny FAO-56) — niezatwierdzony; eksperyment F4 B nie potwierdził zysku |
| `docs/plans/Plan_v4_cel_zawodowy.md` | `SUPERSEDED` |
| `docs/plans/F0…`, `F1…`, `Plan_wdrozenia_pipeline.md`, `Plan_GeoWorldLook_Jupyter_Colab.md`, `Plan_6_tygodni.md` | historyczne; odwołują się do plików `step_02`, `step_06` z v2.5, które są teraz w `legacy/` |
| `docs/evidence/F1_evidence_brief.md`, `docs/evidence/Condom_QC.md` | analizy źródłowe (reguły QC-1, QC-2, QC-5 wdrożone w `step_07.qc_insitu`; QC-4 — krok A4) |

## 9. `legacy/`

Poprzedni potok AgriScreen v2.5 (LST z H-pyDMS, ATPRK, TCARI/OSAVI, TVDI, walidacja Landsat) i poprzednie wersje modułów
(`*_v1.py`). Nie jest uruchamiany i nie jest utrzymywany; zostaje jako archiwum. Obecny kod korzysta wyłącznie z danych
satelitarnych Copernicus (D-048).
