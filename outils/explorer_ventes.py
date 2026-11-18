"""Exploration : retrouver dans le BODACC les avis de vente (achat du fonds) des
sociétés liquidées, et regarder où se trouve le prix dans les avis."""
import json, sys, urllib.parse, urllib.request
API = "https://bodacc-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/annonces-commerciales/records"
def get(params):
    url = API + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)
# 1. Trois avis de vente à Paris, en entier, pour voir la structure
d = get({"where": 'familleavis="vente" and numerodepartement="75" and dateparution>=date\'2025-11-01\' and listeetablissements like "*prix stipul*"', "limit": 1})
print("VENTES PARIS 12 MOIS AVEC PRIX :", d.get("total_count"))
# 2. Avis de vente dont la société liquidée est le nouveau propriétaire
sirens = json.load(open(sys.argv[1]))
hits = []
for i in range(0, len(sirens), 40):
    chunk = sirens[i:i+40]
    w = 'familleavis="vente" and (' + " or ".join(f'registre="{s}"' for s in chunk) + ")"
    r = get({"where": w, "limit": 100})
    hits += r["results"]
print("SOCIETES TESTEES :", len(sirens), "AVIS DE VENTE TROUVES :", len(hits),
      "SOCIETES AVEC AU MOINS UN :", len({tuple(h["registre"]) for h in hits}))
import re
avec_prix = 0
for h in hits:
    le = h.get("listeetablissements") or ""
    m = re.search(r"prix stipul[ée] de ([0-9 .,]+) ?euros", le)
    if m: avec_prix += 1
print("AVIS AVEC PRIX :", avec_prix)
for h in hits[:12]:
    le = h.get("listeetablissements") or ""
    m = re.search(r'"origineFonds": "([^"]*)"', le); a = re.search(r'"activite": "([^"]*)"', le)
    print(h.get("dateparution"), "|", h.get("commercant"), "|", (m.group(1) if m else "-")[:120], "|", (a.group(1) if a else "-")[:80])
