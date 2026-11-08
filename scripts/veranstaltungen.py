"""Veranstaltungskalender Warnemuende (ICS-Abo) aus https://www.ostsee.de/warnemuende/veranstaltungen.php

Die Seite liefert jede Veranstaltung maschinenlesbar (schema.org "Event", JSON-LD) mit fester ID, Name, Start/Ende,
Ort und Status. Zusaetzlich werden die Textfelder "Termin" und "Zeit" gelesen (z. B. "Jeden Samstag und Sonntag",
"ab 10:00 Uhr") und die Kategorien ueber den Filter der Seite ermittelt.

- Alle Veranstaltungen werden in daten/veranstaltungen.json gesammelt. Vergangene werden nie geloescht.
- Verschwindet eine kuenftige Veranstaltung von der Seite, gilt sie als abgesagt und wird entfernt.
- Laengere Veranstaltungen mit festen Wochentagen ("Jeden Samstag und Sonntag") werden als einzelne Tage eingetragen,
  sonst als zusammenhaengender Zeitraum.
- Von den Beschreibungen wird nur ein kurzer Anriss uebernommen (die Texte gehoeren ostsee.de), dazu der Link.
- Ausgabe: docs/veranstaltungen.ics und docs/index.html

Nur Python-Standardbibliothek.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "daten"
OUT = ROOT / "docs"
EVENTS_FILE = DATA / "veranstaltungen.json"
KEEPALIVE_FILE = DATA / "letzte-pruefung.txt"

URL = "https://www.ostsee.de/warnemuende/veranstaltungen.php"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
TZ = ZoneInfo("Europe/Berlin")
TEASER_LEN = 220
DEFAULT_DURATION = dt.timedelta(hours=2)  # wenn nur eine Startzeit angegeben ist
WEEKDAYS = {"montag": 0, "dienstag": 1, "mittwoch": 2, "donnerstag": 3, "freitag": 4, "samstag": 5, "sonntag": 6,
            "montags": 0, "dienstags": 1, "mittwochs": 2, "donnerstags": 3, "freitags": 4, "samstags": 5,
            "sonntags": 6}
WD_SHORT = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


class FetchError(Exception):
    pass


def http_get(url: str) -> str:
    last = None
    for _ in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "de"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 404:
                break
        except Exception as e:  # noqa: BLE001
            last = e
    raise FetchError(f"{url}: {last}")


def clean(s: str) -> str:
    s = re.sub(r"<br\s*/?>|</p>", " ", s or "")
    s = html.unescape(re.sub(r"<[^>]+>", "", s)).replace("\u00ad", "").replace("\u00a0", " ")
    return " ".join(s.split())


def teaser(s: str) -> str:
    s = clean(s)
    if len(s) <= TEASER_LEN:
        return s
    cut = s[:TEASER_LEN].rsplit(" ", 1)[0]
    return cut.rstrip(",;:–-") + " …"


# ------------------------------------------------------------------ Seite lesen

def parse_page(page: str) -> dict[str, dict]:
    events = {}
    for block in page.split('<div class="teaser">')[1:]:
        m = re.search(r"<script type='application/ld\+json'>(.*?)</script>", block, re.S) \
            or re.search(r'<script type="application/ld\+json">(.*?)</script>', block, re.S)
        if not m:
            continue
        try:
            d = json.loads(m.group(1))
        except ValueError:
            continue
        if d.get("@type") != "Event" or not d.get("startDate"):
            continue
        details = {}
        dm = re.search(r'<div class="event-details">(.*?)</div>', block, re.S)
        if dm:
            for k, v in re.findall(r"<h4>(.*?)</h4>\s*<span[^>]*>(.*?)</span>\s*(?=<h4>|$)", dm.group(1), re.S):
                details[clean(k).rstrip(":").lower()] = clean(v)
        loc = d.get("location") or {}
        addr = loc.get("address") or {}
        parts = [clean(loc.get("name", "")), clean(addr.get("streetAddress", "")),
                 " ".join(filter(None, [addr.get("postalCode", ""), clean(addr.get("addressLocality", ""))]))]
        place = ", ".join(x for i, x in enumerate(parts) if x and x not in parts[:i])
        eid = str(d.get("identifier") or d.get("@id")).replace("de-ostsee-event-", "")
        events[eid] = {
            "name": clean(d.get("name", "")),
            "start": d["startDate"],
            "ende": d.get("endDate") or d["startDate"],
            "ort": place,
            "termin": details.get("termin", ""),
            "zeit": details.get("zeit", ""),
            "beschreibung": teaser(re.sub(r"Termin:.*$", "", d.get("description", ""), flags=re.S)),
            "url": d.get("url") or URL,
            "status": (d.get("eventStatus") or "").rsplit("/", 1)[-1],
        }
    return events


def fetch_events() -> dict[str, dict]:
    page = http_get(URL)
    events = parse_page(page)
    if not events:
        raise FetchError(f"Keine Veranstaltungen auf {URL} gefunden – hat sich die Seite geaendert?")
    # Kategorien ueber den Filter der Seite
    form = re.search(r'<select id="event-type-id" name="veranstaltungsart">(.*?)</select>', page, re.S)
    cats = re.findall(r'<option\s+value="([^"]+)"\s*>\s*(.*?)\s*</option>', form.group(1), re.S) if form else []
    for value, label in cats:
        try:
            sub = parse_page(http_get(URL + "?" + urllib.parse.urlencode({"ort": "warnemuende", "veranstaltungsart": value})))
        except FetchError:
            continue
        if len(sub) >= len(events):
            continue  # Filter hat offenbar nicht gegriffen
        for eid in sub:
            if eid in events:
                events[eid].setdefault("kategorien", [])
                if clean(label) not in events[eid]["kategorien"]:
                    events[eid]["kategorien"].append(clean(label))
    return events


def merge(old: dict, new: dict, today: dt.date) -> tuple[dict, list[str]]:
    notes = []
    merged = {}
    for eid, e in old.items():
        if eid in new:
            continue
        if dt.date.fromisoformat(e["ende"][:10]) >= today:
            notes.append(f"entfernt (abgesagt/verschoben): {e['start'][:10]} {e['name']}")
            continue
        merged[eid] = e  # Vergangenheit: wird nie geloescht
    for eid, e in new.items():
        if eid not in old:
            notes.append(f"neu: {e['start'][:10]} {e['name']}")
        elif old[eid] != e:
            notes.append(f"geaendert: {e['start'][:10]} {e['name']}")
        merged[eid] = e
    return dict(sorted(merged.items(), key=lambda kv: (kv[1]["start"], kv[0]))), notes


# ------------------------------------------------------------------ Termine berechnen

def _dt(s: str) -> tuple[dt.date, dt.time | None]:
    d = dt.date.fromisoformat(s[:10])
    t = dt.time.fromisoformat(s[11:16]) if len(s) >= 16 and s[10] == "T" else None
    return d, t


def weekdays_from(text: str) -> list[int]:
    """'Jeden Samstag und Sonntag' -> [5, 6]; 'Mittwoch bis Sonntag' -> [2..6]."""
    t = text.lower()
    m = re.search(r"(montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag)s?\s*(?:bis|–|-)\s*"
                  r"(montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag)", t)
    if m:
        a, b = WEEKDAYS[m.group(1)], WEEKDAYS[m.group(2)]
        return list(range(a, b + 1)) if a <= b else list(range(a, 7)) + list(range(0, b + 1))
    return sorted({WEEKDAYS[w] for w in re.findall(r"\b(" + "|".join(WEEKDAYS) + r")\b", t)})


def occurrences(e: dict) -> list[tuple[str, object, object, bool]]:
    """Liefert (uid-zusatz, start, ende, ganztaegig)."""
    d1, t1 = _dt(e["start"])
    d2, t2 = _dt(e["ende"])
    if d2 < d1:
        d2 = d1
    span = (d2 - d1).days
    wds = weekdays_from(e["termin"]) if span >= 6 else []
    if wds:
        out = []
        day = d1
        while day <= d2:
            if day.weekday() in wds:
                if t1:
                    s = dt.datetime.combine(day, t1, TZ)
                    en = dt.datetime.combine(day, t2, TZ) if t2 and t2 > t1 else s + DEFAULT_DURATION
                    out.append((f"-{day:%Y%m%d}", s, en, False))
                else:
                    out.append((f"-{day:%Y%m%d}", day, day + dt.timedelta(days=1), True))
            day += dt.timedelta(days=1)
        return out
    if t1 and span <= 1:
        s = dt.datetime.combine(d1, t1, TZ)
        if t2:
            en = dt.datetime.combine(d2, t2, TZ)
        else:
            en = s + DEFAULT_DURATION if span == 0 else dt.datetime.combine(d2, dt.time(23, 59), TZ)
        if en <= s:
            en = s + DEFAULT_DURATION
        return [("", s, en, False)]
    return [("", d1, d2 + dt.timedelta(days=1), True)]


# ------------------------------------------------------------------ Ausgabe

def esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")


def fold(line: str) -> str:
    out, b = [], line.encode("utf-8")
    while len(b) > 74:
        cut = 74
        while (b[cut] & 0xC0) == 0x80:
            cut -= 1
        out.append(b[:cut].decode())
        b = b[cut:]
    out.append(b.decode())
    return "\r\n ".join(out)


def utc(t: dt.datetime) -> str:
    return t.astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def fmt_range(e: dict) -> str:
    d1, t1 = _dt(e["start"])
    d2, t2 = _dt(e["ende"])
    s = f"{d1:%d.%m.%Y}" if d1 == d2 else f"{d1:%d.%m.%Y} bis {d2:%d.%m.%Y}"
    if t1:
        s += f", {t1:%H:%M}" + (f"–{t2:%H:%M}" if t2 else "") + " Uhr"
    return s


def render_ics(events: dict) -> str:
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//veranstaltungen-warnemuende//DE", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH", "X-WR-CALNAME:Veranstaltungen Warnemünde", "X-WR-TIMEZONE:Europe/Berlin",
             "REFRESH-INTERVAL;VALUE=DURATION:PT12H", "X-PUBLISHED-TTL:PT12H"]
    for eid, e in events.items():
        cancelled = e.get("status") in ("EventCancelled",)
        desc = [fmt_range(e)]
        if e["termin"]:
            desc.append(f"Termin: {e['termin']}")
        if e["zeit"]:
            desc.append(f"Zeit: {e['zeit']}")
        if e["ort"]:
            desc.append(f"Ort: {e['ort']}")
        if e.get("kategorien"):
            desc.append("Kategorie: " + ", ".join(e["kategorien"]))
        if e["beschreibung"]:
            desc += ["", e["beschreibung"]]
        desc += ["", f"Mehr Infos: {e['url']}", "Quelle: ostsee.de – Angaben ohne Gewähr."]
        title = ("ABGESAGT: " if cancelled else "") + e["name"]
        for suffix, s, en, allday in occurrences(e):
            lines += ["BEGIN:VEVENT", f"UID:{eid}{suffix}@veranstaltungen-warnemuende", "DTSTAMP:20260101T000000Z"]
            if allday:
                lines += [f"DTSTART;VALUE=DATE:{s:%Y%m%d}", f"DTEND;VALUE=DATE:{en:%Y%m%d}"]
            else:
                lines += [f"DTSTART:{utc(s)}", f"DTEND:{utc(en)}"]
            lines += [f"SUMMARY:{esc(title)}", f"LOCATION:{esc(e['ort'])}", f"DESCRIPTION:{esc(chr(10).join(desc))}",
                      f"URL:{e['url']}", "TRANSP:TRANSPARENT"]
            if e.get("kategorien"):
                lines.append("CATEGORIES:" + ",".join(esc(k) for k in e["kategorien"]))
            if cancelled:
                lines.append("STATUS:CANCELLED")
            lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold(x) for x in lines) + "\r\n"


PAGE = """<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Veranstaltungen Warnemünde</title>
<style>
  :root {{ --bg:#fff; --fg:#1d1d1f; --muted:#666; --box:#f3f4f6; --line:#e3e5e8; --btn:#b4461d; --g:#1a73e8; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --bg:#111; --fg:#eee; --muted:#aaa; --box:#222; --line:#333; --btn:#d0602f; --g:#4c8df6; }} }}
  body {{ background:var(--bg); color:var(--fg); font:17px/1.5 system-ui,-apple-system,sans-serif; max-width:46rem; margin:1.5rem auto; padding:0 16px; }}
  h1 {{ font-size:1.6rem; margin-bottom:.25rem; }}
  .btn {{ display:block; text-align:center; text-decoration:none; color:#fff; background:var(--btn); padding:1rem; border-radius:12px; font-weight:600; margin:.75rem 0; }}
  .btn.g {{ background:var(--g); }}
  .box {{ background:var(--box); padding:.75rem 1rem; border-radius:12px; margin:1rem 0; }}
  code {{ word-break:break-all; font-size:.9rem; }}
  small, .muted {{ color:var(--muted); }}
  .list {{ list-style:none; padding:0; }}
  .list li {{ border-bottom:1px solid var(--line); padding:.6rem 0; }}
  .list .top {{ font-weight:600; }}
  .list .sub {{ font-size:.9rem; color:var(--muted); }}
  .list a {{ color:inherit; }}
</style>
</head>
<body>
<h1>Veranstaltungen in Warnemünde</h1>
<p>Alle Veranstaltungen in Warnemünde als Kalender – Feste, Märkte, Konzerte, Sport und mehr, mit Zeit, Ort und Link.
Neue Termine und Änderungen kommen täglich von selbst dazu.</p>

<h2>Abonnieren</h2>
<a class="btn" id="ios" href="veranstaltungen.ics">iPhone / iPad / Mac: Abonnieren</a>
<a class="btn g" id="google" href="https://calendar.google.com/">Android / Google Kalender: Abonnieren</a>
<div class="box">
<small><strong>iPhone:</strong> „Abonnieren“ → „Hinzufügen“. Für iPhone <em>und</em> iPad: Kalender-App → „Kalender“ → „Kalender hinzufügen“ → „Kalenderabo hinzufügen“ → Adresse unten eingeben → bei „Account“ iCloud wählen.<br>
<strong>Google:</strong> Knopf antippen und „Hinzufügen“. Öffnet sich nur die App: im Chrome-Menü „Desktopwebsite“ einschalten oder am PC über calendar.google.com → „Weitere Kalender“ → „+“ → „Per URL“.</small>
</div>
<p>Abo-Adresse:</p>
<div class="box"><code id="url"></code></div>

<h2>Die nächsten Veranstaltungen</h2>
<ul class="list">
{rows}
</ul>
<p><small>Angaben ohne Gewähr. Quelle: <a href="https://www.ostsee.de/warnemuende/veranstaltungen.php">ostsee.de</a> –
maßgeblich sind die Angaben der Veranstalter.</small></p>
<script>
  var url = location.href.replace(/[?#].*$/, "").replace(/[^/]*$/, "") + "veranstaltungen.ics";
  var webcal = url.replace(/^https?:/, "webcal:");
  document.getElementById("url").textContent = url;
  document.getElementById("ios").href = webcal;
  document.getElementById("google").href = "https://calendar.google.com/calendar/render?cid=" + encodeURIComponent(webcal);
</script>
</body>
</html>
"""


def render_page(events: dict, today: dt.date) -> str:
    rows = []
    for e in events.values():
        if dt.date.fromisoformat(e["ende"][:10]) < today:
            continue
        sub = " · ".join(x for x in [e["termin"], e["zeit"], e["ort"]] if x)
        cats = f" · {', '.join(e['kategorien'])}" if e.get("kategorien") else ""
        rows.append(f'<li><div class="top"><a href="{html.escape(e["url"])}">{html.escape(e["name"])}</a></div>'
                    f'<div class="sub">{html.escape(fmt_range(e))}{html.escape(cats)}<br>{html.escape(sub)}</div></li>')
    if not rows:
        rows.append('<li class="muted">Derzeit sind keine Veranstaltungen angekündigt.</li>')
    return PAGE.format(rows="\n".join(rows))


def main() -> int:
    today = dt.date.fromisoformat(os.environ["TODAY"]) if os.environ.get("TODAY") else dt.datetime.now(TZ).date()
    old = json.loads(EVENTS_FILE.read_text(encoding="utf-8")) if EVENTS_FILE.exists() else {}
    try:
        new = fetch_events()
    except FetchError as e:
        print(f"::error::Veranstaltungen nicht abrufbar: {e} – bisheriger Kalender bleibt erhalten")
        return 1
    events, notes = merge(old, new, today)
    for n in notes:
        print(n)
    print(f"{len(new)} Veranstaltungen auf ostsee.de, {len(events)} im Kalender")
    DATA.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    EVENTS_FILE.write_text(json.dumps(events, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    # Einmal pro Monat aendert sich diese Datei -> monatlicher Commit, damit GitHub den Zeitplan nicht abschaltet
    KEEPALIVE_FILE.write_text(f"{today:%Y-%m}\n", encoding="utf-8")
    (OUT / "veranstaltungen.ics").write_text(render_ics(events), encoding="utf-8", newline="")
    (OUT / "index.html").write_text(render_page(events, today), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
