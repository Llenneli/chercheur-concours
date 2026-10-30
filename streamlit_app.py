import streamlit as st
from urllib.parse import quote_plus

st.set_page_config(page_title="Chercheur de concours", page_icon="🏆")

st.title("🏆 Mon chercheur de concours")
st.write("Recherchez des concours sur Internet.")

pays = st.selectbox(
    "Où rechercher ?",
    ["Belgique", "France", "Francophonie"]
)

mot = st.text_input("Type de concours", "concours gratuit")

if st.button("🔎 Rechercher"):
    recherche = f"{mot} {pays} participer concours"
    adresse = "https://www.google.com/search?q=" + quote_plus(recherche)
    st.link_button("Voir les concours", adresse)

st.info("Le nombre de participants n'est pas toujours public.")
