"""Envoie chaque semaine l'alerte aux abonnés.

Les abonnés et leurs choix viennent de Stripe (abonnements actifs + champs
personnalisés du lien de paiement : « metier » et « departements »).
Les e-mails partent par Brevo.

Usage : python3 alertes.py data.json
Variables d'environnement :
  STRIPE_KEY   clé Stripe restreinte (lecture : Checkout Sessions, Subscriptions)
  BREVO_KEY    clé API Brevo
  SENDER_EMAIL adresse d'expédition validée dans Brevo
  SITE_URL     adresse du site (liens dans l'e-mail)
  PORTAL_URL   lien du portail client Stripe (gérer / résilier l'abonnement)
  DRY_RUN=1    n'envoie rien : écrit les e-mails dans le dossier apercu_emails/
  FAKE_SUBS    (test) JSON d'abonnés fictifs à la place de Stripe
"""
import base64, datetime, html, json, os, re, sys, time, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    CFG = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")))
except (OSError, ValueError):
    CFG = {}
os.environ.setdefault("SENDER_EMAIL", CFG.get("expediteur", ""))
os.environ.setdefault("PORTAL_URL", CFG.get("portail_client", ""))

METIERS = {"restaurants": "Restaurants, cafés et bars", "alimentation": "Boulangeries et commerces alimentaires",
           "beaute": "Coiffure et beauté", "boutiques": "Boutiques et commerce de détail", "tous": "Tous les commerces"}
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]


def fd(s):
    if not s:
        return ""
    y, m, d = s.split("-")
    d = int(d)
    return ("1er" if d == 1 else str(d)) + " " + MOIS[int(m) - 1] + " " + y


def eur(v):
    return f"{int(round(v)):,}".replace(",", " ") + " €"


def e(s):
    return html.escape(str(s or ""), quote=True)


# ---------- Abonnés ----------

def stripe_get(path, params):
    url = "https://api.stripe.com/v1/" + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url)
    tok = base64.b64encode((os.environ["STRIPE_KEY"] + ":").encode()).decode()
    req.add_header("Authorization", "Basic " + tok)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def norm_metier(v):
    v = (v or "").lower()
    for k in METIERS:
        if k in v:
            return k
    if "coiff" in v or "beaut" in v:
        return "beaute"
    if "boulang" in v or "aliment" in v:
        return "alimentation"
    if "boutique" in v or "détail" in v or "detail" in v:
        return "boutiques"
    if "restau" in v or "bar" in v or "caf" in v:
        return "restaurants"
    return "tous"


def norm_deps(v):
    out = []
    for m in re.finditer(r"\b(2[ABab]|97[1-6]|\d{1,2})\b", v or ""):
        c = m.group(1).upper()
        c = c.zfill(2) if c.isdigit() and len(c) < 3 else c
        if c not in out:
            out.append(c)
    return out


def abonnes():
    if os.environ.get("FAKE_SUBS"):
        return json.loads(os.environ["FAKE_SUBS"])
    subs, after = [], None
    while True:
        p = {"status": "active", "limit": 100}
        if after:
            p["starting_after"] = after
        page = stripe_get("subscriptions", p)
        subs += page["data"]
        if not page.get("has_more"):
            break
        after = page["data"][-1]["id"]
    out = []
    for s in subs:
        sess = stripe_get("checkout/sessions", {"subscription": s["id"], "limit": 1})["data"]
        if not sess:
            continue
        cs = sess[0]
        fields = {}
        for f in cs.get("custom_fields") or []:
            val = (f.get("dropdown") or {}).get("value") or (f.get("text") or {}).get("value") or ""
            lab = ((f.get("label") or {}).get("custom") or "").lower() + " " + (f.get("key") or "").lower()
            if "tier" in lab:          # « Métier » / metier
                fields["metier"] = val
            elif "part" in lab:        # « Départements » / departements
                fields["departements"] = val
        email = (cs.get("customer_details") or {}).get("email")
        if email:
            out.append({"email": email, "metier": norm_metier(fields.get("metier")),
                        "deps": norm_deps(fields.get("departements"))})
    return out


# ---------- Contenu ----------

def fiche(a):
    ach, comp = a.get("achat"), a.get("comp_cp") or a.get("comp_dep")
    zone = f"le code postal {a.get('cp')}" if a.get("comp_cp") else f"le département {a.get('dep_nom')}"
    adr = ", ".join(x for x in [a.get("rue"), f"{a.get('cp', '')} {a.get('ville', '')}".strip()] if x)
    L = [f'<tr><td style="padding:16px 0;border-top:1px solid #DCE1E8">',
         f'<div style="font:600 12px Arial,sans-serif;color:#5B6678">{e(METIERS.get(a["cat"], ""))} · jugement du {e(fd(a["date_jugement"]))}</div>',
         f'<div style="font:700 19px Arial,sans-serif;color:#16233B;margin:4px 0">{e(a["nom"])}</div>',
         f'<div style="font:14px Arial,sans-serif;color:#16233B">{e(adr)}</div>',
         f'<div style="font:14px Arial,sans-serif;color:#16233B;margin-top:6px"><b>Liquidateur à contacter :</b> {e(a.get("liquidateur") or "voir l’avis officiel")}</div>']
    if ach or comp:
        L.append('<div style="background:#E8EFFB;border-radius:6px;padding:10px 12px;margin-top:10px;font:14px Arial,sans-serif;color:#16233B">')
        L.append('<div style="font:700 12px Arial,sans-serif;color:#1F5FD1;letter-spacing:.4px;margin-bottom:4px">ANALYSE DU FONDS</div>')
        prix = ach.get("prix") if ach else None
        if ach:
            quoi = "Droit au bail acheté" if ach.get("nature") == "droit au bail" else "Fonds acheté"
            L.append(f'<div>{quoi} <b>{eur(prix) if prix else "(prix non publié)"}</b> par la société liquidée (avis du {e(fd(ach["date"]))}).</div>')
        if comp:
            L.append(f'<div style="margin-top:4px">Dans {e(zone)}, la moitié des fonds de ce métier vendus ces 24 derniers mois sont partis entre '
                     f'<b>{eur(comp["p25"])}</b> et <b>{eur(comp["p75"])}</b> (médiane {eur(comp["med"])}, {comp["n"]} ventes).</div>')
            if prix:
                lec = ("moins cher que la plupart des fonds comparables" if prix < comp["p25"] else
                       "plus cher que la plupart des fonds comparables" if prix > comp["p75"] else
                       "dans la fourchette habituelle du secteur")
                L.append(f'<div style="margin-top:4px"><b>Il avait été acheté {lec}.</b></div>')
        L.append("</div>")
    L.append(f'<div style="margin-top:8px;font:14px Arial,sans-serif"><a href="{e(a["url"])}" style="color:#1F5FD1">Voir l’avis officiel au BODACC</a></div></td></tr>')
    return "".join(L)


def email_html(sub, items, semaine):
    site = os.environ.get("SITE_URL", "")
    portal = os.environ.get("PORTAL_URL", "")
    deps = ", ".join(sub["deps"]) if sub["deps"] else "toute la France"
    head = (f'<div style="font:700 20px Arial,sans-serif;color:#16233B">Le Radar <span style="color:#1F5FD1">des Reprises</span></div>'
            f'<div style="font:14px Arial,sans-serif;color:#5B6678;margin:6px 0 14px">Votre alerte de la semaine du {e(semaine)} · '
            f'{e(METIERS[sub["metier"]])} · {e(deps)}</div>')
    if items:
        intro = (f'<p style="font:15px Arial,sans-serif;color:#16233B">{len(items)} nouveau{"x" if len(items) > 1 else ""} commerce{"s" if len(items) > 1 else ""} '
                 f'placé{"s" if len(items) > 1 else ""} en liquidation cette semaine. Le liquidateur n’a en général pas encore publié l’annonce de vente : '
                 f'c’est le moment de l’appeler.</p>')
    else:
        intro = '<p style="font:15px Arial,sans-serif;color:#16233B">Aucune nouvelle liquidation dans vos critères cette semaine. Nous continuons à surveiller pour vous.</p>'
    body = "".join(fiche(a) for a in items)
    foot = ('<p style="font:12px Arial,sans-serif;color:#5B6678;margin-top:18px">Prix du marché : ventes de fonds en activité publiées au BODACC. '
            'Un fonds cédé par un liquidateur est souvent à l’arrêt, ce qui pèse sur son prix. Adresse affichée : siège social. '
            'Ces informations ne constituent pas un conseil juridique ou financier.</p>'
            + (f'<p style="font:12px Arial,sans-serif;color:#5B6678">Changer vos critères ou résilier : <a href="{e(portal)}" style="color:#1F5FD1">gérer mon abonnement</a>.'
               + (f' · <a href="{e(site)}" style="color:#1F5FD1">le site</a>' if site else "") + "</p>" if portal else ""))
    return (f'<div style="max-width:640px;margin:0 auto;padding:20px">{head}{intro}'
            f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0">{body}</table>{foot}</div>')


def selection(A, sub, depuis):
    return [a for a in A
            if a["date_pub"] >= depuis
            and (not sub["deps"] or a["dep"] in sub["deps"])
            and (sub["metier"] == "tous" or a["cat"] == sub["metier"])]


def envoyer(to, sujet, contenu):
    payload = {"sender": {"name": "Le Radar des Reprises", "email": os.environ["SENDER_EMAIL"]},
               "to": [{"email": to}], "subject": sujet, "htmlContent": contenu}
    req = urllib.request.Request("https://api.brevo.com/v3/smtp/email", data=json.dumps(payload).encode(), method="POST")
    req.add_header("api-key", os.environ["BREVO_KEY"])
    req.add_header("content-type", "application/json")
    req.add_header("accept", "application/json")
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status


def main():
    data = json.load(open(sys.argv[1]))
    A = data["annonces"]
    today = datetime.date.today()
    depuis = (today - datetime.timedelta(days=7)).isoformat()
    semaine = fd(today.isoformat())
    dry = os.environ.get("DRY_RUN") == "1"
    subs = abonnes()
    print(f"{len(subs)} abonné(s) actif(s)")
    if dry:
        os.makedirs("apercu_emails", exist_ok=True)
    ok = err = 0
    for i, sub in enumerate(subs):
        items = selection(A, sub, depuis)
        n = len(items)
        sujet = (f"{n} nouvelle{'s' if n > 1 else ''} liquidation{'s' if n > 1 else ''} · {METIERS[sub['metier']]}" if n
                 else "Votre alerte de la semaine · rien de nouveau")
        contenu = email_html(sub, items, semaine)
        if dry:
            open(f"apercu_emails/{i:03d}.html", "w").write(f"<!DOCTYPE html><meta charset=utf-8><title>{e(sujet)}</title>{contenu}")
            print(f"[test] {sub['email'][:2]}*** → {n} fiche(s) · {sujet}")
            continue
        try:
            envoyer(sub["email"], sujet, contenu)
            ok += 1
        except Exception as ex:
            err += 1
            print("Échec d'envoi :", sub["email"][:2] + "***", ex)
        time.sleep(0.2)
    if not dry:
        print(f"Envois réussis : {ok}, échecs : {err}")
        if err:
            sys.exit(1)


if __name__ == "__main__":
    main()
