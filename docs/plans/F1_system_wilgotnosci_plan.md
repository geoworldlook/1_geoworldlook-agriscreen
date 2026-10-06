> **STATUS: częściowo `Superseded` (2026-09-26)** — architektura modułów (sekcja 5) i harmonogram (sekcja 6) zastąpione przez `Plan_wdrozenia_pipeline.md`. **Projekt walidacji (sekcja 4) nadal obowiązuje.**

# AgriWatch — system szacowania anomalii wilgotności gleby: plan wdrożeniowy

> **Status:** `PROPOSED` (2026-09-26) — wymaga zatwierdzenia decyzji **D-013** (`ZMIANA DECYZJI`)
> **Podstawa naukowa:** `docs/evidence/F1_evidence_brief.md` (źródła S01–S20)
> **Obszar:** AOI GBOV Condom (Gers) — 22 działki (sady jabłoni, winnice, gleba odkryta) + poligon stacji
> **Referencja:** ISMN SMOSMANIA Condom (5, 10, 20, 30 cm), pozostałe stacje SMOSMANIA jako zbiór treningowy

---

## 0. Wymagana zmiana decyzji — D-013

| | Plan v2 | Propozycja D-013 |
|---|---|---|
| Główna wielkość | Stres cieplny (ΔT, TVDI) z LST 10 m | **Wilgotność powierzchniowa gleby (0–5 cm) i strefy korzeniowej (0–30 cm) oraz ich anomalie**, w skali działki |
| Rdzeń sensorowy | S-3 LST + S-2 | **S-1 (radar) + S-2**; S-3 LST jako cecha uzupełniająca |
| Sentinel-1 | Backlog | **Rdzeń** |
| Rola SR 2,5 m | Podgląd, bramka SR | Bez zmian: podgląd + eksperyment (maska rzędów) |
| Walidacja | Pośrednia (stres vs wilgotność gleby) | **Bezpośrednia**: produkt w m³/m³ vs czujnik w m³/m³ |
| Bramka F1 | 2027-01-31 | **2027-02-28** (+1 miesiąc) |
| Termin MVP | 2027-06-01 | Bez zmian (F2 krótszy o miesiąc: Mar–Maj) |

**Dlaczego:** przegląd (Evidence Brief F1) pokazuje, że wiarygodne szacowanie wilgotności w skali działki opiera się na S-1. LST pomaga pośrednio (ewaporacja), a TVDI na małym AOI jest niestabilny. Walidacja bezpośrednia w Condom jest znacznie silniejszym dowodem dla klienta i rekrutera niż porównanie pośrednie.

**Wpływ:** więcej pracy w F1 (dochodzi przetwarzanie S-1), mniej w F2. Cel końcowy i daty F3/F4 bez zmian.

**Rekomendacja:** `ZMIENIĆ`.

---

## 1. Cel i hipotezy

### Cel produktu

Dla każdej działki co 6–12 dni (przelot S-1) oraz dodatkowo w dni bezchmurne (S-2):

1. **SSM**: wilgotność 0–5 cm [m³/m³] z niepewnością;
2. **RZSM**: wilgotność 0–30 cm [m³/m³] (filtr wykładniczy);
3. **Anomalia**: odchylenie standaryzowane i percentyl względem klimatologii dnia roku;
4. **Status**: `normal / watch / inspect` + `confidence` + `reason_codes`.

### Hipotezy badawcze — każda ma test

| ID | Hipoteza | Test | Kryterium |
|---|---|---|---|
| H1 | Estymacja S-1 + S-2 w skali działki odtwarza dynamikę wilgotności 5 cm w Condom lepiej niż produkty grubej skali | Porównanie z ERA5-Land, CLMS SSM 1 km, CLMS SWI 1 km, S²MP (jeśli dostępny) | R anomalii i ubRMSD lepsze od najlepszego benchmarku; CI różnicy nie obejmuje 0 |
| H2 | Cechy termiczne (LST po downscalingu, efektywność ewaporacji) poprawiają estymację, zwłaszcza przy NDVI > 0,7 | Ablacja: model z LST vs bez | Poprawa R anomalii ≥ 0,05 w okresie z NDVI > 0,7 |
| H3 | OPTRAM (S-2) wnosi informację w dni bezchmurne przy małej pokrywie | Ablacja | Jak H2 |
| H4 | Cechy z SR 2,5 m (udział koron/międzyrzędzi) poprawiają estymację w sadach/winnicach | Ablacja | **Nie do zweryfikowania w Condom** (stacja na otwartym polu) → pozostaje eksperymentem |
| H5 | System wykrywa epizody przesuszenia widoczne w in situ | Zdarzenia: anomalia in situ < 20. percentyla | POD ≥ 0,6, FAR ≤ 0,4 (progi zamrożone przed testem) |

---

## 2. Architektura logiczna

```text
                            ┌────────────────────────────────────────┐
                            │  AOI: działki (GeoJSON) + scena robocza  │
                            │  30 × 30 km wokół Condom (UTM 31N)       │
                            └───────────────────┬────────────────────┘
      ┌──────────────────────┬─────────────────┼───────────────────┬──────────────────────┐
      v                      v                 v                   v                      v
 [A] Sentinel-1 GRD     [B] Sentinel-2 L2A  [C] Sentinel-3 LST  [D] Kotwice grube     [E] In situ ISMN
 VV, VH, kąt padania    NDVI, NDRE, STR,    SLSTR 1 km          ERA5-Land (SM, opad,  SMOSMANIA 21 stacji
 10 m → 20 m            maska chmur         + Landsat ST        T2m), CLMS SSM/SWI    5/10/20/30 cm
 (asc + desc)           10–20 m             (walidacja LST)     1 km, S²MP (Theia)    flagi G
      │                      │                 │                   │                      │
      v                      v                 v                   │                      │
 ┌──────────────────────────────────────────────────────────┐      │                      │
 │ WARSTWA 1 — retrievale fizyczne (bez danych treningowych)│      │                      │
 │  R1 change detection S-1 (per piksel, suche/mokre odn.)  │      │                      │
 │  R2 Water Cloud Model: σ0 VV − wkład roślinności (NDVI)  │      │                      │
 │  R3 OPTRAM: trapez NDVI–STR (S-2, bezchmurnie)           │      │                      │
 │  R4 DMS: LST 1 km → 20 m (trening na scenie 30 km)       │      │                      │
 │     + efektywność ewaporacji gleby (DISPATCH)            │      │                      │
 └──────────────────────────┬───────────────────────────────┘      │                      │
                            v                                      v                      │
 ┌──────────────────────────────────────────────────────────────────────────┐            │
 │ WARSTWA 2 — fuzja (gradient boosting / RF)                                │<── trening ┤
 │  wejścia: R1–R4, σ0, NDVI, kąt, opad 1/3/7 dni, ERA5-Land SM, CLMS SSM    │   (stacje  │
 │  wyjście: SSM 0–5 cm [m³/m³] + niepewność (kwantyle)                      │   ≠ Condom)│
 └──────────────────────────┬────────────────────────────────────────────────┘            │
                            v                                                              │
 ┌──────────────────────────────────────────────────────────────────────────┐            │
 │ WARSTWA 3 — produkty                                                      │            │
 │  SSM per działka (średnia pikseli wewnętrznych, bez krawędzi)             │            │
 │  RZSM = filtr wykładniczy SWI(T), T kalibrowane na 20/30 cm               │            │
 │  Anomalia: z-score i percentyl vs klimatologia DOY (±15 dni)              │            │
 │  Status + confidence + reason_codes                                       │            │
 └──────────────────────────┬────────────────────────────────────────────────┘            │
                            v                                                              v
 ┌──────────────────────────────────────────────────────────────────────────────────────────┐
 │ WALIDACJA — Condom (stacja nigdy nie użyta w treningu) + test przestrzenny LOSO          │
 │  metryki surowe i anomalii, zdarzenia suche, benchmarki, ablacje, raport Evidence        │
 └──────────────────────────────────────────────────────────────────────────────────────────┘

 Warstwa wizualna (poza estymacją): SEN2SR 2,5 m RGBN — podgląd działek i rzędów
```

---

## 3. Metody — wybory i uzasadnienie

### 3.1 Sentinel-1 (rdzeń, R1 i R2)

| Element | Wybór | Uzasadnienie |
|---|---|---|
| Dane | S-1 GRD IW, VV + VH, σ0 po korekcie terenu (R&D: GEE `COPERNICUS/S1_GRD`; produkcja: CDSE) | Standard; GEE ma gotowe σ0 |
| Normalizacja kąta | σ0 do kąta referencyjnego 40° (regresja per piksel) albo modele osobno per orbita względna | Condom widziany z kilku orbit (asc ~18 UTC, desc ~6 UTC — do potwierdzenia) |
| Speckle | Filtr wieloczasowy + **agregacja do działki** (średnia w dB→liniowo→dB) | Wynik w skali piksela 10 m jest za zaszumiony (S07, S11) |
| R1 change detection | Per piksel: m_v = (σ0 − σ0_dry) / (σ0_wet − σ0_dry), z percentyli serii 2016–2021 (S08) | Nie wymaga treningu; dobre na równinach rolniczych |
| R2 WCM | σ0_VV = σ0_veg(NDVI, θ) + τ²(NDVI, θ) · σ0_soil(m_v, θ); parametry z literatury (S06) i kalibracja na stacjach treningowych | Jawna korekta roślinności |
| Ograniczenie | NDVI > 0,7 → `confidence` obniżone, kod `DENSE_VEGETATION` | S07, S10 |
| Luka 2022–2024 | Tylko S-1A (12 dni) → w metrykach osobne raportowanie okresów | S11, S20 |

### 3.2 Sentinel-2 (R3 + korekta roślinności)

- NDVI, NDRE (10–20 m), **STR = (1 − R_SWIR)² / (2·R_SWIR)** z B12 (OPTRAM, S12).
- OPTRAM: krawędzie suchą i mokrą wyznaczamy na scenie roboczej 30 km i wielu datach (nie na AOI), per typ pokrycia.
- Maska chmur: SCL + s2cloudless; brak interpolacji czasowej danych do walidacji.

### 3.3 Termika (R4) — nowa rola LST

- Źródło: **S-3 SLSTR L2 LST** (CDSE), dziennie ~10:00 czasu lokalnego; MODIS tylko jako jawna alternatywa.
- **DMS trenowany na scenie 30 × 30 km** (≥ 400 pikseli 1 km), stosowany w AOI (S14). Cechy: odbicia S-2, NDVI, DEM, nachylenie.
- Walidacja LST: Landsat 8/9 ST jako niezależna referencja (nie wejście) — zakres z planu v2 (F1.4) zostaje, ale jako **kontrola jakości cechy**, a nie produkt.
- Cecha dla wilgotności: **efektywność ewaporacji gleby** SEE = (T_s,max − T_s) / (T_s,max − T_s,min) ze składowej glebowej LST, z krawędziami na scenie 30 km (DISPATCH, S13).
- TVDI: tylko jako cecha porównawcza, liczony na scenie 30 km, nie na AOI (S15).

### 3.4 Super-resolution (warstwa wizualna + eksperyment H4)

- SEN2SR (RGBN ×4, wagi CC0, S16) z jawnym pobraniem modelu (problem K-09).
- Produkt: podgląd 2,5 m dla użytkownika z etykietą „wizualizacja”.
- Eksperyment H4: klasyfikacja korona / międzyrzędzie na 2,5 m → udział frakcji gleby w pikselu 20 m jako cecha fuzji. Wynik raportujemy, ale nie da się go zwalidować w Condom.

### 3.5 Kotwice grubej skali

- **ERA5-Land** (godzinowo, ~9 km): wilgotność warstwy 1, opad, T2m, promieniowanie; klimatologia 1991–2020.
- **CLMS SSM 1 km** (S-1 change detection) i **CLMS SWI 1 km**: benchmark i cecha.
- **S²MP (Theia)**: benchmark w skali działki, jeśli pokrywa Condom.

### 3.6 Fuzja (warstwa 2)

- Model: **LightGBM lub Random Forest**, regresja kwantylowa (P10/P50/P90 → niepewność). Drzewa ≥ sieci głębokie przy tej liczbie danych (S19).
- Próbki: pary (stacja, przelot S-1) ze stacji SMOSMANIA **poza Condom**. Szacunek do potwierdzenia w discovery: 20 stacji × ~60–120 przelotów/rok × 8 lat.
- Cel treningu: wilgotność 5 cm in situ w oknie ±1 h od przelotu.
- **Zakaz przecieku:** Condom nigdy w treningu ani strojeniu; strojenie hiperparametrów przez GroupKFold po stacjach.
- Wyjaśnialność: SHAP per cecha → `reason_codes` w produkcie.

### 3.7 Strefa korzeniowa i anomalie (warstwa 3)

- **RZSM:** SWI_n = SWI_{n−1} + K_n(SSM_n − SWI_{n−1}), K_n = K_{n−1}/(K_{n−1} + e^{−Δt/T}) (S04). T kalibrowane na stacjach treningowych na 20 i 30 cm; w Condom tylko test.
- **Klimatologia:** per działka, DOY ± 15 dni, z serii satelitarnej 2016–2024, zakotwiczona w ERA5-Land 1991–2020 przez dopasowanie dystrybuant (CDF matching) (S17).
- **Anomalie:**
  - długoterminowa: z = (SM − μ_DOY) / σ_DOY oraz percentyl;
  - krótkoterminowa: odchylenie od średniej ruchomej 35 dni (zgodność z QA4SM, S03).
- **Status** (progi w YAML, do zamrożenia przed testem): `watch` przy percentylu < 20 lub z < −1; `inspect` przy percentylu < 10 lub z < −1,5, utrzymującym się przez ≥ 2 kolejne obserwacje.
- **Confidence:** obniżane przez NDVI > 0,7, brak S-1 > 12 dni, rozrzut kwantyli, małą liczbę pikseli w działce, mróz lub śnieg (ERA5 T2m < 0), opad w ciągu 24 h przed przelotem (mokra powierzchnia).

---

## 4. Projekt walidacji w Condom

### 4.1 Przygotowanie referencji

1. Tylko flaga `G`; zachowanie odrzuconych rekordów z powodem.
2. **5 cm = seria złożona:** ML3 (2016-01 → 2019-02) + ML2x (2019-02 → 2024-12). Test jednorodności: porównanie z 10 cm i ERA5-Land przed/po zmianie. Przy przesunięciu → dwie niezależne klimatologie albo dopasowanie CDF z adnotacją.
3. Klimatologia in situ (DOY ± 15 dni) z 2016–2024 do anomalii referencyjnych.
4. Brak imputacji w danych walidacyjnych.

### 4.2 Kolokacja

| Wymiar | Reguła |
|---|---|
| Czas | Obserwacja in situ najbliższa przelotowi S-1, |Δt| ≤ 1 h; dla S-2/S-3 ≤ 1 h od przelotu |
| Przestrzeń | Trzy warianty raportowane równolegle: (a) poligon `stacja` (≈ 2 × 2 piksele), (b) bufor 100 m, (c) piksel 1 km dla benchmarków |
| Głębokość | 5 cm dla SSM; 0–30 cm (średnia ważona 5/10/20/30) dla RZSM; głębokości nigdy nie mieszane |

### 4.3 Podział danych

| Zbiór | Stacje | Okres | Użycie |
|---|---|---|---|
| Trening | SMOSMANIA bez Condom | 2016–2021 | Fit modeli, kalibracja WCM i T |
| Walidacja | SMOSMANIA bez Condom | 2022 | Strojenie, wybór cech, progi statusu |
| **Test Condom** | **Condom** | **2016–2024** (cała seria; stacja niewidziana) | Wynik główny |
| Test czasowy | Wszystkie bez Condom | 2023–2024 | Stabilność w czasie (okres tylko S-1A) |
| Test przestrzenny | Leave-one-station-out | 2016–2024 | Przenośność na inne miejsca |

**Rejestracja przed testem:** progi sukcesu H1–H5, progi statusu i lista cech zapisujemy w dokumencie nr 3 **przed** pierwszym uruchomieniem na Condom. Wynik testu nie może zmieniać modelu.

### 4.4 Metryki

- Surowe: bias, RMSD, **ubRMSD**, Pearson R, Spearman ρ, n — z 95% CI (bootstrap blokowy, bloki 30 dni).
- Anomalie: R anomalii krótkoterminowych (35 dni) i długoterminowych (klimatologia).
- Zdarzenia: POD, FAR, CSI, Heidke Skill Score dla „przesuszenia” (in situ < 20. percentyla DOY).
- Rozbicie: sezon, NDVI < / > 0,7, okres S-1A+B vs S-1A, orbita asc/desc.
- **Benchmarki na tych samych datach:** ERA5-Land, CLMS SSM 1 km, CLMS SWI 1 km, S²MP, klimatologia (model „zawsze średnia”).
- Opcjonalnie: triple collocation (produkt, ERA5-Land, in situ) do oszacowania błędów losowych bez zakładania, że in situ nie ma błędu.
- Porównanie z QA4SM (tylko benchmarki dostępne na platformie) jako kontrola konfiguracji.

### 4.5 Kryteria sukcesu (wstępne — do zamrożenia przed testem)

| Poziom | Kryterium w Condom (SSM 5 cm) | Interpretacja |
|---|---|---|
| **Sukces** | R anomalii ≥ 0,5, ubRMSD ≤ 0,06 m³/m³, lepszy od najlepszego benchmarku (CI różnicy > 0), H5 spełniona | Produkt: anomalia wilgotności w skali działki |
| **Częściowy** | Nie lepszy od benchmarku, ale R anomalii ≥ 0,4 | Produkt: CLMS/ERA5 jako tło + S-1 jako lokalny sygnał z niskim `confidence`; rozwijamy dalej |
| **Porażka** | R anomalii < 0,4 | Produkt nie obiecuje wilgotności działki; publikujemy negatywny wynik; F2 na produktach 1 km + stres cieplny |

Poziomy w literaturze dla odniesienia: S-1 + S-2 w skali 1 km R ≈ 0,56, SDD 0,05–0,06 (S07); produkty w SW Francji RMSD ≈ 7,6 vol.% (S05).

### 4.6 Uczciwe ograniczenia walidacji

- Jedna stacja w AOI → wynik ważny dla punktu Condom i podobnych warunków (glina, uprawa polowa), a **nie** automatycznie dla sadów i winnic.
- S-1 widzi warstwę ~1–5 cm; czujnik mierzy ~5 cm → różnica głębokości w suszy (S10).
- ThetaProbe w glebie ilastej: możliwy błąd kalibracji czujnika → raportujemy bias osobno od ubRMSD.

---

## 5. Architektura techniczna

### 5.1 Moduły (rozszerzenie pakietu z planu F0)

```text
src/agriwatch/
├── io/
│   ├── s1.py            # GEE/CDSE: σ0 VV/VH, kąt, orbita; ekstrakcja serii w punktach/działkach
│   ├── s2.py            # NDVI, NDRE, STR, maska chmur
│   ├── s3_lst.py        # SLSTR L2 LST z CDSE + flagi
│   ├── landsat.py       # ST do walidacji LST
│   ├── era5.py          # ERA5-Land (CDS API)
│   ├── clms.py          # CLMS SSM/SWI 1 km (CDSE)
│   ├── theia.py         # S²MP (benchmark)
│   └── ismn.py          # odczyt, flagi, jednorodność, klimatologia
├── retrieval/
│   ├── change_detection.py   # R1
│   ├── wcm.py                # R2
│   ├── optram.py             # R3
│   └── evaporative.py        # R4: SEE / DISPATCH
├── thermal/dms.py            # downscaling LST na scenie 30 km
├── superres/sen2sr.py        # podgląd + cechy H4 (experimental)
├── fusion/
│   ├── features.py           # tabela cech (jedna definicja dla treningu i produkcji)
│   ├── model.py              # LightGBM/RF kwantylowy, zapis modelu z wersją
│   └── explain.py            # SHAP → reason_codes
├── products/
│   ├── rzsm.py               # filtr wykładniczy
│   ├── anomaly.py            # klimatologia, z-score, percentyle, 35-dniowe
│   └── status.py             # normal/watch/inspect + confidence
├── validation/
│   ├── matchups.py           # tabela par z powodami odrzuceń
│   ├── metrics.py            # pytesmo + bootstrap CI
│   ├── events.py             # POD/FAR/CSI/HSS
│   └── ablation.py           # H2–H4
└── reporting/evidence.py     # raport Evidence (Markdown + wykresy)
```

### 5.2 Dwa tryby przetwarzania — najpierw punkty, potem mapy

| Tryb | Co | Gdzie | Koszt |
|---|---|---|---|
| **Punktowy** (F1) | Serie czasowe cech w 21 stacjach i 22 działkach → tabela Parquet | GEE `reduceRegions` / CDSE; Colab CPU | Mały: kilkadziesiąt MB |
| **Mapowy** (F1 koniec, F2) | Rastry 20 m / wartości per działka dla AOI i Languedoc | Colab (R&D), potem Docker/CDSE (F2) | Większy: tylko po udanej walidacji |

Cała nauka (retrievale, fuzja, walidacja) odbywa się na **tabeli punktowej**. Mapy robimy dopiero dla metody, która przeszła walidację. To oszczędza tygodnie obliczeń.

### 5.3 Dane i miejsce przechowywania (zgodnie z obecnym przepływem)

| Artefakt | Format | Miejsce |
|---|---|---|
| Kod | Python | GitHub → klon na Dysku |
| In situ ISMN | `.stm` → Parquet po QA | Dysk: `data/7_isismn_data`, `data/10_Matchups` |
| Tabela cech i match-upów | Parquet (1 plik na źródło + tabela złączona) | Dysk: `data/10_Matchups/` |
| Modele | `joblib` + JSON z metadanymi (wersja, cechy, zakres treningu) | Dysk: `data/11_Models/` |
| Mapy | COG z tagami pochodzenia | Dysk: `data/05_Final_Outputs/` |
| Wyniki walidacji | Parquet + raport Markdown + PNG | Dysk + `docs/evidence/` w repo (tylko raport, bez danych) |

Nowe katalogi `10_Matchups` i `11_Models` dodajemy do `.gitignore`.

---

## 6. Harmonogram wdrożenia

Założenia: 10 h/tydzień; F0 (październik) bez zmian, z jedną korektą: F0.3 buduje **ogólny silnik anomalii** (`products/anomaly.py`), a nie tylko alert TCARI/OSAVI.

### F1 — Wilgotność: retrieval i walidacja · 2026-11-02 → 2027-02-28 (17 tygodni)

| Tydzień | Zadanie | Wynik | DoD |
|---|---|---|---|
| 1 (XI) | **F1.1** Domknięcie Evidence Brief: pełne teksty S02, S07, S11, S13, S14; sprawdzenie S²MP i CLMS | Brief `Approved` | Lista parametrów z uzasadnieniem |
| 2–3 | **F1.2** Referencja in situ: QA 21 stacji SMOSMANIA, test jednorodności Condom 5 cm, klimatologie | `ismn_qc.parquet`, raport QA | Każde odrzucenie ma powód; decyzja o serii 5 cm |
| 4–6 | **F1.3** Tabela match-upów w punktach: S-1, S-2, ERA5-Land, CLMS, (S²MP) | `matchups_v1.parquet` | Discovery z liczbą par per stacja; kolumny Δt, orbita, NDVI, powód odrzucenia |
| 7 | **F1.4** Benchmarki w Condom i LOSO: ERA5-Land, CLMS SSM/SWI, S²MP, klimatologia | Tabela „poziom do pobicia” | Metryki z CI |
| 8–10 (w tym przerwa świąteczna) | **F1.5** Retrievale fizyczne R1 (change detection), R2 (WCM), R3 (OPTRAM) na stacjach treningowych/walidacyjnych | Serie R1–R3 | Metryki na zbiorze walidacyjnym (bez Condom) |
| 11–12 | **F1.6** Termika: S-3 LST, DMS na scenie 30 km, kontrola z Landsat, cecha SEE | Serie R4 + raport LST | LST: bias/RMSE vs Landsat z n i CI |
| 13–14 | **F1.7** Fuzja + ablacje H2–H4; **zamrożenie modelu i progów** (rejestracja w dok. nr 3) | `model_v1` | GroupKFold po stacjach; zapis przed testem |
| 15 | **F1.8** Jednorazowy test w Condom + LOSO + zdarzenia (H1, H5) | Wyniki testu | Uruchomiony dokładnie raz, zapisany bez zmian |
| 16 | **F1.9** RZSM (filtr wykładniczy) + anomalie + status; mapy AOI dla metody zwycięskiej | Mapy + serie per działka | COG z pochodzeniem |
| 17 | **F1.10** Raport Evidence (EN) + **bramka F1** | `docs/evidence/F1_report.md` | Decyzja: sukces / częściowy / porażka |

**Bufor:** brak jawnego. Przy opóźnieniu tniemy w kolejności: H4 (SR) → R3 (OPTRAM) → triple collocation. Nie tniemy F1.2–F1.4 ani F1.8.

### F2 — MVP platformy · 2027-03-01 → 2027-05-31 (skrócony)

Zakres z planu v2 z dwiema zmianami:

- Produkt na mapie: **SSM, RZSM i anomalia per działka**, status, `confidence`, `reason_codes`, szereg czasowy z opadem; stres cieplny (LST) jako druga zakładka, jeśli H2 pozytywna.
- Ingestia produkcyjna rozszerzona o S-1 (CDSE) i ERA5-Land.
- Cięcie zakresu przy zagrożeniu terminu: e-mail tygodniowy → płatności → funkcje UI; nigdy ingestia i silnik statusu.

### F3–F4 — bez zmian

W sezonie 2027 piloci dostarczają obserwacje terenowe. Po sezonie liczymy metryki alertów (precision/recall) na działkach pilotów — to pierwsza walidacja w sadach i winnicach, której Condom nie zapewnia.

---

## 7. Ryzyka

| Ryzyko | Prawdopodobieństwo | Działanie |
|---|---|---|
| S-1 nie widzi gleby w sadach/winnicach latem (NDVI > 0,7) | Wysokie | Obniżone `confidence`; w tych okresach cechy termiczne i RZSM z filtra; jawne w Limitations |
| Za mało par in situ – S-1 (szczególnie 2022–2024) | Średnie | Discovery w F1.3 przed modelowaniem; wszystkie orbity asc + desc |
| Zmiana czujnika 5 cm w Condom (2019) psuje klimatologię | Średnie | Test jednorodności w F1.2 |
| S²MP niedostępny dla Condom | Średnie | Benchmark z CLMS i ERA5 wystarcza |
| DMS wymaga dużych scen → dłuższe obliczenia | Średnie | Tryb punktowy; scena 30 km tylko dla dni z S-3 bezchmurnych |
| Wynik gorszy niż benchmarki grubej skali | Realne | Poziom „częściowy / porażka” z góry zdefiniowany; negatywny wynik też jest wartościowym artefaktem portfolio |
| 170 h pracy w F1 przy pełnym etacie | Wysokie | Kolejność cięć w sekcji 6; bramka przesunięta tylko o miesiąc |

---

## 8. Co zostaje z obecnego kodu

| Moduł obecny | Los |
|---|---|
| `step_01_ingest.py` (S-2, DEM, CDSE SWI/HR-VPP, manifest) | Zostaje → `io/s2.py`, `io/clms.py`; baseline TCARI → `products/anomaly.py` |
| `step_02_align_and_scale.py` (DMS/TsHARP) | Przebudowa → `thermal/dms.py` (scena 30 km); TsHARP i AROSICS usunięte |
| `step_03_super_resolve.py` (SEN2SR, ATPRK) | SEN2SR → `superres/` (podgląd); ATPRK → `experimental/` |
| `step_04_metrics_alert.py` (TCARI/OSAVI, TVDI, Z, Wald) | Wskaźniki → `io/s2.py` jako cechy; Z → `products/anomaly.py`; Wald → `validation/` (F0.4) |
| `step_06_station_api.py` (ISMN, QA4SM) | Rdzeń → `io/ismn.py`, `validation/metrics.py` |

---

## 9. Następne kroki

1. Zatwierdzenie **D-013** (`ZMIANA DECYZJI`) → aktualizacja dokumentów 1 i 2 (F1 zastąpione sekcją 6 tego planu).
2. F0 w październiku bez zmian, poza F0.3 (ogólny silnik anomalii).
3. F1.1 w pierwszym tygodniu listopada: domknięcie Evidence Brief.
