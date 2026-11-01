import streamlit as st
import urllib.request
import re
from html.parser import HTMLParser

st.set_page_config(page_title="Chercheur de concours", page_icon="🏆")

class TextePage(HTMLParser):
    def __init__(self):
        super().__init__()
        self.textes = []
        self.ignorer = 0
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.ignorer += 1
    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.ignorer = max(0, self.ignorer - import streamlit as st
import urllib.request
import urllib.parse
import re
from datetime import date, datetime
from html.parser import HTMLParser

st.set_page_config(page_title="Concours Belgique", page_icon="🏆")
st.title("🏆 Mon chercheur de concours belges")

class Lecteur(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parties = []
        self.masquer = 0
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.masquer += 1
    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.masquer = max(0, self.masquer - 1)
    def handle_data(self, data):
        if self.masquer == 0:
            self.parties.append(data)

categories = [
    "Tous", "Voyages", "Argent", "Voitures",
    "High-tech", "Maison", "Alimentation",
    "Beauté", "Culture", "Autres"
]
onglets = st.tabs([
    "🔎 Recherche", "🔗 Mon concours",
    "💡 Réponses", "👥 Estimation"
])

with onglets[0]:
    st.subheader("Concours accessibles aux Belges")
    categorie = st.selectbox("Catégorie", categories)
    mot = st.text_input("Mot-clé", "concours gratuit")
    recherche = f"{mot} {categorie if categorie != 'Tous' else ''} Belgique concours date limite participation"
    lien_google = "https://www.google.com/search?q=" + urllib.parse.quote_plus(recherche)
    st.link_button("🔎 Chercher les concours", lien_google)
    st.caption("Les résultats s'ouvrent dans Google. Vérifie les dates limites et l'éligibilité belge.")

with onglets[1]:
    st.subheader("Ajouter et analyser un concours")
    url = st.text_input("Adresse du concours", key="url")
    titre = st.text_input("Nom du concours")
    limite = st.date_input("Date limite (à vérifier dans le règlement)", value=date.today())
    st.write("Statut selon la date saisie :", "Expiré" if limite < date.today() else "À vérifier / en cours")
    if st.button("Analyser la page"):
        if not url.startswith(("https://", "http://")):
            st.error("Colle une adresse commençant par https://")
        else:
            try:
                req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=10) as rep:
                    page = rep.read(500000).decode("utf-8", errors="replace")
                lecteur = Lecteur()
                lecteur.feed(page)
                texte = re.sub(r"\s+", " ", " ".join(lecteur.parties))
                st.success("Page consultée")
                mentions = re.findall(
                    r".{0,80}\b\d[\d .]*\s+(?:participants|participations|inscrits)\b.{0,80}",
                    texte, flags=re.IGNORECASE
                )
                if mentions:
                    for element in mentions[:8]:
                        st.info(element)
                    st.warning("Vérifie le contexte : minimum requis, prix ou ancienne édition ne sont pas des inscriptions réelles.")
                else:
                    st.info("Aucun chiffre de participants repéré publiquement.")
                dates = re.findall(r".{0,45}(?:date limite|jusqu'au|se termine|clôture).{0,90}", texte, flags=re.IGNORECASE)
                if dates:
                    st.write("Mentions de dates à vérifier :")
                    for element in dates[:5]:
                        st.write(element)
            except Exception:
                st.warning("Cette page ne permet pas une lecture automatique. Consulte son règlement.")

with onglets[2]:
    st.subheader("Aide aux réponses")
    question = st.text_area("Copie une question du concours")
    if question.strip():
        recherche_q = urllib.parse.quote_plus(question)
        st.link_button("Rechercher des sources pour la réponse", "https://www.google.com/search?q=" + recherche_q)
    st.caption("Vérifie les réponses avec des sources fiables.")

with onglets[3]:
    st.subheader("Question subsidiaire")
    st.write("Combien de personnes auront participé à la clôture ?")
    st.info("Sans compteur réel ni statistiques de fréquentation, aucun algorithme ne peut prédire un nombre fiable.")
    connus = st.number_input("Inscriptions réellement connues aujourd'hui (0 si inconnues)", min_value=0, value=0, step=1)
    debut = st.date_input("Début du concours", value=date.today(), key="debut")
    fin = st.date_input("Fin du concours", value=date.today(), key="fin")
    if st.button("Calculer une projection"):
        jours = (date.today() - debut).days + 1
        duree = (fin - debut).days + 1
        if connus <= 0:
            st.warning("Aucune projection basée sur des données réelles n'est possible. Il faut un nombre d'inscrits connu.")
        elif duree <= 0 or jours <= 0:
            st.warning("Vérifie les dates.")
        else:
            if jours >= duree:
                st.write("Concours terminé ou à sa date de fin :", connus)
            else:
                projection = round(connus * duree / jours)
                st.metric("Projection à la clôture", f"{projection:,}")
                st.caption("Hypothèse : inscriptions au même rythme chaque jour. Cette projection peut être très imprécise.")

st.caption("Outil d'aide : aucune inscription n'est réalisée automatiquement.")

    def handle_data(self, data):
        if not self.ignorer:
            self.textes.append(data)

st.title("🏆 Mon chercheur de concours")
lien = st.text_input("Colle ici le lien du concours")

if st.button("🔎 Analyser le concours"):
    if not lien.startswith(("https://", "http://")):
        st.warning("Entre une adresse valide.")
    else:
        try:
            req = urllib.request.Request(lien, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                html = r.read(1000000).decode("utf-8", errors="ignore")
            analyse = TextePage()
            analyse.feed(html)
            texte = re.sub(r"\s+", " ", " ".join(analyse.textes))
            resultats = re.findall(
                r".{0,70}\b\d[\d .]*\s+(?:participants|participations|inscrits)\b.{0,70}",
                texte, re.IGNORECASE
            )
            if resultats:
                st.subheader("👥 Chiffres mentionnés sur la page")
                for resultat in resultats[:10]:
                    st.info(resultat)
                st.warning("Ces chiffres ne représentent pas forcément le nombre de personnes déjà inscrites.")
            else:
                st.info("Aucun nombre de participants trouvé sur cette page.")
        except Exception:
            st.error("Impossible de lire cette page automatiquement.")

st.subheader("📊 Estimation hypothétique")
visiteurs = st.number_input("Nombre supposé de visiteurs", min_value=0, value=0, step=100)
if visiteurs:
    for taux in (1, 5, 10):
        st.write(f"Si {taux}% participent : environ {round(visiteurs*taux/100)} participants")
st.caption("Ces calculs ne sont pas des mesures réelles.")
