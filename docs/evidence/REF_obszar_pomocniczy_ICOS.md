# REF — obszar pomocniczy z pomiarami wilgotności gleby w terenie (notatka metodyczna)

> **Status:** `APPROVED` 2026-10-15 (D-082). Protokół walidacji: `docs/evidence/W2_REF_protokol_walidacji.md` (D-083). Dane sprawdzone 2026-10-15 w portalu ICOS Carbon Portal
> (metadane SPARQL i pliki danych). Żadnej analizy wobec AgriScreen jeszcze nie wykonano.

## Wynik w skrócie

1. **Po co:** AgriScreen twierdzi, że stan wody dowolnego pola można opisać anomalią jego własnego piksela wobec
   jego historii. Tego twierdzenia nie da się obronić na jednej stacji (Condom, ISMN) z czujnikami o znanych
   artefaktach (A4). Potrzebna jest druga, niezależna referencja naziemna, najlepiej z danymi bieżącymi.
2. **Czego szukaliśmy:** otwarte dane, pomiar w gruncie na kilku głębokościach, kilka czujników na głębokość
   (kontrola artefaktów, lekcja z A4), dane w czasie zbliżonym do rzeczywistego, klimat podobny do Gers.
3. **Rekomendacja:**
   - **FR-Lus (Lusignan)** jako obszar pomocniczy z danymi bieżącymi: łąka, 272 km na północ od winnicy, 6 poziomów,
     2–4 czujniki na poziom, dane co pół godziny aktualizowane codziennie.
   - **FR-Aur (Auradé, Gers)** jako druga referencja historyczna w regionie: pole uprawne 78 km od winnicy,
     5 poziomów, 2–4 czujniki na poziom, archiwum 2019–2025 (oraz 2005–2025 w produkcie FLUXNET), bez danych bieżących.
4. **Czego nie ma:** otwartej stacji z wilgotnością gleby w winnicy, z danymi bieżącymi. ICOS nie ma winnic, a ISMN
   (SMOSMANIA Condom) jest niedostępny od kilku dni.

## 1. Sprawdzone stacje (ICOS, dane 2026-10-15)

| Stacja | Ekosystem | Od winnicy | Dane bieżące (NRT) | Wilgotność gleby w NRT | Historia (L2 / FLUXNET) | Ocena |
|---|---|---|---|---|---|---|
| **FR-Lus** Lusignan | łąka | 272 km | tak, do 14.10.2026 | 6 poziomów, 100% kompletności, 2–4 czujniki | L2 2022–VIII 2026 (pełne lata 2023–2026), FLUXNET 2022–2026 | **rekomendowana jako obszar pomocniczy** |
| **FR-Aur** Auradé (Gers) | pole uprawne (pszenica, rzepak, słonecznik, poplony) | 78 km | nie (stacja „Associated”) | — | L2 2019–2025 (78–92% dni, 2022 ok. 50%), FLUXNET 2005–2025 | **rekomendowana jako referencja historyczna** |
| FR-Gri Grignon | pole uprawne | ok. 560 km | tak | **0% — brak odczytów wilgotności** | L2 2021–2026, FLUXNET 2004–2026 | odrzucona (brak bieżącej wilgotności) |
| FR-Lam Lamasquère | pole uprawne | ok. 90 km | zakończona I 2025 | — | — | odrzucona (stacja wycofana) |
| FR-Pue Puéchabon | las dębu ostrolistnego | ok. 260 km | tak, 100% | 5 poziomów | FLUXNET 2000–2026 | las — inna dynamika wody |
| FR-FBn Font-Blanche | las | ok. 435 km | tak, 100% | 5 poziomów | L2 2022–2026 | las |
| FR-Bil Bilos | las sosnowy, gleba piaszczysta | ok. 115 km | tak, 86% | 7 poziomów | FLUXNET 2014–2026 | las na piasku |
| FR-Lqu Laqueuille | łąka górska | ok. 260 km | tak, 100% | 5 poziomów, 6 czujników | L2 2022–2026 | klimat górski |

Licencja danych ICOS: CC BY 4.0 (do potwierdzenia w umowie licencyjnej przy pierwszym pobraniu w potoku).

## 2. Rola obszaru pomocniczego (do zatwierdzenia)

- **Ta sama metoda, inne miejsce.** Na FR-Lus liczymy dokładnie to samo co w Condom: anomalię ERA5-Land 0–100 cm
  piksela stacji, SWI piksela stacji i — po W3b — anomalię Sentinel-2 działki stacji. Nic nie dostrajamy pod FR-Lus.
- **Sprawdzenie bieżące:** co tydzień kategoria (sucho / norma / wilgotno) z ERA5 i SWI wobec kategorii z czujników.
  To jest jedyne miejsce, gdzie bieżąca karta ma niezależną kontrolę w terenie.
- **Sprawdzenie historyczne:** ten sam protokół co w Condom (R z CI z bootstrapu blokowego, POD/FAR suchych dekad)
  na FR-Lus (2023–2026) i FR-Aur (2019–2025).
- **Kontrola czujników:** kilka czujników na głębokość pozwala wykryć artefakt jednego z nich (rozbieżność z pozostałymi)
  — to bezpośrednie zastosowanie reguł A4 (D-060–D-063).

## 3. Ograniczenia (zapisane przed liczeniem)

- **Krótka historia czujników.** FR-Lus ma pełne lata od 2023, więc własna norma czujników jest za krótka na percentyle.
  Główną miarą będą anomalie krótkookresowe (odchylenie od średniej 35-dniowej, jak `anomaly_35d`) i zgodność
  kierunku zmian; percentyle czujników opisujemy jako orientacyjne.
- **Łąka to nie winnica.** FR-Lus sprawdza warstwę wody (ERA5, SWI) i metodę anomalii, nie reakcję winorośli.
  Rozplątanie sygnału winnicy (Plan v8, moduły 2–3) zostaje na Condom.
- **Głębokości poziomów** odczytane 2026-10-15 z plików VARINFO w archiwach ICOS: FR-Lus 0,05 / 0,10 / 0,20 / 0,30 /
  0,60 / 1,00 m; FR-Aur 0,05 / 0,10 / 0,30 / 0,50 / 1,00 m (4 profile; w metadanych FR-Aur zmiana modelu 2020-10-19).
- **Odległość:** FR-Lus leży poza obszarem Condom, więc nie zastępuje lokalnej walidacji. FR-Aur jest w Gers,
  ale bez danych bieżących.

## 4. Dostęp do danych

- Metadane: punkt SPARQL `https://meta.icos-cp.eu/sparql` (specyfikacje „ETC NRT Meteo”, „ETC L2 Meteo”).
- Pliki: `https://data.icos-cp.eu/objects/<id>` po akceptacji licencji. Plik NRT: CSV co pół godziny,
  kolumny `SWC_n`, `SWC_n_SD`, `SWC_n_N` (średnia, odchylenie i liczba czujników na poziomie n).
- Bez kluczy (dane otwarte). Kod pobierania powstaje po akceptacji D-082.

## 5. Decyzja do zatwierdzenia

- **D-082:** obszar pomocniczy FR-Lus (dane bieżące) i referencja historyczna FR-Aur (Gers); ta sama metoda co w Condom,
  bez dostrajania; anomalie krótkookresowe jako główna miara na FR-Lus z powodu krótkiej historii czujników.

## 6. Źródła

- ICOS Carbon Portal: stacje FR-Lus, FR-Aur, FR-Gri, FR-Lam (https://meta.icos-cp.eu/resources/stations/ES_FR-Lus i analogicznie),
  zapytania SPARQL i pliki ETC NRT Meteo / ETC L2 Meteo pobrane 2026-10-15 [P]
- ICOS Ecosystem Thematic Centre: instrukcje pomiarowe dla wilgotności gleby — do przeczytania przed wdrożeniem [—]
