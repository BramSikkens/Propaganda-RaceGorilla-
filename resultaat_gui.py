#!/usr/bin/env python3
"""Simpele GUI: CSV-resultaten (Q1 + Q2) inladen, ranking genereren, bekijken en exporteren.
Daarnaast: wedstrijden en deelnemers opvragen via de RaceGorilla API."""
import csv
import glob
import json
import os
import re
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import pandas as pd
import requests

from resultaat_generator import build_ranking, ontwapen_cel, ontwapen_voor_export

RANKING_KOLOMMEN = ['Rank', 'Name', 'ParticipantId', 'Event', 'TotalPoints', 'TotalTime', 'Final', 'Lane']
RANKING_WEERGAVE = ['Rank', 'Name', 'Event', 'TotalPoints', 'TotalTime', 'Final', 'Lane']  # zonder ParticipantId (enkel intern nodig)
CSV_KOLOMMEN = ['Rank', 'Bib', 'Name', 'Event', 'Country', 'Time', 'Score', 'Total', 'Diff']
JEUGDSPELEN_KOLOMMEN = ['Rank', 'Name', 'Parcours', 'Lopen', 'K1 125m', 'TotaalScore']

RACEGORILLA_BASE = "https://api.racegorilla.com/competition/4446"
RACE_VELDEN = [('RaceId', 'RaceId'), ('RaceName', 'Name'), ('Serie', 'Serie'), ('Event', 'Category'), ('SerieId', 'SerieId')]  # (kolomtitel, JSON-veld)
RACE_WEERGAVE = ['RaceName', 'Serie', 'Event']  # zonder RaceId/SerieId (enkel intern nodig)

# Jeugdspelen-categorie: het Category-veld van de RaceGorilla-races verschilt per discipline.
JEUGDSPELEN_CATEGORIEEN = {
    'Pup Mixed': {'k1': 'pup Mixed', 'jeugdspelen': 'jeugdspelen pupMixed'},
    'Min H': {'k1': 'Min H', 'jeugdspelen': 'jeugdspelen min H'},
    'Min D': {'k1': 'Min D', 'jeugdspelen': 'jeugdspelen min D'},
}
JEUGDSPELEN_GEWICHTEN = {'Parcours': 1.03, 'Lopen': 1.02, 'K1 125m': 1.00}
DEELNEMER_VELDEN = [('ParticipantId', 'ParticipantId'), ('Name', 'Name')]
DEELNEMER_WEERGAVE = ['Name']  # zonder ParticipantId (enkel intern nodig)

# ponytail: in een gebundelde .app wijst __file__ ergens in het app-pakket, niet in de echte
# Resultaten-map -- vaste locatie voor de gebundelde app, __file__-locatie tijdens ontwikkeling.
if getattr(sys, 'frozen', False):
    RESULTATEN_PAD = "/Users/bramsikkens/Desktop/Propaganda26/Resultaten"
else:
    RESULTATEN_PAD = os.path.dirname(os.path.abspath(__file__))


def projecteer(rij, alle_titels, gewenste_titels):
    """Selecteert een subset kolommen uit een positionele rij, op basis van kolomtitels
    (zodat we technische ID-kolommen uit de weergave kunnen halen zonder de data zelf te wijzigen)."""
    return [rij[alle_titels.index(titel)] for titel in gewenste_titels]


def vriendelijke_foutmelding(e):
    """Vertaalt een technische fout naar een begrijpelijke boodschap, zonder Python/HTTP-jargon."""
    if isinstance(e, requests.exceptions.ConnectionError):
        return "Geen verbinding met RaceGorilla. Controleer je internetverbinding en probeer opnieuw."
    if isinstance(e, requests.exceptions.Timeout):
        return "RaceGorilla reageert niet op tijd. Probeer het straks nog eens."
    if isinstance(e, requests.exceptions.HTTPError):
        status = e.response.status_code if e.response is not None else None
        if status == 401:
            return "Het RaceGorilla-token is ongeldig of verlopen. Vraag een nieuw token aan de beheerder."
        if status == 404:
            return "RaceGorilla kon deze gegevens niet vinden."
        return f"RaceGorilla gaf een foutmelding terug (code {status})."
    if isinstance(e, RuntimeError) and "RACEGORILLA_TOKEN" in str(e):
        return "Geen RaceGorilla-token gevonden. Neem contact op met de beheerder."
    return f"Er ging iets mis: {e}"

CACHE_PAD = os.path.join(RESULTATEN_PAD, '.racegorilla_cache.json')


def laad_cache():
    if os.path.exists(CACHE_PAD):
        try:
            with open(CACHE_PAD) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def bewaar_in_cache(**kwargs):
    cache = laad_cache()
    cache.update(kwargs)
    with open(CACHE_PAD, 'w') as f:
        json.dump(cache, f)


def _racegorilla_token():
    """Leest het token uit env (RACEGORILLA_TOKEN), met ~/.config/racegorilla.env als fallback."""
    token = os.environ.get("RACEGORILLA_TOKEN")
    if token:
        return token
    env_pad = os.path.expanduser("~/.config/racegorilla.env")
    if os.path.exists(env_pad):
        for regel in open(env_pad):
            if regel.startswith("RACEGORILLA_TOKEN="):
                return regel.strip().split("=", 1)[1]
    return None


def _racegorilla_headers():
    token = _racegorilla_token()
    if not token:
        raise RuntimeError("Geen RACEGORILLA_TOKEN gevonden. Zet 'm in ~/.config/racegorilla.env en herstart je terminal.")
    return {"Authentication": f"Token {token}"}


def _items_uit_json(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, list):
                return value
    raise ValueError("Onverwacht antwoordformaat van de RaceGorilla API")


def _racegorilla_items(url):
    response = requests.get(url, headers=_racegorilla_headers(), timeout=15)
    response.raise_for_status()
    return _items_uit_json(response.json())


def _racegorilla_alle_paginas(url_voor_pagina, size=200):
    """Blijft pagina's ophalen tot er een kleiner dan `size` terugkomt (= laatste pagina)."""
    alle_items = []
    pagina = 1
    while True:
        items = _racegorilla_items(url_voor_pagina(pagina))
        alle_items.extend(items)
        if len(items) < size:
            return alle_items
        pagina += 1


def haal_wedstrijden():
    items = _racegorilla_alle_paginas(lambda p: f"{RACEGORILLA_BASE}/race?Size=200&Page={p}&sort=Index")
    return [[item.get(veld) for _, veld in RACE_VELDEN] for item in items]


def haal_deelnemers():
    items = _racegorilla_alle_paginas(lambda p: f"{RACEGORILLA_BASE}/participant?size=200&page={p}")
    return [[item.get(veld) for _, veld in DEELNEMER_VELDEN] for item in items]


def haal_serie_resultaten(serie_id):
    return _racegorilla_items(f"{RACEGORILLA_BASE}/serie/{serie_id}/raceresult")


def _tijd_naar_string(milliseconden):
    """Zet milliseconden om naar het bestaande CSV-formaat 'MM:SS.cc'."""
    seconden = milliseconden / 1000
    minuten = int(seconden // 60)
    rest = seconden - minuten * 60
    return f"{minuten:02d}:{rest:05.2f}"


def genereer_csv_rijen_voor_event(event, wedstrijden_lijst):
    """Haalt Qualification-resultaten op voor dit event via de RaceGorilla API en bouwt per
    race (Reeks) CSV-rijen op in hetzelfde formaat als de bestaande handmatige export
    (Rank,Bib,Name,Event,Country,Time,Score,Total,Diff). Geeft {bestandsnaam: [rijen]} terug.
    """
    kwalificatie_races = [w for w in wedstrijden_lijst if w[3] == event and w[2].startswith('Qualification')]
    serie_ids = sorted({w[4] for w in kwalificatie_races})
    naam_per_race_id = {w[0]: w[1] for w in kwalificatie_races}

    resultaten_per_race = {}
    for serie_id in serie_ids:
        for item in haal_serie_resultaten(serie_id):
            if item['Participant']['Category'] != event:
                continue
            afwezig = item.get('Dnf') or item.get('Dns') or item.get('Dsq')
            if item.get('Status') != 'completed' and not afwezig:
                continue  # nog geen resultaat beschikbaar in RaceGorilla
            resultaten_per_race.setdefault(item['RaceId'], []).append(item)

    csv_per_bestand = {}
    for race_id, items in resultaten_per_race.items():
        race_naam = naam_per_race_id.get(race_id, str(race_id))

        geldig = sorted((i for i in items if not (i.get('Dnf') or i.get('Dns') or i.get('Dsq'))), key=lambda i: i['Time'])
        ongeldig = [i for i in items if i.get('Dnf') or i.get('Dns') or i.get('Dsq')]
        leider_tijd = geldig[0]['Time'] if geldig else None

        rijen = []
        for rank, item in enumerate(geldig + ongeldig, start=1):
            if item.get('Dnf'):
                tijd_str, diff_str = 'DNF', ''
            elif item.get('Dns'):
                tijd_str, diff_str = 'DNS', ''
            elif item.get('Dsq'):
                tijd_str, diff_str = 'DSQ', ''
            else:
                tijd_str = _tijd_naar_string(item['Time'])
                diff_str = '' if item['Time'] == leider_tijd else _tijd_naar_string(item['Time'] - leider_tijd)

            rijen.append({
                'Rank': rank, 'Bib': '', 'Name': ontwapen_cel(item['Participant']['Name']), 'Event': event,
                'Country': '', 'Time': tijd_str, 'Score': 0, 'Total': tijd_str, 'Diff': diff_str,
            })

        csv_per_bestand[f"{race_naam}.csv"] = rijen

    return csv_per_bestand


def _veilige_bestandsnaam(naam):
    """Zet een (van RaceGorilla afkomstige) naam om naar een veilige bestandsnaam --
    geen pad-separators of '..', om pad-traversal bij het schrijven te voorkomen."""
    naam = os.path.basename(naam)
    naam = re.sub(r'[^A-Za-z0-9._ -]', '_', naam)
    naam = naam.strip(' .')
    return naam or 'onbekend'


def schrijf_csvs(folder_pad, csv_per_bestand):
    """Verwijdert bestaande CSV's in de map en schrijft de nieuwe weg. Geeft de geschreven paden terug.
    Weigert een folder_pad die (via een gemanipuleerde categorienaam) buiten RESULTATEN_PAD valt."""
    folder_pad_echt = os.path.realpath(folder_pad)
    basis_echt = os.path.realpath(RESULTATEN_PAD)
    if os.path.commonpath([folder_pad_echt, basis_echt]) != basis_echt:
        raise ValueError(f"Ongeldige map: '{folder_pad}' valt buiten {RESULTATEN_PAD}.")

    os.makedirs(folder_pad, exist_ok=True)
    for oud_bestand in glob.glob(os.path.join(folder_pad, '*.csv')):
        os.remove(oud_bestand)

    geschreven_paden = []
    for bestandsnaam, rijen in csv_per_bestand.items():
        pad = os.path.join(folder_pad, _veilige_bestandsnaam(bestandsnaam))
        with open(pad, 'w', newline='', encoding='utf-8') as f:
            schrijver = csv.DictWriter(f, fieldnames=CSV_KOLOMMEN)
            schrijver.writeheader()
            schrijver.writerows(rijen)
        geschreven_paden.append(pad)
    return geschreven_paden


def haal_race_resultaten(race_id):
    return _racegorilla_items(f"{RACEGORILLA_BASE}/race/{race_id}/raceresult")


def plaats_deelnemers(race_id, deelnemers_op_lanevolgorde):
    """Plaatst deelnemers in een race, en wijst daarna per deelnemer de lane toe.

    deelnemers_op_lanevolgorde: lijst van (participant_id, lane), lane 1 eerst.
    De POST-respons geeft geen bruikbare RaceResultId's terug, dus na het plaatsen
    wordt de race opnieuw opgevraagd om de RaceResultId per deelnemer op te zoeken,
    en die worden daarna één voor één gepatcht.
    """
    headers = _racegorilla_headers()
    payload = {"RaceResult": [{"RaceId": race_id, "Participant": {"ParticipantId": pid}} for pid, _ in deelnemers_op_lanevolgorde]}
    response = requests.post(f"{RACEGORILLA_BASE}/raceresult", json=payload, headers=headers, timeout=15)
    response.raise_for_status()

    race_result_id_per_participant = {
        item["Participant"]["ParticipantId"]: item["RaceResultId"]
        for item in haal_race_resultaten(race_id)
    }

    for pid, lane in deelnemers_op_lanevolgorde:
        race_result_id = race_result_id_per_participant.get(pid)
        if race_result_id is None:
            continue  # onverwacht: net geplaatste deelnemer niet teruggevonden in de race
        lane_response = requests.patch(
            f"{RACEGORILLA_BASE}/raceresult/{race_result_id}",
            json={"LaneNumber": lane, "RaceResultId": race_result_id},
            headers=headers,
            timeout=15,
        )
        lane_response.raise_for_status()


def finale_nummer_uit_naam(naam):
    match = re.search(r'(\d+)\s*$', naam)
    return int(match.group(1)) if match else None


def _voltooide_resultaten(items):
    """Enkel resultaten die echt gereden zijn (of expliciet Dnf/Dns/Dsq) -- geen 'pending' plaatsen."""
    return [i for i in items if i.get('Status') == 'completed' or i.get('Dnf') or i.get('Dns') or i.get('Dsq')]


def _sorteer_op_tijd(items):
    """Sorteert oplopend op Time; Dnf/Dns/Dsq komen achteraan."""
    geldig = sorted((i for i in items if not (i.get('Dnf') or i.get('Dns') or i.get('Dsq'))), key=lambda i: i['Time'])
    ongeldig = [i for i in items if i.get('Dnf') or i.get('Dns') or i.get('Dsq')]
    return geldig + ongeldig


def _naar_plaatsen(gerangschikte_items):
    """Zet een al-gerangschikte lijst raceresultaten om naar rijen met Plaats (1..N) en Punten (N - plaats)."""
    n = len(gerangschikte_items)
    return [
        {
            'ParticipantId': item['Participant']['ParticipantId'],
            'Name': item['Participant']['Name'],
            'Plaats': plaats,
            'Punten': n - plaats,
        }
        for plaats, item in enumerate(gerangschikte_items, start=1)
    ]


def bereken_punten_enkele_race(race_id):
    """Rangschikt de (voltooide) resultaten van 1 race op tijd. Punten = aantal deelnemers - plaats."""
    return _naar_plaatsen(_sorteer_op_tijd(_voltooide_resultaten(haal_race_resultaten(race_id))))


def bereken_punten_k1_finales(wedstrijden_lijst, k1_event):
    """Plakt de Finale-races na elkaar (Finale 1 = beste plaatsen, dan Finale 2, enz.) -- niet de
    kwalificatie-ranking. Binnen elke finale wordt op tijd gesorteerd; de finale-volgorde zelf
    weegt zwaarder dan de tijd (iedereen in Finale 1 staat boven iedereen in Finale 2)."""
    finales = sorted(
        (w for w in wedstrijden_lijst if w[3] == k1_event and w[2] == 'Finale'),
        key=lambda w: finale_nummer_uit_naam(w[1]) or 0,
    )
    volgorde = []
    for race_id, naam, serie, ev, serie_id in finales:
        volgorde.extend(_sorteer_op_tijd(_voltooide_resultaten(haal_race_resultaten(race_id))))
    return _naar_plaatsen(volgorde)


def genereer_jeugdspelen_ranking(categorie, wedstrijden_lijst):
    """Combineert Parcours + Lopen + K1 125m Finales tot één jeugdspelen-ranking.

    Geeft (DataFrame, lijst ontbrekende disciplines) terug -- een discipline is 'ontbrekend'
    als er nog geen voltooide resultaten voor zijn (bv. nog niet gereden).
    """
    labels = JEUGDSPELEN_CATEGORIEEN[categorie]

    def vind_race(naam_bevat, event):
        for w in wedstrijden_lijst:
            naam = w[1].lower()
            if w[3] == event and naam_bevat in naam and 'test' not in naam:  # RaceGorilla bevat ook testraces
                return w
        return None

    parcours_race = vind_race('parcours', labels['jeugdspelen'])
    lopen_race = vind_race('lopen', labels['jeugdspelen'])
    if parcours_race is None or lopen_race is None:
        raise ValueError(f"Parcours- of Lopen-race niet gevonden voor '{categorie}'. Klik 'Laad Wedstrijden' opnieuw als de lijst verouderd is.")

    resultaten_per_discipline = {
        'Parcours': bereken_punten_enkele_race(parcours_race[0]),
        'Lopen': bereken_punten_enkele_race(lopen_race[0]),
        'K1 125m': bereken_punten_k1_finales(wedstrijden_lijst, labels['k1']),
    }
    ontbrekend = [discipline for discipline, rijen in resultaten_per_discipline.items() if not rijen]

    naam_per_pid = {}
    punten_per_pid = {}
    for discipline, rijen in resultaten_per_discipline.items():
        for rij in rijen:
            pid = rij['ParticipantId']
            naam_per_pid[pid] = rij['Name']
            punten_per_pid.setdefault(pid, {})[discipline] = rij['Punten']

    uitkomst = []
    for pid, punten in punten_per_pid.items():
        parcours = punten.get('Parcours', 0)
        lopen = punten.get('Lopen', 0)
        k1 = punten.get('K1 125m', 0)
        totaal = (
            parcours * JEUGDSPELEN_GEWICHTEN['Parcours']
            + lopen * JEUGDSPELEN_GEWICHTEN['Lopen']
            + k1 * JEUGDSPELEN_GEWICHTEN['K1 125m']
        )
        uitkomst.append({'Name': naam_per_pid[pid], 'Parcours': parcours, 'Lopen': lopen, 'K1 125m': k1, 'TotaalScore': totaal})

    df = pd.DataFrame(uitkomst, columns=['Name', 'Parcours', 'Lopen', 'K1 125m', 'TotaalScore'])
    df.sort_values(by='TotaalScore', ascending=False, inplace=True)
    df.reset_index(drop=True, inplace=True)
    df['Rank'] = df.index + 1
    return df, ontbrekend


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Resultaat Ranking Generator")
        self.geometry("780x550")

        cache = laad_cache()

        self.bestanden = []
        self.ranking = None
        self.deelnemers_per_naam = {naam: pid for pid, naam in cache.get('deelnemers', [])}
        self.wedstrijden_lijst = cache.get('wedstrijden', [])
        self.geselecteerde_rijen = set()
        self.geplaatste_namen = set()

        # --- stap 1: CSV-resultaten inladen en verwerken ---
        stap1 = ttk.LabelFrame(self, text="1. Resultaten")
        stap1.pack(fill="x", padx=10, pady=(10, 5))

        self.laad_bestanden_btn = tk.Button(stap1, text="Resultaten laden (Q1 + Q2)...", command=self.laad_bestanden)
        self.laad_bestanden_btn.pack(side="left", padx=5, pady=5)
        self.automatisch_inladen_btn = tk.Button(stap1, text="Automatisch inladen...", command=self.automatisch_inladen)
        self.automatisch_inladen_btn.pack(side="left", padx=5)
        self.bestanden_indicator = tk.Label(stap1, text="❌", fg="red")
        self.bestanden_indicator.pack(side="left", padx=(0, 10))
        self.genereer_btn = tk.Button(stap1, text="Genereer ranking", command=self.genereer, state="disabled")
        self.genereer_btn.pack(side="left", padx=5)
        self.export_btn = tk.Button(stap1, text="Exporteren naar Excel...", command=self.exporteer, state="disabled")
        self.export_btn.pack(side="left", padx=5)

        # --- stap 2: RaceGorilla-data ophalen ---
        stap2 = ttk.LabelFrame(self, text="2. RaceGorilla-data")
        stap2.pack(fill="x", padx=10, pady=5)

        self.laad_wedstrijden_btn = tk.Button(stap2, text="Laad Wedstrijden", command=self.toon_wedstrijden)
        self.laad_wedstrijden_btn.pack(side="left", padx=5, pady=5)
        self.wedstrijden_indicator = tk.Label(stap2, text="")
        self.wedstrijden_indicator.pack(side="left", padx=(0, 10))
        self.laad_deelnemers_btn = tk.Button(stap2, text="Laad Deelnemers", command=self.toon_deelnemers)
        self.laad_deelnemers_btn.pack(side="left", padx=5)
        self.deelnemers_indicator = tk.Label(stap2, text="")
        self.deelnemers_indicator.pack(side="left", padx=(0, 10))

        # --- stap 3: deelnemers plaatsen ---
        stap3 = ttk.LabelFrame(self, text="3. Plaatsen")
        stap3.pack(fill="x", padx=10, pady=5)

        self.plaats_btn = tk.Button(stap3, text="Plaats in race...", command=self.plaats_in_race, state="disabled")
        self.plaats_btn.pack(side="left", padx=5, pady=5)
        self.vervolledig_btn = tk.Button(stap3, text="Vervolledig race", command=self.vervolledig_race, state="disabled")
        self.vervolledig_btn.pack(side="left", padx=5)

        # --- stap 4: Jeugdspelen-ranking (Parcours + Lopen + K1 125m Finales) ---
        stap4 = ttk.LabelFrame(self, text="4. Jeugdspelen")
        stap4.pack(fill="x", padx=10, pady=5)

        self.jeugdspelen_btn = tk.Button(stap4, text="Jeugdspelen-ranking...", command=self.jeugdspelen_ranking_dialoog)
        self.jeugdspelen_btn.pack(side="left", padx=5, pady=5)
        self.jeugdspelen_export_btn = tk.Button(stap4, text="Exporteren naar Excel...", command=self.exporteer_jeugdspelen, state="disabled")
        self.jeugdspelen_export_btn.pack(side="left", padx=5)

        self.status = tk.Label(self, text="Geen bestanden geladen.", anchor="w")
        self.status.pack(fill="x", padx=10, pady=(5, 0))

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        ranking_tab = tk.Frame(notebook)
        wedstrijden_tab = tk.Frame(notebook)
        deelnemers_tab = tk.Frame(notebook)
        jeugdspelen_tab = tk.Frame(notebook)
        notebook.add(ranking_tab, text="Ranking")
        notebook.add(wedstrijden_tab, text="Wedstrijden")
        notebook.add(deelnemers_tab, text="Deelnemers")
        notebook.add(jeugdspelen_tab, text="Jeugdspelen")

        self.tree_ranking = self._maak_tabel(ranking_tab, RANKING_WEERGAVE, checkbox=True)
        self.tree_ranking.bind("<Button-1>", self._op_klik)
        self.tree_wedstrijden = self._maak_tabel(wedstrijden_tab, RACE_WEERGAVE)
        self.tree_deelnemers = self._maak_tabel(deelnemers_tab, DEELNEMER_WEERGAVE)
        self.tree_jeugdspelen = self._maak_tabel(jeugdspelen_tab, JEUGDSPELEN_KOLOMMEN)

        self.jeugdspelen_ranking = None

        self._alle_knoppen = [
            self.laad_bestanden_btn, self.automatisch_inladen_btn, self.genereer_btn, self.export_btn,
            self.laad_wedstrijden_btn, self.laad_deelnemers_btn,
            self.plaats_btn, self.vervolledig_btn,
            self.jeugdspelen_btn, self.jeugdspelen_export_btn,
        ]

        self._zet_indicator(self.wedstrijden_indicator, bool(self.wedstrijden_lijst))
        self._zet_indicator(self.deelnemers_indicator, bool(self.deelnemers_per_naam))
        self._vul_wedstrijden_tabel(self.wedstrijden_lijst)
        self._vul_deelnemers_tabel([[pid, naam] for naam, pid in self.deelnemers_per_naam.items()])

    @staticmethod
    def _maak_tabel(parent, kolommen, checkbox=False):
        tree = ttk.Treeview(parent, columns=kolommen, show="tree headings" if checkbox else "headings")
        if checkbox:
            tree.heading("#0", text="")
            tree.column("#0", width=30, stretch=False)
        for kolom in kolommen:
            tree.heading(kolom, text=kolom)
            tree.column(kolom, width=110)
        tree.pack(fill="both", expand=True, padx=5, pady=5)
        return tree

    @staticmethod
    def _zet_indicator(label, geladen):
        if geladen:
            label.config(text="✔", fg="green")
        else:
            label.config(text="❌", fg="red")

    @staticmethod
    def _toon_fout(titel, e):
        messagebox.showerror(titel, vriendelijke_foutmelding(e))

    def _zet_bezig(self, bezig, tekst=None):
        """Blokkeert de knoppen tijdens een netwerkoperatie en toont voortgangstekst."""
        for knop in self._alle_knoppen:
            knop.config(state="disabled")
        if not bezig:
            self.genereer_btn.config(state="normal" if self.bestanden else "disabled")
            self.export_btn.config(state="normal" if self.ranking is not None else "disabled")
            self.plaats_btn.config(state="normal" if self.ranking is not None else "disabled")
            self.vervolledig_btn.config(state="normal" if self.ranking is not None else "disabled")
            self.laad_bestanden_btn.config(state="normal")
            self.automatisch_inladen_btn.config(state="normal")
            self.laad_wedstrijden_btn.config(state="normal")
            self.laad_deelnemers_btn.config(state="normal")
            self.jeugdspelen_btn.config(state="normal")
            self.jeugdspelen_export_btn.config(state="normal" if self.jeugdspelen_ranking is not None else "disabled")
        if tekst is not None:
            self.status.config(text=tekst)
        self.update_idletasks()

    def _vul_eenvoudige_tabel(self, tree, rijen):
        tree.delete(*tree.get_children())
        for rij in rijen:
            tree.insert("", "end", values=rij)

    def _vul_wedstrijden_tabel(self, rijen):
        """Toont enkel de leesbare kolommen (RaceId/SerieId zijn intern nodig, niet nuttig op scherm)."""
        alle_titels = [titel for titel, _ in RACE_VELDEN]
        self._vul_eenvoudige_tabel(self.tree_wedstrijden, [projecteer(rij, alle_titels, RACE_WEERGAVE) for rij in rijen])

    def _vul_deelnemers_tabel(self, rijen):
        """Toont enkel de leesbare kolommen (ParticipantId is intern nodig, niet nuttig op scherm)."""
        alle_titels = [titel for titel, _ in DEELNEMER_VELDEN]
        self._vul_eenvoudige_tabel(self.tree_deelnemers, [projecteer(rij, alle_titels, DEELNEMER_WEERGAVE) for rij in rijen])

    def _vul_ranking_tabel(self):
        self.geselecteerde_rijen = set()
        self.tree_ranking.delete(*self.tree_ranking.get_children())
        for idx, rij in self.ranking.iterrows():
            waarden = [rij[k] for k in RANKING_WEERGAVE]
            if rij['Name'] in self.geplaatste_namen:
                waarden[RANKING_WEERGAVE.index('Name')] = f"{rij['Name']} ✅"
            self.tree_ranking.insert("", "end", iid=str(idx), text="☐", values=waarden)

    def _op_klik(self, event):
        if self.tree_ranking.identify_column(event.x) != "#0":
            return
        iid = self.tree_ranking.identify_row(event.y)
        if not iid:
            return
        if iid in self.geselecteerde_rijen:
            self.geselecteerde_rijen.discard(iid)
            self.tree_ranking.item(iid, text="☐")
        else:
            self.geselecteerde_rijen.add(iid)
            self.tree_ranking.item(iid, text="☑")

    def laad_bestanden(self):
        paden = filedialog.askopenfilenames(title="Selecteer Q1- en Q2-CSV's", filetypes=[("CSV-bestanden", "*.csv")])
        if not paden:
            return
        self.bestanden = list(paden)
        self.ranking = None
        self.geplaatste_namen = set()
        self._zet_indicator(self.bestanden_indicator, True)
        self._zet_bezig(False, f"{len(self.bestanden)} bestanden geladen.")

    def automatisch_inladen(self):
        self._zet_bezig(True, "Wedstrijden ophalen...")
        try:
            wedstrijden = self._zorg_voor_wedstrijden()
        except Exception as e:
            self._zet_bezig(False)
            self._toon_fout("Fout bij ophalen wedstrijden", e)
            return
        self._zet_bezig(False)

        events = sorted({w[3] for w in wedstrijden if w[2].startswith('Qualification')})
        if not events:
            messagebox.showwarning("Geen events gevonden", "Geen Qualification-races gevonden. Klik 'Laad Wedstrijden' opnieuw als de lijst verouderd is.")
            return

        dialoog = tk.Toplevel(self)
        dialoog.title("Automatisch inladen")
        tk.Label(dialoog, text="Kies het event:").pack(padx=10, pady=(10, 0))
        combo = ttk.Combobox(dialoog, values=events, state="readonly", width=30)
        combo.pack(padx=10, pady=10)

        def bevestig():
            keuze_index = combo.current()
            if keuze_index < 0:
                return
            event = events[keuze_index]
            dialoog.destroy()
            self._automatisch_inladen_voor_event(event)

        tk.Button(dialoog, text="Inladen", command=bevestig).pack(pady=(0, 10))

    def _automatisch_inladen_voor_event(self, event):
        folder_naam = re.sub(r'[^A-Z0-9_-]', '', event.replace(' ', '').upper())
        if not folder_naam:
            messagebox.showerror("Ongeldig event", f"Kan geen geldige mapnaam afleiden van '{event}'.")
            return
        folder_pad = os.path.join(RESULTATEN_PAD, folder_naam)

        if not messagebox.askyesno(
            "Bevestigen",
            f"Dit vervangt alle CSV-bestanden in de map '{folder_naam}' door vers opgehaalde resultaten van de API. Doorgaan?",
        ):
            return

        self._zet_bezig(True, f"Resultaten voor '{event}' ophalen...")
        try:
            csv_per_bestand = genereer_csv_rijen_voor_event(event, self.wedstrijden_lijst)
        except Exception as e:
            self._zet_bezig(False)
            self._toon_fout("Fout bij ophalen resultaten", e)
            return

        if not csv_per_bestand:
            self._zet_bezig(False)
            messagebox.showwarning("Geen resultaten", f"Geen voltooide Qualification-resultaten gevonden voor '{event}'.")
            return

        geschreven = schrijf_csvs(folder_pad, csv_per_bestand)

        self.bestanden = geschreven
        self.ranking = None
        self.geplaatste_namen = set()
        self._zet_indicator(self.bestanden_indicator, True)
        self._zet_bezig(False, f"{len(geschreven)} CSV-bestanden automatisch ingeladen voor '{event}' (map '{folder_naam}').")

    def genereer(self):
        try:
            self.ranking = build_ranking(self.bestanden)
        except Exception as e:
            self._toon_fout("Fout bij genereren", e)
            return

        self.ranking['ParticipantId'] = self.ranking['Name'].map(self.deelnemers_per_naam).fillna('')
        self._vul_ranking_tabel()
        self._zet_bezig(False, f"Ranking gegenereerd: {len(self.ranking)} atleten.")

    def exporteer(self):
        pad = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel-bestand", "*.xlsx")], initialfile="Ranking.xlsx")
        if not pad:
            return
        ontwapen_voor_export(self.ranking).to_excel(pad, index=False, engine="openpyxl")
        self.status.config(text=f"Geëxporteerd naar {pad}")

    def toon_wedstrijden(self):
        self._zet_bezig(True, "Wedstrijden ophalen...")
        try:
            rijen = haal_wedstrijden()
        except Exception as e:
            self._zet_bezig(False)
            self._toon_fout("Fout bij ophalen wedstrijden", e)
            return
        self.wedstrijden_lijst = rijen
        bewaar_in_cache(wedstrijden=rijen)
        self._vul_wedstrijden_tabel(rijen)
        self._zet_indicator(self.wedstrijden_indicator, True)
        self._zet_bezig(False, f"{len(rijen)} wedstrijden geladen.")

    def toon_deelnemers(self):
        self._zet_bezig(True, "Deelnemers ophalen...")
        try:
            rijen = haal_deelnemers()
        except Exception as e:
            self._zet_bezig(False)
            self._toon_fout("Fout bij ophalen deelnemers", e)
            return
        self.deelnemers_per_naam = {naam: pid for pid, naam in rijen}
        bewaar_in_cache(deelnemers=rijen)
        self._vul_deelnemers_tabel(rijen)
        self._zet_indicator(self.deelnemers_indicator, True)
        self._zet_bezig(False, f"{len(rijen)} deelnemers geladen.")

    def _zorg_voor_wedstrijden(self):
        """Zorgt dat self.wedstrijden_lijst gevuld is; haalt op via de API indien nog leeg."""
        if not self.wedstrijden_lijst:
            wedstrijden = haal_wedstrijden()
            self.wedstrijden_lijst = wedstrijden
            bewaar_in_cache(wedstrijden=wedstrijden)
            self._vul_wedstrijden_tabel(wedstrijden)
            self._zet_indicator(self.wedstrijden_indicator, True)
        return self.wedstrijden_lijst

    def _finale_races(self, event):
        """Races voor dit event waarvan Serie == 'Finale'."""
        return [w for w in self._zorg_voor_wedstrijden() if w[3] == event and w[2] == 'Finale']

    def plaats_in_race(self):
        if not self.geselecteerde_rijen:
            messagebox.showwarning("Geen selectie", "Vink eerst atleten aan in de ranking-tabel.")
            return

        event = self.ranking['Event'].iloc[0]
        self._zet_bezig(True, "Wedstrijden ophalen...")
        try:
            gefilterd = self._finale_races(event)
        except Exception as e:
            self._zet_bezig(False)
            self._toon_fout("Fout bij ophalen wedstrijden", e)
            return
        self._zet_bezig(False)
        if not gefilterd:
            messagebox.showwarning("Geen finales gevonden", f"Geen race met Event='{event}' en Serie='Finale' gevonden. Klik 'Laad Wedstrijden' opnieuw als de lijst verouderd is.")
            return

        dialoog = tk.Toplevel(self)
        dialoog.title("Plaats in race")
        tk.Label(dialoog, text="Kies de race:").pack(padx=10, pady=(10, 0))
        keuzes = [f"{naam} — #{race_id}" for race_id, naam, serie, ev, serie_id in gefilterd]
        combo = ttk.Combobox(dialoog, values=keuzes, state="readonly", width=50)
        combo.pack(padx=10, pady=10)

        def bevestig():
            keuze_index = combo.current()
            if keuze_index < 0:
                return
            race_id, race_naam = gefilterd[keuze_index][0], gefilterd[keuze_index][1]
            dialoog.destroy()
            self._plaats_geselecteerden(race_id, race_naam)

        tk.Button(dialoog, text="Plaatsen", command=bevestig).pack(pady=(0, 10))

    def _plaats_geselecteerden(self, race_id, race_naam):
        rijen = [self.ranking.loc[int(iid)] for iid in self.geselecteerde_rijen]

        zonder_id = [rij['Name'] for rij in rijen if rij['ParticipantId'] == '']
        if zonder_id:
            messagebox.showerror("Ontbrekend ParticipantId", "Geen ParticipantId bekend voor: " + ", ".join(zonder_id) + "\n\nLaad eerst de deelnemers via 'Laad Deelnemers' en genereer de ranking opnieuw.")
            return

        rijen.sort(key=lambda rij: rij['Lane'])
        deelnemers = [(int(rij['ParticipantId']), int(rij['Lane'])) for rij in rijen]

        namen_per_lane = "\n".join(f"Lane {rij['Lane']}: {rij['Name']}" for rij in rijen)
        if not messagebox.askyesno(
            "Bevestig plaatsing",
            f"Dit plaatst {len(deelnemers)} deelnemers in '{race_naam}' en wijst meteen hun lane toe in RaceGorilla:\n\n{namen_per_lane}\n\nDoorgaan?",
        ):
            return

        self._zet_bezig(True, f"{len(deelnemers)} deelnemers plaatsen in '{race_naam}'...")
        try:
            plaats_deelnemers(race_id, deelnemers)
        except Exception as e:
            self._zet_bezig(False)
            self._toon_fout("Fout bij plaatsen", e)
            return

        self.geplaatste_namen.update(rij['Name'] for rij in rijen)
        self._vul_ranking_tabel()
        self._zet_bezig(False, f"{len(deelnemers)} deelnemers geplaatst in '{race_naam}' (met lane).")

    def vervolledig_race(self):
        """Plaatst alle geladen resultaten in hun Finale-race (gegroepeerd op de kolom Final), lanes inbegrepen."""
        event = self.ranking['Event'].iloc[0]
        self._zet_bezig(True, "Wedstrijden ophalen...")
        try:
            finales = self._finale_races(event)
        except Exception as e:
            self._zet_bezig(False)
            self._toon_fout("Fout bij ophalen wedstrijden", e)
            return

        race_id_per_finale = {}
        for race_id, naam, serie, ev, serie_id in finales:
            nummer = finale_nummer_uit_naam(naam)
            if nummer is not None:
                race_id_per_finale[nummer] = race_id

        if not race_id_per_finale:
            self._zet_bezig(False)
            messagebox.showwarning("Geen finales gevonden", f"Geen races met Event='{event}' en Serie='Finale' gevonden. Klik 'Laad Wedstrijden' opnieuw als de lijst verouderd is.")
            return

        self._zet_bezig(False)
        aantal_finales = self.ranking['Final'].nunique()
        if not messagebox.askyesno(
            "Bevestig vervolledigen",
            f"Dit plaatst alle {len(self.ranking)} geladen atleten in hun {aantal_finales} Finale-race(s) "
            "en wijst meteen hun lanes toe in RaceGorilla. Doorgaan?",
        ):
            return

        verwerkt = []
        overgeslagen = []
        groepen = list(self.ranking.groupby('Final'))

        for i, (finale_nummer, groep) in enumerate(groepen, start=1):
            self._zet_bezig(True, f"Finale {finale_nummer} plaatsen ({i}/{len(groepen)})...")

            race_id = race_id_per_finale.get(int(finale_nummer))
            if race_id is None:
                overgeslagen.append(f"Finale {finale_nummer}: geen bijpassende race gevonden")
                continue

            zonder_id = groep.loc[groep['ParticipantId'] == '', 'Name'].tolist()
            if zonder_id:
                overgeslagen.append(f"Finale {finale_nummer}: ontbrekend ParticipantId voor {', '.join(zonder_id)}")
                continue

            groep = groep.sort_values('Lane')
            deelnemers = [(int(rij['ParticipantId']), int(rij['Lane'])) for _, rij in groep.iterrows()]

            try:
                plaats_deelnemers(race_id, deelnemers)
            except Exception as e:
                overgeslagen.append(f"Finale {finale_nummer}: fout bij plaatsen ({e})")
                continue

            self.geplaatste_namen.update(groep['Name'])
            verwerkt.append(f"Finale {finale_nummer} -> {len(deelnemers)} deelnemers in race #{race_id}")

        self._vul_ranking_tabel()

        bericht = "Verwerkt:\n" + ("\n".join(verwerkt) if verwerkt else "(niets)")
        if overgeslagen:
            bericht += "\n\nOvergeslagen:\n" + "\n".join(overgeslagen)
        messagebox.showinfo("Vervolledig race", bericht)
        self._zet_bezig(False, f"Vervolledig race: {len(verwerkt)} finale(s) geplaatst, {len(overgeslagen)} overgeslagen.")

    def jeugdspelen_ranking_dialoog(self):
        self._zet_bezig(True, "Wedstrijden ophalen...")
        try:
            wedstrijden = self._zorg_voor_wedstrijden()
        except Exception as e:
            self._zet_bezig(False)
            self._toon_fout("Fout bij ophalen wedstrijden", e)
            return
        self._zet_bezig(False)

        dialoog = tk.Toplevel(self)
        dialoog.title("Jeugdspelen-ranking")
        tk.Label(dialoog, text="Kies de categorie:").pack(padx=10, pady=(10, 0))
        categorieen = list(JEUGDSPELEN_CATEGORIEEN)
        combo = ttk.Combobox(dialoog, values=categorieen, state="readonly", width=20)
        combo.pack(padx=10, pady=10)

        def bevestig():
            keuze_index = combo.current()
            if keuze_index < 0:
                return
            categorie = categorieen[keuze_index]
            dialoog.destroy()
            self._genereer_jeugdspelen_ranking(categorie, wedstrijden)

        tk.Button(dialoog, text="Genereer", command=bevestig).pack(pady=(0, 10))

    def _genereer_jeugdspelen_ranking(self, categorie, wedstrijden):
        self._zet_bezig(True, f"Jeugdspelen-ranking voor '{categorie}' berekenen...")
        try:
            df, ontbrekend = genereer_jeugdspelen_ranking(categorie, wedstrijden)
        except Exception as e:
            self._zet_bezig(False)
            self._toon_fout("Fout bij berekenen", e)
            return

        self.jeugdspelen_ranking = df
        self._vul_eenvoudige_tabel(self.tree_jeugdspelen, [[rij[k] for k in JEUGDSPELEN_KOLOMMEN] for _, rij in df.iterrows()])

        if ontbrekend:
            messagebox.showwarning(
                "Nog niet alle disciplines voltooid",
                f"Voor '{categorie}' zijn nog geen (voltooide) resultaten voor: {', '.join(ontbrekend)}.\n"
                "Die discipline telt voorlopig als 0 punten voor iedereen.",
            )
        self._zet_bezig(False, f"Jeugdspelen-ranking '{categorie}' gegenereerd: {len(df)} atleten.")

    def exporteer_jeugdspelen(self):
        pad = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel-bestand", "*.xlsx")], initialfile="Jeugdspelen_Ranking.xlsx")
        if not pad:
            return
        ontwapen_voor_export(self.jeugdspelen_ranking).to_excel(pad, index=False, engine="openpyxl")
        self.status.config(text=f"Geëxporteerd naar {pad}")


if __name__ == "__main__":
    App().mainloop()
