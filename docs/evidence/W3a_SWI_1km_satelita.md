# W3a — satelitarna wilgotność gleby: CLMS Soil Water Index 1 km (notatka metodyczna)

> **Status:** `PROPOSED` (2026-10-14) — metoda ustalona **przed** pobraniem danych SWI i przed jakąkolwiek walidacją
> (pre-rejestracja jak w A4). Plan v9, krok W3a (D-072).

## Wynik w skrócie

1. **Produkt:** CLMS Soil Water Index 1 km, Europa, dziennie, od 2015 r. — wilgotność gleby z radaru: Sentinel-1 (1 km)
   połączony z Metop ASCAT (25 km) przez filtr czasowy (SCATSAR-SWI; Bauer-Marschallinger i in. 2018). Produkt serwisu
   Copernicus Land, więc zgodny z D-048.
2. **Co wnosi do karty:** drugie, **niezależne od modelu** źródło stanu gleby (obserwacja radarowa, nie ERA5), w skali
   1 km zamiast 9 km i z opóźnieniem ok. 2 dni zamiast ok. 5. Na karcie: „satelita potwierdza / nie potwierdza”.
3. **Czego nie wnosi:** wartości dla działki (piksel 1 km miesza winnice, pola i las), milimetrów wody (to indeks
   względny 0–100%), pewnej poprawy trafności (w F4 fuzja z własnym SWI z Sentinel-1 dała +0,05 R, co nie przetrwało
   korekty na wielokrotne porównania).
4. **Klucze:** czytane z folderu `MyDrive/GeoWorldLook/secrets/` (D-074). Jest tam dziś `clms_token.json`; pliku
   z kluczami Copernicus Data Space nie ma. Proponowana droga pobierania i potrzebny plik — §4.

## 1. Produkt

| Cecha | Wartość | Źródło |
|---|---|---|
| Nazwa | Soil Water Index 2015–present (raster 1 km), Europe, daily — version 1; od 2025 r. także wersja 2 (COG) | strona produktu CLMS, rekord FEDEO v2 |
| Dane wejściowe | wilgotność warstwy powierzchniowej z Sentinel-1 C-SAR (1 km) i Metop ASCAT (25 km), łączona filtrem wykładniczym | Bauer-Marschallinger i in. 2018; strona produktu |
| Warstwy | 8 wartości T (2, 5, 10, 15, 20, 40, 60, 100 dni) — **nie głębokości**, tylko stałe czasowe filtra; większe T ≈ wolniej reagująca, głębsza warstwa | ATBD / PUM; kod `legacy/step_01_ingest_v1.py` (pasma SWI002…SWI100) |
| Jednostka | indeks względny 0–100% (stopień nasycenia), bez mm | PUM |
| Opóźnienie | ok. 2 dni od obserwacji | strona produktu |
| Opublikowana walidacja | Włochy: mediana R = 0,61 wobec pomiarów in situ (Bauer-Marschallinger i in. 2018); walidacja europejska 2015–2019 na stronie jakości CLMS | [A/F] |

## 2. Rola na karcie wody

- **Nowy wiersz karty:** „Satelita (radar Sentinel-1 + ASCAT, 1 km): <kategoria> (percentyl X wobec 2015–2024) —
  zgodne / niezgodne z modelem ERA5-Land”.
- **Zgodność** (reguła ustalona teraz): oba źródła po tej samej stronie przy **tej samej normie 2015–2024** — oba ≤ 30
  (sucho), oba 30–70 (norma) albo oba ≥ 70 (wilgotno). Inaczej „niezgodne” i pokazujemy, co mówi każde.
- **Na ile ufać:** do czasu walidacji (§5) wiersz ma dopisek „walidacja w toku”.

## 3. Decyzje metodyczne (ustalone przed pobraniem danych)

1. **Stała T (D-075).** Jedną wartość T wybieramy przed pobraniem danych, z dokumentacji produktu (rozdział PUM/ATBD
   o interpretacji T) i z pracy Albergel i in. 2008 (filtr wykładniczy na stacjach SMOSMANIA, strefa korzeni na 30 cm).
   **Kandydat: T = 20 dni** (referencja ISMN 20–30 cm) — do potwierdzenia lekturą tych dwóch źródeł w Colab, bo z kontenera
   asystenta strony są niedostępne. T = 10 i T = 40 raportujemy jako wrażliwość. **T nie dobieramy pod ISMN ani pod ERA5**:
   dobór pod ERA5 zawyżyłby zgodność, którą pokazujemy jako miarę pewności.
2. **Wspólna norma (D-076).** SWI istnieje od 2015 r., więc jego percentyl liczymy wobec 2015–2024 (okno ±15 dni roku).
   Lata 2015–2024 były suchsze niż 1991–2020, więc do reguły zgodności ERA5 też liczymy wobec 2015–2024. Kategoria
   ERA5 na górze karty zostaje wobec 1991–2020; na karcie piszemy, która norma dotyczy którego wiersza.
3. **Jedna spójna wersja archiwum (D-077).** Jeśli archiwum to wersja 1 do 2024 r. i wersja 2 od 2025 r., najpierw
   porównujemy je w okresie wspólnym; nie łączymy wersji w jedną normę bez sprawdzenia przesunięcia (ta sama lekcja co
   z termiką S-3 w F7).
4. **Piksel.** Piksel 1 km zawierający środek VINEYARD_06; średnia z 3 × 3 pikseli jako wrażliwość. Dni z flagą
   jakości poniżej progu z PUM pomijamy.

## 4. Dostęp do danych i klucze (D-074, D-078)

**Zasada kluczy:** pliki z kluczami tylko w `MyDrive/GeoWorldLook/secrets/` (ścieżka w `MONITOR_CONFIG["SECRETS_DIR"]`),
nigdy w repozytorium; kod sprawdza tylko istnienie pliku, nie wypisuje ani nie zapisuje jego treści w logach,
rejestrze ani `run_summary.md`.

| Droga | Klucz | Za | Przeciw |
|---|---|---|---|
| **A (proponowana): Copernicus Data Space, Sentinel Hub Statistical API** | plik `secrets/cdse.env` z `CDSE_CLIENT_ID` i `CDSE_CLIENT_SECRET` (te same wartości, których używa ETL strony GeoWorldLook jako `COPERNICUS_CLIENT_ID/SECRET`) | dzienny szereg dla małego obszaru w jednym zapytaniu — ten sam wzorzec co ETL strony; uwierzytelnienie i kolekcja SWI były już używane w `legacy/step_01_ingest_v1.py` | trzeba dodać jeden plik do `secrets/`; identyfikator kolekcji z kodu legacy do potwierdzenia |
| B: API Copernicus Land (CLMS) | istniejący `secrets/clms_token.json` (klucz usługi, sądząc po nazwie) | klucz już jest | sposób uwierzytelnienia i format pobierania do potwierdzenia w dokumentacji API CLMS; prawdopodobnie pobieranie całych plików produktu, a nie szeregu dla punktu |

**Pierwszy krok w Colab — sonda (bez analizy):** uwierzytelnienie wybraną drogą, pobranie jednego miesiąca dla piksela
winnicy, wypisanie nazw pasm, wersji produktu, pierwszej i ostatniej dostępnej daty. Dopiero potem pełny kod.

## 5. Sprawdzenie (D-067) i karta wyników (D-070)

- **Walidacja (po A4):** anomalia SWI(T) wobec czujnika ISMN 20–30 cm — ten sam protokół co ERA5 (R z CI z bootstrapu
  blokowego, POD/FAR suchych dekad), na referencji po kontroli czujników.
- **Karta wyników:** na tej samej, poprawionej referencji i w tych samych latach (2016–2024): POD/FAR/CSI suchych dekad
  dla (i) samego ERA5 i (ii) reguły „ERA5 i SWI zgodnie suche”; sparowany bootstrap blokowy po sezonach. Wpisujemy
  wynik niezależnie od kierunku.
- **Uczciwe oczekiwanie:** trafność może nie wzrosnąć. Wartością jest niezależne, satelitarne potwierdzenie, świeższe
  i w skali 1 km.

## 6. Kod (po akceptacji; tylko zmienione fragmenty i changelog)

- `step_01_ingest.py`: `read_secret(name, cfg)` (folder `SECRETS_DIR`), `sync_swi_point(lat, lon, start, end, cache_dir)`
  — dzienny szereg SWI dla piksela, cache roczny jak ERA5.
- `step_05_colab_run.py`: `SECRETS_DIR`, `SWI_T`, `SWI_NORM` w `MONITOR_CONFIG`; `task_ingest_swi`; selftest
  z syntetycznym szeregiem SWI.
- `step_09_panels.py`: wiersz satelity i reguła zgodności w `water_card`; wiersz w „Na ile ufać”.
- Notatnik (przez `build_colab_master.py`): komórka sondy z §4.

## 7. Ograniczenia

- Piksel 1 km obejmuje winnice, pola i las; radar reaguje też na roślinność i szorstkość powierzchni.
- SWI to filtr sygnału powierzchniowego, a nie pomiar strefy korzeni; T tylko przybliża głębokość.
- Norma 2015–2024 jest krótka i sucha; percentyle SWI nie są porównywalne z kategorią ERA5 wobec 1991–2020.
- Walidacja tylko na jednej stacji (Condom); inne stacje SMOSMANIA — Plan v7, etap B.

## 8. Decyzje do zatwierdzenia

- **D-074:** klucze tylko z `MyDrive/GeoWorldLook/secrets/`, bez wypisywania treści.
- **D-075:** jedna wartość T wybrana z dokumentacji produktu i literatury przed pobraniem danych (kandydat T = 20);
  T = 10 i 40 jako wrażliwość; bez dopasowania do ISMN ani ERA5.
- **D-076:** zgodność ERA5–SWI oceniana na wspólnej normie 2015–2024.
- **D-077:** jedna spójna wersja archiwum SWI; wersji 1 i 2 nie łączymy bez sprawdzenia przesunięcia.
- **D-078:** droga A (Copernicus Data Space, Statistical API) jako główna; wymaga pliku `secrets/cdse.env`.

## 9. Źródła

Poziom dostępu: P = pełny tekst, A = abstrakt lub streszczenie, F = fragment z wyszukiwania, W = wiedza własna (do sprawdzenia).

- CLMS: Soil Water Index 2015–present (raster 1 km), Europe, daily — version 1, strona produktu:
  https://land.copernicus.eu/en/products/soil-moisture/daily-soil-water-index-europe-1km [F]
- CLMS: Product User Manual — Soil Water Index 1 km (I1.50, 2025):
  https://land.copernicus.eu/en/technical-library/product-user-manual-soil-water-index-version-1 [F]
- CLMS: Algorithm Theoretical Basis Document — Soil Water Index:
  https://land.copernicus.eu/en/technical-library/algorithm-theoretical-basis-document-soil-water-index/@@download/file [F]
- CLMS: strona jakości produktu (walidacja europejska 2015–2019):
  https://land.copernicus.eu/api/en/products/soil-moisture/daily-soil-water-index-europe-v1-0-1km/quality [F]
- FEDEO: rekord kolekcji CLMS SWI Europe 1 km daily v2 (COG):
  https://fedeo.ceos.org/series/eo:platform/Sentinel-1/clms_swi_europe_1km_daily_v2_cog [F]
- Bauer-Marschallinger B. i in. 2018. Soil Moisture from Fusion of Scatterometer and SAR: Closing the Scale Gap with
  Temporal Filtering. Remote Sensing 10(7): 1030, doi:10.3390/rs10071030 [A]
- Albergel C. i in. 2008. From near-surface to root-zone soil moisture using an exponential filter: an assessment of
  the method based on in-situ observations and model simulations. HESS 12: 1323–1337, doi:10.5194/hess-12-1323-2008
  [F — optymalne T dla SMOSMANIA do odczytania w pełnym tekście przed wyborem T]
- Paulik C. i in. 2014. Validation of the ASCAT Soil Water Index using in situ data from the International Soil
  Moisture Network. Int. J. Appl. Earth Obs. Geoinf., doi:10.1016/j.jag.2014.01.007 [F — zależność T od głębokości
  niepotwierdzona; późniejsze prace podają wyniki niejednoznaczne]
- Wagner W. i in. 1999 — filtr wykładniczy (Soil Water Index) z wilgotności powierzchniowej [W]
