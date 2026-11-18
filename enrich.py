"""Enrichit les liquidations avec les données de vente du BODACC :
  - le prix auquel la société liquidée avait acheté son fonds (relié par SIREN) ;
  - les prix de vente des fonds du même métier dans le même département
    et le même code postal (24 derniers mois).

Usage : python3 enrich.py data.json data.json            (pipeline)
        python3 enrich.py data.json out.json --deps 75,92  (limiter les comparables)
"""
import csv, datetime, io, json, re, statistics, sys, time, urllib.parse, urllib.request

csv.field_size_limit(10**9)
BASE = "https://bodacc-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/annonces-commerciales"
sys.path.insert(0, ".")
from prepare import cat  # même classement par métier que les liquidations


def get(url, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                return r.read()
        except Exception as ex:  # réseau instable : on réessaie
            if i == tries - 1:
                raise
            time.sleep(5 * (i + 1))


def records(where, limit=100):
    url = BASE + "/records?" + urllib.parse.urlencode({"where": where, "limit": limit})
    return json.loads(get(url))["results"]


PRIX_RE = re.compile(r"prix stipul[ée]e? de ([0-9][0-9 .,]*)\s*(?:euros|eur|€)", re.I)


def parse_prix(txt):
    m = PRIX_RE.search(txt or "")
    if not m:
        return None
    s = m.group(1).strip().replace(" ", "")
    s = re.sub(r"[.,](\d{1,2})$", "", s)       # retire les centimes
    s = s.replace(".", "").replace(",", "")
    try:
        v = int(s)
    except ValueError:
        return None
    return v if 1000 <= v <= 5_000_000 else None


def etab(rec):
    try:
        e = json.loads(rec.get("listeetablissements") or "{}").get("etablissement")
    except ValueError:
        return {}
    if isinstance(e, list):
        e = e[0] if e else {}
    return e or {}


def nature(origine):
    o = (origine or "").lower()
    if "droit au bail" in o:
        return "droit au bail"
    return "fonds"


def fmt_siren(s):
    return f"{s[0:3]} {s[3:6]} {s[6:9]}"


def achats(sirens):
    """Pour chaque SIREN : les avis où la société est le nouveau propriétaire du fonds."""
    out = {}
    sirens = list(sirens)
    for i in range(0, len(sirens), 40):
        chunk = sirens[i:i + 40]
        w = 'familleavis="vente" and (' + " or ".join(f'registre="{s}"' for s in chunk) + ")"
        for rec in records(w):
            lp = rec.get("listepersonnes") or ""
            prev = rec.get("listeprecedentproprietaire") or ""
            e = etab(rec)
            prix = parse_prix(e.get("origineFonds", ""))
            for s in chunk:
                if fmt_siren(s) in lp and fmt_siren(s) not in prev:
                    out.setdefault(s, []).append({
                        "date": rec.get("dateparution"), "prix": prix,
                        "nature": nature(e.get("origineFonds")),
                        "activite": (e.get("activite") or "")[:200],
                        "adresse": " ".join(str(x) for x in [
                            (e.get("adresse") or {}).get("numeroVoie", ""), (e.get("adresse") or {}).get("typeVoie", ""),
                            (e.get("adresse") or {}).get("nomVoie", ""), (e.get("adresse") or {}).get("codePostal", ""),
                            (e.get("adresse") or {}).get("ville", "")] if x).strip(),
                        "url": rec.get("url_complete"),
                    })
        time.sleep(0.3)
    for s in out:
        out[s].sort(key=lambda a: a["date"] or "", reverse=True)
    return out


def comparables(deps=None, mois=24):
    debut = (datetime.date.today() - datetime.timedelta(days=30 * mois)).isoformat()
    w = f'familleavis="vente" and dateparution>=date\'{debut}\' and listeetablissements like "*prix stipul*"'
    if deps:
        w += " and (" + " or ".join(f'numerodepartement="{d}"' for d in deps) + ")"
    url = BASE + "/exports/csv?" + urllib.parse.urlencode({
        "where": w, "select": "dateparution,numerodepartement,cp,listeetablissements"})
    rows = csv.DictReader(io.StringIO(get(url).decode("utf-8-sig")), delimiter=";")
    out = []
    for r in rows:
        e = etab(r)
        if nature(e.get("origineFonds")) != "fonds":
            continue
        p = parse_prix(e.get("origineFonds", ""))
        c = cat(e.get("activite") or "")
        if p and c:
            cp = (e.get("adresse") or {}).get("codePostal") or r.get("cp", "").split(",")[0].strip()
            out.append({"dep": r["numerodepartement"], "cp": cp, "cat": c, "prix": p})
    return out


def stats(vals):
    vals = sorted(vals)
    if len(vals) < 5:
        return None
    q = statistics.quantiles(vals, n=4)
    return {"n": len(vals), "p25": round(q[0], -3), "med": round(statistics.median(vals), -3), "p75": round(q[2], -3)}


def main():
    src, dst = sys.argv[1], sys.argv[2]
    deps = None
    if "--deps" in sys.argv:
        deps = sys.argv[sys.argv.index("--deps") + 1].split(",")
    data = json.load(open(src))
    A = data["annonces"]
    sir = {a["siren"] for a in A if a.get("siren")}
    ach = achats(sir)
    comp = comparables(deps)
    by_dep, by_cp = {}, {}
    for c in comp:
        by_dep.setdefault((c["dep"], c["cat"]), []).append(c["prix"])
        by_cp.setdefault((c["cp"], c["cat"]), []).append(c["prix"])
    for a in A:
        h = ach.get(a.get("siren"), [])
        a["achat"] = next((x for x in h if x["prix"] and x["nature"] == "fonds"), None) or (h[0] if h else None)
        a["comp_cp"] = stats(by_cp.get((a.get("cp"), a["cat"]), []))
        a["comp_dep"] = stats(by_dep.get((a["dep"], a["cat"]), []))
    data["enrich"] = {"achats_trouves": sum(1 for a in A if a.get("achat")),
                      "achats_avec_prix": sum(1 for a in A if a.get("achat") and a["achat"].get("prix")),
                      "ventes_comparables": len(comp), "date": datetime.date.today().isoformat()}
    json.dump(data, open(dst, "w"), ensure_ascii=False)
    print("ENRICH", json.dumps(data["enrich"]))


if __name__ == "__main__":
    main()
