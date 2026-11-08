"""Erkundung ostsee.de Veranstaltungen Warnemuende (laeuft in GitHub Actions). Ergebnisse -> debug/"""
import json, re, urllib.parse, urllib.request, urllib.error, gzip
from collections import Counter
from pathlib import Path

OUT = Path("debug"); OUT.mkdir(exist_ok=True)
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
URL = "https://www.ostsee.de/warnemuende/veranstaltungen.php"
rep = []
def log(m): print(m); rep.append(str(m))
def get(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "de"})
        with urllib.request.urlopen(req, timeout=40) as r:
            b = r.read()
            if b[:2] == b"\x1f\x8b": b = gzip.decompress(b)
            return r.status, r.headers.get("Content-Type", ""), b.decode("utf-8", "replace"), r.geturl()
    except urllib.error.HTTPError as e:
        return e.code, "", e.read().decode("utf-8", "replace"), url
    except Exception as e:
        return None, "", str(e), url
def text(h): return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>|<style.*?</style>", " ", h, flags=re.S)))

st, ct, page, final = get(URL)
log(f"HAUPTSEITE {st} {ct} {len(page)}B final={final}")
(OUT / "veranstaltungen.html").write_text(page, encoding="utf-8")

# strukturierte Daten
for i, m in enumerate(re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', page, re.S)):
    (OUT / f"ldjson_{i}.json").write_text(m, encoding="utf-8")
    log(f"LD+JSON {i}: {len(m)}B {m.strip()[:600]}")
log("Microdata itemtype: " + str(Counter(re.findall(r'itemtype="([^"]+)"', page)).most_common(10)))
log("itemprops: " + str(Counter(re.findall(r'itemprop="([^"]+)"', page)).most_common(20)))
# Links
links = re.findall(r'href="([^"#]+)"', page)
ev = [l for l in links if re.search(r"veranstalt|event|termin", l, re.I)]
log(f"{len(links)} Links, davon Veranstaltung/Event: {len(ev)}; Beispiele: {sorted(set(ev))[:40]}")
log("ICS/RSS/JSON: " + str([l for l in links if re.search(r"\.ics|ical|rss|feed|\.json|api", l, re.I)][:20]))
log("Blaettern: " + str(sorted(set(l for l in links if re.search(r"page=|seite=|monat=|start=|offset=|p=\d|datum=", l, re.I)))[:30]))
log("Iframes/Widgets: " + str(re.findall(r'<iframe[^>]+src="([^"]+)"', page)[:10]))
log("Scripts: " + str(re.findall(r'<script[^>]+src="([^"]+)"', page)[:30]))
log("Formulare: " + str([re.sub(r"\s+", " ", f)[:400] for f in re.findall(r"<form.*?</form>", page, re.S)][:5]))
# Datumsangaben im Text
t = text(page)
dates = re.findall(r"\b\d{1,2}\.\d{1,2}\.(?:\d{2,4})?", t)
log(f"Datumsangaben im Text: {len(dates)}, Beispiele: {dates[:30]}")
i = t.find("Veranstaltung")
log("TEXTAUSZUG: " + t[:200] + " ... " + t[i:i+4000])
# CSS-Klassen, die nach Eintraegen aussehen
log("Klassen: " + str(Counter(c for cl in re.findall(r'class="([^"]+)"', page) for c in cl.split() if re.search(r"event|veranst|termin|item|card|list|date|datum", c, re.I)).most_common(30)))

# erste 3 Detailseiten
for j, l in enumerate(sorted(set(ev))[:3]):
    u = urllib.parse.urljoin(final, l)
    st, ct, h, f2 = get(u)
    (OUT / f"detail_{j}.html").write_text(h, encoding="utf-8")
    lds = re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', h, re.S)
    log(f"\nDETAIL {j} {st} {u} {len(h)}B LD+JSON={len(lds)} {lds[0].strip()[:500] if lds else ''}\n   {text(h)[:1200]}")

(OUT / "report.txt").write_text("\n".join(rep), encoding="utf-8")
