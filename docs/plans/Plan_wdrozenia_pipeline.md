# AgriWatch — plan wdrożenia pipeline'u wilgotności gleby z super-rozdzielczością

> **Status:** `PROPOSED` (2026-09-26) — do zatwierdzenia przez użytkownika
> **Zastępuje:** `F0_plan_jakosci_kodu.md` (restrukturyzacja do pakietu — odrzucona) oraz część architektoniczną `F1_system_wilgotnosci_plan.md` (walidacja z tego dokumentu zostaje)
> **Podstawa naukowa:** `docs/evidence/F1_evidence_brief.md`

---

## 0. Założenia od użytkownika (2026-09-26)

1. Pipeline modułowy, działający, z minimum pracy ręcznej.
2. Super-resolution jako odważny, nowatorski element — z gotowych bibliotek.
3. Złożony pipeline złożony z **gotowych, sprawdzonych narzędzi**.
4. Jedna osoba: **obecna struktura plików zostaje** (`step_01…step_06` + notatnik). Zmieniamy jakość naukową i wyniki, nie architekturę.
5. Cel: **wyniki do pokazania klientowi i rekruterowi**, szybko. Bez mnożenia skryptów.

Konsekwencje: nie tworzymy pakietu `src/`, nie tłumaczymy kodu, nie dodajemy nowych plików `.py`. Każda zmiana trafia do jednego z sześciu istniejących modułów.

---

## 1. Koncepcja naukowa w trzech zdaniach

- **Radar Sentinel-1 mówi *kiedy i ile* wody jest w glebie** — co 6–12 dni, niezależnie od chmur, w rozdzielczości 20 m.
- **Super-rozdzielczy Sentinel-2 (SEN2SR, 2,5 m) mówi *gdzie* w obrębie działki** jest sucho, a gdzie mokro — przez pasma SWIR (metoda OPTRAM), które SEN2SR wyostrza z 20 m do 2,5 m (8×).
- **Fuzja zachowująca bilans** łączy oba: średnia wilgotność w każdym bloku 20 m jest dokładnie równa pomiarowi radarowemu, a wzór wewnątrz bloku pochodzi z SR. Termika (LST 1 km → 20 m, pyDMS) jest trzecim, opcjonalnym sygnałem.

```text
 S-1 GRD (VV, VH) ──► change detection ──► SM_20m [m³/m³] ──────────────┐
   (GEE, 20 m)        per orbita, kalibracja 2016–2021                   │
                                                                          ▼
 S-2 L2A 10 pasm ──► SEN2SR (10 → 2,5 m) ──► OPTRAM (STR–NDVI) ──► wzór W_2.5m ──► FUZJA z zachowaniem średniej bloku 20 m
   (GEE, 10 m)        test spójności radiometrycznej                                 │
                                                                                      ▼
 LST 1 km ──► pyDMS (Sen-ET) ──► LST_20m ──► efektywność ewaporacji (opcja) ─► SM_2.5m ─► anomalie (pytesmo) ─► status per działka
                                                                                      │
 ISMN Condom (5 cm) + ERA5-Land + CGLS SWI 1 km ─────────────────────────────────────►│ WALIDACJA: 2,5 m vs 20 m vs 1 km vs czujnik
```

**Nowatorskie:** OPTRAM na pasmach SWIR wyostrzonych przez sieć neuronową do 2,5 m i użyty jako wzór przestrzenny do downscalingu radarowej wilgotności. Każdy element osobno jest opublikowany i sprawdzony. Ich połączenie nie jest standardem — to wyróżnik projektu.

**Uczciwe:** walidacja wprost odpowiada na pytanie, czy wersja 2,5 m zgadza się z czujnikiem lepiej niż 20 m i 1 km (sekcja 5). Jeśli nie — mówimy to i pokazujemy 2,5 m jako wizualizację wzoru w działce, a nie pomiar.

---

## 2. Stos gotowych narzędzi

| Zadanie | Narzędzie | Status | Uzasadnienie |
|---|---|---|---|
| S-2, S-1, ERA5-Land, LST, DEM | Google Earth Engine (`earthengine-api`, `geemap`) | **już używane** | Działa w obecnym kodzie |
| SWI 1 km, HR-VPP | CDSE Process API | **już używane** | Działa w obecnym kodzie |
| Super-resolution S-2 | **SEN2SR** (`mlstac`, `sen2sr`) — model `SEN2SRLite/main`, 10 pasm → 2,5 m | poprawka | ESA OpenSR, RSE 2025, licencja otwarta |
| Downscaling LST | **pyDMS** (`python_dms`) — Data Mining Sharpener | nowe (zastępuje własny kod) | Implementacja referencyjna Sen-ET (Guzinski & Nieto 2019); GPL-3 |
| Klimatologia i anomalie | **pytesmo** `time_series.anomaly` | nowe użycie | Standard QA4SM |
| Metryki walidacji | **pytesmo** `metrics` | już częściowo | Standard QA4SM |
| Dane in situ | **ismn** `ISMN_Interface` | **już używane** | Oficjalna biblioteka TU Wien |
| Fuzja ML (etap M3) | **scikit-learn** RandomForest | już zainstalowane | Drzewa ≥ głębokie sieci przy małej liczbie próbek |
| Resampling i agregacja | **rasterio** `reproject` (`Resampling.average`) | zamiast `scipy.zoom` | Poprawna geometria i średnie powierzchniowe |

---

## 3. Moduły — co robi każdy plik po zmianach

Zasada: każdy moduł ma **jedną funkcję główną** (tak jak dziś), zapisuje wyniki na Dysk od razu i pomija to, co już jest policzone (cache jak w `step_01`).

### `step_01_ingest.py` — dane (rozszerzenie, bez przebudowy)

| Zmiana | Szczegóły |
|---|---|
| **+ Sentinel-1** | `COPERNICUS/S1_GRD`, IW, VV+VH, `angle`, orbita względna i kierunek; seria 2016 → dziś. Dwa tryby: (a) **tabela punktowa** — `reduceRegions` dla 22 działek, poligonu stacji i 21 stacji SMOSMANIA (szybkie, bez rastrów); (b) rastry 20 m tylko dla AOI |
| **+ ERA5-Land** | `ECMWF/ERA5_LAND/DAILY_AGGR` (wilgotność warstwy 1, opad, T2m) w tych samych punktach — benchmark i maska mrozu/opadu |
| LST | Region eksportu LST powiększony do ~30 × 30 km (wymóg pyDMS); oznaczenie źródła (S3/MODIS/ERA5) w nazwie pliku i w manifeście |
| Baseline GEE | Poprawka K-01: nazwy zgodne z treścią (`ndvi_mean` zamiast `tvdi_mean`) |
| Bez zmian | S-2 + maska chmur, DEM, SWI, HR-VPP, synchronizacja przyrostowa, manifest |

### `step_02_align_and_scale.py` — termika (uproszczenie)

- **Zastąpienie** `HybridThermalSharpener` wywołaniem **pyDMS** (`DecisionTreeSharpener`, regresja liniowa w liściach, korekta reszt `residualAnalysis`).
- Trening na scenie 30 km, zastosowanie w AOI; wynik LST 20 m + mapa reszt.
- **Usunięcie:** AROSICS (K-11), TsHARP ze stałymi β/γ, clipping 5–60 °C bez flagi.
- Wynik pomocniczy: efektywność ewaporacji gleby (SEE) do fuzji (etap M3).

### `step_03_super_resolve.py` — super-resolution (naprawa + rozszerzenie)

| Zmiana | Szczegóły |
|---|---|
| **Poprawne ładowanie modelu (K-09)** | `mlstac.download(...)` raz na Dysk (`data/models/SEN2SRLite_main`), potem `mlstac.load(...)`; brak modelu = **błąd z jasnym komunikatem**, bez cichego przejścia na bikubikę |
| **Model `SEN2SRLite/main`** | Wszystkie 10 pasm (w tym B11, B12) → 2,5 m; kolejność pasm zgodna z README (B02, B03, B04, B05, B06, B07, B08, B8A, B11, B12). Obecny kod podaje RGBN w złej kolejności (B02, B03, B04, B08 zamiast B04, B03, B02, B08) |
| **Test spójności radiometrycznej (automatyczny)** | Każdą scenę SR agregujemy średnią 4×4 z powrotem do 10 m i porównujemy z oryginałem; RMSE per pasmo zapisany w manifeście; scena powyżej progu jest odrzucana |
| **Seria czasowa** | SR dla każdej bezchmurnej sceny nad AOI (przyrostowo, cache na Dysku), nie tylko dla jednej daty |
| **Fuzja zachowująca średnią** | Istniejąca `atprk_fusion_channel` przerobiona na fuzję SM: regresja + korekta reszt **średnią blokową** (dziś: interpolacja — K-10) |
| Siatka | `scipy.zoom` zastąpiony przez `rasterio.reproject` / agregację blokową (K-14) |
| Bez zmian | Eksport RGB, porównanie 10 m vs 2,5 m, mapa folium |

### `step_04_metrics_alert.py` — wilgotność i anomalie (rdzeń naukowy)

1. **SM z S-1 (change detection)** — per piksel/działka i per orbita względna:
   - σ⁰ w skali liniowej do uśredniania, dB do modelu;
   - odniesienia suche/mokre = percentyl 5/95 z **okresu kalibracji 2016–2021**;
   - SM_rel = (σ⁰ − σ⁰_dry) / (σ⁰_wet − σ⁰_dry), przycięte do [0, 1];
   - konwersja do m³/m³ przez porowatość z danych glebowych (nie z czujnika Condom — brak przecieku);
   - flagi: NDVI > 0,7 (`DENSE_VEGETATION`), mróz (ERA5 T2m < 0 °C), opad w ciągu 24 h.
2. **OPTRAM na SR 2,5 m** — STR = (1 − B12)² / (2·B12) oraz NDVI; krawędzie sucha i mokra wyznaczone z chmury punktów **wszystkich dat i pikseli AOI** (zgodnie z metodą); W ∈ [0, 1].
3. **Fuzja 2,5 m** — SM_2.5m = SM_20m + β·(W − średnia_bloku(W)); β z regresji w okresie kalibracji; średnia bloku zachowana dokładnie.
4. **Anomalie** — `pytesmo.time_series.anomaly`: klimatologia dnia roku (2016–2024) i anomalie 35-dniowe; percentyle; status `normal / watch / inspect` + `confidence` + `reason_codes`; progi w `CONFIG`.
5. **Warstwy wtórne (bez zmian merytorycznych, po poprawkach):** TCARI/OSAVI z kierunkowym Z (K-02), TVDI jako warstwa referencyjna.
6. **Protokół Walda na prawdziwym SEN2SR** (K-05) + test spójności z `step_03`.

### `step_05_colab_run.py` — orkiestrator

- Jeden `CONFIG` (także ścieżki Colab/lokalne). Notatnik importuje go i nadpisuje tylko ścieżki — koniec duplikacji konfiguracji.
- `run_pipeline(CONFIG)` robi wszystko przyrostowo: sync → SR nowych scen → SM → fuzja → anomalie → walidacja → raport.
- Wyjścia:
  - COG na Dysku,
  - **tabela per działka i data** (`data/05_Final_Outputs/parcel_timeseries.csv`),
  - raport `report.md` (EN) z wykresami.
- Usunięcie cichych wartości zastępczych w trybie awaryjnym (K-06); brak danych = wyraźny błąd lub flaga.

### `step_06_station_api.py` — walidacja

- **Poprawka K-13:** ekstrakcja z rastrów tylko wskazanych produktów (wzorzec nazwy per produkt), nie z dowolnego `*.tif`.
- Porównanie **czterech skal** na poligonie `stacja`: SM_2.5m (fuzja), SM_20m (S-1), CGLS SWI 1 km, ERA5-Land.
- Kolokacja czasowa z przelotem S-1 (±1 h, czasy z metadanych sceny, nie stałe 11:00).
- Metryki pytesmo: bias, RMSD, ubRMSD, R, ρ, R anomalii (35 dni i klimatologia), n, **95% CI** (bootstrap blokowy).
- **Skalowanie tylko na okresie kalibracji** (2016–2021), test na 2022–2024 (K-15: dziś min-max liczone na danych testowych).
- Epizody przesuszenia: POD, FAR (in situ < 20. percentyla).
- Usunięcie ścieżek zastępczych (ERA5 jako satelita, czujnik vs czujnik — K-07) i zdań zakodowanych na sztywno w raporcie.

### Notatnik (`build_colab_master.py`)

- Mniej komórek:
  1. montowanie + `git pull`,
  2. instalacja,
  3. GEE + klucze,
  4. **`run_pipeline(CONFIG)`**,
  5. prezentacja wyników (mapa, wykres Condom, raport).
- Usunięcie podwójnego uruchamiania (dziś moduły 1–4 w komórkach, a potem `run_pipeline` jeszcze raz — K-16).

---

## 4. Lista błędów do naprawy

| ID | Moduł | Błąd | Wpływ na wynik |
|---|---|---|---|
| K-09 | 03 | Model SEN2SR nigdy nie jest pobierany; cichy fallback na bikubikę; zła kolejność pasm RGBN | **Krytyczny** — „2,5 m SR” to interpolacja |
| K-13 | 06 | Walidacja czyta dowolny `*.tif` z datą (RGB, pasma, LST) jako TVDI | **Krytyczny** — metryki walidacji z przypadkowych plików |
| K-14 | 02, 03, 04 | `scipy.ndimage.zoom` wyrównuje narożniki, nie siatki → przesunięcie do ~1,5 piksela 2,5 m na krawędziach | Wysoki — błędna koregistracja 2,5 m ↔ 10 m |
| K-10 | 03 | Agregacja interpolacją zamiast średnią blokową; „zachowanie energii” nie działa | Wysoki |
| K-15 | 06 | Skalowanie min-max na tych samych danych, na których liczone są metryki | Wysoki — zawyżone wyniki |
| K-06 | 02–05 | Ciche wartości zastępcze (0,15/0,05, SWI 50, PPI 0,45, 28 °C) | Wysoki |
| K-01, K-02 | 01, 04 | Baseline „TVDI” to NDVI; alert z \|Z\| | Średni |
| K-11 | 02 | AROSICS bez efektu | Niski (strata czasu) |
| K-16 | notatnik | Podwójne uruchamianie potoku | Niski (czas) |
| K-05, K-07 | 04, 06 | Wald na bikubice; walidacja zastępcza | Średni |

---

## 5. Walidacja w Condom (skrót — szczegóły w `F1_system_wilgotnosci_plan.md`, sekcja 4)

- Referencja: 5 cm, flaga `G` **plus własna kontrola jakości** (`docs/evidence/Condom_QC.md`): artefakt wymiany czujnika do wykluczenia, **dwa niezależne segmenty 5 cm** (ML3 2016–2019, ML2x 2019–2024), możliwy dryf od końca 2022, utrata kontaktu 20/30 cm latem. Główne metryki: R, ρ i R anomalii w obrębie segmentu; test na 2022–2024 w segmencie ML2x.
- **Główne pytanie produktu:** czy SM_2.5m ≥ SM_20m ≥ SWI 1 km ≥ ERA5-Land wobec czujnika? Tabela 4 skal × metryki z CI to **najmocniejszy slajd dla rekrutera**.
- Kalibracja 2016–2021, test 2022–2024 (w tym okres z samym S-1A — raportowany osobno).
- Etap M3: model RF trenowany na pozostałych stacjach SMOSMANIA, Condom wyłączony (leave-one-station-out).
- Kryteria sukcesu zapisujemy **przed** pierwszym testem.

---

### 5.1 Trzy poziomy dowodu (dodane 2026-09-26)

| Poziom | Dane | Co waliduje | Czego nie waliduje |
|---|---|---|---|
| **1. Punkt — Condom** | ISMN SMOSMANIA Condom 5/10/20/30 cm (2016–2024); GBOV RM10 (to te same dane 5 cm, przetworzone) i **RM11 (opad przy stacji)** | Dynamikę w czasie, anomalie, porównanie 4 skal na otwartym polu uprawnym | Zachowania w winnicach i sadach; wzoru 2,5 m wewnątrz działki |
| **2. Sieć — SMOSMANIA** | 20 pozostałych stacji (uprawy, łąki, rejony winiarskie Langwedocji: Pézenas, Villevielle, Cabrières-d'Avignon) | Przenośność na inne miejsca (leave-one-station-out). Stacje w odległości < 5 km (Pézenas, Pézenas-old, Prades-le-Lez) tworzą **jedną grupę**, żeby nie było przecieku | Jak wyżej |
| **3. Działki — winnice** | **Dane terenowe użytkownika** (do opisania) albo kampania z ręczną sondą TDR | Dokładność w winnicach; czy wzór 2,5 m (rzędy / międzyrzędzia) jest prawdziwy | — |

Bez poziomu 3 mapa 2,5 m jest prezentowana jako „szacunek wzoru w działce”, a nie jako zwalidowany pomiar.

### 5.2 Ograniczenia wykonalności (dodane 2026-09-26)

- **Miejsce na Dysku:** pełne 10 pasm SR 2,5 m dla AOI to ok. 80 MB na scenę; kilkaset scen nie zmieści się w 15 GB. Zapisujemy tylko produkty pochodne (W OPTRAM, NDVI, SM 2,5 m jako COG z kompresją, typ `int16` ze skalą). Pełne pasma SR tylko dla dat pokazowych.
- **GPU w Colab (darmowy):** limity dzienne i rozłączenia. SR przyrostowo z cache — przerwane uruchomienie wznawia się od ostatniej sceny.
- **pyDMS (M3):** sceny 30 km i dane S-2 20 m z tego obszaru na każdą datę — cięższe pobrania; pierwszy kandydat do cięcia.
- **Użycie komercyjne:** GEE i Colab tylko do czasu platformy (F2); sprzedaż wymaga ingestii z CDSE.

## 6. Harmonogram (10 h/tydzień)

Każdy kamień milowy kończy się **artefaktem do pokazania**.

| Kamień | Termin | Zakres | Artefakt do pokazania |
|---|---|---|---|
| **M1 — Radar i pierwsza walidacja** | 28 IX → 18 X 2026 | Naprawy krytyczne K-13, K-15, K-06; S-1 i ERA5-Land w `step_01` (tabela punktowa); SM z S-1 w `step_04`; walidacja w `step_06` | **Wykres Condom 2016–2024: S-1 vs czujnik vs SWI vs ERA5 + tabela metryk z CI** |
| **M2 — Super-resolution** | 19 X → 8 XI | K-09, K-10, K-14; SEN2SR `main` dla serii scen z testem spójności; OPTRAM 2,5 m; fuzja SM 2,5 m; Wald na SEN2SR | **Mapa 2,5 m wilgotności nad sadami i winnicami + porównanie 10 m / 2,5 m + tabela 4 skal w Condom** |
| **M3 — Termika i ML** | 9 XI → 29 XI | pyDMS; SEE; RF na stacjach SMOSMANIA (LOSO); ablacje: z SR / bez SR, z LST / bez LST | **Tabela ablacji: co daje SR, co daje termika** |
| **M4 — Produkt v0.1** | 30 XI → 20 XII | Anomalie i status per działka; `parcel_timeseries.csv`; raport EN; uproszczony notatnik jednym kliknięciem; README EN | **Raport Evidence + animacja anomalii sezonu 2023 + demo w 5 minut** |

**Cięcia przy opóźnieniu:** najpierw M3 (termika i ML — zostają na styczeń), nigdy M1 i walidacja.

Po M4 (styczeń 2027) → platforma (F2 z planu v2): te same wyniki na mapie w GeoWorldLook.

---

## 7. Co upraszczamy albo usuwamy

| Element | Decyzja | Dlaczego |
|---|---|---|
| Pakiet `src/agriwatch`, YAML, CLI (plan F0) | **Wycofane** | Wymóg użytkownika: obecna struktura zostaje |
| Tłumaczenie kodu na EN | **Wycofane** | Tylko README i raport po angielsku |
| AROSICS, TsHARP, własny H-pyDMS | Usunięte / zastąpione pyDMS | Gotowe, sprawdzone rozwiązanie |
| ATPRK dla LST i PPI → 2,5 m | Usunięte | Brak informacji w 2,5 m; źródło błędów |
| ATPRK — silnik | **Przerobiony na fuzję SM** | Wykorzystanie istniejącego kodu |
| TCARI/OSAVI, TVDI | Warstwy wtórne | Rdzeniem jest wilgotność |

---

## 8. Decyzje do zatwierdzenia

| ID | Decyzja |
|---|---|
| D-013 (zaktualizowana) | Produkt = wilgotność gleby i jej anomalie; **S-1 + SEN2SR (OPTRAM 2,5 m) w rdzeniu**, fuzja zachowująca średnią; LST opcjonalnie; walidacja w Condom z porównaniem 4 skal |
| D-014 | Struktura plików `step_01…06` zostaje; plan F0 (pakiet) i decyzje D-008, D-011 → `Rejected`; D-009, D-010, D-012 → wchodzą w ten plan |
| D-015 | Harmonogram M1–M4 (do 20 XII 2026) zastępuje F0 i F1; bramka F1 → ocena po M2 (8 XI) i M4 (20 XII) |
