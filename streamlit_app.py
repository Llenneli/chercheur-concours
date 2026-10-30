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
            self.ignorer = max(0, self.ignorer - 1)
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
