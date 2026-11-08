"""Erkundung ostsee.de: wie funktioniert der Kategorie-Filter? Ergebnisse -> debug/filter_report.txt"""
import json, re, urllib.parse, urllib.request, urllib.error
from pathlib import Path
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
URL = "https://www.ostsee.de/warnemuende/veranstaltungen.php"
rep = []
def log(m): print(m); rep.append(str(m))
def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=40) as r:
            return r.status, r.read().decode("utf-8", "replace"), r.geturl()
    except urllib.error.HTTPError as e:
        return e.code, "", url
def ids(h): return re.findall(r'"identifier":"de-ostsee-event-(\d+)"', h)
st, page, _ = get(URL)
form = re.search(r'<form class="form event-form.*?</form>', page, re.S).group(0)
Path("debug/formular.html").write_text(form, encoding="utf-8")
log(f"Formular: {re.sub(r'\s+', ' ', form)[:3000]}")
opts = re.findall(r'<option[^>]*value="([^"]+)"[^>]*>\s*(.*?)\s*</option>', form, re.S)
log(f"Optionen: {opts}")
log(f"ohne Filter: {len(ids(page))}")
v = opts[0][0] if opts else "festivals"
for q in [{"ort": "warnemuende", "veranstaltungsart": v},
          {"veranstaltungsart": v},
          {"ort": "warnemuende", "veranstaltungsart": v, "datum_heute": "", "datum_von": "", "datum_bis": ""},
          {"ort": "warnemuende", "veranstaltungsart": v, "datum_von": "08.11.2026", "datum_bis": "31.12.2027"}]:
    u = URL + "?" + urllib.parse.urlencode(q)
    st, h, f = get(u)
    log(f"{st} {len(ids(h))} Treffer {u} -> {f}")
for path in [f"/warnemuende/veranstaltungen/{v}.php", f"/warnemuende/{v}.php", f"/veranstaltungen/{v}.php"]:
    st, h, f = get("https://www.ostsee.de" + path)
    log(f"{st} {len(ids(h))} Treffer {path} -> {f}")
# JS des Formulars
for js in re.findall(r'<script[^>]+src="([^"]*(?:calendar|event)[^"]*)"', page):
    st, h, _ = get(urllib.parse.urljoin(URL, js))
    log(f"JS {js}: {re.findall(r'.{0,80}veranstaltungsart.{0,120}', h)[:5]}")
Path("debug/filter_report.txt").write_text("\n".join(rep), encoding="utf-8")
