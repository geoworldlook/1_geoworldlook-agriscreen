# F3 — Przegląd literatury dla platformy anomalii wilgotności (v6)

> **Data:** 2026-10-07 · **Status:** `Draft` — wnioski i propozycje zmian do zatwierdzenia (sekcja 5).
> **Powiązane:** `docs/plans/Plan_v6_platforma_anomalii_wilgotnosci.md`, `docs/evidence/F1_evidence_brief.md`, `docs/plans/Plan_v3_monitoring_winnic_SR.md` (część A).

**Poziomy weryfikacji źródeł:**
- `pełny tekst` — przeczytane w całości. Dotyczy czterech dokumentów przekazanych przez użytkownika; tabelę 2a factsheetu EDO odczytano z obrazu strony.
- `snippet` — tylko streszczenie wyniku wyszukiwania; proxy sesji blokuje pobieranie stron.
- `cytowane za` — praca znana tylko z cytowania w innym przeczytanym tekście.

**Strona projektu WineEO** ([eo4society](https://eo4society.esa.int/projects/wine-eo/)) jest zablokowana przez proxy. Opis WineEO pochodzi ze streszczeń zebranych w `Plan_v6`, sekcja 2 i źródła W1–W15.

---

## 1. Dokumenty przekazane przez użytkownika (pełny tekst)

### 1.1 EDO Combined Drought Indicator, factsheet v4.1.1 (JRC, lipiec 2026)

**Co mówi:**
- **Progi** (s. 3–4): watch = SPI-1 ≤ −2 lub SPI-3 ≤ −1; warning = SMA ≤ −1; alert = anomalia fAPAR ≤ −1. Dane co 10 dni, siatka ~5 km, ERA5 do SPI, LISFLOOD/EFAS v5 do SMA.
- **Klasa zależy też od poprzedniej dekady** (s. 3, tabela 2a). Siedem klas: no drought, watch, warning, alert, recovery, temporary soil-moisture recovery, temporary vegetation recovery.
- **Utrzymanie klasy (odczyt tabeli 2a ze strony 6):**
  - Warning trwa, dopóki SMA ≤ −0,5.
  - Przy SMA w (−0,5; 0] klasa zmienia się na „temporary SM recovery”, a przy SMA > 0 na recovery lub watch.
  - Alert trwa, dopóki anomalia roślinności ≤ −0,5; analogicznie przechodzi w „temporary vegetation recovery”.
- **Alert nie wymaga SMA ≤ −1.** Anomalia roślinności ≤ −1 daje alert, jeśli:
  - jest deficyt opadu (kolumna G), albo
  - poprzednia dekada była już w stanie suszy (kolumna D).

  Bez deficytu opadu i po dekadzie „no drought” lub „recovery” sama anomalia roślinności nie daje alertu.
- **Reguła mokrego opadu (kolumna C):** SMA ≤ −1 po dekadzie „no drought” lub „recovery” daje „no drought”, jeśli SPI-1 > 0,5 i SPI-3 > 0, czyli wróciły opady.
- **v4.1 (luty 2026, s. 5):** ujemne anomalie fAPAR są pomijane, gdy SPI-1 > 1. Spadek zieloności przy nadmiarze wody to nie susza.
- **Maski upraw (s. 4):** poza sezonem wegetacji ujemne anomalie roślinności nie wchodzą do wskaźnika (tabela 2b). Słabość, którą przyznaje sam JRC (s. 12): maski są statyczne, z ustalonym początkiem i końcem sezonu.
- **Mocna strona (s. 12):** połączenie opadu, gleby i roślinności zmniejsza liczbę fałszywych alarmów, bo spadek biomasy może mieć inne przyczyny niż susza.

**Co z tego wynika dla nas:**
- Nasz `build_status` to uproszczenie: alert = warning ∧ NDVI ≤ −1, bez pamięci stanu, a klasa recovery jest jedna.
- Odtworzyłem logikę z tabeli 2a na twoim `status_dekads.csv` (VINEYARD_06, 2016–2026, NDVI 10 m; skrypt `docs/evidence/edo_cdi_replay.py`):

| | AgriWatch (obecnie) | EDO v4.1.1 (odtworzone) |
|---|---|---|
| Zgodność klas (recovery zgrupowane) | — | 86% dekad |
| Dekady alert, roślinność IV–X | 28 | 40 (2017: 8, 2019: 7, 2020: 1, 2022: 11, 2023: 2, 2026: 11) |
| Dekady alert, roślinność VI–IX | 15 | 20 (2020: 1, 2022: 8, 2026: 11) |

- Dodatkowe alerty EDO pochodzą z utrzymania klasy przy anomalii roślinności między −1 a −0,5 oraz z kolumn D i G (roślinność ≤ −1 bez SMA ≤ −1).
- Część z nich przypada na kwiecień–czerwiec 2017 i 2019. Sekcja 1.2 pokazuje, dlaczego wiosenny NDVI winnicy jest podejrzany.

### 1.2 Pantaleoni Reluy i in. 2022, *Can we detect the damage of a heatwave on vineyards using Sentinel-2?*, OENO One 56(1):145–159, [DOI 10.20870/oeno-one.2022.56.1.4632](https://doi.org/10.20870/oeno-one.2022.56.1.4632)

**Co mówi:**
- **Dane:** 141 działek (100,85 ha) w Hérault i Gard; 102 sceny S-2 z okresu III–X 2016–2019; fala upałów 24–28 VI 2019.
- **Działki:** rozstaw rzędów 2 m w 22%, 2,5 m w 74,5%; okrywa w międzyrzędziu na 66%.
- **Cykl NDVI winnicy (s. 6):**
  - zimą ~0,3 (gleba i rośliny zimozielone),
  - w czerwcu 0,5–0,6,
  - w VII–VIII 0,4–0,6.

  Do analizy brali tylko piksele ze średnim NDVI > 0,2 w okresie 27 VI – 5 IX.
- **Kryteria:**
  - C1 (między latami): średnie NDVI 27 VI – 5 IX 2019 minus średnia z lat 2016–2018, próg −0,05.
  - C2 (w obrębie roku): maksimum NDVI po upale minus NDVI przed upałem, próg 0.
  - Uśrednianie NDVI z dwóch miesięcy zmniejsza szum i luki chmurowe (s. 7).
- **Wyniki na 18 działkach (s. 10–11):**

| Kryterium | Trafność ogółem | Nieuszkodzone rozpoznane poprawnie | Uszkodzone wykryte |
|---|---|---|---|
| C1 | 76% | 91% | 46% |
| C2 | 80% | 88% | 62% |
| C1 ∧ C2 | 79% | 99% | 40% |

- **Wykrywalność (s. 13):** przy 10 m widać tylko silne uszkodzenia liści. 81% (C1) i 91% (C2) błędnie sklasyfikowanych uszkodzonych pikseli to uszkodzenia umiarkowane.
- **Fałszywe alarmy (s. 12):** w roku bez fali upałów (2017) C1 oznaczyło 28% pikseli jako uszkodzone. Autorzy łączą to z bardzo gorącym czerwcem 2017.
- **Międzyrzędzie (s. 13):** na południu Francji okrywę zwykle niszczy się od kwietnia do połowy maja. Latem w nienawadnianych winnicach trawa wysycha. Pod koniec czerwca wpływ międzyrzędzia na NDVI uznali za mały.

**Co z tego wynika dla nas:**
1. **Wiosenny NDVI winnicy mierzy głównie zabiegi w międzyrzędziu, nie suszę.** Warstwa roślinności w IV–V jest źródłem fałszywych alertów. Uzasadnia to test sezonu VI–IX (sekcja 5, Z2).
2. **Anomalia z jednej sceny jest zaszumiona.** Uśrednienie z okna (np. 30 dni) poprawia stabilność i omija chmury (Z3).
3. **Drugie kryterium podnosi swoistość z ~90% do 99%** kosztem czułości. Nasz „alert” to komunikat „sprawdź winnicę”, więc swoistość jest ważniejsza (Z3).
4. **Upał zmniejsza NDVI tak samo jak susza.** Bez informacji o temperaturze alert może mylić przyczynę (Z6).
5. **NDVI 10 m widzi tylko silne zmiany.** Uczciwy opis na karcie: „wykrywamy wyraźne pogorszenie roślinności, nie umiarkowany stres”.

### 1.3 Laroche-Pinel i in. 2021, *Monitoring vineyard water status using Sentinel-2 images: qualitative survey on five wine estates*, OENO One 55(4):115–127, [DOI 10.20870/oeno-one.2021.55.4.4752](https://doi.org/10.20870/oeno-one.2021.55.4.4752)

**Co mówi:**
- **Model z wcześniejszej pracy (s. 3):** ponad 2500 pomiarów Ψstem komorą ciśnieniową na 36 działkach w latach 2018–2020. Najlepszy model używa pasm **B4, B8, B6, B11**: R² = 0,40, RMSE = 0,26.
  - Uwaga: streszczenie z wyszukiwarki w `Plan_v6` (W12) podawało B8A i B12. Pełny tekst je koryguje.
- **Zastosowanie:**
  - 170 działek (220 ha) w 5 gospodarstwach koło Carcassonne i Béziers.
  - VI–IX 2020: około 10 użytecznych scen na działkę, czyli jedna bezchmurna scena na ~7 dni.
  - Pas wewnętrzny 5 m; tylko piksele w całości wewnątrz działki (s. 4).
- **Interpretacja Ψstem (s. 5):** pożądany poziom stresu zależy od fazy rozwoju i od docelowego wina. Ψstem < −1,6 MPa oznacza nadmierny stres (za Deloire 2020).
- **Ocena przez winiarzy (s. 9):**
  - 3 z 5 chcą korzystać z usługi.
  - 1 z 5 chce najpierw kilku lat testów.
  - 1 z 5 (gospodarstwo poniżej 50 ha) zna swoje działki i nie potrzebuje usługi.
- **Spójność wyników (s. 6–9):** model reaguje na upał i deszcz oraz odróżnia działki nawadniane kroplowo, zraszaczami i nienawadniane. Mapy pokazały wpływ źródła wody, gleby i wieku winorośli.
- **Ograniczenia (s. 10):**
  - Wypady krzewów > 20% zawyżają stres; potrzebny próg wigoru, poniżej którego nie liczy się stresu.
  - Latem trawa w międzyrzędziu na południu nie przeszkadzała.
  - Ψstem ma własne ograniczenia, m.in. dla odmian izohydrycznych.
- **Usługa (s. 10):** dwa poziomy — gospodarstwo i region (syndykat); monitoring wieloletni; dołączenie pogody, historii i prognozy.

**Co z tego wynika dla nas:**
1. **Pas wewnętrzny określony w metrach (5 m), nie w pikselach.** U nas pas to 1 piksel, czyli 10 m przy 10 m i tylko 2,5 m przy SR. To wspiera wariant C testu H-SR2 (`Plan_v6`, sekcja 6) i wspólny pas metryczny dla obu produktów (Z4).
2. **Maska wigoru:** działka lub piksel z niskim NDVI w lecie (wypady, młode nasadzenia) nie powinny dawać alertu z roślinności (Z5).
3. **Ta sama sucha anomalia znaczy co innego dla różnych win.** Karta nie powinna sugerować szkody. Pole „cel produkcji” to kandydat na atrybut działki (później).
4. **Dwa poziomy odbiorców:** winiarz (działka) i spółdzielnia (wszystkie działki). Nasze 15 winnic przy Cave de Condom pasuje do poziomu „spółdzielnia”.
5. **Model TerraNIS używa pasm 20 m (B6, B11).** U nas pasma 20 m po SR nie przechodzą H-SR1, więc wskaźniki tego typu liczymy z 10 m, nie z SR.

### 1.4 Núñez-Ibarra i in. 2025, *From grid to ground: How well do gridded products represent soil moisture dynamics…*, EGUsphere preprint, [DOI 10.5194/egusphere-2025-2606](https://doi.org/10.5194/egusphere-2025-2606)

> Preprint w dyskusji (od 28 VII 2025), **bez recenzji**. Dotyczy naturalnych ekosystemów Chile, nie winnic.

**Co mówi:**
- **Dane:** 10 stacji w Chile (5 półsuchych, 5 wilgotnych); 4 produkty (SMAP L4, GLDAS-Noah, ERA5, ERA5-Land); krok 3 godziny.
- **ERA5 i ERA5-Land wypadają najlepiej.** Strefa korzeni (0–100 cm) jest odwzorowana lepiej niż warstwa powierzchniowa.
- **ERA5-Land, strefa korzeni:** średnie KGE′ = 0,70; Spearman ρ szeregów bez sezonowości > 0,5 na wszystkich stacjach (s. 32).
- **Duże obciążenie wartości bezwzględnych na stacjach suchych:** PBIAS ERA5-Land na północy = 51,2% (powierzchnia) i 39,1% (strefa korzeni) (tab. 5).
- **Pierwszy deszcz po suszy:** wszystkie produkty zawyżają czas narastania wilgotności (o > 20 h, ~100%) i amplitudę (> 0,02 m³/m³). Przy intensywnych opadach błąd jest mniejszy (s. 32).
- **Wilgotność strefy korzeni z czujników:** średnia ważona grubością warstw przypisanych czujnikom do ~100 cm (równ. 1b, 2).
- **Zalecenia:** Spearman ρ na szeregach bez sezonowości; uśrednianie przestrzenne stacji poprawia zgodność.
- **Wyższa rozdzielczość nie gwarantuje lepszej zgodności z pomiarem** (s. 30; cytowane za Schmidt i in. 2024, Degano i in. 2024, Ortenzi i in. 2024).

**Co z tego wynika dla nas:**
1. **Pracujemy na anomaliach — to właściwy wybór.** Wartość bezwzględna ERA5 może mieć obciążenie rzędu kilkudziesięciu procent. Na karcie (`Plan_v6`, pole `absolute`) trzeba ją podpisać jako wartość modelu, nie pomiar (Z7).
2. **Nasza walidacja porównuje ERA5 0–100 cm z czujnikami 20–30 cm.** To niezgodność głębokości. Condom ma czujniki tylko do 30 cm. Uczciwsze porównanie:
   - ERA5 0–28 cm (warstwy 1–2, ważone grubością)
   - z profilem in situ 0–30 cm ważonym jak w równ. 1b–2 (5, 10, 20, 30 cm) (Z8).
3. **Dodać Spearman ρ obok Pearson R** w `gwl_validation_metrics` (Z8).
4. **Klasa recovery po pierwszym jesiennym deszczu** może przyjść w ERA5 za szybko lub za mocno. Do sprawdzenia testem zdarzeń: czas narastania i amplituda wilgotności po pierwszym deszczu po lecie, ERA5 vs Condom (Z8).
5. **Ostrzeżenie dla SR:** wyższa rozdzielczość sama w sobie nie poprawia zgodności z pomiarem. Potwierdza to sens testu H-SR2 przed wnioskami.

---

## 2. Mój przegląd: prace uzupełniające

| Źródło | Co mówi | Wniosek dla nas | Poziom |
|---|---|---|---|
| Sozzi i in. 2020, OENO One — [HAL](https://hal.inrae.fr/hal-02942190v1) | 30 bloków bez trawy w międzyrzędziu (płd. Francja): NDVI S-2 vs UAV R² = 0,87 dla bloku, 0,84 wewnątrz bloku. Korelacja rośnie po usunięciu pikseli brzegowych. Poniżej 0,5 ha zwykle nieistotna | Usuwać brzeg (Z4); działki < 0,5 ha = niska pewność (u nas najmniejsza ma 0,68 ha) | snippet |
| Devaux i in. 2019, OENO One 53(1):52–59 — [HAL](https://hal.inrae.fr/hal-02609421) | Z szeregów NDVI S-2 da się odczytać fazy winorośli (pąkowanie, wzrost, ogławianie, koniec wzrostu, starzenie) oraz zabiegi na chwastach i w międzyrzędziu | NDVI winnicy zawiera sygnał zabiegów; anomalia może być zabiegiem (Z2, Z3) | snippet |
| Ji i Peters 2003, Remote Sens. Environ. — [USGS](https://pubs.usgs.gov/publication/70156737) | NDVI najlepiej koreluje z SPI-3 (opóźnienie i kumulacja). Korelacja najwyższa w środku sezonu, niższa na początku i końcu | Roślinność reaguje z opóźnieniem tygodni; początek i koniec sezonu mają najsłabszy związek z wodą (Z2) | snippet |
| Beck i in. 2021, HESS 25:17–40 — [HESS](https://hess.copernicus.org/articles/25/17/2021/) | 18 produktów wilgotności gleby vs 826 czujników (5 cm, 2015–2019, głównie USA i Europa) | Ramy wyboru i walidacji produktu wilgotności; tło dla ERA5-Land | snippet |
| Groenveld i in. 2023, BMC Plant Biol. — [PMC](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10367393/) | 30 odmian: potencjał przedświtowy liścia ≈ potencjał wody w glebie tylko w suchej glebie; w mokrej jest niższy | Wilgotność gleby i stan wody winorośli to różne wielkości; status nie diagnozuje stresu winorośli (Z7) | snippet |
| Klasy potencjału przedświtowego (Carbonneau) — [wyniki wyszukiwania](https://oeno-one.eu/article/view/1566) | 0…−0,2 MPa brak deficytu; −0,2…−0,4 łagodny–umiarkowany; −0,4…−0,6 umiarkowany–silny; −0,6…−0,8 silny | Język „umiarkowany niedobór bywa pożądany” na karcie; progi dopiero w pilotażu z pomiarem | snippet |
| opensr-test (Aybar i in.) — [GitHub](https://github.com/ESAOpenSR/opensr-test) | Benchmark SR S-2 na rzeczywistych parach obrazów; trzy grupy metryk: spójność, synteza, poprawność | Nasze H-SR0 i H-SR1 to uproszczone „synteza” i „spójność”; pełny test na danych referencyjnych jest możliwy później | snippet |
| Schmidt i in. 2024; Degano i in. 2024; Ortenzi i in. 2024 | Produkty wilgotności w wyższej rozdzielczości nie zawsze lepsze od grubszych | Jak 1.4, wniosek 5 | cytowane za Núñez-Ibarra 2025 |

---

## 3. Co uważam (synteza)

1. **Wzorzec EDO jest dobry, ale mamy go w uproszczeniu.** Pełna logika v4.1.1 (pamięć stanu, klasy przejściowe, wykluczenie przy SPI-1 > 1) to około 60 linii kodu. Daje produkt bliższy temu, co publikuje JRC. Na naszych danych zmienia 14% dekad.
2. **Największe ryzyko produktu to fałszywe alerty z roślinności,** nie brak czułości. Trzy niezależne źródła (Pantaleoni 2022, Devaux 2019, Ji i Peters 2003) wskazują ten sam okres ryzyka: początek i koniec sezonu. Wtedy NDVI winnicy mówi o zabiegach w międzyrzędziu i o fenologii, nie o wodzie. Na naszych danych ograniczenie do VI–IX skupia alerty w latach 2022 i 2026.
   - To **hipoteza, nie dowód**. Trzeba ją sprawdzić na niezależnej referencji (dekady suszy z ISMN) **przed** zmianą, a nie dobierać sezon tak, żeby wynik „ładnie wyglądał”.
3. **Pojedyncza scena to za mało do alertu.** Okno 30 dni plus drugie kryterium (spadek w sezonie) to tani sposób na wysoką swoistość. To właściwy kierunek dla komunikatu „sprawdź winnicę”.
4. **SR 2,5 m: brak dowodów, że pomaga w wykrywaniu.**
   - W literaturze nie znalazłem pracy, która pokazuje poprawę wykrywania suszy w winnicach dzięki SR S-2.
   - Są natomiast dowody, że **usunięcie brzegu** i **czysty rdzeń działki** poprawiają NDVI winnicy (Sozzi 2020, Laroche-Pinel 2021).
   - Najbardziej prawdopodobny zysk z SR to precyzyjniejsza maska rdzenia i czytelna mapa. Pod warunkiem że pas brzegowy liczymy w metrach (wariant C testu H-SR2), a nie w pikselach.
5. **ERA5-Land to rozsądne źródło anomalii strefy korzeni** (Núñez-Ibarra 2025; nasze R = 0,58 w Condom). Wartości bezwzględne i szybkość reakcji po pierwszym deszczu wymagają ostrożności. Nasza walidacja ma niezgodność głębokości, którą łatwo poprawić.
6. **Komunikat „sprawdź winnicę” jest właściwy.** Literatura winiarska jest zgodna, że niedobór wody bywa celowy, a jego znaczenie zależy od fazy i stylu wina. Produkt mówi o odchyleniu od normy, nie o stresie.

---

## 4. Korekty w `Plan_v6`

| Miejsce | Było | Jest (pełny tekst) |
|---|---|---|
| Źródło A1 | „do sprawdzenia: alert w EDO bez warunku SMA” | Potwierdzone (tab. 2a): alert = roślinność ≤ −1 przy deficycie opadu **albo** po dekadzie suszy; SMA nie jest konieczne |
| Źródło W12 | pasma B4, B6, B8A, B12 | **B4, B8, B6, B11**; R² = 0,40, RMSE = 0,26; > 2500 pomiarów Ψstem |

---

## 5. Propozycje zmian (do zatwierdzenia)

Kolejność według stosunku wartości do kosztu.

| ID | Zmiana | Uzasadnienie | Test przed włączeniem | Koszt |
|---|---|---|---|---|
| Z1 | Pełna logika EDO CDI v4.1.1 w `build_status`: pamięć stanu, klasy `temp_sm_recovery` i `temp_veg_recovery`, wykluczenie roślinności przy SPI-1 > 1, reguła mokrego opadu | 1.1; produkt zgodny ze źródłem wzorca | Odtworzenie na danych 2016–2026 (zrobione: zgodność 86%); POD/FAR obu wersji vs dekady suszy ISMN | ~1 h; prototyp: `edo_cdi_replay.py` |
| Z2 | Warstwa roślinności w statusie tylko VI–IX (`VEG_STATUS_MONTHS`); IV–V i X zostają na wykresach | 1.2, Devaux 2019, Ji i Peters 2003 | **Zapisane przed testem:** zmiana wchodzi, jeśli FAR alertów vs dekady suszy ISMN (20–30 cm ≤ −1) nie rośnie, a liczba alertów w IV–V i X spada | 0,5 h |
| Z3 | Anomalia roślinności z okna 30 dni (średnia czystych scen) zamiast jednej sceny; drugie kryterium: spadek NDVI od maksimum sezonu większy niż w innych latach | 1.2 (C1 ∧ C2: swoistość 99%) | R anomalii z ISMN (paired) i liczba zmian klas dekada do dekady (stabilność) | 2–3 h |
| Z4 | Wspólny pas brzegowy w metrach (`EDGE_BUFFER_M`, np. 5 lub 10 m) dla 10 m i 2,5 m | 1.3 (5 m), Sozzi 2020 | Wariant C w H-SR2 | 0,5 h |
| Z5 | Maska wigoru: piksele i działki ze średnim NDVI VI–IX < 0,2 poza warstwą roślinności; przy wysokim udziale takich pikseli — niska pewność | 1.2 (NDVI > 0,2), 1.3 (wypady > 20%) | Liczba wykluczonych pikseli per działka | 1 h |
| Z6 | Flaga upału w `reason_codes`: Tmax ≥ 35 °C w 10 dniach przed sceną (dodać `temperature_2m_max` do ERA5-Land) | 1.2 (2017, 2019) | Liczba alertów z flagą upału w 2016–2026 | 1 h |
| Z7 | Karta: wartość bezwzględna ERA5 podpisana jako model; zdanie „status ≠ stres winorośli”; opcjonalny atrybut celu produkcji | 1.3, 1.4, Groenveld 2023 | — | w ramach `Plan_v6`, tydz. 3 |
| Z8 | Walidacja: ERA5 0–28 cm vs profil Condom 0–30 cm ważony grubością; Spearman ρ obok R; test zdarzeń po pierwszym jesiennym deszczu (czas narastania, amplituda) | 1.4 | — (to sama walidacja) | 2 h |

**Proponowana kolejność:** Z1 + Z2 + Z4 (jedno uruchomienie, test POD/FAR) → Z8 → Z3 → Z5, Z6.

---

## 6. Inne wskaźniki: co wnoszą i czy je dodać

**Punkt wyjścia z naszych danych** (`Plan_v4`, sekcja 2; Condom, okres kalibracji 2016–2021, wartości surowe, nie anomalie):

| Źródło | R z czujnikiem 20–30 cm |
|---|---|
| ERA5-Land | 0,83 |
| NDVI S-2 | 0,56 |
| STR S-2 | 0,39 |
| OPTRAM S-2 | 0,35 |
| Sentinel-1 change detection (bufor 50 m) | 0,34 |

ERA5 z dodanymi satelitami nie był lepszy od samego ERA5 (0,81 vs 0,81). Na jednej stacji satelity nie poprawiają więc przebiegu w czasie.

**Co z tego wynika dla oceny wskaźników:**
- Wskaźnik roślinny ma inną rolę: pokazać, **która winnica** odstaje od sąsiednich.
- Jedna stacja ISMN tego nie sprawdzi. Do oceny wskaźników roślinnych potrzebne są:
  - zgodność ze zdarzeniami (np. 2022),
  - odporność na zabiegi,
  - docelowo obserwacje terenowe (pilotaż).

### 6.1 Przegląd według warstw wzorca EDO

| Warstwa | Wskaźnik | Co mówi literatura | Ocena dla nas |
|---|---|---|---|
| Opad | **SPI-1, SPI-3** (mamy) | Wskaźnik WMO, używany w EDO (F3, 1.1) | Zostaje (logika EDO) |
| Opad + parowanie | **SPEI-3** (opad − ET0) | SPEI dodaje zapotrzebowanie atmosfery na wodę (Vicente-Serrano 2010). W porównaniu globalnym różnice z SPI są małe, ale latem SPEI najlepiej koreluje z skutkami suszy. Wzrost temperatury nasila susze w płd. Europie (Vicente-Serrano 2014) — [przegląd UniRioja](https://investigacion.unirioja.es/documentos/5ea025a5a56eaf31994806ef?lang=en), [NHESS 2019](https://nhess.copernicus.org/articles/19/1215/2019/) | **Dodać jako przyczynę na karcie (Z9).** Lata 2022 i 2026 to susza z upałem, a SPI tego nie widzi. Do logiki statusu dopiero po teście |
| Gleba | **SMA ERA5-Land 0–100 cm** (mamy) | R anomalii 0,58 w Condom; ERA5-Land najlepszy z 4 produktów w Núñez-Ibarra 2025 | Zostaje |
| Gleba | **CGLS SWI 1 km** (ASCAT + S-1, filtr wykładniczy) | Metoda filtra wykładniczego (Albergel 2008, [HESS 12:1323](https://hess.copernicus.org/articles/12/1323/2008/)) powstała **na sieci SMOSMANIA**. SWI dobrze oddaje wilgotność strefy korzeni | **Dodać jako niezależne drugie źródło gleby (Z10)**: zgodność ERA5 i SWI podnosi pewność, rozbieżność ją obniża |
| Gleba | Sentinel-1 SSM 1 km (CLMS) | Balenzano 2021 ([rsc4earth](https://rsc4earth.de/publication/balenzano-sentinel-1-2021/)): 167 stacji, R 0,54, RMSE 0,07 m³/m³; tylko 5 cm | Nie jako warstwa główna: płytko, a w oczku 1 km jest wiele upraw |
| Gleba | Sentinel-1 change detection 50 m (mamy w `step_07`) | Nasze: R 0,34; szum plamkowy | **Nie** dla działki |
| Gleba (optyka) | STR, OPTRAM | Sadeghi 2017 ([RSE 198:52](https://experts.umn.edu/en/publications/the-optical-trapezoid-model-a-novel-approach-to-remote-sensing-of/)): błąd ~0,04 m³/m³ w zlewniach półsuchych; wymaga kalibracji krawędzi trapezu | **Nie**: nasze R 0,35–0,39; okrywa winnicy zakłóca sygnał gleby |
| Roślinność | **NDVI** (mamy; SR 2,5 m) | Zielona masa; w winnicy miesza rząd i międzyrzędzie (F3, 1.2) | Zostaje (Z2–Z5) |
| Roślinność, woda | **NDMI / NDWI (Gao)** (NIR–SWIR) | Brak pracy z NDMI vs Ψstem na S-2. NDWI: R² 0,54–0,67 na datę, MSI 0,53–0,63; NDWI/EVI najlepszy w dwóch winnicach w Belgii (Delval i in., [EGU22-3908](https://meetingorganizer.copernicus.org/EGU22/EGU22-3908.html), konferencja). TerraNIS używa SWIR B11 (F3, 1.3). NDWI reaguje szybciej niż NDVI | **Dodać jako drugi wskaźnik roślinny na karcie (Z11)**, liczony **z pasm natywnych 10/20 m** (pasma 20 m po SR nie przechodzą H-SR1). Nasze R ≈ 0,4, tak jak NDVI — do statusu tylko, jeśli test paired pokaże wartość dodaną |
| Roślinność | **fAPAR / LAI (S-2, SL2P)** | Zmienna EDO. SL2P (Weiss i Baret 2016) dostępny w GEE (LEAF Toolbox). Dobrze dla jednorodnych upraw; zaniża LAI w łanach niejednorodnych (brak skupienia liści w modelu) — [Brown i in., Southampton](https://eprints.soton.ac.uk/503206/) | **Opcjonalnie (Z12)**: zgodność z EDO, ale winnica to łan rzędowy; zysk względem NDVI do pokazania |
| Roślinność | NDRE, CIre (red-edge) | Reagują na chlorofil i azot, nie wprost na wodę; dłużej czułe w gęstym łanie | **Nie** do suszy; ewentualnie do wigoru |
| Roślinność | kNDVI, NIRv | Odpowiedź na nasycenie NDVI w gęstym łanie; kNDVI zależy od parametru jądra | **Nie**: NDVI winnicy (0,4–0,6) nie jest nasycone |
| Roślinność | VCI / VHI (Kogan) | VCI = położenie w zakresie min–max z lat. Krótki zapis danych to znana słabość ([droughtmanagement.info](https://www.droughtmanagement.info/vegetation-condition-index-vci/)) | **Nie**: przy 9–10 latach S-2 min i max są niestabilne. Nasz z-score i percentyl robią to samo stabilniej |
| Termika | **LST Landsat 8/9** (100 m, próbkowane do 30 m) | Najbardziej bezpośredni sygnał stresu (zamykanie aparatów szparkowych). Termika wykrywa stres, którego nie widzą wskaźniki odbiciowe (USDA ARS: [NASA Landsat](https://landsat.gsfc.nasa.gov/article/landsat-thermal-data-provides-insight-to-vintners)). CWSI winorośli z czujników naziemnych: R² 0,83 z Ψliścia; wymaga kalibracji na fazę i odmianę ([Bellvert 2013](https://quantalab.ias.csic.es/pdf/PrecAgricul_CWSI%20Bellvert%202013_n.pdf)) | **Eksperyment (Z13)**: winnice 0,7–4 ha to 1–4 piksele termiczne; anomalia LST względem sąsiednich działek w dniu przelotu (L8 + L9 co ~8 dni) |
| Termika | ECOSTRESS (70 m) | Różne pory dnia; produkt ESI ([JPL](https://ecostress.jpl.nasa.gov/)) | **Nie** jako podstawa: nieregularne przeloty, misja do ~2026 |
| Termika | S-3 LST 1 km + wyostrzanie (DMS/TsHARP) | Sen-ET: wyostrzanie do 20 m; walidacja ET na 8 wieżach (w tym winnice Hérault): R 0,60, RMSE 1,38 mm/d ([Guzinski, LPS 2022](https://earth.esa.int/living-planet-symposium-2022-presentations/25.05.Wednesday/H1-01/1330-1510/05_Guzinski_2_.pdf)). pyDMS: R > 0,74 z temperaturą gleby, RMSE 4–15 °C | **Nie teraz**: duży błąd na poziomie działki; kod jest w `legacy/` (v2.5). Wrócić przy TRISHNA |

### 6.2 Zasada doboru wskaźnika

Każdy nowy wskaźnik przechodzi ten sam test, zapisany przed obliczeniem:

1. **R anomalii** z czujnikiem 20–30 cm na tych samych dniach co wskaźnik odniesienia (paired), z 95% CI.
2. **Wartość dodana:** korelacja cząstkowa z czujnikiem po usunięciu wpływu ERA5 SMA. Wskaźnik, który nie dodaje nic do ERA5, nie wchodzi do logiki statusu, najwyżej na kartę.
3. **Zdarzenia:** czy w 2022 (VII–IX) wskaźnik pokazuje anomalię ≤ −1 w ≥ 12 z 15 winnic (V4 z `Plan_v6`).
4. **Odporność na zabiegi:** odsetek zmian znaku anomalii dekada do dekady w IV–V (niższy = lepiej).

### 6.3 Propozycje (ciąg dalszy Z1–Z8)

| ID | Zmiana | Uzasadnienie | Koszt |
|---|---|---|---|
| Z9 | SPEI-3 z ERA5-Land (ET0 metodą Hargreavesa z Tmin/Tmax albo FAO Penman-Monteith z promieniowania, wiatru i punktu rosy) na karcie jako przyczyna | Susze z upałem; SPI ich nie widzi | 1–2 h (dodatkowe pasma ERA5-Land w `step_01`) |
| Z10 | CGLS SWI 1 km (T = 10–40) jako drugie źródło anomalii gleby; zgodność z ERA5 w polu `confidence` | Niezależny pomiar satelitarny; metoda z sieci SMOSMANIA | 2–3 h (dostęp GEE/CDSE do sprawdzenia) |
| Z11 | NDMI z pasm natywnych (10/20 m) dla każdej winnicy: anomalia na karcie; test paired vs NDVI | SWIR jest czuły na wodę w liściach; TerraNIS używa B11 | 1 h (`compute_indices` już liczy NDMI) |
| Z12 | fAPAR S-2 (SL2P) jako alternatywa NDVI w warstwie roślinności; test wg 6.2 | Zgodność z EDO | 3–4 h |
| Z13 | Eksperyment: anomalia LST Landsat 8/9 winnicy względem mediany winnic AOI w dniu przelotu | Najbardziej bezpośredni sygnał stresu | 4–6 h |

**Nie dodajemy:**
- VCI (krótki zapis),
- kNDVI i NIRv (brak nasycenia),
- NDRE do suszy (to wskaźnik chlorofilu),
- STR, OPTRAM i S-1 na poziomie działki (nasze R ≤ 0,39),
- ECOSTRESS (nieregularny, kończąca się misja),
- wyostrzone LST S-3 (błąd za duży dla działki).

**Kolejność:** Z11 i Z9 (tanie, wartość na karcie od razu) → Z10 → Z12 → Z13.

**Źródła sekcji 6:** wszystkie na poziomie `snippet` (pełne teksty zablokowane), poza danymi własnymi z `Plan_v4`.

---

## Źródła

**Pełny tekst (przekazane przez użytkownika):**
1. JRC, *EDO Indicator Factsheet: Combined Drought Indicator v4.1.1*, 2026 (ostatnia aktualizacja 2026-07-24).
2. Pantaleoni Reluy N., Baghdadi N., Simonneau T., Bazzi H., El Hajj M. M., Pret V., Amin G., Daret E. (2022). OENO One 56(1):145–159. DOI 10.20870/oeno-one.2022.56.1.4632.
3. Laroche-Pinel E., Duthoit S., Costard A. D., Rousseau J., Hourdel J., Vidal-Vigneron M., Cheret V., Clenet H. (2021). OENO One 55(4):115–127. DOI 10.20870/oeno-one.2021.55.4.4752.
4. Núñez-Ibarra D. A., Zambrano-Bigiarini M., Galleguillos M. (2025). EGUsphere, preprint. DOI 10.5194/egusphere-2025-2606.

**Streszczenia wyszukiwania (snippet):** źródła z sekcji 6 (linki w tabeli 6.1); Sozzi i in. 2020; Devaux i in. 2019; Ji i Peters 2003; Beck i in. 2021; Groenveld i in. 2023; klasy Carbonneau; opensr-test — linki w tabeli w sekcji 2.
