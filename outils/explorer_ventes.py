"""Exploration : retrouver dans le BODACC les avis de vente (achat du fonds) des
sociétés liquidées, et regarder où se trouve le prix dans les avis."""
import json, sys, urllib.parse, urllib.request
API = "https://bodacc-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/annonces-commerciales/records"
def get(params):
    url = API + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)
# 1. Trois avis de vente à Paris, en entier, pour voir la structure
d = get({"where": 'familleavis="vente" and numerodepartement="75"', "order_by": "dateparution desc", "limit": 3})
print("TOTAL ventes Paris :", d.get("total_count"))
for rec in d["results"]:
    print(json.dumps(rec, ensure_ascii=False)[:3000]); print("-----")
# 2. Avis de vente dont la société liquidée est le nouveau propriétaire
sirens = json.load(open(sys.argv[1]))
hits = []
for i in range(0, len(sirens), 40):
    chunk = sirens[i:i+40]
    w = 'familleavis="vente" and (' + " or ".join(f'registre="{s}"' for s in chunk) + ")"
    r = get({"where": w, "limit": 100})
    hits += r["results"]
print("SOCIETES TESTEES :", len(sirens), "AVIS DE VENTE TROUVES :", len(hits),
      "SOCIETES AVEC AU MOINS UN :", len({h["registre"] for h in hits}))
for h in hits[:15]:
    print(json.dumps({k: h.get(k) for k in ("dateparution","commercant","registre","ville","typeavis_lib","acte","listeprecedentproprietaire","listeetablissements")}, ensure_ascii=False)[:1500]); print("-----")
