#!/usr/bin/env python3
"""Refresh data/ferrari-titles.json from the Jolpica-F1 (Ergast-compatible) API.

Two jobs:
  1. Title verification — whether Ferrari has won a Drivers'/Constructors'
     championship since its last recorded titles, and the most recent
     fully-completed season verified.
  2. Chart data — per-season Ferrari wins plus win/podium/season totals and
     title years, so the centrepiece chart and headline figures self-extend.

Designed to run on a schedule. It only writes valid data: the title fields are
guarded by a completed-season check, and the chart block is written only if it
passes sanity guards (totals never below the known 2024 baseline, internally
consistent). On any failure the previous good values are preserved, so a network
hiccup or API change never corrupts the committed file.

Run `python update_titles.py --selftest` to exercise the pure logic offline.
"""
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request

API = "https://api.jolpi.ca/ergast/f1"
UA = "ferrari-the-long-wait/1.0 (+https://github.com/mquinn614/ferrari)"
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, "..", "data", "ferrari-titles.json"))
FERRARI = "ferrari"
START_YEAR = 1950

# Known totals through the 2024 season; computed figures must never fall below
# these (they only grow), which catches a truncated/garbage API response.
BASELINE = {"wins": 249, "podiums": 841, "seasons": 75,
            "constructorsTitles": 16, "driversTitles": 15}


def get(path):
    sep = "&" if "?" in path else "?"
    url = API + path + sep + "format=json"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError("HTTP %s for %s" % (e.code, url)) from e


# ---------------------------------------------------------------- title checks

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


# ----------------------------------------------------------- chart aggregation

def result_seasons(position):
    """Every season (with repetition) a Ferrari finished in `position`, paged in full."""
    seasons, total, offset = [], None, 0
    while True:
        d = get("/constructors/ferrari/results/%d/?limit=100&offset=%d" % (position, offset))["MRData"]
        if total is None:
            total = int(d["total"])
        races = d["RaceTable"]["Races"]
        if not races:
            break
        seasons.extend(int(r["season"]) for r in races)
        offset += 100
        if offset >= total:
            break
        time.sleep(0.3)
    return seasons


def title_years(kind):
    """Seasons Ferrari (or a Ferrari driver) finished 1st in the given standings."""
    lists = get("/constructors/ferrari/%s/1/?limit=100" % kind)["MRData"]["StandingsTable"]["StandingsLists"]
    return sorted(int(s["season"]) for s in lists)


def count_by_year(seasons):
    by = {}
    for y in seasons:
        by[y] = by.get(y, 0) + 1
    return by


def wins_array(by_year, start, end):
    return [by_year.get(y, 0) for y in range(start, end + 1)]


def compute_chart(latest_complete, start_year=START_YEAR):
    """Build the chart block from Jolpica, constrained to completed seasons."""
    print("chart: paging Ferrari finishes P1/P2/P3...", file=sys.stderr)
    p1 = [y for y in result_seasons(1) if y <= latest_complete]
    p2 = [y for y in result_seasons(2) if y <= latest_complete]
    p3 = [y for y in result_seasons(3) if y <= latest_complete]
    print("chart: seasons entered...", file=sys.stderr)
    seasons_list = get("/constructors/ferrari/seasons/?limit=100")["MRData"]["SeasonTable"]["Seasons"]
    seasons = sum(1 for s in seasons_list if int(s["season"]) <= latest_complete)
    print("chart: title years...", file=sys.stderr)
    cons_years = [y for y in title_years("constructorStandings") if y <= latest_complete]
    drv_years = [y for y in title_years("driverStandings") if y <= latest_complete]
    return {
        "startYear": start_year,
        "wins": wins_array(count_by_year(p1), start_year, latest_complete),
        "driversTitleYears": drv_years,
        "constructorsTitleYears": cons_years,
        "totals": {
            "wins": len(p1),
            "podiums": len(p1) + len(p2) + len(p3),
            "seasons": seasons,
            "constructorsTitles": len(cons_years),
            "driversTitles": len(drv_years),
        },
    }


def chart_passes_guards(chart, latest_complete):
    t = chart["totals"]
    return (
        t["wins"] >= BASELINE["wins"]
        and t["podiums"] >= BASELINE["podiums"]
        and t["seasons"] >= BASELINE["seasons"]
        and t["constructorsTitles"] >= BASELINE["constructorsTitles"]
        and t["driversTitles"] >= BASELINE["driversTitles"]
        and t["wins"] <= t["podiums"]
        and sum(chart["wins"]) == t["wins"]
        and len(chart["wins"]) == latest_complete - chart["startYear"] + 1
        and t["constructorsTitles"] == len(chart["constructorsTitleYears"])
        and t["driversTitles"] == len(chart["driversTitleYears"])
        and (not chart["constructorsTitleYears"] or max(chart["constructorsTitleYears"]) <= latest_complete)
        and (not chart["driversTitleYears"] or max(chart["driversTitleYears"]) <= latest_complete)
    )


# --------------------------------------------------------------------- runtime

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
        except Exception as e:  # never write partial/uncertain title results
            print("standings check failed for %d: %s" % (year, e), file=sys.stderr)
            return 1
        time.sleep(0.3)

    # Chart data is best-effort: if it fails or looks wrong, keep the last good
    # chart and don't advance recordThrough, but still update the title fields.
    record_through = int(cur.get("recordThrough", 2024))
    chart = cur.get("chart")
    try:
        fresh = compute_chart(latest_complete)
        if chart_passes_guards(fresh, latest_complete):
            chart = fresh
            record_through = latest_complete
        else:
            print("chart guards failed; preserving existing chart data", file=sys.stderr)
    except Exception as e:
        print("chart aggregation failed (%s); preserving existing chart data" % e, file=sys.stderr)

    out = {
        "driversYear": drivers_year,
        "constructorsYear": constructors_year,
        "verifiedThrough": latest_complete,
        "recordThrough": record_through,
        "droughtBroken": drivers_year > 2007 or constructors_year > 2008,
        "source": "https://api.jolpi.ca/ergast/f1/",
        "updated": today.isoformat(),
    }
    if chart is not None:
        out["chart"] = chart

    os.makedirs(os.path.dirname(DATA), exist_ok=True)
    with open(DATA, "w") as f:
        json.dump(out, f, indent=2)
        f.write("\n")
    print("wrote", DATA, "(recordThrough=%s, chart=%s)" % (record_through, "yes" if chart else "no"))
    return 0


def selftest():
    assert count_by_year([2019, 2019, 2022]) == {2019: 2, 2022: 1}
    assert wins_array({2019: 2, 2022: 1}, 2018, 2022) == [0, 2, 0, 0, 1]
    good = {
        "startYear": 1950,
        "wins": [4] * (2025 - 1950 + 1),                    # 76 entries, sum 304
        "driversTitleYears": list(range(1990, 2005)),       # 15
        "constructorsTitleYears": list(range(1990, 2006)),  # 16
        "totals": {"wins": 304, "podiums": 900, "seasons": 76,
                   "constructorsTitles": 16, "driversTitles": 15},
    }
    assert chart_passes_guards(good, 2025), "valid chart should pass"
    below = json.loads(json.dumps(good))
    below["totals"]["wins"] = 248
    assert not chart_passes_guards(below, 2025), "below-baseline wins should fail"
    wrong_len = json.loads(json.dumps(good))
    wrong_len["wins"] = [4] * 40
    assert not chart_passes_guards(wrong_len, 2025), "wins length mismatch should fail"
    mism = json.loads(json.dumps(good))
    mism["driversTitleYears"] = list(range(1990, 2004))     # 14 != 15
    assert not chart_passes_guards(mism, 2025), "title-count mismatch should fail"
    print("selftest OK")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    sys.exit(main())
