import streamlit as st
from datetime import date
from urllib.request import Request, urlopen
from urllib.parse import urljoin, quote_plus, urlparse
from html.parser import HTMLParser
import re

st.set_page_config(page_title="Concours Belgique V8", page_icon="🏆")
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

tab1, tab2, tab3, tab4 = st.tabs(
    ["🔎 Recherche", "🔗 Mes concours", "💡 Réponses", "🎯 Estimation"]
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
        if jours < 1:
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
