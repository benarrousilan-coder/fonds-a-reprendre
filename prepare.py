import csv, json, re, sys, collections
csv.field_size_limit(10**9)
src = sys.argv[1]
rows = list(csv.DictReader(open(src, encoding='utf-8-sig'), delimiter=';'))
LJ = {"Jugement d'ouverture de liquidation judiciaire",
      "Jugement de conversion en liquidation judiciaire",
      "Jugement prononçant la résolution du plan de redressement et la liquidation judiciaire"}
CATS = [
 ("restaurants", "Restaurants, cafés & bars", ["restaura","repas","débit de boisson","debit de boisson","brasserie","traiteur","pizz","snack","salon de thé","bar ","bar,","café","coffee","burger","sandwich","kebab","sushi"]),
 ("alimentation", "Boulangeries & alimentation", ["boulang","pâtiss","patiss","épicerie","epicerie","boucher","charcut","primeur","fromag","supérette","superette","caviste","vins et spiritueux","chocolat","produits alimentaires","fruits et légumes","fruits et legumes"]),
 ("beaute", "Coiffure & beauté", ["coiff","esthéti","esthetique","beauté","beaute","ongle","onglerie","barbier","institut","manucure","soins du corps","tatou"]),
 ("boutiques", "Boutiques & commerce de détail", ["commerce de détail","commerce de detail","vente au détail","vente au detail","prêt-à-porter","pret-a-porter","prêt à porter","vêtement","vetement","chaussure","boutique","magasin","bijou","fleur","optique","téléphon","telephon","maroquin","parfum","jouet","librairie","décoration","decoration"]),
]
def cat(act):
    a = " " + act.lower() + " "
    for key, lab, kws in CATS:
        if any(k in a for k in kws): return key
    return None
def liq(txt):
    m = re.search(r"liquidateur\s*:?\s*(.+?)(?:\.\s?Les |\. Les|, avec |\.?$)", txt)
    if not m: return ""
    s = m.group(1).strip().rstrip('.')
    return re.sub(r"\s+", " ", s)
out, stats = [], collections.Counter()
for r in rows:
    if not r['jugement']: continue
    j = json.loads(r['jugement'])
    if j.get('nature') not in LJ: continue
    stats['lj'] += 1
    try: p = json.loads(r['listepersonnes'])['personne']
    except Exception: continue
    if not isinstance(p, dict) or p.get('typePersonne') != 'pm': continue
    stats['pm'] += 1
    act = p.get('activite', '') or ''
    c = cat(act)
    if not c: stats['autres'] += 1; continue
    stats[c] += 1
    ad = p.get('adresseSiegeSocial', {}) or {}
    rue = " ".join(x for x in [ad.get('numeroVoie',''), ad.get('typeVoie',''), ad.get('nomVoie','')] if x)
    out.append({
        "nom": p.get('denomination') or r['commercant'],
        "activite": act.strip(),
        "cat": c,
        "rue": rue,
        "cp": ad.get('codePostal') or r['cp'],
        "ville": ad.get('ville') or r['ville'],
        "dep": r['numerodepartement'],
        "date_jugement": j.get('date', ''),
        "date_pub": r['dateparution'],
        "nature": j.get('nature'),
        "liquidateur": liq(j.get('complementJugement','')),
        "tribunal": r['tribunal'],
        "url": r['url_complete'],
    })
out.sort(key=lambda x: x['date_pub'], reverse=True)
json.dump({"annonces": out, "cats": [[k,l] for k,l,_ in CATS], "stats": stats,
           "periode": [min(r['dateparution'] for r in rows), max(r['dateparution'] for r in rows)]},
          open(sys.argv[2], 'w'), ensure_ascii=False)
print(stats, len(out))
