# AgriWatch v4: plan pod cel zawodowy — działający, użyteczny produkt i praca w FR/IT/DACH

> **Status:** `SUPERSEDED` (2026-10-06) przez `Plan_v5_bilans_wodny_winnic.md` — nie został zatwierdzony. Sekcja 2 (diagnostyka danych Condom) pozostaje podstawą v5.
> **Zasoby:** 1 osoba, około 10 h tygodniowo (7 h projekt, 3 h kariera), darmowe narzędzia.
> **Architektura (bez zmian):** GitHub → Colab → Dysk Google (`MyDrive/GeoWorldLook/agriwatch`), rejestr `gwl_*`, notatnik `AgriWatch_Monitor.ipynb`.
> **Zastępuje:** harmonogram E0–E6 z `Plan_v3_monitoring_winnic_SR.md` oraz decyzję D-020 („S-1 w rdzeniu”). Przegląd literatury z v3 (część A) i hipotezy SR zostają.

---

## 1. Cel i jak zmierzymy sukces

**Cel:** wyższy dochód. Droga główna to praca zdalna lub relokacja do firmy EO we Francji, Włoszech albo regionie DACH. Droga poboczna to płatny lub bezpłatny pilotaż z doradcą winiarskim.

| Do 29 XI 2026 | Miara „zrobione” |
|---|---|
| **Produkt działa** | 4 kolejne cotygodniowe uruchomienia bez ręcznych poprawek (widać w `gwl_runs`) |
| **Produkt jest użyteczny** | Cotygodniowy raport z listą winnic do odwiedzenia w pierwszej kolejności; pokazany co najmniej 3 osobom z branży (doradca, spółdzielnia, rekruter EO) |
| **Wynik naukowy jest uczciwy** | Tabela błędów z 95% CI na stacjach ISMN; wynik ablacji SR (dodatni albo ujemny) |
| **Portfolio jest publiczne** | README po angielsku, strona na geoworldlook.vercel.app, film 5 min, test automatyczny na GitHub |
| **Kariera** | ≥ 15 aplikacji, ≥ 3 rozmowy, CV i LinkedIn po angielsku z linkiem do projektu |
| **Opcjonalnie: produkt** | 1 zgoda na bezpłatny pilotaż w sezonie 2027 (kwiecień–wrzesień) |

---

## 2. Dlaczego zmieniamy rdzeń (dowód z danych Condom, 2026-10-06)

Pierwsze prawdziwe uruchomienie `step_07` i analiza Sentinel-2. Dane z okresu kalibracji 2016–2021; okres testowy nie był używany do decyzji.

| Źródło | R z czujnikiem 5 cm | R z 20–30 cm | Wniosek |
|---|---|---|---|
| ERA5-Land (~9 km) | 0,72–0,80 | 0,83 | Najlepiej oddaje **kiedy** jest sucho |
| Sentinel-1 (bufor 50 m) | 0,36–0,39 | 0,34 | Szum plamkowy: dwa przeloty w odstępie < 2 dni różnią się o 0,29 zakresu wilgotności |
| Sentinel-2 NDVI / STR / OPTRAM (punkt) | 0,44 / 0,27 / 0,19 | 0,56 / 0,39 / 0,35 | Słabo w czasie na jednym punkcie |
| ERA5 + S-2 + S-1 (walidacja rok po roku) | 0,58–0,63 (sam ERA5: 0,63) | 0,79–0,81 (sam ERA5: 0,81) | **Satelity nie dodają informacji o przebiegu w czasie** |

**Wniosek:** ERA5-Land dobrze mówi, **kiedy** w okolicy jest sucho, ale ma jedną wartość dla całego oczka około 9 km, czyli dla wszystkich winnic w AOI. Satelity mają sens tam, gdzie ERA5 nie sięga: **która winnica reaguje gorzej od sąsiednich**. To jest pytanie Sentinel-2 i super-resolution.

---

## 3. Produkt: „AgriWatch — cotygodniowa lista winnic do sprawdzenia”

**Użytkownik:** doradca winiarski albo technik spółdzielni, który ma pod opieką dziesiątki działek.
**Jego pytanie:** „Które działki odwiedzić w tym tygodniu i dlaczego?”
**Zasada z planu v1:** priorytetyzacja inspekcji, nie diagnoza.

### Trzy warstwy

| Warstwa | Pytanie | Dane | Rozdzielczość | Walidacja |
|---|---|---|---|---|
| **1. Kiedy** | Czy w okolicy jest okres suchy? | ERA5-Land, warstwy 0–7, 7–28 i 28–100 cm; percentyl wobec 1991–2020 | ~9 km, codziennie | Stacje ISMN: Condom i stacje Gers (R, ubRMSD, CI) |
| **2. Gdzie** | Która winnica reaguje gorzej? | Sentinel-2 (NDVI, NDMI, STR, OPTRAM) → **SEN2SR 2,5 m** → statystyki działki bez brzegu | Działka, co 2–5 dni przy bezchmurnym niebie | Hipoteza H-S2 na stacjach SMOSMANIA + ablacja 10 m wobec SR |
| **3. Kontrola** | Czy był deszcz albo zmoczenie między scenami S-2? | Sentinel-1 uśredniony na 200–500 m | Co 3–6 dni, niezależnie od chmur | Condom (test rozmiaru obszaru) |

### Wynik dla działki (co tydzień)

| Pole | Przykład |
|---|---|
| `status` | `normal` / `watch` / `inspect` |
| `reason_codes` | `ERA5_RZ_P15` (strefa korzeni poniżej 15. percentyla) + `S2_BELOW_PEERS_2X` (działka 2 razy z rzędu gorsza od sąsiednich winnic) |
| `confidence` | Niższe przy chmurach (stara scena S-2), małej działce, braku zgodności warstw |
| `expected_error` | Błąd warstwy 1 z tabeli walidacji (np. ubRMSD 0,05 m³/m³ dla strefy korzeni) |

**Reguła statusu** (zapisana przed testem):
- `watch`: warstwa 1 w percentylu < 20 **i** działka poniżej mediany sąsiednich winnic (anomalia S-2);
- `inspect`: to samo przez 2 kolejne bezchmurne sceny albo percentyl warstwy 1 < 10.

### Pokaz: susza 2022

Rok 2022 to jedna z najcięższych susz we Francji. Raport „jak AgriWatch wyglądałby w lipcu 2022” na prawdziwych danych to najmocniejszy materiał dla rekrutera i doradcy. Dane już są w zakresie pipeline'u.

---

## 4. Eksperyment SR (rdzeń warstwy 2, wyróżnik projektu)

| ID | Pytanie | Test | Wynik do pokazania |
|---|---|---|---|
| H-SR0 | Czy SR naprawdę działa (a nie interpolacja)? | Różnica SR i interpolacji bikubicznej, energia szczegółów < 10 m | Automatyczna kontrola przy każdej scenie (stary potok ją oblał: różnica 0,5%) |
| H-SR1 | Czy SR zachowuje radiometrię? | Uśrednienie SR do 10 m wobec oryginału (opensr-test) | Błąd per pasmo |
| H-SR3 | Czy SR daje stabilniejszą statystykę małej działki? | Szum serii czasowej działki: 10 m wobec 2,5 m | Tabela dla 15 winnic |
| **H-S2** | Czy S-2 (10 m / SR 2,5 m) wyjaśnia, o ile miejsce różni się od średniej ERA5? | Na stacjach SMOSMANIA: (czujnik − ERA5) wobec lokalnego odchylenia S-2; ablacja 10 m wobec 2,5 m | **Główny wynik naukowy projektu** |

**Uczciwe zastrzeżenia:**
- Pasma SWIR (20 m) SEN2SR wyostrza 8×, a szczegół przestrzenny pochodzi z pasm 10 m.
- SR nie dodaje informacji o wodzie. Daje czystsze piksele w małych działkach i w poligonie stacji (34 piksele zamiast 2).

**Zakres, żeby był wykonalny:** SR tylko dla bezchmurnych scen sezonów wegetacyjnych 2022–2025 nad AOI (szacunkowo 80–120 scen). Sceny są małe (około 380 × 340 pikseli 10 m). Zapisujemy indeksy per działka i rastry tylko dla dat pokazowych.

---

## 5. Harmonogram: 8 tygodni

Każdy tydzień kończy się **artefaktem**, który można pokazać.

| Tydz. | Daty | Projekt (~7 h) | Kariera (~3 h) | Artefakt |
|---|---|---|---|---|
| **1** | 6–11 X | ERA5-Land 3 warstwy dla stacji i AOI; percentyle wobec 1991–2020; walidacja warstw wobec 5, 20 i 30 cm; `END_DATE = dziś` z dopisywaniem nowych danych | Lista 20 firm z wymaganiami (sekcja 6) | Wykres „Condom 1991 → dziś: percentyl wilgotności strefy korzeni” + tabela błędów |
| **2** | 12–18 X | S-2 dla 23 poligonów (`reduceRegions`, Cloud Score+); indeksy per działka; anomalie: względem własnej historii i względem sąsiednich winnic; status per działka | CV po angielsku (wersja EO data scientist) | **Raport „lipiec 2022”** dla 15 winnic: mapa + lista priorytetów |
| **3** | 19–25 X | H-S2 na stacjach SMOSMANIA (S-2 punktowo, tanie); S-1 na 200–500 m w Condom (krótko) | LinkedIn EN; 3 pierwsze aplikacje | Tabela: czy S-2 wyjaśnia różnice lokalne względem ERA5 |
| **4** | 26 X – 1 XI | `step_03`: naprawa SEN2SR (K-09, K-17), H-SR0 i H-SR1 automatycznie; SR dla scen 2022–2025 | 3 aplikacje | Porównanie 10 m wobec 2,5 m z wynikiem kontroli |
| **5** | 2–8 XI | H-SR3 i ablacja H-S2 (10 m wobec SR); wpięcie SR do warstwy 2 tylko przy wyniku dodatnim | 3 aplikacje; post na LinkedIn z wykresem 2022 | Tabela ablacji SR z CI |
| **6** | 9–15 XI | Raport tygodniowy jednym kliknięciem (MD/HTML: mapa, lista, wykresy); eksport JSON + PNG na stronę GeoWorldLook | Rozmowy z 3 doradcami lub spółdzielniami (sekcja 7) | **Publiczna strona demo** |
| **7** | 16–22 XI | README EN, opis metody i walidacji (2 strony), test automatyczny na GitHub (selftest); przeniesienie repozytorium poza firmowy OneDrive przed publikacją | 3 aplikacje; przygotowanie do rozmów | Repozytorium gotowe do pokazania |
| **8** | 23–29 XI | Film 5 min; poprawki po 4 tygodniach pracy; podsumowanie wyników | 3 aplikacje; oferta pilotażu 2027 | Film + 15 aplikacji wysłanych |

**Cięcia przy opóźnieniu (w tej kolejności):** S-1 (tydz. 3) → H-SR3 → strona HTML (zostaje README z obrazkami). **Nie tniemy:** tygodni 1, 2 i 6, czyli działającego produktu z raportem, oraz kariery.

**Zasada:** pierwsze aplikacje idą w tygodniu 3, nie po skończeniu projektu. Projekt w trakcie, z wynikiem 2022 i uczciwą walidacją, wystarcza na rozmowę.

---

## 6. Ścieżka kariery

**Na jakie stanowiska:** EO / Remote Sensing Data Scientist, Geospatial Data Engineer, Agri-EO Analyst.

**Co projekt pokazuje rekruterowi** (mapowanie na typowe wymagania ogłoszeń):

| Wymaganie | Dowód w projekcie |
|---|---|
| Python, GEE, Sentinel-1/2 | Cały pipeline |
| Walidacja, statystyka, niepewność | Tabela błędów z CI, triple collocation / ablacje, wybór metody na okresie kalibracji |
| Deep learning / SR | SEN2SR z kontrolą H-SR0/H-SR1 i ablacją |
| Inżynieria danych | Rejestr z kluczami (upsert), przyrostowe pobieranie, log uruchomień, test na GitHub |
| Zrozumienie domeny | Uzasadnienie: kiedy (ERA5) a gdzie (S-2), winnice, strefa korzeni |
| Komunikacja | Raport tygodniowy, film, uczciwe „S-1 nie zadziałał w 50 m i dlaczego” |

**Lista startowa firm.** Do sprawdzenia bieżących ofert w tygodniu 1; nie wszystkie mają teraz rekrutacje.

| Kraj | Przykłady | Dlaczego pasują |
|---|---|---|
| Francja | TerraNIS (Tuluza, teledetekcja winnic), CLS, Telespazio France, Airbus Defence and Space, Kermap | Rolnictwo, winnice, Copernicus |
| Włochy | Eurac Research (Bolzano: wilgotność gleby S-1/S-2 + in situ), e-GEOS, Planetek Italia | Wilgotność gleby, Copernicus |
| DACH | TU Wien / EODC (wilgotność gleby z S-1), sarmap (SAR), GAF AG, EOMAP, VISTA, Planet (produkt wilgotności gleby), reasekuratorzy z zespołami EO | Wilgotność, susze, ubezpieczenia |

**Uwaga:** bez francuskiego lub niemieckiego trudniej o oferty lokalne. Praca zdalna i instytuty badawcze (Eurac, TU Wien) częściej działają po angielsku.

---

## 7. Ścieżka produktu (poboczna, bez kosztów)

- **Kogo zapytać:** doradcy winiarscy (np. izba rolnicza Gers), instytut winiarski, spółdzielnie z regionu.
- **Co pokazać:** raport „lipiec 2022” + raport z bieżącego tygodnia.
- **O co zapytać:** czy taka lista jest przydatna, jakie decyzje by wspierała, ile działek mają pod opieką.
- **Oferta:** bezpłatny pilotaż w sezonie 2027 na ich działkach w zamian za informację zwrotną, a jeśli się da, kilka pomiarów naziemnych, np. potencjału wodnego. To dałoby brakującą walidację w winnicach.
- **Ograniczenie prawne:** GEE i Colab są dla użytku niekomercyjnego. Płatna usługa wymaga przejścia na dane z CDSE (lista „później”).

---

## 8. Ryzyka

| Ryzyko | Obejście |
|---|---|
| H-S2 wyjdzie ujemnie (S-2 nie wyjaśnia różnic lokalnych) | Pokazujemy uczciwie. Produkt dalej działa jako „kiedy” (ERA5) + ranking wigoru działek (S-2), bez twierdzenia o wilgotności w działce |
| SEN2SR nie działa w Colab (GPU, pamięć) | SEN2SRLite na CPU dla małego AOI; w ostateczności ablacja na mniejszej liczbie scen |
| Brak czasu | Cięcia z sekcji 5 |
| Repozytorium w firmowym OneDrive | Przeniesienie przed publikacją (tydz. 7) |
| Dane ISMN w publicznym repozytorium | Sprawdzić warunki ISMN; w razie potrzeby usunąć z repo i pobierać skryptem lub ręcznie |

---

## 9. Decyzje do zatwierdzenia

| ID | Decyzja |
|---|---|
| D-024 | Rdzeń produktu: **ERA5-Land = kiedy** (3 warstwy, percentyle 1991–2020), **Sentinel-2 + SEN2SR = gdzie** (działki), **Sentinel-1 = warstwa pomocnicza**. Zastępuje D-020 |
| D-025 | Harmonogram 8 tygodni (do 29 XI 2026) z równoległą ścieżką kariery zastępuje E0–E6 z v3 |
| D-026 | Pokaz produktu: hindcast suszy 2022 + raport bieżący |
| D-027 | Główny wynik naukowy: hipoteza H-S2 z ablacją 10 m wobec SR 2,5 m |
