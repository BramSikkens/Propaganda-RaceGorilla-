#!/usr/bin/env python3
"""Genereert een Ranking.xlsx uit de CSV-resultaten van een categorie."""
import argparse
import glob

import pandas as pd

DNF_TIME = 9999.0  # ponytail: sentinel groter dan elke realistische wedstrijdtijd, zodat DNF/DNS/DSQ nooit als snelste telt
GEVAARLIJKE_CEL_PREFIXES = ('=', '+', '-', '@', '\t', '\r')  # kunnen als Excel-formule geïnterpreteerd worden


def ontwapen_cel(waarde):
    """Voorkomt CSV/Excel-formule-injectie: prefixt een tekstcel die begint met =/+/-/@ met een apostrof.
    Namen komen uiteindelijk van een inschrijfformulier -- niet zomaar vertrouwen bij export."""
    if isinstance(waarde, str) and waarde[:1] in GEVAARLIJKE_CEL_PREFIXES:
        return "'" + waarde
    return waarde


def ontwapen_voor_export(df):
    """Kopie van df met tekstkolommen ontwapend (zie ontwapen_cel) -- enkel voor export, niet voor
    intern gebruik (zou naam-matching elders in de app kunnen breken)."""
    df = df.copy()
    for kolom in df.select_dtypes(include='object').columns:
        df[kolom] = df[kolom].map(ontwapen_cel)
    return df


def time_to_seconds(time_str):
    """Zet tijd in het formaat 'mm:ss.milliseconds' om naar seconden."""
    try:
        return sum(float(x) * 60**i for i, x in enumerate(reversed(time_str.split(':'))))
    except (ValueError, AttributeError):
        return None  # DNF/DNS/DSQ of ontbrekende tijd


def calculate_points(rank, time):
    """0 punten bij DNF/DNS/DSQ (NaN-tijd), ongeacht de ruwe Rank."""
    if pd.isna(time) or not (1 <= rank <= 5):
        return 0
    return 6 - rank


def build_ranking(file_list):
    """Bouwt de resultsOverview-tabel op uit een lijst CSV-paden (Q1 + Q2 reeksen)."""
    dfs = [pd.read_csv(file, usecols=lambda col: col not in ['Bib', 'Country', 'Score', 'Diff', 'Total'], na_values=['']).fillna(0) for file in file_list]
    resultsCombined = pd.concat(dfs, ignore_index=True)

    resultsCombined['Time'] = resultsCombined['Time'].apply(time_to_seconds)
    resultsCombined['Points'] = [calculate_points(r, t) for r, t in zip(resultsCombined['Rank'], resultsCombined['Time'])]
    resultsCombined['Time'] = resultsCombined['Time'].fillna(DNF_TIME)

    grouped = resultsCombined.groupby(['Name', 'Event'])

    rows_to_add = []
    for group_name, group_data in grouped:
        name, event = group_name
        ranks = group_data['Rank'].values
        times = group_data['Time'].values
        points = group_data['Points'].values

        row_data = {
            'Name': name,
            'Event': event,
            'Rank1': ranks[0],
            'Time1': times[0],
            'Points1': points[0],
        }

        if len(ranks) > 1:
            row_data['Rank2'] = ranks[1]
            row_data['Time2'] = times[1]
            row_data['Points2'] = points[1]

        rows_to_add.append(row_data)

    resultsOverview = pd.DataFrame(rows_to_add)
    for kolom in ['Rank2', 'Time2', 'Points2']:
        if kolom not in resultsOverview.columns:
            resultsOverview[kolom] = 0  # niemand had een 2e run (bv. Q2 nog niet gereden)
    resultsOverview.fillna(0, inplace=True)

    resultsOverview['TotalPoints'] = resultsOverview['Points1'] + resultsOverview['Points2']
    resultsOverview['TotalTime'] = resultsOverview['Time1'] + resultsOverview['Time2']

    resultsOverview.sort_values(by=['TotalPoints', 'TotalTime'], ascending=[False, True], inplace=True)
    resultsOverview.reset_index(drop=True, inplace=True)
    resultsOverview['Rank'] = resultsOverview.index + 1

    resultsOverview['Final'] = 0
    resultsOverview['Lane'] = 0

    aantal_finales = len(resultsOverview) // 6 + 1

    for finale in range(1, aantal_finales + 1):
        start_index = (finale - 1) * 6
        end_index = min(finale * 6, len(resultsOverview))
        lanes = [3, 4, 2, 5, 1, 6][:end_index - start_index]
        final_values = [finale] * (end_index - start_index)
        resultsOverview.loc[start_index:end_index - 1, 'Lane'] = lanes
        resultsOverview.loc[start_index:end_index - 1, 'Final'] = final_values

    return resultsOverview


def genereer_ranking(category):
    folder_path = './' + category + '/'
    export_name = category + "_Ranking"

    file_list = glob.glob(folder_path + '*.csv')
    if not file_list:
        raise SystemExit(f"Geen CSV-bestanden gevonden in {folder_path}")

    resultsOverview = build_ranking(file_list)
    ontwapen_voor_export(resultsOverview).to_excel(export_name + ".xlsx", index=False, engine='openpyxl')
    print(f"Geëxporteerd naar {export_name}.xlsx ({len(resultsOverview)} atleten)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("category", nargs="?", default="SENH", help="Categorie-map, bv. SENH (default: SENH)")
    args = parser.parse_args()
    genereer_ranking(args.category)
