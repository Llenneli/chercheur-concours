import streamlit as st
from datetime import date
from urllib.request import Request, urlopen
from urllib.parse import urljoin, quote_plus, urlparse
from html.parser import HTMLParser
import re
import csv
import io
import json
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError, URLError

st.set_page_config(page_title="Concours Belgique V11", page_icon="🏆")
st.title("🏆 Fou de Concours — pour les Belges")

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
    ("Fou de Concours — Étranger pour les Belges",
     "https://www.foudeconcours.com/forum/concours/concours-%C3%A3%C2%A9trangers-pour-les-belges"),
]

@st.cache_data(ttl=1800)
def sources_regulieres():
    """Adresses publiques des rubriques périodiques, sans étape de découverte."""
    base = "https://www.foudeconcours.com/forum/concours/concours-r%C3%A3%C2%A9guliers"
    sources = [
        ("Fou de Concours — Journaliers", base + "/concours-journaliers"),
        ("Fou de Concours — Mensuels", base + "/concours-mensuels"),
    ]
    return sources, []



# Liens directs confirmés par l'utilisatrice, associés à leur édition précise.
LIENS_DIRECTS_VERIFIES = [
    {
        "mots": ("festival", "cin", "moustique", "17l11"),
        "lien": "https://www.moustique.be/concours/2026/11/09/concours-remportez-vos-places-pour-la-26eme-edition-du-cinemamed-clone-PEIKUIGDJFHTRKYXPMFKNBBD6Q/",
        "fin": date(2026, 11, 17),
    },
]

def lien_direct_confirme(concours):
    titre = concours["titre"].casefold()
    for entree in LIENS_DIRECTS_VERIFIES:
        if all(mot in titre for mot in entree["mots"]):
            return entree
    return None


def liens_sans_erreur(url):
    try:
        return liens_externes_du_sujet(url)
    except Exception:
        return []


@st.cache_data(ttl=3600)
def liens_externes_du_sujet(url):
    """Propose les liens externes trouvés sur le sujet, jamais un lien inventé."""
    page = lire(url)
    candidats = []
    domaines_refuses = (
        "foudeconcours.com", "google.com", "google.be", "facebook.com",
        "instagram.com", "x.com", "twitter.com", "youtube.com",
        "youtu.be", "tiktok.com", "pinterest.com",
    )
    mots_ignores = ("connexion", "inscription au forum", "se connecter",
                    "règlement du forum", "signaler", "profil", "partager")
    for lien_info in page.liens:
        destination = urljoin(url, lien_info["url"])
        analyse = urlparse(destination)
        domaine = (analyse.hostname or "").lower()
        if analyse.scheme not in ("https", "http") or not domaine:
            continue
        if domaine.startswith("www."):
            domaine = domaine[4:]
        if any(domaine == bloque or domaine.endswith("." + bloque) for bloque in domaines_refuses):
            continue
        if destination.lower().split("?")[0].endswith(
            (".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf", ".svg")
        ):
            continue
        libelle = " ".join(lien_info["titre"].split())
        if any(mot in libelle.casefold() for mot in mots_ignores):
            continue
        if destination not in candidats:
            candidats.append(destination)
    return candidats[:6]


def date_limite_du_titre(titre):
    """Lit les dates du titre sans inventer l'année lorsqu'elle est absente."""
    texte = date_dans_titre(titre)
    if not texte:
        return None
    parties = [int(x) for x in texte.split("/")]
    jour, mois = parties[:2]
    aujourd_hui = date.today()
    if len(parties) == 3:
        annee = parties[2]
    else:
        annee = aujourd_hui.year
        # Un concours annoncé en fin d'année peut terminer en janvier/février.
        if aujourd_hui.month >= 10 and mois <= 3:
            annee += 1
    try:
        return date(annee, mois, jour)
    except ValueError:
        return None


@st.cache_data(ttl=1800)
def chercher_foudeconcours():
    resultats, erreurs = [], []
    vus = set()
    regulieres, erreurs_regulieres = sources_regulieres()
    erreurs.extend(erreurs_regulieres)
    # Explorer également les pages suivantes des deux grandes rubriques.
    # La page 1 reste prioritaire ; les doublons sont retirés par URL.
    rubriques = FDC_SECTIONS + regulieres
    pages_a_lire = []
    for source, adresse in rubriques:
        pages_a_lire.append((source, adresse))
        if source in ("Fou de Concours — Belgique", "Fou de Concours — Étranger pour les Belges"):
            pages_a_lire.extend((source, adresse.rstrip("/") + "/page" + str(n)) for n in (2, 3))
    for source, adresse in pages_a_lire:
        try:
            page = lire(adresse)
            for a in page.liens:
                titre = " ".join(a["titre"].split())
                lien = urljoin(adresse, a["url"])
                path = urlparse(lien).path.rstrip("/")
                # Les accents d'URL peuvent varier entre les liens et la rubrique.
                from urllib.parse import unquote
                chemin_lu = unquote(unquote(path)).casefold()
                if source == "Fou de Concours — Belgique":
                    bonne_rubrique = "concours-belges-pour-les-belges/" in chemin_lu
                elif source == "Fou de Concours — Étranger pour les Belges":
                    bonne_rubrique = "trangers-pour-les-belges/" in chemin_lu
                elif source.endswith("Journaliers"):
                    bonne_rubrique = "/concours-journaliers/" in chemin_lu
                else:
                    bonne_rubrique = "/concours-mensuels/" in chemin_lu
                if not bonne_rubrique:
                    continue
                reste = chemin_lu.rsplit("/", 1)[-1]
                if not re.match(r"^\d+-[^/]+$", reste):
                    continue
                if not 12 <= len(titre) <= 190 or lien in vus:
                    continue
                # Ne pas proposer les concours organisés sur les réseaux sociaux.
                # Vérifier le titre et l'adresse du sujet (y compris son slug).
                texte_reseau = (titre + " " + chemin_lu).casefold()
                if re.search(r"facebook|face-book|fb\b|instagram|insta\b", texte_reseau):
                    continue
                vus.add(lien)
                resultats.append({
                    "titre": titre, "url": lien,
                    "categorie": categorie(titre, ""),
                    "source": source,
                    "date_non_confirmee": True,
                    "date_titre": date_dans_titre(titre),
                    "limite_calculee": date_limite_du_titre(titre),
                })
        except Exception:
            # Une page supplémentaire inaccessible ne rend pas la rubrique entière absente.
            if not re.search(r"/page[23]$", adresse):
                erreurs.append(source)
    return resultats[:180], erreurs

def chercher():
    # Fou de Concours uniquement, y compris les concours étrangers ouverts aux Belges.
    return chercher_foudeconcours()

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
    ecrivain = csv.DictWriter(tampon, fieldnames=CHAMPS_CARNET, extrasaction="ignore")
    ecrivain.writeheader()
    ecrivain.writerows(lignes)
    return tampon.getvalue().encode("utf-8-sig")



# Connexion personnelle à Supabase ; les identifiants restent uniquement dans la session.
def configuration_supabase():
    try:
        base = str(st.secrets["SUPABASE_URL"]).rstrip("/")
        cle = str(st.secrets["SUPABASE_PUBLISHABLE_KEY"])
        return base, cle
    except (KeyError, FileNotFoundError):
        return None, None

def requete_supabase(chemin, methode="GET", donnees=None, avec_session=True):
    base, cle = configuration_supabase()
    if not base or not cle:
        raise RuntimeError("Connexion Supabase non configurée dans les Secrets Streamlit.")
    corps = json.dumps(donnees).encode("utf-8") if donnees is not None else None
    def faire_requete():
        jeton = st.session_state.get("sb_access_token") if avec_session else None
        entetes = {"apikey": cle, "Content-Type": "application/json"}
        if jeton:
            entetes["Authorization"] = "Bearer " + jeton
        if methode in ("POST", "PATCH"):
            entetes["Prefer"] = "return=representation"
        return Request(base + chemin, data=corps, headers=entetes, method=methode)
    try:
        with urlopen(faire_requete(), timeout=18) as reponse:
            contenu = reponse.read().decode("utf-8")
            return json.loads(contenu) if contenu else None
    except HTTPError as e:
        if e.code == 401 and avec_session and st.session_state.get("sb_refresh_token"):
            renouveler_session()
            try:
                with urlopen(faire_requete(), timeout=18) as reponse:
                    contenu = reponse.read().decode("utf-8")
                    return json.loads(contenu) if contenu else None
            except HTTPError as e2:
                raise RuntimeError("Connexion expirée ou accès refusé. Reconnecte-toi.") from e2
        raise RuntimeError("Supabase a refusé la requête (code " + str(e.code) + ").") from e
    except URLError as e:
        raise RuntimeError("Impossible de joindre Supabase. Vérifie ta connexion Internet.") from e

def enregistrer_jetons(reponse):
    st.session_state.sb_access_token = reponse["access_token"]
    st.session_state.sb_refresh_token = reponse["refresh_token"]
    # Le mot de passe n'est jamais sauvegardé dans Safari.
    st.session_state.sb_browser_action = "save"

def renouveler_session():
    jeton = st.session_state.get("sb_refresh_token")
    if not jeton:
        raise RuntimeError("Reconnecte-toi.")
    resultat = requete_supabase(
        "/auth/v1/token?grant_type=refresh_token",
        "POST", {"refresh_token": jeton}, avec_session=False
    )
    enregistrer_jetons(resultat)

# Connexion conservée sur cet appareil : seul le jeton de renouvellement Supabase
# est enregistré dans le stockage local du navigateur (jamais le mot de passe).
# Ce stockage est réservé au navigateur et peut être effacé par Safari.
STOCKAGE_CONNEXION_JS = """
export default function({data, setStateValue}) {
    const cle = "concours_belgique_v11_supabase_refresh_v1";
    try {
        if (data?.action === "clear") {
            window.localStorage.removeItem(cle);
            setStateValue("refresh_token", null);
        } else if (data?.action === "save" && data?.refresh_token) {
            window.localStorage.setItem(cle, data.refresh_token);
        } else if (data?.action === "read") {
            const souvenir = window.localStorage.getItem(cle);
            if (souvenir) setStateValue("refresh_token", souvenir);
        }
    } catch (e) {
        // Safari peut bloquer le stockage local : la connexion manuelle reste possible.
    }
}
"""

def restaurer_connexion_navigateur():
    """Retrouve une session Supabase sur le même navigateur, sans mot de passe."""
    try:
        composant = st.components.v2.component(
            "concours_belgique_memoire_connexion", js=STOCKAGE_CONNEXION_JS
        )
    except AttributeError:
        st.caption("La mémorisation nécessite une version récente de Streamlit.")
        return

    action = st.session_state.get("sb_browser_action", "read")
    jeton = (st.session_state.get("sb_refresh_token", "") if action == "save" else "")
    # Un composant Streamlit v2 n'exécute son JavaScript qu'au montage.
    # Changer de key lors d'une sauvegarde ou déconnexion force ce montage.
    import hashlib
    empreinte = hashlib.sha256(jeton.encode("utf-8")).hexdigest()[:16] if jeton else ""
    cle_composant = "sb_memoire_navigateur_" + action + "_" + empreinte
    resultat = composant(
        key=cle_composant,
        data={"action": action, "refresh_token": jeton},
        on_refresh_token_change=lambda: None,
    )
    if (action == "read" and not st.session_state.get("sb_access_token")
            and not st.session_state.get("sb_recovery_attempted")
            and getattr(resultat, "refresh_token", None)):
        st.session_state.sb_recovery_attempted = True
        st.session_state.sb_refresh_token = resultat.refresh_token
        try:
            renouveler_session()
            st.rerun()
        except RuntimeError as erreur:
            st.session_state.pop("sb_access_token", None)
            st.session_state.pop("sb_refresh_token", None)
            if "code 400" in str(erreur) or "code 401" in str(erreur):
                st.session_state.sb_browser_action = "clear"
            else:
                st.caption("Reconnexion automatique momentanément indisponible.")

restaurer_connexion_navigateur()

def lire_concours_ignores():
    """Choix personnels enregistrés dans les métadonnées du compte Supabase."""
    if not st.session_state.get("sb_access_token"):
        return set()
    profil = requete_supabase("/auth/v1/user")
    metadonnees = (profil or {}).get("user_metadata") or {}
    liens = metadonnees.get("concours_ignores_v11") or []
    return set(x for x in liens if isinstance(x, str)) if isinstance(liens, list) else set()


def enregistrer_concours_ignores(liens):
    """N'écrase pas les autres préférences du compte."""
    if not st.session_state.get("sb_access_token"):
        raise RuntimeError("Connecte-toi dans 📒 Participations pour enregistrer ce choix.")
    requete_supabase("/auth/v1/user", "PUT", {
        "data": {"concours_ignores_v11": sorted(liens)}
    })


def lire_concours_favoris():
    """Favoris privés mémorisés dans les métadonnées de l'utilisateur Supabase."""
    if not st.session_state.get("sb_access_token"):
        return {}
    profil = requete_supabase("/auth/v1/user")
    metadonnees = (profil or {}).get("user_metadata") or {}
    donnees = metadonnees.get("concours_favoris_v11") or []
    if not isinstance(donnees, list):
        return {}
    return {
        element["url"]: {
            "url": element["url"],
            "titre": str(element.get("titre") or "Concours favori")[:190],
            "source": str(element.get("source") or "")[:120],
        }
        for element in donnees
        if isinstance(element, dict)
        and isinstance(element.get("url"), str)
        and element["url"].startswith("https://")
    }


def enregistrer_concours_favoris(favoris):
    """Confirme que Supabase a bien mémorisé les favoris avant d'annoncer le succès."""
    if not st.session_state.get("sb_access_token"):
        raise RuntimeError("Connecte-toi dans 📒 Participations pour gérer tes favoris.")
    reponse = requete_supabase("/auth/v1/user", "PUT", {
        "data": {"concours_favoris_v11": list(favoris.values())}
    })
    # L'API peut répondre sans renvoyer le champ modifié. Relire alors le profil.
    confirme = (reponse or {}).get("user_metadata", {}).get("concours_favoris_v11")
    if confirme is None:
        profil = requete_supabase("/auth/v1/user")
        confirme = (profil or {}).get("user_metadata", {}).get("concours_favoris_v11")
    if not isinstance(confirme, list) or {
        item.get("url") for item in confirme if isinstance(item, dict)
    } != set(favoris):
        raise RuntimeError("Supabase n'a pas confirmé l'enregistrement. Réessaie.")
    st.session_state.concours_favoris_v11 = dict(favoris)
    st.session_state.concours_favoris_confirmation = "⭐ Favoris enregistrés dans ton compte."



def charger_participations():
    if not st.session_state.get("sb_access_token"):
        return []
    donnees = requete_supabase("/rest/v1/participations?select=*&order=created_at.desc")
    return donnees or []

def sauvegarder_participation(ligne):
    champs = {cle: ligne.get(cle, "") for cle in CHAMPS_CARNET}
    return requete_supabase("/rest/v1/participations", "POST", champs)

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["🔎 Recherche", "🔗 Mes concours", "💡 Réponses", "🎯 Estimation", "📒 Participations"]
)


def statut_deja_joue(concours, historique, aujourdhui):
    """Réinitialise l'indicateur des concours journaliers et mensuels à chaque période."""
    uri = concours["url"].rstrip("/").casefold()
    titre = concours["titre"].strip().casefold()
    periodique = concours["source"]
    for participation in historique:
        p_uri = str(participation.get("url") or "").rstrip("/").casefold()
        p_titre = str(participation.get("concours") or "").strip().casefold()
        if not ((uri and p_uri == uri) or (titre and p_titre == titre)):
            continue
        if periodique.endswith("Journaliers") or periodique.endswith("Mensuels"):
            try:
                jour_joue = date.fromisoformat(str(participation.get("date_participation") or "")[:10])
            except ValueError:
                continue
            if periodique.endswith("Journaliers") and jour_joue != aujourdhui:
                continue
            if periodique.endswith("Mensuels") and (jour_joue.year, jour_joue.month) != (aujourdhui.year, aujourdhui.month):
                continue
        return True
    return False


@st.fragment(run_every="30m")
def afficher_liste_concours():
    st.subheader("🔎 Concours ouverts aux Belges")
    st.caption("Source : Fou de Concours — Belgique, étranger pour les Belges, journaliers et mensuels. Mise à jour toutes les 30 minutes tant que la page est ouverte.")
    origine = st.selectbox(
        "Origine des concours",
        ["Tous les concours pour les Belges", "Organisés en Belgique", "Organisés à l'étranger",
         "Journaliers", "Mensuels"],
        key="origine_forum"
    )
    cat = st.selectbox("Catégorie", CATEGORIES, key="cat_forum")
    mots = st.text_input("Filtrer par mot-clé", key="filtre_forum")
    masquer = st.checkbox("Masquer les concours terminés", value=True, key="masquer_expires")
    masquer_joues = st.checkbox("Masquer les concours déjà joués", value=False, key="masquer_deja_joues")
    masquer_ignores = st.checkbox("Masquer les concours sans intérêt", value=True, key="masquer_concours_ignores")
    favoris_uniquement = st.checkbox("⭐ Afficher seulement mes favoris", value=False, key="filtre_favoris")
    connecte = bool(st.session_state.get("sb_access_token"))
    historique = []
    historique_ok = False
    ignores = set(st.session_state.get("concours_ignores_v11") or [])
    ignores_ok = False
    favoris = dict(st.session_state.get("concours_favoris_v11") or {})
    favoris_ok = False
    if connecte:
        try:
            historique = charger_participations()
            historique_ok = True
        except RuntimeError as erreur:
            st.warning("Le suivi des concours joués est indisponible : " + str(erreur))
        try:
            ignores = lire_concours_ignores()
            st.session_state.concours_ignores_v11 = ignores
            ignores_ok = True
        except RuntimeError:
            st.caption("Impossible de retrouver pour le moment les concours masqués.")
        try:
            favoris_distants = lire_concours_favoris()
            favoris = favoris_distants
            st.session_state.concours_favoris_v11 = favoris
            favoris_ok = True
        except RuntimeError:
            st.caption("Impossible de retrouver les favoris pour le moment.")
    else:
        st.info("Pour enregistrer et retrouver les concours déjà joués, connecte-toi d'abord dans l'onglet 📒 Participations.")
    if st.button("🔄 Actualiser maintenant", key="rafraichir_forum"):
        chercher_foudeconcours.clear()
    liste, erreurs = chercher()
    confirmation_favoris = st.session_state.pop("concours_favoris_confirmation", "")
    if confirmation_favoris:
        st.success(confirmation_favoris)
    if connecte and favoris_ok:
        with st.expander(f"⭐ Mes favoris ({len(favoris)})"):
            if favoris:
                st.caption("Tes favoris restent enregistrés même si un concours disparaît de la recherche.")
                for favori in favoris.values():
                    st.link_button("🌐 " + favori["titre"], favori["url"])
            else:
                st.caption("Appuie sur « ⭐ Ajouter aux favoris » sous un concours pour le retrouver ici.")
    elif favoris_uniquement:
        st.info("Connecte-toi dans 📒 Participations pour retrouver tes favoris.")
    if connecte and ignores_ok and ignores:
        with st.expander(f"🚫 Concours sans intérêt ({len(ignores)})"):
            st.caption("Ces choix sont conservés dans ton compte. Tu peux réafficher un concours à tout moment.")
            if st.button("↩️ Réafficher tous les concours masqués", key="retablir_concours_ignores"):
                try:
                    enregistrer_concours_ignores(set())
                    st.session_state.concours_ignores_v11 = set()
                    st.rerun(scope="fragment")
                except RuntimeError as erreur:
                    st.error(str(erreur))
    if erreurs:
        st.warning("Certaines rubriques n'ont pas pu être lues automatiquement : " + ", ".join(erreurs))
        if "Fou de Concours — Journaliers" in erreurs:
            st.link_button("Consulter les journaliers sur le forum",
                "https://www.foudeconcours.com/forum/concours/concours-r%C3%A3%C2%A9guliers/concours-journaliers")
        if "Fou de Concours — Mensuels" in erreurs:
            st.link_button("Consulter les mensuels sur le forum",
                "https://www.foudeconcours.com/forum/concours/concours-r%C3%A3%C2%A9guliers/concours-mensuels")
    nb_belges = sum(1 for x in liste if x["source"] == "Fou de Concours — Belgique")
    nb_etrangers = sum(1 for x in liste if x["source"] == "Fou de Concours — Étranger pour les Belges")
    nb_journaliers = sum(1 for x in liste if x["source"] == "Fou de Concours — Journaliers")
    nb_mensuels = sum(1 for x in liste if x["source"] == "Fou de Concours — Mensuels")
    st.caption(
        f"Trouvés sur le forum : {nb_belges} belges, {nb_etrangers} étrangers pour les Belges, "
        f"{nb_journaliers} journaliers et {nb_mensuels} mensuels (avant filtrage des dates)."
    )
    if nb_etrangers == 0:
        st.warning("Aucun concours étranger récupéré pour le moment. La rubrique peut être indisponible.")
        st.link_button("Voir la rubrique étrangère sur le forum",
            "https://www.foudeconcours.com/forum/concours/concours-%C3%A3%C2%A9trangers-pour-les-belges")
    aujourdhui = date.today()
    affichables = []
    for concours in liste:
        if origine == "Organisés en Belgique" and concours["source"] != "Fou de Concours — Belgique":
            continue
        if origine == "Organisés à l'étranger" and concours["source"] != "Fou de Concours — Étranger pour les Belges":
            continue
        if origine == "Journaliers" and concours["source"] != "Fou de Concours — Journaliers":
            continue
        if origine == "Mensuels" and concours["source"] != "Fou de Concours — Mensuels":
            continue
        limite = concours.get("limite_calculee")
        if masquer and limite and limite < aujourdhui and concours["source"] not in (
            "Fou de Concours — Journaliers", "Fou de Concours — Mensuels"
        ):
            continue
        if cat != "Toutes" and concours["categorie"] != cat:
            continue
        if mots and mots.casefold() not in concours["titre"].casefold():
            continue
        if masquer_joues and historique_ok and statut_deja_joue(concours, historique, aujourdhui):
            continue
        if masquer_ignores and concours["url"] in ignores:
            continue
        if favoris_uniquement and concours["url"] not in favoris:
            continue
        affichables.append(concours)
    st.write(f"**{len(affichables)} concours affiché(s)**")
    taille_page = 12
    pages = max(1, (len(affichables) + taille_page - 1) // taille_page)
    numero_page = st.selectbox(
        "Page des concours", range(1, pages + 1),
        format_func=lambda n: f"Page {n} sur {pages}",
        key="page_concours"
    )
    debut_page = (numero_page - 1) * taille_page
    a_afficher = affichables[debut_page:debut_page + taille_page]
    # Chercher les liens externes pour tous les concours visibles de la page.
    # Le cache évite de relire chaque discussion à chaque interaction.
    urls_a_verifier = [
        concours["url"] for concours in a_afficher
        if not lien_direct_confirme(concours)
    ]
    liens_automatiques = {}
    if urls_a_verifier:
        with ThreadPoolExecutor(max_workers=6) as pool:
            trouves = list(pool.map(liens_sans_erreur, urls_a_verifier))
        liens_automatiques = dict(zip(urls_a_verifier, trouves))
    for i, concours in enumerate(a_afficher, start=debut_page):
        with st.container(border=True):
            st.write("**" + concours["titre"] + "**")
            st.caption(concours["categorie"] + " — " + concours["source"])
            if connecte and favoris_ok:
                url_favori = concours["url"]
                # Afficher la réponse exactement sous le bouton cliqué :
                # un rerun immédiat effaçait le message et pouvait déplacer la page.
                if url_favori in favoris:
                    if st.button("⭐ Retirer des favoris", key=f"retirer_favori_{i}"):
                        try:
                            nouveaux_favoris = dict(favoris)
                            nouveaux_favoris.pop(url_favori, None)
                            enregistrer_concours_favoris(nouveaux_favoris)
                            favoris = nouveaux_favoris
                            st.success("✅ Retiré des favoris !")
                            st.caption("Le bouton sera mis à jour au prochain affichage.")
                        except RuntimeError as erreur:
                            st.error("Favori non modifié : " + str(erreur))
                elif st.button("☆ Ajouter aux favoris", key=f"ajouter_favori_{i}"):
                    try:
                        nouveaux_favoris = dict(favoris)
                        nouveaux_favoris[url_favori] = {
                            "url": url_favori,
                            "titre": concours["titre"],
                            "source": concours["source"],
                        }
                        enregistrer_concours_favoris(nouveaux_favoris)
                        favoris = nouveaux_favoris
                        st.success("✅ Ajouté aux favoris ! Tu le retrouveras dans ⭐ Mes favoris.")
                        st.caption("Le bouton sera mis à jour au prochain affichage.")
                    except RuntimeError as erreur:
                        st.error("Favori non enregistré : " + str(erreur))
            if connecte and ignores_ok:
                if concours["url"] in ignores:
                    st.caption("🚫 Tu avais indiqué ne pas être intéressée.")
                    if st.button("↩️ Remettre ce concours", key=f"remettre_ignore_{i}"):
                        try:
                            nouveaux = ignores - {concours["url"]}
                            enregistrer_concours_ignores(nouveaux)
                            st.session_state.concours_ignores_v11 = nouveaux
                            st.rerun(scope="fragment")
                        except RuntimeError as erreur:
                            st.error(str(erreur))
                elif st.button("🚫 Pas intéressée", key=f"ignorer_concours_{i}"):
                    try:
                        nouveaux = ignores | {concours["url"]}
                        enregistrer_concours_ignores(nouveaux)
                        st.session_state.concours_ignores_v11 = nouveaux
                        st.rerun(scope="fragment")
                    except RuntimeError as erreur:
                        st.error(str(erreur))
            if historique_ok:
                deja_joue = statut_deja_joue(concours, historique, aujourdhui)
                if deja_joue:
                    if concours["source"].endswith("Journaliers"):
                        st.success("✅ Déjà joué aujourd'hui")
                    elif concours["source"].endswith("Mensuels"):
                        st.success("✅ Déjà joué ce mois-ci")
                    else:
                        st.success("✅ Déjà participé")
                else:
                    if st.button("✅ Marquer comme joué", key=f"marquer_joue_{i}"):
                        ligne = {
                            "concours": concours["titre"],
                            "url": concours["url"],
                            "source": concours["source"],
                            "date_participation": aujourdhui.isoformat(),
                            "nombre_envoye": "",
                            "question_subsidiaire": "",
                            "notes": "Marqué comme joué depuis la recherche",
                        }
                        try:
                            sauvegarder_participation(ligne)
                            st.success("Participation enregistrée dans ton carnet !")
                            st.rerun(scope="fragment")
                        except RuntimeError as erreur:
                            st.error("Enregistrement impossible : " + str(erreur))
            limite = concours.get("limite_calculee")
            if limite:
                st.write("📅 Date du titre :", limite.strftime("%d/%m/%Y"))
                st.caption("Date déduite du titre du forum : vérifier le règlement, surtout si l'année n'est pas indiquée.")
                if limite < aujourdhui:
                    st.write("🔴 Date dépassée")
            else:
                st.write("🟡 Date inconnue : vérifier la fin du concours")
            if concours["source"] in ("Fou de Concours — Journaliers", "Fou de Concours — Mensuels"):
                st.caption("Concours récurrent : la date du titre peut concerner une édition passée.")
            lien_confirme = lien_direct_confirme(concours)
            if lien_confirme:
                if lien_confirme["fin"] >= aujourdhui:
                    st.link_button("🌐 Participer directement sur Moustique",
                                   lien_confirme["lien"], key=f"direct_valide_{i}")
                    st.caption("Lien fourni pour cette édition du concours, jusqu'au 17/11/2026.")
                else:
                    st.caption("Le lien direct connu correspond à une ancienne édition.")
            else:
                externes = liens_automatiques.get(concours["url"], [])
                if len(externes) == 1:
                    st.link_button("🌐 Ouvrir le site du concours (à vérifier)",
                                   externes[0], key=f"externe_{i}")
                elif len(externes) > 1:
                    st.caption("🔗 Plusieurs liens trouvés dans la discussion :")
                    for j, externe in enumerate(externes):
                        domaine = urlparse(externe).hostname or "Site externe"
                        st.link_button("🌐 " + domaine + " (à vérifier)", externe,
                                       key=f"externe_{i}_{j}")
                else:
                    st.caption("🔎 Aucun lien direct accessible automatiquement pour ce concours.")
                st.caption("Vérifie la page du concours et ses conditions avant de participer.")
            st.link_button("Voir la discussion sur Fou de Concours", concours["url"], key=f"fdc_{i}")
    st.caption("Le bouton « Marquer comme joué » enregistre la participation sans numéro subsidiaire. Pour conserver le nombre envoyé, utilise plutôt l'onglet 🎯 Estimation. Les concours journaliers redeviennent disponibles le lendemain et les mensuels le mois suivant.")
    st.caption("Les concours sans date lisible restent visibles. Ton historique de participations n'est jamais supprimé par ce filtre.")

with tab1:
    afficher_liste_concours()

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
            ligne = {
                "concours": concours_choisi["titre"],
                "url": concours_choisi["url"],
                "source": concours_choisi["source"],
                "date_participation": date_envoi.isoformat(),
                "nombre_envoye": nombre_envoye.strip(),
                "question_subsidiaire": st.session_state.get("question_sub", "").strip() if choix_sub == "📋 Coller ma question" else "",
                "notes": notes_sub.strip(),
            }
            if not st.session_state.get("sb_access_token"):
                st.warning("Connecte-toi d'abord dans l'onglet 📒 Participations. Rien n'a été enregistré.")
            else:
                try:
                    sauvegarder_participation(ligne)
                    st.success("Participation sauvegardée automatiquement dans ton carnet privé !")
                except RuntimeError as e:
                    st.error(str(e) + " Rien n'a été confirmé comme enregistré.")
    else:
        st.caption("Choisis d'abord un concours pour enregistrer ta participation.")


with tab5:
    st.subheader("📒 Mon carnet privé de participations")
    base, cle = configuration_supabase()
    if not base or not cle:
        st.warning("La connexion à Supabase n'est pas encore configurée. Il faut renseigner SUPABASE_URL et SUPABASE_PUBLISHABLE_KEY dans les Secrets de cette application Streamlit.")
        st.info("Ton ancienne V10 et ta sauvegarde CSV restent disponibles.")
    else:
        if not st.session_state.get("sb_access_token"):
            st.write("Connecte-toi avec ton compte Supabase.")
            st.caption("Après la connexion, cet appareil pourra te reconnecter automatiquement. Ton mot de passe n'est pas enregistré par l'application.")
            with st.form("connexion_privee", clear_on_submit=True):
                email = st.text_input("Adresse e-mail", key="sb_email")
                mot_de_passe = st.text_input("Mot de passe", type="password", key="sb_password")
                connexion = st.form_submit_button("🔒 Me connecter")
            if connexion:
                try:
                    resultat = requete_supabase(
                        "/auth/v1/token?grant_type=password", "POST",
                        {"email": email.strip(), "password": mot_de_passe},
                        avec_session=False
                    )
                    enregistrer_jetons(resultat)
                    st.success("Connectée !")
                    st.rerun()
                except (RuntimeError, KeyError) as e:
                    st.error("Connexion impossible. Vérifie l'adresse e-mail et le mot de passe.")
        else:
            if st.button("Me déconnecter", key="sb_deconnexion"):
                st.session_state.pop("sb_access_token", None)
                st.session_state.pop("sb_refresh_token", None)
                st.session_state.sb_browser_action = "clear"
                st.session_state.sb_recovery_attempted = True
                st.rerun()
            try:
                carnet = charger_participations()
            except RuntimeError as e:
                carnet = []
                st.error(str(e))
            else:
                st.write(f"**{len(carnet)} participation(s) sauvegardée(s) dans Supabase**")
                recherche = st.text_input("🔎 Rechercher un concours", key="sb_recherche")
                for p in carnet:
                    if recherche and recherche.casefold() not in (str(p.get("concours") or "") + " " + str(p.get("nombre_envoye") or "")).casefold():
                        continue
                    with st.container(border=True):
                        st.write("**" + str(p.get("concours") or "Sans titre") + "**")
                        st.caption("Participation le " + str(p.get("date_participation") or "?"))
                        st.write("Nombre envoyé :", p.get("nombre_envoye") or "Non indiqué")
                        if p.get("question_subsidiaire"):
                            st.write("Question :", p["question_subsidiaire"])
                        if p.get("notes"):
                            st.write("Notes :", p["notes"])
                        if str(p.get("url") or "").startswith("https://"):
                            st.link_button("Voir le concours", p["url"], key="lien_db_" + str(p["id"]))
                        if st.button("🗑️ Supprimer cette participation", key="del_db_" + str(p["id"])):
                            try:
                                from urllib.parse import quote
                                requete_supabase("/rest/v1/participations?id=eq." + quote(str(p["id"]), safe=""), "DELETE")
                                st.success("Participation supprimée.")
                                st.rerun()
                            except RuntimeError as e:
                                st.error(str(e))
                st.download_button(
                    "⬇️ Télécharger une copie CSV",
                    exporter_carnet(carnet),
                    file_name="mes_participations_concours.csv",
                    mime="text/csv", key="sb_export"
                )
                st.markdown("#### Récupérer ton ancien carnet V10")
                st.caption("Tu peux importer ton fichier CSV une seule fois. Les lignes déjà présentes avec les mêmes informations sont ignorées.")
                ancien = st.file_uploader("Choisir le fichier mes_participations_concours.csv", type=["csv"], key="sb_ancien")
                if ancien is not None and st.button("📥 Importer mes anciennes participations", key="sb_importer"):
                    try:
                        lecteur = csv.DictReader(io.StringIO(ancien.getvalue().decode("utf-8-sig")))
                        if not lecteur.fieldnames or not set(CHAMPS_CARNET).issubset(set(lecteur.fieldnames)):
                            st.error("Ce CSV ne correspond pas au carnet V10.")
                        else:
                            existants = {tuple(str(p.get(k) or "") for k in CHAMPS_CARNET) for p in carnet}
                            ajoutes = 0
                            for p in lecteur:
                                ligne = {k: str(p.get(k) or "") for k in CHAMPS_CARNET}
                                signature = tuple(ligne[k] for k in CHAMPS_CARNET)
                                if signature not in existants:
                                    sauvegarder_participation(ligne)
                                    existants.add(signature)
                                    ajoutes += 1
                            st.success(f"{ajoutes} participation(s) importée(s).")
                            st.rerun()
                    except (RuntimeError, UnicodeError, csv.Error, ValueError) as e:
                        st.error("Importation interrompue. Vérifie le fichier, puis recharge le carnet.")
