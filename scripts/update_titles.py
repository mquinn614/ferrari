#!/usr/bin/env python3
"""Refresh data/ferrari-titles.json from the Jolpica-F1 (Ergast-compatible) API.

Checks whether Ferrari has won a Drivers' or Constructors' championship since its
last recorded titles, and records the most recent fully-completed season verified.
Designed to run on a schedule. It only writes when it has valid data, so a network
hiccup never corrupts the committed file (the page keeps serving the last good values).
"""
import datetime as dt
import json
import os
import sys
import time
import urllib.request

API = "https://api.jolpi.ca/ergast/f1"
UA = "ferrari-the-long-wait/1.0 (+https://github.com/mquinn614/ferrari)"
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, "..", "data", "ferrari-titles.json"))
FERRARI = "ferrari"


def get(path):
    req = urllib.request.Request(API + path + "?format=json", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def season_complete(year, today):
    """True if the season's last scheduled race is already in the past."""
    races = get("/%d/races/" % year)["MRData"]["RaceTable"]["Races"]
    if not races or not races[-1].get("date"):
        return False
    return dt.date.fromisoformat(races[-1]["date"]) < today


def standings(path, key):
    lists = get(path)["MRData"]["StandingsTable"]["StandingsLists"]
    if not lists or not lists[0].get(key):
        return None
    return lists[0][key][0]


def constructors_champion(year):
    top = standings("/%d/constructorstandings/" % year, "ConstructorStandings")
    if top and top.get("position") == "1":
        return top["Constructor"]["constructorId"]
    return None


def drivers_champion_constructors(year):
    top = standings("/%d/driverstandings/" % year, "DriverStandings")
    if top and top.get("position") == "1":
        return [c["constructorId"] for c in top.get("Constructors", [])]
    return []


def load_current():
    try:
        with open(DATA) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"driversYear": 2007, "constructorsYear": 2008}


def main():
    today = dt.date.today()
    cur = load_current()
    drivers_year = int(cur.get("driversYear", 2007))
    constructors_year = int(cur.get("constructorsYear", 2008))

    # Most recent fully-completed season (don't claim a season that's still running).
    latest_complete = None
    for year in range(today.year, 2008, -1):
        try:
            if season_complete(year, today):
                latest_complete = year
                break
        except Exception as e:  # network/parse issue: try an earlier season
            print("schedule check failed for %d: %s" % (year, e), file=sys.stderr)
        time.sleep(0.3)
    if latest_complete is None:
        print("could not determine a completed season; leaving data unchanged", file=sys.stderr)
        return 1

    # Scan seasons since the last recorded titles for any new Ferrari championship.
    for year in range(2009, latest_complete + 1):
        try:
            if year > constructors_year and constructors_champion(year) == FERRARI:
                constructors_year = year
            if year > drivers_year and FERRARI in drivers_champion_constructors(year):
                drivers_year = year
        except Exception as e:  # never write partial/uncertain results
            print("standings check failed for %d: %s" % (year, e), file=sys.stderr)
            return 1
        time.sleep(0.3)

    out = {
        "driversYear": drivers_year,
        "constructorsYear": constructors_year,
        "verifiedThrough": latest_complete,
        "droughtBroken": drivers_year > 2007 or constructors_year > 2008,
        "source": "https://api.jolpi.ca/ergast/f1/",
        "updated": today.isoformat(),
    }
    os.makedirs(os.path.dirname(DATA), exist_ok=True)
    with open(DATA, "w") as f:
        json.dump(out, f, indent=2)
        f.write("\n")
    print("wrote", DATA, out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
