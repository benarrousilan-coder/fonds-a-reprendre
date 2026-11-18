"""Construit le site statique : une page France, une page par département,
une page par département et par métier, plus sitemap.xml et robots.txt.

Usage : python3 build.py data.json template.html site/
Variables d'environnement :
  BASE_URL   adresse publique du site (pour Google), ex. https://exemple.fr
  ROOT_PATH  chemin du site sur ce domaine, ex. /fonds-a-reprendre/ ou /
"""
import collections, datetime, html, json, os, re, sys, unicodedata

data = json.load(open(sys.argv[1]))
tpl = open(sys.argv[2]).read()
out = sys.argv[3]
BASE_URL = os.environ.get("BASE_URL", "https://benarrousilan-coder.github.io").rstrip("/")
ROOT = os.environ.get("ROOT_PATH", "/fonds-a-reprendre/")
if not ROOT.endswith("/"):
    ROOT += "/"

A = data["annonces"]
CFG = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")))
ED = CFG.get("editeur", {})
PRIX = CFG.get("prix_mensuel", 29)
CATS = [tuple(c) for c in data["cats"]]
LAB = dict(CATS)
PHRASE = {
    "restaurants": "Restaurants, cafés et bars",
    "alimentation": "Boulangeries et commerces alimentaires",
    "beaute": "Salons de coiffure et instituts de beauté",
    "boutiques": "Boutiques et commerces de détail",
}
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]


def fd(s):
    if not s:
        return ""
    y, m, d = s.split("-")
    d = int(d)
    return ("1er" if d == 1 else str(d)) + " " + MOIS[int(m) - 1] + " " + y


def e(s):
    return html.escape(str(s or ""), quote=True)


def slug(s):
    s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def dep_key(code):
    m = re.match(r"(\d+)", code)
    return (int(m.group(1)) if m else 999, code)


deps = collections.OrderedDict()
for a in sorted(A, key=lambda a: dep_key(a["dep"])):
    deps.setdefault(a["dep"], {"nom": a.get("dep_nom") or a["dep"], "items": []})["items"].append(a)
for code, d in deps.items():
    d["path"] = f"{code.lower()}-{slug(d['nom'])}/"

updated = fd(datetime.date.today().isoformat())
periode = f"avis publiés du {fd(data['periode'][0])} au {fd(data['periode'][1])}"


ANALYSE = os.environ.get("ANALYSE", "0") == "1"


def eur(v):
    return f"{int(round(v)):,}".replace(",", "\u202f") + "\u00a0€"


def analyse(a):
    ach, cp, dep = a.get("achat"), a.get("comp_cp"), a.get("comp_dep")
    comp, zone = (cp, f"le code postal {a.get('cp')}") if cp else (dep, f"le département {a.get('dep_nom') or a['dep']}")
    if not ach and not comp:
        return ""
    metier = PHRASE[a["cat"]].lower()
    parts = ['<div class="ana"><div class="ana-h">Analyse du fonds</div>']
    prix = ach.get("prix") if ach else None
    if ach:
        quoi = "Droit au bail acheté" if ach.get("nature") == "droit au bail" else "Fonds acheté"
        montant = f" <strong>{eur(prix)}</strong>" if prix else " (prix non publié)"
        parts.append(f'<p class="ana-l">{quoi}{montant} par la société liquidée, avis du {e(fd(ach["date"]))}. '
                     f'<a href="{e(ach.get("url"))}" target="_blank" rel="noopener">Voir l’avis de vente</a></p>')
    if comp:
        top = max(comp["p75"] * 1.25, (prix or 0) * 1.1, 1)
        step = 10 ** max(3, len(str(int(top))) - 1)
        top = -(-top // step) * step
        x = lambda v: max(0, min(100, v / top * 100))
        mark = (f'<span class="ana-m" style="left:{x(prix):.1f}%" title="Prix d’achat"></span>' if prix else "")
        parts.append(
            f'<div class="ana-bar" role="img" aria-label="Fourchette de prix de {eur(comp["p25"])} à {eur(comp["p75"])}">'
            f'<span class="ana-band" style="left:{x(comp["p25"]):.1f}%;width:{x(comp["p75"]) - x(comp["p25"]):.1f}%"></span>'
            f'<span class="ana-med" style="left:{x(comp["med"]):.1f}%"></span>{mark}</div>'
            f'<div class="ana-ax"><span>0</span><span class="ana-lg"><i class="lg-b"></i>moitié des ventes <i class="lg-m"></i>médiane'
            + (' <i class="lg-p" style="background:var(--c)"></i>prix d’achat' if prix else '') + f'</span><span>{eur(top)}</span></div>'
            f'<p class="ana-l">Dans {e(zone)}, la moitié des {e(metier)} vendus ces 24 derniers mois sont partis entre '
            f'<strong>{eur(comp["p25"])}</strong> et <strong>{eur(comp["p75"])}</strong> '
            f'(prix médian {eur(comp["med"])}, {comp["n"]} ventes publiées au BODACC).</p>')
        if prix:
            if prix < comp["p25"]:
                lec = "Il avait été acheté moins cher que la plupart des fonds comparables."
            elif prix > comp["p75"]:
                lec = "Il avait été acheté plus cher que la plupart des fonds comparables."
            else:
                lec = "Il avait été acheté dans la fourchette habituelle du secteur."
            parts.append(f'<p class="ana-l ana-r">{lec}</p>')
        parts.append('<p class="ana-n">Ces prix concernent des fonds vendus en activité. Un fonds cédé par un liquidateur est souvent à l’arrêt, ce qui pèse sur son prix.</p>')
    parts.append("</div>")
    return "".join(parts)


def card(a):
    adr = ", ".join(x for x in [a.get("rue", ""), f"{a.get('cp', '')} {a.get('ville', '')}".strip()] if x)
    act = a.get("activite", "")
    if len(act) > 170:
        act = act[:170].rsplit(" ", 1)[0] + "…"
    return (f'<article class="avis" style="--c:var(--c-{a["cat"]})">'
            f'<div class="meta"><span class="pill">{e(LAB[a["cat"]])}</span>'
            f'<span>Publié le {e(fd(a["date_pub"]))}</span><span>Jugement du {e(fd(a["date_jugement"]))}</span></div>'
            f'<h3>{e(a["nom"])}</h3><p class="act">{e(act)}</p>'
            f'<dl><dt>Siège</dt><dd>{e(adr)}</dd><dt>Liquidateur</dt><dd>{e(a.get("liquidateur") or "Voir l’avis officiel")}</dd></dl>'
            + (analyse(a) if ANALYSE else "") +
            f'<a class="link" href="{e(a["url"])}" target="_blank" rel="noopener">Voir l’avis officiel au BODACC</a></article>')


def tiles(items, dep=None, current=None):
    cnt = collections.Counter(a["cat"] for a in items)
    parts = []
    for k, lab in CATS:
        inner = f'<div class="n">{cnt.get(k, 0)}</div><div class="l">{e(lab)}</div>'
        cls = "tile on" if k == current else "tile"
        if dep and cnt.get(k):
            parts.append(f'<a class="{cls}" style="--c:var(--c-{k})" href="{ROOT}{deps[dep]["path"]}{k}/">{inner}</a>')
        else:
            parts.append(f'<div class="{cls}" style="--c:var(--c-{k})">{inner}</div>')
    return '<div class="tiles">' + "".join(parts) + "</div>"


def opt_cats(current=None):
    return "".join(f'<option{" selected" if k == current else ""}>{e(l)}</option>' for k, l in CATS)


def opt_deps(current=None):
    opts = "".join(f'<option value="{e(c)}">{e(c)} · {e(d["nom"])}</option>' for c, d in deps.items())
    return opts


def cta():
    pts = ("<ul><li>Chaque lundi, les nouvelles liquidations de votre métier et de vos départements</li>"
           "<li>Pour chaque commerce : le prix d’achat du fonds quand il a été publié, et les prix de vente du quartier</li>"
           "<li>Le liquidateur à contacter, avant l’annonce de vente</li></ul>")
    head = ('<div class="box cta"><h2>Soyez prévenu avant l’annonce de vente</h2>'
            '<p>Un commerce liquidé n’est souvent mis en vente que des semaines plus tard, et les repreneurs n’ont parfois que deux semaines '
            'pour déposer leur offre une fois l’annonce publiée.</p>' + pts +
            f'<div class="price">{PRIX} € <small>/ mois, sans engagement</small></div>')
    if CFG.get("lien_paiement"):
        return head + f'<a class="btn" href="{e(CFG["lien_paiement"])}" target="_blank" rel="noopener">S’abonner à l’alerte</a></div>'
    return head + '<p class="notice">Les abonnements ouvrent très bientôt.</p></div>'


def page(path, title, desc, h1, lede, crumbs, tiles_html, cards_html, before="", sidenav="", cur_cat=None, cur_dep=None, legal=False):
    s = tpl
    rep = {
        "__TITLE__": e(title), "__DESC__": e(desc), "__CANON__": e(BASE_URL + ROOT + path),
        "__ROOT__": ROOT, "__UPDATED__": e(updated), "__CRUMBS__": crumbs, "__H1__": e(h1),
        "__LEDE__": lede, "__TILES__": tiles_html, "__BEFORE__": before, "__CARDS__": cards_html,
        "__SIDENAV__": sidenav, "__CTA__": cta(),
    }
    for k, v in rep.items():
        s = s.replace(k, v)
    if legal:
        s = re.sub(r'<div class="bar">.*?</div></div>', '', s, count=1, flags=re.S)
    dest = os.path.join(out, path, "index.html")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    open(dest, "w").write(s)
    urls.append(BASE_URL + ROOT + path)


urls = []
os.makedirs(out, exist_ok=True)
home = f'<a href="{ROOT}">France</a>'

# Page France
latest = sorted(A, key=lambda a: a["date_pub"], reverse=True)[:60]
dirgrid = ('<h2 class="sec">Par département</h2><ul class="dirgrid">' +
           "".join(f'<li><a href="{ROOT}{d["path"]}"><span>{e(c)} · {e(d["nom"])}</span><span class="c">{len(d["items"])}</span></a></li>'
                   for c, d in deps.items()) + '</ul><h2 class="sec">Les 60 dernières liquidations</h2>')
page("", "Commerces en liquidation à reprendre en France | Le Radar des Reprises",
     f"{len(A)} restaurants, boutiques, boulangeries et salons placés en liquidation judiciaire en France, avec le liquidateur à contacter. Mis à jour chaque lundi.",
     "Commerces mis en liquidation en France",
     f"<strong>{len(A)} commerces</strong> placés en liquidation judiciaire, {periode}. Choisissez votre département pour voir tous les commerces près de chez vous.",
     "France", tiles(A), "".join(card(a) for a in latest), before=dirgrid)

# Pages département et département × métier
for code, d in deps.items():
    items = sorted(d["items"], key=lambda a: a["date_pub"], reverse=True)
    nom = d["nom"]
    side = (f'<div class="box"><h2>Par métier</h2><ul class="deps">' +
            "".join(f'<li><a href="{ROOT}{d["path"]}{k}/">{e(l)}</a><span class="c">{sum(1 for a in items if a["cat"] == k)}</span></li>'
                    for k, l in CATS if any(a["cat"] == k for a in items)) +
            f'</ul><p style="margin:10px 0 0;font-size:14px"><a href="{ROOT}">Tous les départements</a></p></div>')
    page(d["path"], f"Commerces en liquidation : {nom} ({code}) | Le Radar des Reprises",
         f"{len(items)} commerces en liquidation judiciaire dans le département {nom} ({code}) : restaurants, boutiques, boulangeries, salons. Liquidateur à contacter pour chaque fonds.",
         f"Commerces en liquidation : {nom} ({code})",
         f"<strong>{len(items)} commerces</strong> placés en liquidation judiciaire dans le département {e(nom)}, {periode}.",
         f'{home} › {e(nom)}', tiles(items, code), "".join(card(a) for a in items),
         sidenav=side, cur_dep=code)
    for k, lab in CATS:
        sub = [a for a in items if a["cat"] == k]
        if not sub:
            continue
        page(d["path"] + k + "/", f"{PHRASE[k]} en liquidation : {nom} ({code}) | Le Radar des Reprises",
             f"{len(sub)} {PHRASE[k].lower()} en liquidation judiciaire dans le département {nom} ({code}), avec le liquidateur à contacter pour racheter le fonds.",
             f"{PHRASE[k]} en liquidation : {nom} ({code})",
             f"<strong>{len(sub)} commerces</strong> de ce métier placés en liquidation judiciaire dans le département {e(nom)}, {periode}.",
             f'{home} › <a href="{ROOT}{d["path"]}">{e(nom)}</a> › {e(lab)}',
             tiles(items, code, k), "".join(card(a) for a in sub),
             sidenav=side, cur_cat=k, cur_dep=code)

# Pages légales
def v(x, defaut="[à compléter]"):
    return e(x) if x else defaut


LEGAL = {
 "mentions-legales": ("Mentions légales", f"""
<h2>Éditeur du site</h2>
<p>{v(ED.get("nom"))}, {v(ED.get("statut"))}<br>SIRET : {v(ED.get("siret"))}<br>Adresse : {v(ED.get("adresse"))}<br>Contact : {v(ED.get("email"))}</p>
<p>Directeur de la publication : {v(ED.get("nom"))}.</p>
<h2>Hébergement</h2>
<p>GitHub Inc. (GitHub Pages), 88 Colin P Kelly Jr Street, San Francisco, CA 94107, États-Unis.</p>
<h2>Source des données</h2>
<p>Les annonces proviennent du Bulletin officiel des annonces civiles et commerciales (BODACC), publié par la Direction de l’information légale et administrative (DILA) et réutilisé sous Licence Ouverte 2.0. Les données sont mises à jour chaque semaine ; la date de mise à jour figure en haut de chaque page. Le Radar des Reprises n’est pas affilié à la DILA ni au BODACC.</p>
<p>Seules des sociétés (personnes morales) sont présentées. Les informations sont fournies à titre indicatif et ne constituent pas un conseil juridique, financier ou d’investissement.</p>"""),
 "cgv": ("Conditions générales de vente", f"""
<h2>Objet</h2>
<p>Les présentes conditions régissent l’abonnement « Alerte » du site Le Radar des Reprises, édité par {v(ED.get("nom"))}. L’abonnement donne accès à un e-mail hebdomadaire listant les nouvelles liquidations judiciaires de commerces correspondant aux critères choisis (métier, départements), accompagnées d’une analyse indicative fondée sur des données publiques.</p>
<h2>Prix et paiement</h2>
<p>L’abonnement coûte {PRIX} € par mois. Il est payé par carte bancaire via Stripe, à la souscription puis chaque mois à la même date.</p>
<h2>Durée et résiliation</h2>
<p>L’abonnement est sans engagement. Il peut être résilié à tout moment depuis le lien « gérer mon abonnement » présent dans chaque e-mail ; la résiliation prend effet à la fin de la période mensuelle en cours.</p>
<h2>Droit de rétractation</h2>
<p>Le client consommateur dispose d’un délai de 14 jours à compter de la souscription pour se rétracter et être remboursé, en écrivant à {v(ED.get("email"))}.</p>
<h2>Nature du service et responsabilité</h2>
<p>Les informations proviennent de publications officielles et sont transmises en l’état. Elles peuvent comporter des erreurs ou être incomplètes ; une liquidation ne garantit pas la mise en vente du fonds. Les prix indiqués sont des repères statistiques, non une évaluation. L’éditeur ne fournit aucun conseil juridique ou financier et ne peut être tenu responsable des décisions prises sur la base de ces informations.</p>
<h2>Contact et litiges</h2>
<p>Pour toute question : {v(ED.get("email"))}. Les présentes conditions sont soumises au droit français.</p>"""),
 "confidentialite": ("Politique de confidentialité", f"""
<h2>Données collectées</h2>
<p>Lors de l’abonnement : adresse e-mail, critères d’alerte (métier, départements) et informations de paiement. Les données de carte bancaire sont traitées uniquement par Stripe et ne sont jamais transmises à l’éditeur.</p>
<h2>Utilisation</h2>
<p>Ces données servent uniquement à envoyer l’alerte hebdomadaire et à gérer l’abonnement. Elles ne sont ni vendues ni louées.</p>
<h2>Prestataires</h2>
<p>Stripe (paiement et gestion des abonnements) et Brevo (envoi des e-mails) agissent comme sous-traitants. Le site est hébergé par GitHub Pages.</p>
<h2>Durée de conservation</h2>
<p>Les données sont conservées pendant la durée de l’abonnement, puis le temps nécessaire aux obligations comptables et légales.</p>
<h2>Vos droits</h2>
<p>Vous pouvez accéder à vos données, les rectifier ou en demander la suppression en écrivant à {v(ED.get("email"))}. Vous pouvez aussi saisir la CNIL (cnil.fr).</p>
<h2>Données publiées sur le site</h2>
<p>Le site ne présente que des sociétés, à partir des annonces officielles du BODACC. Pour toute demande concernant une fiche, écrivez à {v(ED.get("email"))}.</p>"""),
}
for slugp, (titre, corps) in LEGAL.items():
    page(slugp + "/", f"{titre} | Le Radar des Reprises", titre, titre, "", f'{home} › {e(titre)}', "", "",
         before=f'<div class="legal">{corps}</div>', legal=True)

today = datetime.date.today().isoformat()
open(os.path.join(out, "sitemap.xml"), "w").write(
    '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
    "".join(f"  <url><loc>{html.escape(u)}</loc><lastmod>{today}</lastmod></url>\n" for u in urls) + "</urlset>\n")
open(os.path.join(out, "robots.txt"), "w").write(f"User-agent: *\nAllow: /\nSitemap: {BASE_URL}{ROOT}sitemap.xml\n")
print(f"{len(urls)} pages, {len(deps)} départements, {len(A)} commerces")
