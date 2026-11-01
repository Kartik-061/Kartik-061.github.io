"""Build dashboard/status.json from a Forge backup. Read-only: uses backup files, never the VM.
Usage (repo root): python dashboard/make_status.py backups/forge-YYYYMMDD.db backups/nav_history-YYYYMMDD.csv"""
import csv, glob, json, sqlite3, sys
from datetime import date, datetime, timedelta
from pathlib import Path

db_path, nav_path = sys.argv[1], sys.argv[2]
root = Path(__file__).resolve().parent.parent

def read_csv(path):
    return list(csv.DictReader(l for l in open(path) if not l.startswith("#")))

rows = read_csv(nav_path)
nav0, b0 = float(rows[0]["value"]), float(rows[0]["benchmark"])
series = [{"t": r["timestamp"][:10], "nav": round(float(r["value"]) / nav0 * 100, 3),
           "bench": round(float(r["benchmark"]) / b0 * 100, 3)} for r in rows]
peak, mdd = 0.0, 0.0
for p in series:
    peak = max(peak, p["nav"]); mdd = min(mdd, p["nav"] / peak - 1)
summary = {"start": series[0]["t"], "asof": series[-1]["t"], "nav": round(float(rows[-1]["value"]), 2),
           "ret": round(series[-1]["nav"] - 100, 2), "bench_ret": round(series[-1]["bench"] - 100, 2),
           "gap": round(series[-1]["nav"] - series[-1]["bench"], 2), "max_dd": round(mdd * 100, 2)}

hold = json.loads(sqlite3.connect(db_path).execute("select holdings_json from portfolio_state").fetchone()[0])
entry, rot = {}, []
for f in sorted(glob.glob(str(root / "records" / "*.csv"))):
    for r in read_csv(f):
        if "side" in r:
            rot = read_csv(f) if "rotation" in f else rot
            if r["side"] == "BUY": entry[r["symbol"]] = (float(r["price"]), r["date"])
        elif r.get("symbol"):
            entry[r["symbol"]] = (float(r["entry_price"]), "2026-10-06")
holdings = []
for s, q in sorted(hold.items()):
    px, d = entry.get(s, (None, None))
    holdings.append({"symbol": s, "qty": round(q, 3), "entry_price": px, "entry_date": d,
                     "entry_value": round(q * px, 2) if px else None})
last_rotation = {"date": rot[0]["date"] if rot else None,
                 "sells": [r["symbol"] for r in rot if r["side"] == "SELL"],
                 "buys": [r["symbol"] for r in rot if r["side"] == "BUY"]}

def last_trading_day(y, m):
    try:
        sys.path.insert(0, str(root)); from app.nse_calendar import last_trading_day_of_month as f
        return f(y, m)
    except Exception:
        d = date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)
        while d.weekday() > 4: d -= timedelta(days=1)
        return d
today = date.today()
nxt = last_trading_day(today.year, today.month)
if nxt < today: nxt = last_trading_day(today.year + (today.month == 12), today.month % 12 + 1)

out = {"generated": datetime.now().strftime("%Y-%m-%d %H:%M"), "summary": summary, "series": series,
       "holdings": holdings, "last_rotation": last_rotation, "next_rotation": str(nxt)}
(Path(__file__).parent / "status.json").write_text(json.dumps(out, indent=1))
print("wrote status.json:", summary)
