import streamlit as st
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
from html.parser import HTMLParser
from datetime import date
import re

st.set_page_config(page_title="Concours Belgique", page_icon="🏆")
st.title("🏆 Mon chercheur de concours belges")

class Lecteur(HTMLParser):
    def __init__(self):
        super().__init__()
        self.mots = []
        self.ignorer = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.ignorer += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.ignorer = max(0, self.ignorer - 1)

    def handle_data(self, data):
        if self.ignorer == 0:
            self.mots.append(data)

onglets = st.tabs(["🔎 Recherche", "🔗 Concours", "💡 Réponses", "👥 Estimation"])

with onglets[0]:
    st.subheader("Trouver des concours en Belgique")
    categorie = st.selectbox("Catégorie", [
        "Tous", "Voyages", "Argent", "Voitures",
        "High-tech", "Maison", "Alimentation",
        "Beauté", "Culture"
    ])
    mots = st.text_input("Mots-clés", "concours gratuit")
    q = f"{mots} {categorie} concours Belgique date limite"
    st.link_button("🔎 Rechercher sur Google",
                   "https://www.google.com/search?q=" + quote_plus(q))
    st.caption("Vérifie la date limite et les conditions de chaque concours.")

with onglets[1]:
    st.subheader("Analyser un concours")
    lien = st.text_input("Colle l'adresse Internet du concours")
    fin = st.date_input("Date limite connue", value=date.today())
    if fin < date.today():
        st.warning("La date saisie est dépassée.")
    if st.button("Analyser le lien"):
        if not lien.startswith(("https://", "http://")):
            st.error("Entre une adresse Internet valide.")
        else:
            try:
                req = Request(lien, headers={"User-Agent": "Mozilla/5.0"})
                with urlopen(req, timeout=10) as rep:
                    page = rep.read(500000).decode("utf-8", errors="replace")
                lecteur = Lecteur()
                lecteur.feed(page)
                texte = re.sub(r"\s+", " ", " ".join(lecteur.mots))
                extraits = re.findall(
                    r".{0,65}\b\d[\d .]*\s+(?:participants|participations|inscrits)\b.{0,65}",
                    texte, re.IGNORECASE
                )
                if extraits:
                    for extrait in extraits[:8]:
                        st.info(extrait)
                    st.warning("Les chiffres trouvés ne sont pas forcément des inscriptions réelles.")
                else:
                    st.info("Aucun chiffre public trouvé sur cette page.")
            except Exception:
                st.warning("Impossible de lire automatiquement cette page.")

with onglets[2]:
    st.subheader("Chercher les réponses")
    question = st.text_area("Écris la question du concours")
    if question.strip():
        st.link_button("🔎 Vérifier sur Google",
            "https://www.google.com/search?q=" + quote_plus(question))

with onglets[3]:
    st.subheader("Estimer la participation finale")
    st.info("Sans chiffre de départ réel, une prévision fiable est impossible.")
    nombre = st.number_input("Participants connus actuellement",
                             min_value=0, value=0, step=1)
    debut = st.date_input("Début du concours", value=date.today())
    cloture = st.date_input("Clôture du concours", value=date.today())
    if st.button("Calculer"):
        jours = (date.today() - debut).days + 1
        total = (cloture - debut).days + 1
        if nombre == 0 or jours <= 0 or total <= 0:
            st.warning("Indique un nombre réel et des dates valides.")
        elif jours >= total:
            st.metric("Participants connus", nombre)
        else:
            projection = round(nombre * total / jours)
            st.metric("Projection indicative", projection)
            st.caption("Hypothèse : même nombre d'inscriptions par st.divider()
st.header("🎯 Estimation sans compteur public")
st.write("Simule le nombre de participants à la clôture.")

date_debut = st.date_input("Début du concours", key="auto_debut")
date_fin = st.date_input("Date de clôture", key="auto_fin")

visites = st.number_input(
    "Visites supposées par jour",
    min_value=1, value=1000, step=100
)

st.caption(
    "1000 visites par jour est une hypothèse de départ, "
    "pas une mesure du site."
)

if st.button("🎯 Calculer les scénarios"):
    duree = (date_fin - date_debut).days + 1
    if duree <= 0:
        st.error("Vérifie les dates du concours.")
    else:
        total_visites = duree * visites
        taux = [0.005, 0.02, 0.05]
        noms = ["Basse", "Centrale", "Haute"]
        for nom, t in zip(noms, taux):
            estimation = round(total_visites * t)
            st.metric(
                "Estimation " + nom,
                f"{estimation:,} participants"
            )
        st.warning(
            "Résultats purement hypothétiques. "
            "Les taux de 0,5%, 2% et 5% ne sont "
            "pas mesurés pour ce concours. "
            "Une visite n'est pas forcément "
            "une personne unique."
        )
