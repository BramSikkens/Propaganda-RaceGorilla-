# Propaganda RaceGorilla

Tool voor Propaganda Mechelen om wedstrijdresultaten (kajak-sprint) te verwerken tot een ranking en
die te koppelen aan [RaceGorilla](https://www.racegorilla.com/), het timing- en wedstrijdplatform dat
op de wedstrijddag gebruikt wordt.

## Wat kan het

- **Ranking genereren** uit CSV-resultaten van Q1 + Q2 (handmatig geëxporteerd, of automatisch
  opgehaald via de RaceGorilla-API), met correcte puntentelling en DNF/DNS/DSQ-afhandeling.
- **RaceGorilla-data ophalen**: wedstrijden en deelnemers, lokaal gecached zodat je niet telkens
  opnieuw moet laden.
- **Deelnemers automatisch plaatsen** in de juiste finale-race in RaceGorilla, met correcte lane-
  toewijzing op basis van de kwalificatie-ranking.
- **Jeugdspelen-ranking**: combineert Parcours, Lopen en de K1 125m-finales tot één ranking per
  categorie (Pup Mixed / Min H / Min D).

Een GUI (`resultaat_gui.py`) en een lichtgewicht CLI-variant (`resultaat_generator.py`) voor puur
CSV-gebaseerde rankings, zonder RaceGorilla-koppeling.

## Vereisten

- Python 3.9+
- `pip install -r requirements.txt`
- Een RaceGorilla API-token (zie hieronder)

## RaceGorilla-token instellen

De RaceGorilla-integratie heeft een token nodig, meegegeven als omgevingsvariabele `RACEGORILLA_TOKEN`.

```bash
mkdir -p ~/.config
echo 'RACEGORILLA_TOKEN=<jouw-token>' > ~/.config/racegorilla.env
chmod 600 ~/.config/racegorilla.env
echo '[ -f ~/.config/racegorilla.env ] && source ~/.config/racegorilla.env' >> ~/.zshenv
```

**Belangrijk over dit token:** RaceGorilla biedt (voor zover bekend) geen apart, beperkt API-token
aan — het token dat je in je browser terugvindt na het inloggen is functioneel gelijk aan je account-
wachtwoord. Behandel het dus ook zo: nooit in chat, code of commits, enkel als omgevingsvariabele.

## Gebruik

**GUI** (aanbevolen):
```bash
python3 resultaat_gui.py
```

**CLI**, puur CSV-gebaseerd, zonder RaceGorilla:
```bash
python3 resultaat_generator.py <CATEGORIE>   # bv. python3 resultaat_generator.py SENH
```
Verwacht een map `<CATEGORIE>/` met de CSV-resultaten van Q1 en Q2, en schrijft
`<CATEGORIE>_Ranking.xlsx`.

## Dubbelklikbare app bouwen (macOS)

```bash
pip install pyinstaller
python3 -m PyInstaller --windowed --name "ResultaatGenerator" ResultaatGenerator.spec
```
Resultaat: `ResultaatGenerator.app`. Deze bundel wijst intern naar een vaste projectmap (zie
`RESULTATEN_PAD` in `resultaat_gui.py`) — pas dat pad aan als je de app op een andere machine/locatie
gebruikt.

## Niet in deze repo

CSV-resultaten, gegenereerde Excel-exports en de RaceGorilla-cache (`.racegorilla_cache.json`) bevatten
persoonsgegevens van deelnemers en wisselen per wedstrijd — die staan bewust niet onder versiebeheer
(zie `.gitignore`).
