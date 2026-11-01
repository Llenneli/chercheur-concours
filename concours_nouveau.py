import streamlit as st
from datetime import date
from urllib.parse import quote_plus

st.set_page_config(page_title="Concours Belgique", page_icon="🏆")
st.title("🏆 Mon chercheur de concours belges")

if "concours" not in st.session_state:
    st.session_state.concours = []

recherche, mes_concours, reponses, estimation = st.tabs(
    ["🔎 Recherche", "🔗 Mes concours", "💡 Réponses", "🎯 Estimation"]
)

with recherche:
    st.subheader("Trouver des concours belges")
    categorie = st.selectbox("Catégorie", [
        "Tous", "Voyages", "Argent", "Voitures", "Technologie",
        "Maison", "Alimentation", "Beauté", "Culture", "Autres"
    ])
    mots = st.text_input("Mots-clés", "concours gratuit")
    termes = f"{mots} {categorie if categorie != 'Tous' else ''} Belgique concours date limite"
    st.link_button("🔎 Rechercher sur Google",
                   "https://www.google.com/search?q=" + quote_plus(termes))
    st.caption("Vérifie les dates limites et les conditions de chaque concours.")

with mes_concours:
    st.subheader("Ajouter un concours")
    titre = st.text_input("Nom du concours")
    url = st.text_input("Adresse Internet (https://...)")
    limite = st.date_input("Date limite selon le règlement", value=date.today())
    if st.button("➕ Ajouter à ma liste"):
        if not titre.strip() or not url.startswith("https://"):
            st.warning("Indique un nom et une adresse commençant par https://")
        elif any(c["url"] == url for c in st.session_state.concours):
            st.warning("Ce concours est déjà dans la liste.")
        else:
            st.session_state.concours.append(
                {"titre": titre.strip(), "url": url, "limite": limite}
            )
            st.success("Concours ajouté !")
    for i, c in enumerate(st.session_state.concours):
        st.write("**" + c["titre"] + "**")
        st.write("Date limite saisie :", c["limite"].strftime("%d/%m/%Y"))
        st.write("Expiré selon cette date" if c["limite"] < date.today()
                 else "Date à vérifier dans le règlement")
        st.link_button("Ouvrir le concours", c["url"], key=f"lien_{i}")
    st.caption("La liste reste disponible pendant cette session, pas après sa fermeture.")

with reponses:
    st.subheader("Vérifier une réponse")
    question = st.text_area("Recopie la question du concours")
    if question.strip():
        st.link_button("🔎 Rechercher des sources",
                       "https://www.google.com/search?q=" + quote_plus(question))
    st.caption("Les réponses ne sont pas garanties : vérifie les sources.")

with estimation:
    st.subheader("Question subsidiaire : combien participeront ?")
    st.info("Sans statistiques publiques, le calcul est hypothétique.")
    debut = st.date_input("Début du concours", key="debut")
    fin = st.date_input("Fin du concours", key="fin")
    visites = st.number_input("Visiteurs supposés par jour", min_value=1,
                              value=1000, step=100)
    taux = st.slider("Pourcentage supposé de participation", 0.1, 10.0, 2.0, 0.1)
    if st.button("🏆 Proposer une réponse"):
        jours = (fin - debut).days + 1
        if jours < 1:
            st.error("La fin doit être postérieure ou égale au début.")
        else:
            centre = round(jours * visites * taux / 100)
            basse = round(jours * visites * max(0.1, taux / 2) / 100)
            haute = round(jours * visites * min(100, taux * 2) / 100)
            st.metric("Réponse proposée (simulation)", f"{centre:,}".replace(",", " "))
            st.write("Scénario bas :", basse, "— Scénario haut :", haute)
            st.warning("Le chiffre proposé n'est pas une estimation fiable : "
                       "les visites et le taux sont supposés, non mesurés.")
