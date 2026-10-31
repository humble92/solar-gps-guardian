"""Repository: sqlite persistence behind a small interface (swap-ready).

Tables: subscriptions (email+region), telemetry_cache (latest snapshot),
send_log (dedup + audit). One writer at a time; WAL enabled.
"""
import json
import sqlite3
import threading
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS subscriptions(
  id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL,
  region_name TEXT, lat REAL, lon REAL, radius_km REAL DEFAULT 100,
  active INTEGER DEFAULT 1, created_at REAL);
CREATE TABLE IF NOT EXISTS telemetry_cache(
  id INTEGER PRIMARY KEY CHECK(id=1), snapshot TEXT, updated_at REAL);
CREATE TABLE IF NOT EXISTS tec_grid(
  id INTEGER PRIMARY KEY CHECK(id=1), cells TEXT, updated_at REAL);
CREATE TABLE IF NOT EXISTS send_log(
  id INTEGER PRIMARY KEY, email TEXT, kind TEXT, event_key TEXT,
  sent_at REAL, UNIQUE(email, kind, event_key));
CREATE TABLE IF NOT EXISTS newsletters(
  id INTEGER PRIMARY KEY, period TEXT UNIQUE NOT NULL,
  title TEXT, markdown TEXT, chart_svg TEXT, package TEXT, created_at REAL);
"""


class Store:
    def __init__(self, path="data/guardian.db"):
        self.path = path
        self._lock = threading.Lock()
        conn = self._conn()
        conn.executescript(SCHEMA)
        conn.commit()
        conn.close()

    def _conn(self):
        import os
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        return c

    # subscriptions ----------------------------------------------------
    def subscribe(self, email, region_name, lat, lon, radius_km=100):
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT INTO subscriptions(email,region_name,lat,lon,radius_km,created_at)"
                " VALUES(?,?,?,?,?,?) ON CONFLICT(email) DO UPDATE SET"
                " region_name=excluded.region_name, lat=excluded.lat,"
                " lon=excluded.lon, radius_km=excluded.radius_km, active=1",
                (email, region_name, lat, lon, radius_km, time.time()))
            return c.execute("SELECT * FROM subscriptions WHERE email=?",
                             (email,)).fetchone()["id"]

    def unsubscribe(self, email):
        with self._lock, self._conn() as c:
            cur = c.execute("UPDATE subscriptions SET active=0 WHERE email=?", (email,))
            return cur.rowcount > 0

    def list_active(self):
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM subscriptions WHERE active=1")]

    # snapshot cache ---------------------------------------------------
    def save_snapshot(self, snap):
        with self._lock, self._conn() as c:
            c.execute("INSERT INTO telemetry_cache(id,snapshot,updated_at) VALUES(1,?,?)"
                      " ON CONFLICT(id) DO UPDATE SET snapshot=excluded.snapshot,"
                      " updated_at=excluded.updated_at",
                      (json.dumps(snap), time.time()))

    def load_snapshot(self):
        with self._conn() as c:
            row = c.execute("SELECT snapshot FROM telemetry_cache WHERE id=1").fetchone()
            return json.loads(row["snapshot"]) if row else None

    def save_tec_grid(self, cells):
        with self._lock, self._conn() as c:
            c.execute("INSERT INTO tec_grid(id,cells,updated_at) VALUES(1,?,?)"
                      " ON CONFLICT(id) DO UPDATE SET cells=excluded.cells,"
                      " updated_at=excluded.updated_at",
                      (json.dumps(cells), time.time()))

    def load_tec_grid(self):
        with self._conn() as c:
            row = c.execute("SELECT cells FROM tec_grid WHERE id=1").fetchone()
            return json.loads(row["cells"]) if row else []

    # send log ---------------------------------------------------------
    def already_sent(self, email, kind, event_key):
        with self._conn() as c:
            return c.execute("SELECT 1 FROM send_log WHERE email=? AND kind=? AND event_key=?",
                             (email, kind, event_key)).fetchone() is not None

    def log_sent(self, email, kind, event_key):
        with self._lock, self._conn() as c:
            c.execute("INSERT OR IGNORE INTO send_log(email,kind,event_key,sent_at)"
                      " VALUES(?,?,?,?)", (email, kind, event_key, time.time()))

    # newsletters ------------------------------------------------------
    def save_newsletter(self, period, title, markdown, chart_svg, package):
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT INTO newsletters(period,title,markdown,chart_svg,package,created_at)"
                " VALUES(?,?,?,?,?,?) ON CONFLICT(period) DO UPDATE SET"
                " title=excluded.title, markdown=excluded.markdown,"
                " chart_svg=excluded.chart_svg, package=excluded.package,"
                " created_at=excluded.created_at",
                (period, title, markdown, chart_svg,
                 json.dumps(package), time.time()))
            return c.execute("SELECT id FROM newsletters WHERE period=?",
                             (period,)).fetchone()["id"]

    def list_newsletters(self):
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT id,period,title,created_at FROM newsletters ORDER BY period DESC")]

    def get_newsletter(self, nid):
        with self._conn() as c:
            row = c.execute("SELECT * FROM newsletters WHERE id=?", (nid,)).fetchone()
            if not row:
                return None
            d = dict(row)
            d["package"] = json.loads(d["package"]) if d.get("package") else None
            return d
