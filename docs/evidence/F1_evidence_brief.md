# Evidence Brief — F1: szacowanie anomalii wilgotności gleby w wysokiej rozdzielczości

> **Status:** `Draft` (2026-09-26) — wymaga przeczytania kluczowych prac w pełnym tekście przed zmianą na `Approved for implementation`
> **Autor przeglądu:** Claude Code (na zlecenie użytkownika)
> **Powiązany plan:** `docs/plans/F1_system_wilgotnosci_plan.md`

---

## Pytanie decyzyjne

Jakimi metodami, z otwartych danych Copernicus i pokrewnych, można szacować **wilgotność powierzchniowej warstwy gleby i jej anomalie** w skali działki (20–100 m) dla sadów i winnic w Gers? Jak zwalidować wynik na stacji ISMN SMOSMANIA **Condom**, żeby wynik był wiarygodny? Czy zwiększanie rozdzielczości (downscaling LST, super-resolution S-2) wnosi informację o wilgotności?

## Zakres wyszukiwania

- Data przeglądu: 2026-09-26
- Wyszukiwarka: ogólna wyszukiwarka internetowa + strony wydawców, HAL, ResearchGate, GitHub
- Zapytania: SMOSMANIA Condom; S2MP Theia; walidacja satelitarnej wilgotności gleby (Gruber 2020, CEOS LPV); DISPATCH; OPTRAM; Sentinel-1 change detection 1 km; ograniczenia S-1 w roślinności; Sen-ET/DMS; TVDI – krytyka; SEN2SR; filtr wykładniczy SWI; anomalie w QA4SM; ML + ISMN + walidacja przestrzenna
- Zakres lat: 2002–2026 (prace fundamentalne + ostatnie 5 lat)
- Język: angielski

## Kryteria włączenia / wyłączenia

- **Włączone:** protokoły instytucjonalne (CEOS LPV, QA4SM), prace recenzowane z walidacją na danych in situ, prace wykonane w południowo-zachodniej Francji lub na SMOSMANIA, dokumentacja produktów Copernicus.
- **Wyłączone:** materiały marketingowe, metody bez walidacji in situ, prace wyłącznie dla obszarów pustynnych lub lasów.

## Ograniczenie tego przeglądu

Nie jest to przegląd systematyczny. Część prac oceniono **tylko na podstawie abstraktu lub streszczenia** (kolumna „Weryfikacja”). Źródła oznaczone `abstrakt` trzeba przeczytać w pełnym tekście przed oparciem na nich parametrów implementacji.

---

## Dane referencyjne — stacja Condom (z plików ISMN w repozytorium)

| Cecha | Wartość | Konsekwencja |
|---|---|---|
| Położenie | 43,9744°N, 0,3361°E, 174 m n.p.m. | Stacja leży wewnątrz AOI; poligon `stacja` ma ~20 × 18 m (≈ 2 × 2 piksele S-2) |
| Pokrycie terenu (ESA CCI 300 m) | Cropland rainfed / tree or shrub cover | Otoczenie rolnicze mieszane, zgodne z sadami i winnicami w AOI |
| Gleba (in situ, 5 cm) | glina ~41% iłu, 15% piasku; gęstość 1,42 g/cm³; porowatość ~0,50 m³/m³ | Gleba ciężka: wysoka wilgotność przy saturacji, silne pęcznienie i kurczenie |
| Klimat | Cfa/Cfb | Suche lata, wilgotne zimy: wyraźny cykl sezonowy |
| **5 cm** | ThetaProbe ML3 **2016-01 → 2019-02**, ML2x **2019-02 → 2024-12**; ~97–99% rekordów z flagą `G` | **Zmiana czujnika w lutym 2019** → obowiązkowy test jednorodności serii |
| 10 cm | ML3 2016 → 2020 | Krótka seria |
| 20 i 30 cm | ML3 2016 → 2024 | Walidacja strefy korzeniowej (0–30 cm) |
| Częstotliwość | godzinowa | Kolokacja z przelotem S-1 w oknie ±1 h jest możliwa |

---

## Źródła wybrane

| ID | Typ | Rok | Źródło | Pytanie | Kluczowy wniosek | Ograniczenie | Weryfikacja |
|---|---|---:|---|---|---|---|---|
| S01 | Protokół | 2020 | CEOS LPV, *Soil Moisture Product Validation Good Practices Protocol* v1.0 — [PDF](https://lpvs.gsfc.nasa.gov/PDF/CEOS_SM_LPV_Protocol_V1_20201027_final.pdf) | Jak walidować? | Zestaw uzupełniających się metryk; niepewność; błąd reprezentatywności punktu | Pisany dla produktów grubej rozdzielczości | abstrakt/opis |
| S02 | Recenzowana | 2020 | Gruber et al., *Validation practices for satellite soil moisture retrievals: What are (the) errors?*, RSE — [link](https://www.sciencedirect.com/science/article/pii/S0034425720301760) | Jak walidować? | Żadna pojedyncza metryka nie opisuje błędu; raportować bias, ubRMSD, R dla danych surowych i anomalii, CI | Jak wyżej | abstrakt |
| S03 | Dokumentacja | — | QA4SM / pytesmo, obliczanie anomalii — [pytesmo](https://pytesmo.readthedocs.io/en/latest/examples/anomalies.html), [EGU24](https://meetingorganizer.copernicus.org/EGU24/EGU24-2102.html) | Definicja anomalii | Anomalie krótkoterminowe = odchylenie od średniej ruchomej 35 dni; długoterminowe = od klimatologii wieloletniej | — | opis |
| S04 | Recenzowana | 2008 | Albergel et al., *From near-surface to root-zone soil moisture using an exponential filter*, HESS 12:1323 — [link](https://hess.copernicus.org/articles/12/1323/2008/) | Strefa korzeniowa | Filtr wykładniczy (SWI, stała T) odtwarza wilgotność strefy korzeniowej z pomiarów powierzchniowych na **SMOSMANIA** | T optymalizowane per stacja | abstrakt |
| S05 | Recenzowana | 2018 | El Hajj et al., *Evaluation of SMOS, SMAP, ASCAT and Sentinel-1 SSM products at sites in southwestern France*, Remote Sensing 10(4):569 — [HAL](https://hal.inrae.fr/view/index/identifiant/hal-01900522) | Jakość istniejących produktów w regionie | 7 stacji SMOSMANIA: bias ≈ −3,2 vol.%, RMSD ≈ 7,6 vol.% dla SMAP/ASCAT/S-1; produkt SMAP/S-1 1 km słabszy niż SMAP 9/36 km | 1,5 roku danych | streszczenie |
| S06 | Produkt / recenzowana | 2017– | S²MP (Theia), S-1 VV + S-2 NDVI + sieć neuronowa trenowana na modelu WCM — [HAL](https://hal.inrae.fr/hal-02631856), [katalog Theia](https://catalogue.theia.data-terra.org/meta/doi_10.57745_OBEXYH) | Metoda w skali działki | Mapy dla **Occitanie** (obejmuje Gers) od 2016, co 6–12 dni; dokładność ~5 vol.% | Działa przy NDVI < ~0,7; dostępność dla Condom do sprawdzenia | streszczenie |
| S07 | Recenzowana | 2023 | Madelon et al., *Soil moisture estimates at 1 km resolution making a synergistic use of Sentinel data*, HESS 27:1221 — [link](https://hess.copernicus.org/articles/27/1221/2023/) | Skuteczność S-1 + S-2 | 42 stacje (w tym SMOSMANIA): R ≈ 0,56, bias −0,06, SDD 0,05–0,06 m³/m³; słabo przy rozwiniętej roślinności | Skala 1 km | pełny opis strony |
| S08 | Recenzowana | 2019 | Bauer-Marschallinger et al., *Toward Global Soil Moisture Monitoring With Sentinel-1*, IEEE TGRS — [PDF](https://repositum.tuwien.at/bitstream/20.500.12708/919/2/Bauer-Marschallinger%20Bernhard%20-%202019%20-%20Toward%20Global%20Soil%20Moisture%20Monitoring...pdf) | Metoda bez danych treningowych | Change detection TU Wien; podstawa produktu CLMS SSM 1 km; dobra zgodność na równinach rolniczych | Słabo w lasach i terenie górzystym | abstrakt |
| S09 | Produkt | 2014– | CLMS *Surface Soil Moisture 1 km* i *Soil Water Index 1 km*, Europa, dziennie — [SSM](https://land.copernicus.eu/en/products/soil-moisture/daily-surface-soil-moisture-v1.0), [SWI v2](https://land.copernicus.eu/en/products/soil-moisture/daily-soil-water-index-europe-1km-v2) | Benchmark i kotwica | Gotowe, otwarte, przez CDSE | SSM: pojedynczy dzień pokrywa 5–10% Europy | opis produktu |
| S10 | Recenzowana | 2024 | *Retrieving Soil Moisture from Sentinel-1: Limitations over Certain Crops and Sensitivity to the First Soil Thin Layer*, Water 16(1):40 — [DOI](https://doi.org/10.3390/w16010040) | Ograniczenia S-1 | Estymacje ważne przy NDVI < 0,7; w suchych warunkach S-1 (warstwa ~1 cm) zaniża względem 10 cm nawet o ~20 vol.% | Uprawy polowe, nie sady | streszczenie |
| S11 | Recenzowana | 2025 | *Soil moisture retrieval from Sentinel-1: Lessons learned after more than a decade in orbit*, RSE — [link](https://www.sciencedirect.com/science/article/pii/S0034425725005504) | Stan wiedzy S-1 | Przerwa S-1B: 12 dni rewizyty 2022–2024; S-1C (XII 2024) przywraca 6 dni | **Do przeczytania w całości** (PDF nie został odczytany) | tylko metadane |
| S12 | Recenzowana | 2017 | Sadeghi et al., *The optical trapezoid model (OPTRAM)…*, RSE — [RG](https://www.researchgate.net/publication/317338205) | Wilgotność z optyki | Przestrzeń NDVI–STR (przetransformowany SWIR) bez termiki; S-2 20 m; r ≈ 0,7–0,8 na glebie odkrytej | Tylko bezchmurnie; kalibracja krawędzi per obszar | streszczenie |
| S13 | Recenzowana | 2013 | Merlin et al., *Self-calibrated evaporation-based disaggregation of SMOS soil moisture… at 3 km and 100 m*, RSE — [link](https://www.sciencedirect.com/science/article/abs/pii/S0034425712004324) | Rola LST | DISPATCH: efektywność ewaporacji gleby z LST i NDVI rozdziela wilgotność grubej skali do 100 m i poprawia korelację z in situ | Działa, gdy wilgotność kontroluje ewaporację (lato półsuche) | abstrakt |
| S14 | Recenzowana | 2019 | Guzinski & Nieto, *Evaluating the feasibility of using Sentinel-2 and Sentinel-3 satellites for high-resolution ET*, RSE 221:157 — [RG](https://researchgate.net/publication/329117541) | Downscaling LST S-3 | DMS (zespół drzew decyzyjnych) wyostrza LST S-3 1 km do skali S-2 z dobrymi wynikami; podstawa Sen-ET | Model trenowany na całej scenie, nie na małym AOI | streszczenie |
| S15 | Recenzowana | 2002 / 2015 | Sandholt et al. 2002 (TVDI); krytyka: *Soil Water Content Assessment: Critical Issues Concerning the Operational Application of the Triangle Method*, Sensors 15:6699 — [DOI](https://doi.org/10.3390/s150306699) | Czy TVDI? | TVDI wymaga dużego, heterogenicznego obszaru do wyznaczenia krawędzi; w roślinności mierzy raczej wodę dostępną dla roślin niż wilgotność na danej głębokości | — | streszczenie |
| S16 | Recenzowana | 2025 | Aybar et al., *A radiometrically and spatially consistent super-resolution framework for Sentinel-2* (SEN2SR), RSE — [link](https://www.sciencedirect.com/science/article/pii/S0034425725006261), [GitHub, CC0](https://github.com/ESAOpenSR/SEN2SR) | Rola SR | SR wiąże niskie częstotliwości z oryginałem S-2 (spójność radiometryczna); wagi CC0 | Nie dodaje informacji o wilgotności; żadnej walidacji dla SM | streszczenie + README |
| S17 | Recenzowana | 2025 | *High-resolution drought monitoring with Sentinel-1 and ASCAT: Mozambique*, Agric. Water Manag. — [link](https://www.sciencedirect.com/science/article/pii/S037837742500352X) | Klimatologia anomalii | Seria S-1 (~7 lat) za krótka na stabilną klimatologię; użyto ASCAT 2007–2023 jako tła | Inny klimat | streszczenie |
| S18 | Recenzowana | 2021 | O & Orth, *Global soil moisture data derived through machine learning trained with in-situ measurements*, Sci. Data — [link](https://www.nature.com/articles/s41597-021-00964-1) | ML z ISMN | ML trenowany na ISMN daje wiarygodne produkty przy walidacji na stacjach niewidzianych | Skala globalna | abstrakt |
| S19 | Recenzowane (kilka) | 2024 | ML dla S-1 na ISMN (np. [Frontiers RS 2024](https://www.frontiersin.org/journals/remote-sensing/articles/10.3389/frsen.2024.1513620/full)) | ML: jaki model i jak walidować | Modele drzewiaste (RF/XGBoost) ≥ głębokie sieci; walidacja z wyłączeniem stacji (spatial CV) konieczna | Różne regiony | streszczenie |
| S20 | Dokumentacja | 2024–25 | SentiWiki S-1 — [link](https://sentiwiki.copernicus.eu/web/s1-mission) | Ciągłość danych | S-1C od XII 2024, S-1D planowany | — | opis |

---

## Synteza

### Co jest dobrą praktyką

1. **Głównym sensorem wilgotności powierzchniowej w skali działki jest Sentinel-1 (radar C).** Działa przez chmury, co 6–12 dni, 10–20 m. Wynik trzeba jednak agregować do działki lub ~100 m z powodu szumu plamkowego (speckle). Sprawdzone podejścia: change detection (S08, bez danych treningowych) oraz inwersja Water Cloud Model z korektą roślinności z S-2 (S06, S07).
2. **Roślinność jest głównym ograniczeniem.** Powyżej NDVI ~0,7 sygnał S-1 pochodzi głównie z korony (S07, S10). Latem w sadach i winnicach to realny problem → potrzebne źródła uzupełniające i obniżenie `confidence`.
3. **Termika (LST) ma wartość przez fizykę ewaporacji, nie przez TVDI.** DISPATCH (S13) wiąże LST z efektywnością ewaporacji gleby i rozdziela wilgotność grubej skali do 100 m. TVDI na małym obszarze jest niestabilny (S15) — obecny kod liczy go na AOI ~1,8 × 1,5 km.
4. **Downscaling LST trzeba trenować na całej scenie** (S14), nie na AOI. AOI Condom zawiera ~4 piksele LST 1 km, więc obecny kod zawsze przechodzi na uproszczony TsHARP.
5. **OPTRAM (S12)** daje wilgotność z samego S-2 (20 m) bez termiki. Użyteczny w dni bezchmurne i przy małej pokrywie roślinnej.
6. **Walidacja:** bias, RMSD, ubRMSD, R dla danych surowych **i anomalii**, przedziały ufności, n (S01, S02). Anomalie liczymy tak jak QA4SM (S03). Modele ML walidujemy na **stacjach niewidzianych** w treningu (S18, S19).
7. **Strefa korzeniowa:** filtr wykładniczy SWI kalibrowany na SMOSMANIA (S04). Można go skalibrować na 20 i 30 cm w Condom.
8. **Klimatologia anomalii:** ~9 lat S-1 to mało (S17). Klimatologię trzeba zakotwiczyć w dłuższej serii (ERA5-Land od 1950, CLMS SWI od 2015) i/lub w in situ.

### Co pozostaje niepewne

- Czy S-1 w **sadach i winnicach** (struktura rzędowa, drzewa) daje użyteczny sygnał gleby. Prace S06, S07 i S10 dotyczą głównie upraw polowych.
- Czy downscaling LST poprawia estymację wilgotności ponad sam S-1 + S-2 w warunkach Gers (klimat umiarkowany, nie półsuchy jak w S13).
- Reprezentatywność punktu Condom dla działki 20 m i dla produktów 1 km.
- Jednorodność serii 5 cm przy zmianie czujnika w lutym 2019.

### Wnioski dla roli zwiększania rozdzielczości

| Zabieg | Czy wnosi informację o wilgotności? | Rola w systemie |
|---|---|---|
| S-1 10–20 m → agregacja do działki | **Tak** — bezpośredni pomiar dielektryczny warstwy ~1–5 cm | Rdzeń |
| Wyostrzanie pasm 20 m S-2 do 10 m | Częściowo — lepsze NDVI/STR na małych działkach | Wejście do korekty roślinności i OPTRAM |
| LST S-3 1 km → 20–100 m (DMS) | **Możliwe** — przez efektywność ewaporacji (DISPATCH) | Cecha w fuzji, do sprawdzenia ablacją |
| SR S-2 10 → 2,5 m (SEN2SR) | **Nie bezpośrednio** — model odtwarza teksturę, nie mierzy wody | Podgląd; ewentualnie maska rzędów/międzyrzędzi (eksperyment) |

**Zasada:** każde zwiększenie rozdzielczości wchodzi do produktu dopiero wtedy, gdy **ablacja** (model z nim vs bez niego) pokaże poprawę metryk na stacji niewidzianej w treningu.

### Twierdzenia zakazane

- „Mapa 2,5 m pokazuje wilgotność gleby w rozdzielczości 2,5 m”.
- „TVDI = wilgotność gleby”.
- „Walidacja w Condom potwierdza dokładność na każdej działce”.
- „Anomalia satelitarna = susza” (dozwolone: „anomalia zgodna z przesuszeniem warstwy powierzchniowej”).

---

## Decyzja dla etapu

- **`POTRZEBNA ZMIANA DECYZJI`** — plan v2 przesunął Sentinel-1 do backlogu i opierał produkt na stresie cieplnym z LST. Przegląd wskazuje, że wiarygodne narzędzie do **anomalii wilgotności** wymaga S-1 jako rdzenia, a LST i SR jako warstw uzupełniających. Propozycja: decyzja **D-013** (opisana w `docs/plans/F1_system_wilgotnosci_plan.md`, sekcja 0).
- Pozostałe ustalenia: zgodne z planem v2 (walidacja ISMN, QA4SM jako benchmark, podział po czasie i stacjach, SR tylko po bramce).

## Do zrobienia przed `Approved for implementation`

- [ ] Przeczytać w pełnym tekście: S02, S06, S07, S11, S13, S14 (priorytet: S11 i S07)
- [ ] Sprawdzić dostępność S²MP dla okolic Condom (katalog Theia)
- [ ] Sprawdzić Albergel 2008: czy Condom jest wśród 13 stacji i jaka jest wartość T
- [ ] Sprawdzić ścieżki dostępu do CLMS SSM/SWI przez CDSE
- [ ] Zatwierdzić D-013

## Replikowalność

- Data dostępu do wszystkich linków: 2026-09-26
- Dane in situ: `data/7_isismn_data/SMOSMANIA/Condom/*.stm` (ISMN, pobranie 2016-01-01 → 2025-01-01)
