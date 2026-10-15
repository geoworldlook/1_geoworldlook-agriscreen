# Plan v9 — „Woda w winnicy”: użyteczna informacja z tego, co AgriScreen już liczy (prototyp w Colab)

Status: PROPOSED, 2026-10-14; uporządkowany 2026-10-15 (§0). Kierunek i forma prototypu zatwierdzone 2026-10-14;
W1 i W1b wdrożone.
Przedefiniowuje moduł 1 Planu v8 (D-064). Moduły 2 i 3 Planu v8 (U-Net na ortofotomapie, rozplątanie sygnału)
zostają jako kolejne moduły. Etapy v7 B–D bez zmian.

**Forma:** prototyp w obecnym układzie — notatnik Colab, Dysk Google, `dashboard.html` (D-068). Publikacja na
GeoWorldLook i automatyczna aktualizacja dopiero po prototypie.

## 0. Stan, cel i kolejność (porządek z 2026-10-15)

**Cel modułu:** zwalidowana warstwa „woda w winnicy”, w której każda liczba na karcie ma albo wynik walidacji wobec
niezależnej referencji naziemnej (z przedziałem ufności), albo napis „niezwalidowane”. Testy zapisujemy przed
liczeniem, wyniki raportujemy niezależnie od kierunku, „przed” i „po” liczymy na tej samej referencji (D-067, D-070).
Żadnego produktu nie da się uczynić niepodważalnym; da się sprawić, że każde twierdzenie ma dowód i opisaną granicę.

**Zasada produktu:** stan dowolnego pola opisujemy anomalią jego własnego piksela wobec jego historii — nie zalecamy
podlewania ani zabiegów. Żeby obronić „dowolne pole”, metoda musi działać na co najmniej dwóch niezależnych
miejscach z pomiarami w gruncie: Condom (obszar główny) i obszar pomocniczy (D-082).

**Stan (2026-10-15):**
- Wdrożone: W1 (karta wody), W1b („Na ile ufać”), poprawki po pierwszym przebiegu na prawdziwych danych (D-079).
- W3a (2026-10-15, decyzja: „najnowsze dane, docelowo czas zbliżony do rzeczywistego”): wdrożone pobieranie
  CLMS SWI 0,1° v4 (nowa generacja 2025, dane do 24 h po pomiarze, jedna wersja od 2007) do wiersza satelity na karcie
  oraz SWI 1 km v2 (od 13 VII 2025), zbierany bez normy; T = 15, norma 2007–2024, zgodność klas ERA5–SWI (D-080) w
  „Na ile ufać”. **Pierwszy przebieg (2026-10-15):** satelita na 14.10 suszej niż w każdym roku 2007–2024 o tej porze,
  zgodnie z modelem; zgodność klas ERA5–SWI 2007–2024: 63% dni [59; 68], kappa 0,44 [0,36; 0,52] (umiarkowana);
  T = 10: 61%, T = 40: 65%. Szczegóły: `docs/evidence/W3a_SWI_1km_satelita.md` §0 pkt 8.
- Referencja naziemna: ISMN (Condom) niedostępny; zaproponowane FR-Lus i FR-Aur z sieci ICOS
  (`docs/evidence/REF_obszar_pomocniczy_ICOS.md`, D-082, do akceptacji).
- Słabości, o których piszemy wprost: jedna stacja naziemna z artefaktami czujników (A4), alarm z NDVI bez trafień,
  brak prawdy terenowej o wodzie w samej winnicy, krótkie normy danych satelitarnych.

**Kolejność (propozycja 2026-10-15, do akceptacji; najpierw walidacja, potem nowe elementy):**

| Etap | Krok | Co | Jedno sprawdzenie |
|---|---|---|---|
| I. Warstwa wody zwalidowana | **W3a** | SWI 0,1° v4 2007–dziś, T = 15, wiersz satelity na karcie, zgodność kategorii ERA5–SWI (D-080) | odsetek zgodnych dni i kappa 2007–2024; T = 10 i 40 jako wrażliwość |
| | **W2** | A4: kontrola czujników (reguły D-060–D-063); kilka czujników na głębokość w ICOS jako kontrola reguł | raport dni oznaczonych, nowe błędy na karcie |
| | **REF** | obszar pomocniczy: FR-Lus (dane bieżące), FR-Aur (historia w Gers); ta sama metoda bez dostrajania | protokół jak w Condom; na FR-Lus anomalie krótkookresowe |
| | **W1b+** | sekcja „Jak to liczymy”: tabela źródeł (model / satelita / pomiar, rozdzielczość, opóźnienie) i wyniki walidacji ze wszystkich referencji | każda liczba karty ma wiersz w tabeli |
| II. Okolica i perspektywa | **W3b** | Sentinel-2 10 m: anomalie działek wobec własnej historii i sąsiadów; „X z N winnic” i zmiana od poprzedniej sceny; bez klas bezwzględnych (D-081) | kalibracja z i reakcja z opóźnieniem (§5b) |
| | **W4–W6** | 7 dni, 30 dni z lat podobnych, faza winorośli; alert tylko przy nowym pogorszeniu kategorii | jak w tabeli §3 |
| III. Rozplątanie sygnału | Plan v8, moduły 2–3 | U-Net na ortofotomapie (winorośl / międzyrzędzie / gleba), rozplątanie reflektancji, test H-F6 zahashowany przed uruchomieniem | FAR i opóźnienie składowej winorośli wobec NDVI całego piksela |
| Później (osobne decyzje) | W3, W7; choroby | publikacja na GeoWorldLook i automatyczna aktualizacja; ryzyko chorób winorośli jako kandydat po W6 (walidacja np. wobec regionalnych biuletynów fitosanitarnych — do sprawdzenia) | — |

## 1. Cel

Winiarz z działkami w okolicy Condom raz w tygodniu dostaje odpowiedź na cztery pytania:
1. **Jak sucho jest teraz** w porównaniu z normą tej pory roku — słowami, w milimetrach i na tle lat, które pamięta.
2. **Co dalej** — najbliższe 7 dni i perspektywa miesiąca.
3. **Co to znaczy teraz** — w której fazie jest winorośl i czego dotyczy niedobór wody w tej fazie.
4. **Na ile temu ufać** — błąd każdej liczby.

## 2. Diagnoza (stan v1.2)

| # | Problem | Skutek |
|---|---|---|
| 1 | Informacja jako z-score i klasy EDO | nieczytelna dla winiarza (myśli w mm, latach, fazach) |
| 2 | Tylko przeszłość (dekada, ERA5 z opóźnieniem ~5 dni); prognoza 7 dni (opad, ET0) pokazana, ale niepołączona ze stanem gleby | brak odpowiedzi „co dalej” |
| 3 | Brak kontekstu rośliny | ten sam komunikat w maju i w sierpniu |
| 4 | Najmocniej wyeksponowany alarm z NDVI (0 trafień), najlepiej zwalidowane warstwy (opad, pogoda) niżej | odwrócone priorytety |
| 5 | Gleba z oczka ERA5 ~9 km | to informacja o okolicy — trzeba to mówić wprost |
| 6 | Referencja ISMN 20/30 cm częściowo niewiarygodna | podany błąd do rewizji (A4) |

## 3. Kroki (prototyp w Colab)

| Krok | Co | Jak | Jedno sprawdzenie (D-067), potem do produktu | Sesje |
|---|---|---|---|---|
| **W1** | Karta „Woda w winnicy” na górze dashboardu; alarm z NDVI do sekcji informacyjnej; logika EDO do „Szczegółów” | przeliczenie istniejącej wilgotności ERA5-Land 0–100 cm i opadu (specyfikacja w §5) | testy jednostkowe przeliczeń i zgodność percentyla z `clim_anomaly` | 2 |
| **W2** | A4: QC czujników ISMN i ponowne oszacowanie ρ | reguły z `docs/evidence/A4_QC_czujnikow_ISMN.md` (D-060–D-063, do akceptacji) | raport dni oznaczonych i nowe błędy na karcie | 2 |
| **W4** | Najbliższe 7 dni | prosty bilans wody od ostatniego stanu ERA5: opad − parowanie z prognozy, którą dashboard już pobiera (Open-Meteo, ET0 FAO) | test wsteczny 2016–2025 z rzeczywistą pogodą ERA5 zamiast prognozy: błąd zmiany niedoboru w mm; trafność samej prognozy opisana jako niesprawdzona | 1–2 |
| **W5** | Perspektywa 30 dni z lat podobnych | lata 1991–2025 o najbardziej podobnym przebiegu wilgotności w ostatnich 60 dniach i co działo się w nich dalej | test z pominięciem roku (1991–2025): Brier dla „susza za 30 dni” wobec klimatologii; tylko ERA5, bez zależności od ISMN | 2 |
| **W6** | Faza winorośli i znaczenie niedoboru w tej fazie | model sumy temperatur z literatury; najpierw notatka: źródła, parametry dla odmian z Gers, co mówi literatura o niedoborze w każdej fazie | porównanie z publicznymi datami faz, jeśli są dostępne; inaczej opis „orientacyjnie” | 1–2 |

Razem ok. 8–10 sesji. Kolejność jak w tabeli.

**Rozszerzenie 2026-10-14 (zatwierdzona kolejność):** W1 → **W1b** → **W3a** → **W3b** → W2 → W4 → W5 → W6.

| Krok | Co | Jak | Jedno sprawdzenie (D-067) | Sesje |
|---|---|---|---|---|
| **W1b** | „Na ile ufać” na karcie wody | odczyt walidacji z `validation_weather.csv` i `validation_anomalies.csv` (liczby z potoku, nie wpisane na sztywno); niedobór w mm, miejsce wśród lat i „od kiedy” oznaczone „niezwalidowane, orientacyjnie” (D-071) | test: każda liczba karty ma opis walidacji albo napis „niezwalidowane” | 1 |
| **W3a** | Satelitarna wilgotność gleby: CLMS Soil Water Index 1 km (radar) jako drugie, niezależne źródło (D-072); metoda: `docs/evidence/W3a_SWI_1km_satelita.md` (D-074–D-078) | pobieranie z Copernicus Data Space (kod w `legacy/step_01_ingest_v1.py`, `fetch_cdse_swi_multidepth`); wartość T dobrana z literatury przed walidacją; percentyl wobec własnej normy SWI (krótszej niż 1991–2020 — opisane); na karcie „satelita potwierdza / nie potwierdza” | po A4: walidacja wobec ISMN tym samym protokołem; w karcie wyników POD/FAR „ERA5 i SWI zgodnie” wobec samego ERA5 | 2 |
| **W3b** | **Okolica w Sentinel-2 (10 m)**: mapa anomalii w działkach obszaru, tabela działek, zdanie na karcie (D-073; specyfikacja §5b) | rastry S-2 z Dysku (414 scen), 22 działki z `1_AOI_GBOV_CONDOM.geojson`; ta sama metoda anomalii co status (lata wcześniejsze, ten sam tor, z predykcyjne) | kalibracja z (częstość z ≤ −1 w latach bez suszy gleby) i reakcja: mediana anomalii winnic obszaru wobec anomalii gleby ERA5 z opóźnieniem 30–60 dni (okno ustalone przed liczeniem); to nie jest walidacja trafności w działce — brak prawdy terenowej, piszemy wprost | 3–4 |

**Stan 2026-10-14:** W1 wdrożone w kodzie (`step_09.water_card`, karta na górze dashboardu, sekcja w biuletynie,
`water_card` w `agriwatch_latest.json`, sekcja w `run_summary.md`; selftest przechodzi). Czeka na pierwszy przebieg w Colab
na prawdziwych danych. W1 nie zmienia trafności — te same liczby inaczej podane (§3a).

**Stan 2026-10-14:** W1b wdrożone (`step_09.water_trust`): sekcja „Na ile ufać” na karcie, w biuletynie (EN)
i w `run_summary.md`; liczby walidacji odczytywane z `validation_weather.csv` i `validation_anomalies.csv`; niedobór,
miejsce wśród lat i „od kiedy” opisane jako niezwalidowane (D-071). Mapa W3b: NDMI domyślnie (decyzja 2026-10-14).

**Stan 2026-10-15:** W3a — sonda dostępu wdrożona (`step_01.probe_swi`, zadanie `task_probe_swi`, sekcja 3b notatnika;
klucze z `MyDrive/GeoWorldLook/secrets/cdse.env`, bez wypisywania treści). Czeka na wynik sondy z Colab; potem
pobieranie całego archiwum i wiersz satelity na karcie.

**Pierwszy przebieg na prawdziwych danych (2026-10-15, ERA5 do 6 X 2026):** karta W1 — wyjątkowa susza (D4,
percentyl 2 wobec 1991–2020), niedobór ok. 45 mm w 0–100 cm, 2. najsuchszy stan na 6 X od 1991 r. (bardziej sucho
w 2011), susza od 1 VI (13 dekad), opad 30 dni 65% i 90 dni 54% normy, szansa potwierdzenia przez czujnik 49%.
Poprawki po przeglądzie: częstość w nagłówku (D-079) i forma „w roku 2011”. Sonda SWI #1: logowanie działa,
kolekcja z kodu legacy nie zwróciła danych za ostatnie 31 dni. Strona produktu CLMS opisuje wersję 1 jako
zastąpioną, z danymi 2015 – VII 2025, więc brak bieżących dni jest oczekiwany. Dokumentacja CDSE potwierdza:
wersja 1 (identyfikator z legacy) do 12 VII 2025, wersja 2 osobną kolekcją od VII 2025; te same pasma i skala.
Sonda #2 sprawdza bieżące dni w wersji 2, archiwum w wersji 1 i ich wspólny okres (D-077).

**Po prototypie (osobna decyzja):** W3 — publikacja karty na GeoWorldLook (Supabase, mapa); W7 — automatyczna
cotygodniowa aktualizacja (GitHub Actions, ERA5-Land z Copernicus Climate Data Store). To część etapu E Planu v8.

## 3a. Karta wyników: co się poprawiło (D-070)

Stała tabela metryk mierzonych na starcie (v1.2) i po każdym kroku. **„Przed” i „po” zawsze na tej samej referencji
i w tym samym okresie** — porównanie starych liczb (referencja z artefaktami) z nowymi (po A4) byłoby nieuczciwe.
Wynik „brak poprawy” też wpisujemy. Tabela żyje w `docs/evidence/karta_wynikow.md` od kroku W2.

| Krok | Czy zmienia trafność | Co porównujemy |
|---|---|---|
| W1 karta | nie — te same liczby inaczej podane | nic; zapisujemy wprost, że to zmiana prezentacji |
| W3a satelita | nowe, niezależne źródło (nie zmienia kategorii ERA5) | zgodność klas ERA5–SWI 2007–2024: 63% [59; 68], kappa 0,44 [0,36; 0,52] (2026-10-15); trafność SWI wobec czujników — po W2 i REF |
| W2 A4 | zmienia referencję, nie produkt | stara i nowa reguła statusu policzone na tej samej, poprawionej referencji: POD/FAR suchych dekad, Brier prawdopodobieństwa (W1/W2/W3 z notatki A4) |
| W4 7 dni | nowy element | błąd zmiany niedoboru wobec punktu odniesienia „bez zmian przez 7 dni” |
| W5 30 dni | nowy element | Brier wobec klimatologii i wobec „susza dziś = susza za 30 dni”; poprawa tylko, gdy lepszy od obu |
| Moduł 3 (Plan v8) | rozplątanie | FAR i opóźnienie składowej winorośli wobec NDVI całego piksela (H-F6, zahashowana przed testem) |

## 4. Czego w tym module nie robimy

- Nie mówimy „winorośl jest w stresie”: bez pojemności wodnej działki (Plan v7 C, D) nie da się tego uczciwie powiedzieć (D-066).
- Bez nowych upraw i chorób w tym module (choroby: kandydat po W6). Deep learning (rozplątanie sygnału) dopiero
  w etapie III, na obszarze Condom; obszar pomocniczy służy walidacji warstwy wody, nie rozplątaniu.
- Bez bezwzględnych klas „zdrowe / stres” dla wskaźników roślinności (D-081).
- Bez zaleceń zabiegów: karta opisuje stan i jego znaczenie, decyzja należy do winiarza.

## 5. Specyfikacja W1 — karta „Woda w winnicy” (do akceptacji przed kodem)

Wszystkie wielkości z danych, które potok już ma: dzienna ERA5-Land w punkcie winnicy (`era5_land_daily.csv`),
status dekadowy (`status_dekads.csv`), zagrożenia pogodowe (`hazard_summary.csv`). Okres normy: 1991–2020,
okno ±15 dni roku (jak w statusie).

| Element karty | Definicja | Przykład tekstu |
|---|---|---|
| **Kategoria** (nagłówek, kolor) | percentyl wilgotności 0–100 cm wobec normy dla tego dnia roku (empiryczny, jak `clim_anomaly`); kategorie wg percentyli US Drought Monitor (D-069): ≤ 2 wyjątkowa susza, ≤ 5 skrajna, ≤ 10 silna, ≤ 20 umiarkowana, ≤ 30 nienormalnie sucho, 30–70 w normie, ≥ 70 wilgotniej niż zwykle | „Silna susza w glebie — sucho jak w 1 roku na 10 o tej porze” |
| **Niedobór w mm** | (mediana normy − stan) × 1000 mm dla warstwy 0–100 cm; zaokrąglony do 5 mm; pokazywany, gdy > 0 | „Brakuje ok. 60 mm wody w glebie względem typowego stanu na koniec września” |
| **Na tle lat** | miejsce bieżącego stanu wśród tego samego dnia roku 1991 – bieżący rok | „Trzeci najsuchszy stan na 30 IX od 1991 r. (po 2003 i 2022)” |
| **Od kiedy** | początek obecnego ciągu dekad ze średnim percentylem ≤ 20 | „Susza w glebie od 1 VII (9 dekad)” |
| **Opad** | suma 30 i 90 dni z ERA5-Land w mm i jako % mediany sum z tego samego okna w normie | „Ostatnie 90 dni: 62 mm, 45% normy” |
| **Prawdopodobieństwo** | istniejące `p_soil_drought` | „Szansa, że czujnik w gruncie też pokazuje suszę: 49%” + dopisek „liczba w rewizji (QC czujników, A4)” do czasu W2 |
| **Przymrozki i upały** | bez zmian (`hazard_summary`) | jak dziś |
| **Skala i opóźnienie** | stała stopka karty | „Okolica (~9 km, model ERA5-Land), nie pomiar w działce. Stan na <ostatni dzień ERA5> — dane dochodzą z ok. 5-dniowym opóźnieniem.” |

Układ dashboardu po W1:
1. Karta „Woda w winnicy” (nowa) + krzywa sezonu (gleba na tle normy, już jest).
2. Przymrozki i upały, pogoda, prognoza (bez zmian).
3. „Roślinność działki (informacyjnie)”: mapa NDVI i kafelki NDVI/NDRE/NDMI (bez zmian treści).
4. „Szczegóły”: status EDO z przyczynami (z-score), matryca sygnałów, wiarygodność, tabela ostatnich lat.

Kod (do napisania po akceptacji; przy zmianach pokazujemy tylko zmienione fragmenty i changelog):
- `step_09_panels.py`: `water_card(era5, status, cfg)` → słownik z elementami tabeli powyżej, `water_card_caption`.
- `step_06_dashboard.py`: nowa karta na górze, przeniesienie sekcji, wskaźnik ryzyka z percentyla zamiast klasy EDO.
- `step_05_colab_run.py`: klucze `WATER_*` w `MONITOR_CONFIG` (kategorie, próg „od kiedy” = 20, zaokrąglenie 5 mm);
  testy karty w selfteście (kategorie, znak niedoboru, ranking, początek ciągu, zgodność percentyla).
- Biuletyn (EN) i `agriwatch_latest.json`: sekcja „Water in the soil” z tymi samymi wielkościami.

## 5b. Specyfikacja W3b — „Okolica w Sentinel-2 (10 m)” (do akceptacji przed kodem)

**Po co:** ERA5-Land (~9 km) i SWI (1 km) mówią o okolicy. Sentinel-2 pokazuje, **co dzieje się w poszczególnych działkach
obszaru** (4 × 4,4 km): które winnice i sady wyglądają gorzej niż zwykle i gdzie w działce.

**Co Sentinel-2 mierzy, a czego nie (napis na karcie):** reakcję roślinności — zieleń (NDVI) i wodę w liściach (NDMI)
winorośli i międzyrzędzi razem. Nie mierzy wilgotności gleby. Reaguje z opóźnieniem ok. 1 miesiąca (F7) i na koszenie
lub uprawę międzyrzędzi.

**Obiekty:** 22 działki z `1_AOI_GBOV_CONDOM.geojson` — 15 winnic, 5 sadów jabłoni, 2 działki z odkrytą glebą
(odniesienie). Poza działkami mapa szara: pola uprawne i las zmieniają się z powodów niezwiązanych z wodą (żniwa, orka).

**Dane:** rastry `data/01_Raw_Sentinel2/S2_L2A_*.tif` z Dysku (414 scen 2016–2026, IV–X, 10 pasm + maska chmur).
Bez SR: 10 m (SR jest dla sygnału równoważny, a na mapie mógłby dodawać szczegół, którego nie ma). NDMI liczony z pasm
20 m (B8A, B11) na siatce 10 m — rzeczywisty szczegół ok. 20 m; piszemy to na mapie.

| Element | Definicja |
|---|---|
| **Mapa anomalii** (ostatnia bezchmurna scena) | dla każdego piksela działek: z wskaźnika wobec tego samego piksela w scenach z 5 poprzednich lat, ±15 dni, ten sam tor orbity, z predykcyjne z rozkładu t (te same reguły co `scene_anomaly`, min. 5 scen odniesienia, tylko piksele bezchmurne); skala brąz (poniżej normy) – szary – morski (powyżej); obrysy działek; warstwy NDMI (domyślna) i NDVI |
| **Tabela działek** | typ, ha, data ostatniej sceny, z działki wobec jej własnej historii (`scene_anomaly` na średniej działki), z **na tle sąsiednich winnic** (z działki minus mediana z pozostałych winnic tej samej sceny — usuwa wspólny wpływ pogody i orbity), klasa (`z_class`: ≤ −1,5 / ≤ −1 / w normie / ≥ 1), zmiana w 3 ostatnich scenach; wiersz VINEYARD_06 wyróżniony |
| **Zdanie na karcie wody** | np. „W okolicy 9 z 15 winnic ma wodę w liściach wyraźnie poniżej normy (NDMI, scena 21.09); Twoja winnica: z = −1,5, 4. najniżej z 15” |

**Kod (po akceptacji):**
- `step_05`: `task_area_stats` — statystyki 10 m dla 22 działek z każdej sceny (raz dla archiwum, potem przyrostowo;
  „zrobione” liczone per działka i scena); `task_area_map` — z pikseli dla ostatniej sceny, GeoTIFF + PNG do mapy.
- `step_09`: `area_table`, `area_sentence`; `step_06`: sekcja „Okolica w Sentinel-2 (10 m)” zaraz pod kartą wody
  (mapa Leaflet jak mapa NDVI, tabela, podpis).
- Selftest: syntetyczne działki z różną anomalią (kolejność w tabeli, z na tle sąsiadów, maska poza działkami).

**Czego nie robimy w W3b:** wilgotności gleby z Sentinel-2 (wynik F4: nie dodaje informacji ponad ERA5), rozplątania
winorośl/międzyrzędzie (Plan v8, moduł 3), sygnału z odkrytej gleby w SWIR (możliwy później jako osobny krok).

## 6. Decyzje

- **D-064:** moduł 1 = „Woda w winnicy” (W1, W2, W4, W5, W6); zmienia kolejność z Planu v8 (D-052).
- **D-065:** na górze karty stan wody i perspektywa; alarm z NDVI tylko informacyjnie; logika EDO w „Szczegółach”.
- **D-066:** niedobór względem normy w glebie modelu ERA5-Land, z dopiskiem „okolica, model”; żadnych twierdzeń o stresie winorośli.
- **D-067:** każdy nowy element ma jedno sprawdzenie na danych historycznych, zapisane przed policzeniem; potem trafia do produktu.
- **D-068:** prototyp w obecnym układzie Colab + Dysk + `dashboard.html`; publikacja (W3) i automatyzacja (W7) po prototypie.
- **D-070:** karta wyników (§3a): „przed” i „po” na tej samej referencji i w tym samym okresie, z punktami odniesienia.
- Specyfikacja W1 (§5) zaakceptowana 2026-10-14: próg „od kiedy” = percentyl ≤ 20, karta po polsku w prototypie.
- **D-071:** W1b w wariancie (a): niedobór w mm, miejsce wśród lat i „od kiedy” zostają na karcie z napisem
  „niezwalidowane, orientacyjnie”; liczby walidacji odczytywane z wyników potoku.
- **D-072:** W3a — CLMS SWI 1 km (Copernicus) jako satelitarne, niezależne potwierdzenie stanu gleby w okolicy.
- **D-073:** W3b — lokalna warstwa Sentinel-2 10 m: anomalie pikseli i działek obszaru wobec własnej historii
  i na tle sąsiednich winnic; opisana jako reakcja roślinności, nie wilgotność gleby.
- **D-069:** kategorie suszy w glebie wg percentyli US Drought Monitor (NDMC/NOAA; system opisany w Svoboda i in. 2002).
- **D-079 (2026-10-15, po pierwszym przebiegu na prawdziwych danych):** częstość „raz na N lat” w nagłówku karty tylko
  dla N ≤ długość normy (30 lat). Przebieg z 6 X 2026 dał „raz na 58 lat” (percentyl 1,7) przy „2. najsuchszy stan od
  1991 r.” — ekstrapolacja poza 30 lat normy i sprzeczność z rankingiem. Rzadsze stany opisuje sam percentyl i ranking.

- **D-080 (zatwierdzona 2026-10-15):** zgodność kategorii ERA5–SWI mierzona (odsetek zgodnych dni, kappa) i pokazana
  w „Na ile ufać”, nie zakładana. (Wniosek z przeglądu Siora: tam zgodność klas między metodami jest założona.)
- **D-081 (zatwierdzona 2026-10-15):** żadnych bezwzględnych klas „zdrowe / marginal / stres” dla wskaźników
  roślinności; tylko anomalia wobec własnej historii piksela lub działki i wobec sąsiednich winnic. Uzasadnienie:
  winnica to uprawa rzędowa z międzyrzędziem; mediana NDVI VINEYARD_06 w VII–VIII z 5 lat to ok. 0,45–0,5, więc
  progi bezwzględne (np. NDVI > 0,5 „zdrowe”) oznaczałyby ją jako „marginal” w każde normalne lato.
- **Dopiski zatwierdzone 2026-10-15** (z przeglądu Siora): W3b — „X z N winnic” i zmiana od poprzedniej sceny;
  W1b+ — sekcja „Jak to liczymy”; W4/W7 — alert tylko przy nowym pogorszeniu kategorii, eksport CSV;
  choroby winorośli — kandydat po W6.
- **D-075, D-076, D-077 (rewizja 2026-10-15, przyjęta 2026-10-15 decyzją „bierzemy najnowsze dane”):** na karcie
  SWI 0,1° v4 (nowa generacja, jedna wersja 2007–dziś, czas zbliżony do rzeczywistego) zamiast łączenia wersji 1 i 2
  produktu 1 km (zalecenie producenta); 1 km v2 zbierany od 13 VII 2025 bez normy (15 miesięcy historii — norma z lat
  2025–2026 pokazałaby suszę 2026 jako „normę”); T = 15 z literatury; norma 2007–2024;
  `docs/evidence/W3a_SWI_1km_satelita.md` §0.
- **D-082 (do akceptacji):** obszar pomocniczy FR-Lus (dane bieżące) i referencja historyczna FR-Aur (Gers), sieć ICOS;
  `docs/evidence/REF_obszar_pomocniczy_ICOS.md`.
- **Kolejność §0 (do akceptacji):** walidacja (W3a, W2, REF, W1b+) przed nowymi elementami (W3b, W4–W6); zmienia
  kolejność zatwierdzoną 2026-10-14 (W2 i REF przed W3b).

## 7. Źródła

- Kategorie D0–D4 US Drought Monitor z percentyli (D0 21–30, D1 11–20, D2 6–10, D3 3–5, D4 0–2): samouczek National
  Drought Mitigation Center, University of Nebraska–Lincoln, https://drought.unl.edu/Education/Tutorials/Usdm/Section-Five.aspx
  [F], zgodnie z opisem NOAA NCEI https://www.ncei.noaa.gov/node/9066 [F].
- Svoboda M. i in. 2002. The Drought Monitor. Bulletin of the American Meteorological Society 83(8): 1181–1190 —
  opis systemu USDM [W; progi percentyli potwierdzone w źródłach powyżej, nie w tym artykule].
- Plan v7, Plan v8, `docs/evidence/A4_QC_czujnikow_ISMN.md`, `docs/MIGRACJA_PODSUMOWANIE.md` (wyniki walidacji opadu,
  pogody i gleby).
