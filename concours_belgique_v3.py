import streamlit as st
import re
from datetime import date
from html.parser import HTMLParser
from urllib.request import Request, urlopen
from urllib.parse import urljoin, urlparse, quote_plus

st.set_page_config(page_title="Concours Belgique", page_icon="🏆")
st.title("🏆 Mon chercheur de concours belges")

SOURCES = [
    ("Échantillons Gratuits", "https://www.echantillonsgratuits.be/concours-belgique", "Toutes"),
    ("Échantillons Gratuits Voyages", "https://www.echantillonsgratuits.be/concours-belgique/concours-voyages", "Voyages"),
    ("Mitspiel Voyages", "https://mitspiel.be/gagner-un-voyage", "Voyages"),
]

CATEGORIES = [
    "Toutes", "Voyages", "Voitures", "Argent et bons",
    "High-tech", "Alimentation", "Beauté", "Maison",
    "Culture et loisirs", "Divers"
]

class Liens(HTMLParser):
    def __init__(self):
        super().__init__()
        self.actifs = []
        self.liens = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href", "")
            self.actifs.append({"href": href, "texte": ""})

    def handle_data(self, data):
        for lien in self.actifs:
            lien["texte"] += data

    def handle_endtag(self, tag):
        if tag == "a" and self.actifs:
            self.liens.append(self.actifs.pop())

def classer(titre, categorie_source):
    if categorie_source == "Voyages":
        return "Voyages"
    t = titre.lower()
    mots = {
        "Voyages": ["voyage", "séjour", "week-end", "vacances", "hôtel", "disneyland"],
        "Voitures": ["voiture", "automobile", "véhicule"],
        "Argent et bons": ["bon d'achat", "carte cadeau", "chèques-cadeaux", "cash"],
        "High-tech": ["console", "playstation", "ps5", "nintendo", "smartphone", "ordinateur", "iphone"],
        "Alimentation": ["chocolat", "pizza", "restaurant", "café", "alimentaire", "dégustation"],
        "Beauté": ["beauté", "cosmétique", "parfum", "maquillage"],
        "Maison": ["maison", "aspirateur", "meuble", "cuisine"],
        "Culture et loisirs": ["concert", "cinéma", "livre", "festival", "spectacle"]
    }
    for categorie, termes in mots.items():
        if any(terme in t for terme in termes):
            return categorie
    return "Divers"

@st.cache_data(ttl=3600)
def charger_concours():
    trouves = []
    erreurs = []
    deja = set()
    for nom_source, adresse, cat_source in SOURCES:
        try:
            req = Request(adresse, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(req, timeout=12) as reponse:
                contenu = reponse.read(1200000).decode("utf-8", errors="replace")
            lecteur = Liens()
            lecteur.feed(contenu)
            for lien in lecteur.liens:
                titre = " ".join(lien["texte"].split())
                url = urljoin(adresse, lien["href"])
                chemin = urlparse(url).path.rstrip("/")
                if len(titre) < 14 or len(titre) > 180:
                    continue
                if nom_source.startswith("Échantillons"):
                    if "/concours-belgique/" not in chemin:
                        continue
                    if chemin.endswith("/concours-voyages"):
                        continue
                else:
                    if "/concours/" not in chemin:
                        continue
                if not re.search(r"gagnez|gagner|remportez|séjour|concours|à gagner", titre, re.I):
                    continue
                if url in deja:
                    continue
                deja.add(url)
                trouves.append({
                    "titre": titre,
                    "url": url,
                    "categorie": classer(titre, cat_source),
                    "source": nom_source,
                    "date": None
                })
        except Exception:
            erreurs.append(nom_source)
    return trouves, erreurs

if "mes_concours" not in st.session_state:
    st.session_state.mes_concours = []

onglets = st.tabs(["🔎 Recherche", "🔗 Mes concours", "💡 Réponses", "🎯 Estimation"])

with onglets[0]:
    st.subheader("Liste des concours belges")
    st.caption("Les concours sont extraits de répertoires publics. Vérifie toujours leur règlement.")
    choix = st.selectbox("Catégorie", CATEGORIES)
    mots = st.text_input("Rechercher dans les titres")
    if st.button("🔄 Actualiser la liste"):
        charger_concours.clear()
    liste, erreurs = charger_concours()
    filtres = [
        c for c in liste
        if (choix == "Toutes" or c["categorie"] == choix)
        and (not mots or mots.lower() in c["titre"].lower())
    ]
    st.write(f"{len(filtres)} concours trouvés dans cette sélection")
    if erreurs:
        st.warning("Certaines sources sont momentanément indisponibles : " + ", ".join(erreurs))
    if not filtres:
        st.info("Aucun concours trouvé pour ce filtre. Essaie Toutes.")
    for i, concours in enumerate(filtres):
        with st.container(border=True):
            st.markdown("**" + concours["titre"] + "**")
            st.write("Catégorie :", concours["categorie"])
            st.write("Source :", concours["source"])
            st.write("📅 Date limite : à vérifier")
            st.link_button("Voir le concours", concours["url"], key=f"lien_{i}")
    st.warning("Une date non vérifiée ne garantit pas qu'un concours est toujours ouvert.")

with onglets[1]:
    st.subheader("Ajouter un concours")
    nom = st.text_input("Nom du concours")
    url = st.text_input("Adresse Internet")
    limite = st.date_input("Date limite vérifiée", value=date.today())
    if st.button("➕ Ajouter"):
        if nom.strip() and url.startswith("https://"):
            st.session_state.mes_concours.append((nom, url, limite))
            st.success("Concours ajouté pour cette session.")
        else:
            st.warning("Indique un nom et un lien https://")
    for i, (nom, url, limite) in enumerate(st.session_state.mes_concours):
        with st.container(border=True):
            st.write("**" + nom + "**")
            st.write("Fin :", limite.strftime("%d/%m/%Y"))
            st.write("Expiré selon cette date" if limite < date.today() else "Date non dépassée")
            st.link_button("Ouvrir", url, key=f"perso_{i}")
    st.caption("La liste personnelle n'est pas conservée durablement.")

with onglets[2]:
    st.subheader("Aide aux réponses")
    question = st.text_area("Copie la question du concours")
    if question.strip():
        st.link_button("🔎 Vérifier sur Internet",
            "https://www.google.com/search?q=" + quote_plus(question))
    st.caption("Vérifie les réponses avec des sources fiables.")

with onglets[3]:
    st.subheader("Question subsidiaire")
    st.write("Combien de personnes auront participé à la fin ?")
    debut = st.date_input("Début du concours", key="debut")
    fin = st.date_input("Clôture du concours", key="fin")
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
            st.warning("Calcul hypothétique : aucune fréquentation réelle n'est mesurée.")
