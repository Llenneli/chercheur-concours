import streamlit as st
import re
from datetime import date
from html.parser import HTMLParser
from urllib.request import Request, urlopen
from urllib.parse import urljoin, urlparse, quote_plus

st.set_page_config(page_title="Concours Belgique", page_icon="🏆")
st.title("🏆 Mon chercheur de concours belges")

SOURCE = "https://www.echantillonsgratuits.be/concours-belgique"

class Lecteur(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.blocks = []

    def handle_starttag(self, tag, attrs):
        if tag in ("h2", "h3", "p", "a"):
            self.tags.append([tag, [], dict(attrs).get("href", "")])

    def handle_data(self, data):
        for element in self.tags:
            element[1].append(data)

    def handle_endtag(self, tag):
        if self.tags and self.tags[-1][0] == tag:
            nom, morceaux, lien = self.tags.pop()
            texte = " ".join(" ".join(morceaux).split())
            if texte:
                self.blocks.append((nom, texte, lien))

@st.cache_data(ttl=1800)
def charger():
    req = Request(SOURCE, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=15) as rep:
        contenu = rep.read(1500000).decode("utf-8", errors="replace")
    lecteur = Lecteur()
    lecteur.feed(contenu)
    return lecteur.blocks

def categorie(titre):
    t = titre.lower()
    groupes = {
        "Voyages": ["voyage", "week-end", "séjour", "vacances", "hôtel"],
        "High-tech": ["ps5", "console", "nintendo", "switch", "iphone", "ordinateur"],
        "Alimentation": ["pizza", "chocolat", "café", "restaurant"],
        "Beauté": ["parfum", "beauté", "maquillage", "cosmétique"],
        "Maison": ["maison", "aspirateur", "cuisine"],
        "Argent & bons": ["euros", "€", "bon d'achat", "carte cadeau"],
        "Culture & loisirs": ["cinéma", "concert", "spectacle", "livre"]
    }
    for nom, mots in groupes.items():
        if any(mot in t for mot in mots):
            return nom
    return "Divers"

def concours_trouves(blocs):
    resultats = []
    mois = {
        "janvier": 1, "février": 2, "mars": 3, "avril": 4,
        "mai": 5, "juin": 6, "juillet": 7, "août": 8,
        "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12
    }
    deja = set()
    for i, (tag, titre, _) in enumerate(blocs):
        if tag not in ("h2", "h3"):
            continue
        if not re.search("gagnez|concours|remportez|à gagner", titre, re.I):
            continue
        voisins = blocs[i + 1:i + 14]
        contexte = " ".join(texte for _, texte, _ in voisins)
        m = re.search(
            r"Expire le\s*:?\s*(\d{1,2})\s+"
            r"(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)"
            r"\s+(20\d\d)", contexte, re.I
        )
        limite = None
        if m:
            try:
                limite = date(int(m.group(3)), mois[m.group(2).lower()], int(m.group(1)))
            except ValueError:
                pass
        lien = None
        for genre, texte, href in voisins:
            if genre == "a" and href:
                possible = urljoin(SOURCE, href)
                if urlparse(possible).scheme in ("http", "https"):
                    lien = possible
                    break
        if lien and titre.casefold() not in deja:
            deja.add(titre.casefold())
            resultats.append((titre, lien, limite))
    return resultats

onglets = st.tabs(["🔎 Recherche", "🔗 Mes concours", "💡 Réponses", "🎯 Estimation"])

with onglets[0]:
    st.subheader("Liste des concours belges")
    choix = st.selectbox("Catégorie", [
        "Toutes", "Voyages", "High-tech", "Alimentation",
        "Beauté", "Maison", "Argent & bons", "Culture & loisirs", "Divers"
    ])
    mot = st.text_input("Filtrer par mot-clé")
    masquer = st.checkbox("Masquer les concours expirés", value=True)
    if st.button("🔄 Actualiser"):
        charger.clear()
    try:
        liste = concours_trouves(charger())
        selection = []
        for titre, lien, limite in liste:
            if choix != "Toutes" and categorie(titre) != choix:
                continue
            if mot and mot.casefold() not in titre.casefold():
                continue
            if masquer and limite is not None and limite < date.today():
                continue
            selection.append((titre, lien, limite))
        st.write(f"{len(selection)} concours trouvés")
        if not selection:
            st.info("Aucun concours trouvé pour ces critères.")
        for i, (titre, lien, limite) in enumerate(selection):
            with st.container(border=True):
                st.write("**" + titre + "**")
                st.caption(categorie(titre))
                st.write("Date limite :", limite.strftime("%d/%m/%Y") if limite else "Non trouvée")
                st.link_button("Voir le concours", lien, key=f"concours_{i}")
    except Exception:
        st.warning("Impossible de charger la liste pour le moment.")
        st.link_button("Consulter la source", SOURCE)
    st.caption("Résultats provenant d'un répertoire public. Vérifie la date et le règlement auprès de l'organisateur.")

with onglets[1]:
    st.subheader("Ajouter mes concours")
    if "mes_concours" not in st.session_state:
        st.session_state.mes_concours = []
    nom = st.text_input("Nom du concours")
    adresse = st.text_input("Lien du concours")
    fin = st.date_input("Date limite à vérifier")
    if st.button("➕ Ajouter"):
        if nom.strip() and adresse.startswith("https://"):
            st.session_state.mes_concours.append((nom, adresse, fin))
            st.success("Concours ajouté pour cette session")
        else:
            st.warning("Indique un nom et un lien https://")
    for nom, adresse, fin in st.session_state.mes_concours:
        st.write("**" + nom + "**")
        st.write("Date saisie :", fin.strftime("%d/%m/%Y"))
        st.link_button("Ouvrir", adresse)
    st.caption("Cette liste n'est pas sauvegardée durablement.")

with onglets[2]:
    st.subheader("Aide aux réponses")
    question = st.text_area("Question du concours")
    if question.strip():
        st.link_button("Vérifier les réponses sur Internet",
            "https://www.google.com/search?q=" + quote_plus(question))
    st.caption("Les réponses doivent être vérifiées avec des sources fiables.")

with onglets[3]:
    st.subheader("Estimation des participants")
    st.info("Sans compteur public, les résultats sont hypothétiques.")
    debut = st.date_input("Début du concours", key="debut")
    fin = st.date_input("Fin du concours", key="cloture")
    visites = st.number_input("Visiteurs supposés par jour", min_value=1, value=1000)
    taux = st.slider("Taux de participation supposé (%)", 0.1, 10.0, 2.0)
    if st.button("🏆 Proposer une réponse"):
        jours = (fin - debut).days + 1
        if jours < 1:
            st.error("Vérifie les dates.")
        else:
            centre = round(jours * visites * taux / 100)
            st.metric("Réponse simulée", f"{centre:,}".replace(",", " "))
            st.write("Scénario bas :", round(centre / 2))
            st.write("Scénario haut :", centre * 2)
            st.warning("Simulation seulement : les visites et le taux ne sont pas mesurés.")
