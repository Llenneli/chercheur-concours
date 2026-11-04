import streamlit as st
from datetime import date
from urllib.request import Request, urlopen
from urllib.parse import urljoin, quote_plus, urlparse
from html.parser import HTMLParser
import re
import csv
import io

st.set_page_config(page_title="Concours Belgique V10", page_icon="🏆")
st.title("🏆 Mon chercheur de concours belges")

SOURCES = [
    ("Concours Belgique", "https://www.echantillonsgratuits.be/concours-belgique", ""),
    ("Voyages Belgique", "https://www.echantillonsgratuits.be/concours-belgique/concours-voyages", "Voyages"),
    ("Mitspiel Voyages", "https://mitspiel.be/gagner-un-voyage", "Voyages")
]
CATEGORIES = ["Toutes", "Voyages", "Voitures", "Argent",
              "High-tech", "Alimentation", "Beauté", "Maison",
              "Culture", "Divers"]
MOIS = {"janvier": 1, "février": 2, "fevrier": 2, "mars": 3,
        "avril": 4, "mai": 5, "juin": 6, "juillet": 7,
        "août": 8, "aout": 8, "septembre": 9, "octobre": 10,
        "novembre": 11, "décembre": 12, "decembre": 12}

class AnalyseHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.texte = []
        self.liens = []
        self.actif = None
        self.masquer = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.masquer += 1
        if tag == "a" and not self.masquer:
            self.actif = {"url": dict(attrs).get("href", ""), "titre": ""}

    def handle_data(self, data):
        if not self.masquer:
            self.texte.append(data)
            if self.actif is not None:
                self.actif["titre"] += data

    def handle_endtag(self, tag):
        if tag == "a" and self.actif is not None:
            self.liens.append(self.actif)
            self.actif = None
        if tag in ("script", "style"):
            self.masquer = max(0, self.masquer - 1)

def lire(url):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=12) as rep:
        html = rep.read(1200000).decode("utf-8", errors="replace")
    p = AnalyseHTML()
    p.feed(html)
    return p

def categorie(titre, source):
    if source == "Voyages":
        return "Voyages"
    t = titre.lower()
    mots = {
        "Voyages": ["voyage", "séjour", "week-end", "vacances", "disneyland", "hôtel"],
        "Voitures": ["voiture", "véhicule", "auto"],
        "Argent": ["carte cadeau", "bon d'achat", "cash"],
        "High-tech": ["console", "ps5", "nintendo", "iphone", "smartphone"],
        "Alimentation": ["chocolat", "pizza", "restaurant", "café"],
        "Beauté": ["parfum", "cosmétique", "maquillage"],
        "Maison": ["aspirateur", "meuble", "cuisine"],
        "Culture": ["cinéma", "concert", "livre", "spectacle"]
    }
    for cat, termes in mots.items():
        if any(m in t for m in termes):
            return cat
    return "Divers"

def trouver_date(texte):
    texte = re.sub(r"\s+", " ", texte)
    motif = (r"(?:date limite|expire le|jusqu.au|clôture|fin du concours)"
             r"\s*:?\s*(?:le\s*)?(\d{1,2})\s+"
             r"([a-zéûôè]+)\s+(20\d{2})")
    for m in re.finditer(motif, texte, re.I):
        mois = MOIS.get(m.group(2).lower())
        if mois:
            try:
                return date(int(m.group(3)), mois, int(m.group(1)))
            except ValueError:
                pass
    return None



def date_dans_titre(titre):
    """Lire une date en fin de titre : 19/11, 30l11, 08I11, 28l02/2027."""
    # Les séparateurs 'l', 'I' et '|' sont courants sur ce forum.
    motif = r"(?<!\d)(\d{1,2})\s*[/lI|]\s*(\d{1,2})(?:\s*[/lI|]\s*(20\d{2}))?(?!\d)"
    resultats = list(re.finditer(motif, titre))
    if not resultats:
        return None
    for m in reversed(resultats):
        jour, mois = int(m.group(1)), int(m.group(2))
        annee = int(m.group(3)) if m.group(3) else None
        try:
            date(annee or date.today().year, mois, jour)
        except ValueError:
            continue
        texte = f"{jour:02d}/{mois:02d}"
        if annee is not None:
            texte += f"/{annee}"
        return texte
    return None

FDC_SECTIONS = [
    ("Fou de Concours — Belgique",
     "https://www.foudeconcours.com/forum/concours/concours-belges-pour-les-belges"),
]

@st.cache_data(ttl=3600)
def chercher_foudeconcours():
    resultats, erreurs = [], []
    vus = set()
    for source, adresse in FDC_SECTIONS:
        try:
            page = lire(adresse)
            prefixe = urlparse(adresse).path.rstrip("/") + "/"
            for a in page.liens:
                titre = " ".join(a["titre"].split())
                lien = urljoin(adresse, a["url"])
                path = urlparse(lien).path.rstrip("/")
                reste = path[len(prefixe):] if path.startswith(prefixe) else ""
                # Garder les discussions, pas les menus, profils ou catégories.
                if not re.match(r"^\d+-[^/]+$", reste):
                    continue
                if not 12 <= len(titre) <= 190 or lien in vus:
                    continue
                vus.add(lien)
                resultats.append({
                    "titre": titre, "url": lien,
                    "categorie": categorie(titre, ""),
                    "source": source,
                    "date_non_confirmee": True,
                    "date_titre": date_dans_titre(titre),
                })
        except Exception:
            erreurs.append(source)
    return resultats[:60], erreurs

@st.cache_data(ttl=3600)
def chercher():
    liste, erreurs, vus = [], [], set()
    for source, adresse, cat in SOURCES:
        try:
            page = lire(adresse)
            for a in page.liens:
                titre = " ".join(a["titre"].split())
                lien = urljoin(adresse, a["url"])
                chemin = urlparse(lien).path.lower()
                if not 15 <= len(titre) <= 190:
                    continue
                if "echantillonsgratuits" in adresse:
                    if "/concours-belgique/" not in chemin:
                        continue
                    if chemin.endswith("/concours-voyages"):
                        continue
                elif "/concours/" not in chemin:
                    continue
                if not re.search("gagnez|gagner|concours|remportez|séjour|voyage", titre, re.I):
                    continue
                if lien in vus:
                    continue
                vus.add(lien)
                liste.append({"titre": titre, "url": lien,
                              "categorie": categorie(titre, cat),
                              "source": source})
        except Exception:
            erreurs.append(source)
    forum, erreurs_forum = chercher_foudeconcours()
    liste.extend(c for c in forum if c["url"] not in {x["url"] for x in liste})
    return liste[:140], erreurs + erreurs_forum

@st.cache_data(ttl=3600)
def date_concours(url):
    try:
        return trouver_date(" ".join(lire(url).texte))
    except Exception:
        return None

if "mes_concours" not in st.session_state:
    st.session_state.mes_concours = []
if "participations" not in st.session_state:
    st.session_state.participations = []
if "fichier_importe" not in st.session_state:
    st.session_state.fichier_importe = None

CHAMPS_CARNET = [
    "concours", "url", "source", "date_participation",
    "nombre_envoye", "question_subsidiaire", "notes"
]

def exporter_carnet(lignes):
    tampon = io.StringIO()
    ecrivain = csv.DictWriter(tampon, fieldnames=CHAMPS_CARNET)
    ecrivain.writeheader()
    ecrivain.writerows(lignes)
    return tampon.getvalue().encode("utf-8-sig")


tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["🔎 Recherche", "🔗 Mes concours", "💡 Réponses", "🎯 Estimation", "📒 Participations"]
)

with tab1:
    st.subheader("Concours belges, Fou de Concours et dates limites")
    st.caption("Fou de Concours est un forum : les dates et l’accès aux discussions peuvent nécessiter une vérification.")
    cat = st.selectbox("Catégorie", CATEGORIES)
    mots = st.text_input("Filtrer par mot-clé")
    filtre = st.checkbox("Masquer les concours expirés", value=True)
    if st.button("🔄 Actualiser"):
        chercher.clear()
        chercher_foudeconcours.clear()
        date_concours.clear()
    liste, erreurs = chercher()
    liste = [c for c in liste if
             (cat == "Toutes" or c["categorie"] == cat)
             and (not mots or mots.lower() in c["titre"].lower())]
    if erreurs:
        st.warning("Sources indisponibles : " + ", ".join(erreurs))
    st.write(len(liste), "concours à examiner")
    for i, c in enumerate(liste):
        with st.container(border=True):
            limite = None if c.get("date_non_confirmee") else date_concours(c["url"])
            if filtre and limite and limite < date.today():
                continue
            st.write("**" + c["titre"] + "**")
            st.caption(c["categorie"] + " — " + c["source"])
            if limite:
                st.write("📅 Date limite :", limite.strftime("%d/%m/%Y"))
                st.write("🟢 Date non dépassée" if limite >= date.today() else "🔴 Date dépassée")
            else:
                if c.get("date_titre"):
                    st.write("📅 Date dans le titre : " + c["date_titre"] + " — à confirmer dans le règlement")
                else:
                    st.write("🟡 Date à vérifier" + (" (forum : vérifier dans le règlement)" if c.get("date_non_confirmee") else ""))
            st.link_button("Voir le concours", c["url"], key=f"lien_{i}")
    st.caption("Une date non dépassée ne garantit pas que le concours est encore ouvert. Vérifie le règlement.")

with tab2:
    st.subheader("Ajouter mes concours")
    nom = st.text_input("Nom du concours")
    url = st.text_input("Adresse du concours")
    fin = st.date_input("Date limite vérifiée")
    if st.button("➕ Ajouter"):
        if nom.strip() and url.startswith("https://"):
            st.session_state.mes_concours.append((nom, url, fin))
            st.success("Concours ajouté pour cette session.")
        else:
            st.warning("Indique un nom et un lien https://")
    for i, (n, u, d) in enumerate(st.session_state.mes_concours):
        st.write("**" + n + "** — " + d.strftime("%d/%m/%Y"))
        st.link_button("Ouvrir", u, key=f"perso_{i}")
    st.caption("La liste personnelle n'est pas sauvegardée durablement.")

with tab3:
    st.subheader("Aide aux réponses")
    q = st.text_area("Question du concours")
    if q.strip():
        st.link_button("Vérifier sur Internet",
            "https://www.google.com/search?q=" + quote_plus(q))


with tab4:
    st.subheader("🎯 Aide aux questions subsidiaires")
    st.info("Ces nombres sont des estimations fondées sur des hypothèses, pas des données réelles du concours.")
    st.markdown("#### 1. Choisir le concours")
    concours_disponibles, erreurs_estimation = chercher()
    concours_disponibles = list(concours_disponibles)
    for nom_perso, url_perso, date_perso in st.session_state.mes_concours:
        concours_disponibles.append({
            "titre": nom_perso, "url": url_perso,
            "source": "Mes concours", "date_verifiee": date_perso
        })
    options_concours = ["— Choisir un concours —"] + [
        f"{i + 1}. {c['titre']} — {c['source']}"
        for i, c in enumerate(concours_disponibles)
    ]
    selection = st.selectbox(
        "Sélectionne ton concours dans la liste",
        range(len(options_concours)),
        format_func=lambda i: options_concours[i],
        key="sub_concours"
    )
    concours_choisi = concours_disponibles[selection - 1] if selection else None
    if concours_choisi:
        st.write("**Concours choisi :**", concours_choisi["titre"])
        st.caption("Source : " + concours_choisi["source"])
        st.link_button("🔗 Ouvrir ce concours", concours_choisi["url"])
        if concours_choisi.get("date_verifiee"):
            st.write("📅 Date enregistrée :", concours_choisi["date_verifiee"].strftime("%d/%m/%Y"))
        elif concours_choisi.get("date_titre"):
            st.write("📅 Date dans le titre :", concours_choisi["date_titre"], "— à confirmer")
        else:
            st.caption("Date limite à consulter dans le règlement.")
        st.caption("Le titre et le lien sont repris automatiquement. La question subsidiaire reste à coller si tu veux l'analyser.")
    else:
        st.caption("Choisis d'abord un concours pour savoir auquel correspond ton estimation.")
    st.markdown("#### 2. Préparer la réponse")
    choix_sub = st.radio(
        "Choisis ton aide",
        ["🎲 Proposer un nombre", "📋 Coller ma question"],
        horizontal=False, key="choix_sub"
    )
    if choix_sub == "📋 Coller ma question":
        question_sub = st.text_area(
            "Copie ici la question subsidiaire complète",
            placeholder="Exemple : Combien de participations valables recevrons-nous avant le 30 novembre ?",
            height=110, key="question_sub"
        )
        if question_sub.strip():
            t = question_sub.casefold()
            nb = bool(re.search(r"combien|nombre|total|quantité", t))
            participants = bool(re.search(
                r"particip|réponse|inscri|joueur|bulletin|formulaire|personne|candidat",
                t
            ))
            if nb and participants:
                st.success("Cette question semble concerner le nombre de participations ou de réponses.")
                st.write("Tu peux utiliser l'estimation ci-dessous, puis ajuster les hypothèses.")
            elif nb:
                st.warning(
                    "Cette question demande un nombre, mais pas forcément un nombre de participants. "
                    "L'estimation ci-dessous n'est valable que pour des participations ou des réponses. "
                    "Pour une quantité différente (poids, ventes, objets...), il faut des données adaptées."
                )
            else:
                st.warning(
                    "Je ne peux pas reconnaître automatiquement le type de cette question. "
                    "Vérifie si elle demande bien un nombre de participations avant d'utiliser le calcul."
                )
        else:
            st.caption("Colle ta question pour savoir si cette estimation convient.")
    else:
        st.write("Choisis quelques hypothèses : l'application te proposera un nombre.")

    debut_sub = st.date_input("Date de début du concours", value=date.today(), key="sub_debut")
    fin_sub = st.date_input(
        "Date de fin du concours",
        value=date.fromordinal(date.today().toordinal() + 14),
        key="sub_fin"
    )
    audience = st.selectbox(
        "Popularité supposée du concours",
        ["Petit concours", "Concours moyen", "Concours très connu"],
        index=1, key="sub_audience"
    )
    visiteurs_supposes = {
        "Petit concours": 200,
        "Concours moyen": 1000,
        "Concours très connu": 5000,
    }[audience]
    st.caption(
        f"Hypothèse pour ce choix : {visiteurs_supposes:,} visiteurs par jour."
        " Ce n'est pas une mesure réelle."
    )
    participation = st.slider(
        "Pourcentage supposé des visiteurs qui participent",
        0.1, 10.0, 2.0, step=0.1, key="sub_taux"
    )
    if st.button("🏆 Proposer mon nombre", key="sub_calcul"):
        jours = (fin_sub - debut_sub).days + 1
        if not concours_choisi:
            st.warning("Choisis d’abord un concours dans la liste.")
        elif jours < 1:
            st.error("La date de fin doit être après la date de début.")
        elif choix_sub == "📋 Coller ma question" and not question_sub.strip():
            st.warning("Colle d'abord ta question subsidiaire.")
        elif choix_sub == "📋 Coller ma question" and not (
            re.search(r"combien|nombre|total|quantité", question_sub.casefold())
            and re.search(r"particip|réponse|inscri|joueur|bulletin|formulaire|personne|candidat", question_sub.casefold())
        ):
            st.warning("Je ne propose pas de nombre : il faut d'abord vérifier la nature de cette question.")
        else:
            estimation = round(jours * visiteurs_supposes * participation / 100)
            proposition = max(1, estimation + 7)
            st.metric("Nombre proposé (estimation)", f"{proposition:,}".replace(",", " "))
            st.write(f"Durée : {jours} jours")
            st.write("Estimation centrale avant ajustement :", f"{estimation:,}".replace(",", " "))
            st.write("Scénario bas :", round(estimation / 2))
            st.write("Scénario haut :", estimation * 2)
            st.caption("Le petit ajustement de +7 ne donne aucun avantage statistique prouvé.")
            st.warning(
                "Aucune donnée sur les participations réelles n'est disponible ici. "
                "Ce résultat est une simulation et peut être très éloigné de la bonne réponse."
            )

    st.markdown("#### 3. Enregistrer ma participation")
    if concours_choisi:
        st.caption("Écris le nombre que tu as réellement envoyé au concours.")
        nombre_envoye = st.text_input("Nombre envoyé", key="sub_nombre_envoye")
        date_envoi = st.date_input("Date de participation", value=date.today(), key="sub_date_envoi")
        notes_sub = st.text_area("Notes (facultatif)", key="sub_notes")
        if st.button("💾 Enregistrer ma participation", key="sub_sauver"):
            st.session_state.participations.append({
                "concours": concours_choisi["titre"],
                "url": concours_choisi["url"],
                "source": concours_choisi["source"],
                "date_participation": date_envoi.isoformat(),
                "nombre_envoye": nombre_envoye.strip(),
                "question_subsidiaire": st.session_state.get("question_sub", "").strip() if choix_sub == "📋 Coller ma question" else "",
                "notes": notes_sub.strip(),
            })
            st.success("Ajoutée à ton carnet ! Télécharge la sauvegarde dans l'onglet Participations.")
    else:
        st.caption("Choisis d'abord un concours pour enregistrer ta participation.")


with tab5:
    st.subheader("📒 Mon carnet de participations")
    st.warning("Le carnet n'est pas conservé après un redémarrage de Streamlit. Télécharge ta sauvegarde CSV après chaque changement, puis importe-la à la prochaine visite. Ne publie pas ce fichier sur GitHub.")
    sauvegarde = st.file_uploader("📂 Importer mon fichier de sauvegarde CSV", type=["csv"], key="carnet_upload")
    if sauvegarde is not None:
        signature = (sauvegarde.name, sauvegarde.size, sauvegarde.getvalue()[:100])
        if signature != st.session_state.fichier_importe:
            try:
                lecteur = csv.DictReader(io.StringIO(sauvegarde.getvalue().decode("utf-8-sig")))
                if not lecteur.fieldnames or not set(CHAMPS_CARNET).issubset(lecteur.fieldnames):
                    st.error("Ce fichier ne correspond pas au format du carnet.")
                else:
                    existants = {tuple(p.get(k, "") for k in CHAMPS_CARNET) for p in st.session_state.participations}
                    for ligne in lecteur:
                        entree = {k: ligne.get(k, "") or "" for k in CHAMPS_CARNET}
                        cle = tuple(entree[k] for k in CHAMPS_CARNET)
                        if cle not in existants:
                            st.session_state.participations.append(entree)
                            existants.add(cle)
                    st.session_state.fichier_importe = signature
                    st.success("Carnet importé !")
            except (UnicodeError, csv.Error, ValueError):
                st.error("Impossible de lire ce fichier CSV.")
    carnet = st.session_state.participations
    st.write(f"**{len(carnet)} participation(s) enregistrée(s)**")
    filtre = st.text_input("🔎 Rechercher un concours dans le carnet", key="carnet_filtre")
    for i in range(len(carnet)-1, -1, -1):
        p = carnet[i]
        if filtre and filtre.casefold() not in (p["concours"] + " " + p["nombre_envoye"]).casefold():
            continue
        with st.container(border=True):
            st.write("**" + p["concours"] + "**")
            st.caption("Participé le " + p["date_participation"] + " — " + p["source"])
            st.write("Nombre envoyé :", p["nombre_envoye"] or "Non indiqué")
            if p["question_subsidiaire"]:
                st.write("Question :", p["question_subsidiaire"])
            if p["notes"]:
                st.write("Notes :", p["notes"])
            if p["url"].startswith("https://"):
                st.link_button("Voir le concours", p["url"], key=f"carnet_lien_{i}")
            if st.button("🗑️ Supprimer", key=f"carnet_suppr_{i}"):
                st.session_state.participations.pop(i)
                st.rerun()
    st.download_button(
        "⬇️ Télécharger ma sauvegarde CSV",
        data=exporter_carnet(carnet),
        file_name="mes_participations_concours.csv",
        mime="text/csv",
        key="carnet_export"
    )
    st.caption("Télécharge un nouveau fichier après chaque ajout ou suppression.")
