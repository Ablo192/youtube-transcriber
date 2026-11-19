import os
import sys
import time
import re
from pathlib import Path
from typing import List, Optional, Dict, Any

import streamlit as st

# S'assurer que le dossier du module est accessible pour les imports
module_dir = Path(__file__).resolve().parent
if str(module_dir) not in sys.path:
    sys.path.insert(0, str(module_dir))

from transcriber import (
    get_youtube_transcript,
    transcribe_uploaded_media,
    extract_video_id,
    get_video_metadata
)

# Configuration de la page Streamlit
st.set_page_config(
    page_title="Transcripteur YouTube Pro",
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Style CSS personnalisé pour une interface moderne et élégante
st.markdown("""
<style>
    /* Polices et conteneurs */
    .main-title {
        font-size: 2.2rem;
        font-weight: 800;
        background: linear-gradient(90deg, #FF0000, #FF6B6B);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    .subtitle {
        font-size: 1.05rem;
        color: #6c757d;
        margin-bottom: 1.5rem;
    }
    
    /* Cartes de résultats */
    .metric-card {
        background-color: #f8f9fa;
        border-radius: 10px;
        padding: 12px 18px;
        border-left: 4px solid #FF0000;
        margin-bottom: 15px;
    }
    .metric-title {
        font-size: 0.85rem;
        text-transform: uppercase;
        color: #888;
        font-weight: 600;
    }
    .metric-value {
        font-size: 1.4rem;
        font-weight: 700;
        color: #111;
    }
    
    /* Carte vidéo */
    .video-card {
        display: flex;
        gap: 15px;
        background: #ffffff;
        border: 1px solid #e9ecef;
        border-radius: 12px;
        padding: 15px;
        margin-bottom: 20px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
    }
    .video-info h3 {
        margin: 0 0 8px 0;
        font-size: 1.15rem;
    }
    .video-meta {
        font-size: 0.9rem;
        color: #555;
    }
    
    /* Boîtes de badges */
    .badge {
        display: inline-block;
        padding: 3px 8px;
        border-radius: 6px;
        font-size: 0.78rem;
        font-weight: 600;
        margin-right: 6px;
    }
    .badge-primary { background-color: #e3f2fd; color: #1976d2; }
    .badge-success { background-color: #e8f5e9; color: #388e3c; }
    .badge-warning { background-color: #fff3e0; color: #f57c00; }
</style>
""", unsafe_allow_html=True)


# --- BARRE LATÉRALE (Paramètres) ---
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/e/ef/Youtube_logo.png", width=160)
    st.markdown("### ⚙️ Paramètres d'extraction")
    
    lang_choice = st.selectbox(
        "Langue prioritaire :",
        options=[
            "Français d'abord (puis Anglais)",
            "Anglais d'abord",
            "N'importe quelle langue disponible"
        ],
        index=0
    )
    
    if lang_choice.startswith("Français"):
        preferred_langs = ['fr', 'fr-FR', 'fr-CA', 'en', 'en-US']
    elif lang_choice.startswith("Anglais"):
        preferred_langs = ['en', 'en-US', 'en-GB', 'fr', 'fr-FR']
    else:
        preferred_langs = None
        
    st.markdown("---")
    st.markdown("### 🧹 Formatage du texte")
    
    include_timestamps = st.checkbox(
        "Inclure les horodatages [MM:SS]",
        value=False,
        help="Ajoute le repère temporel au début de chaque paragraphe."
    )
    
    include_header = st.checkbox(
        "Inclure l'en-tête descriptif",
        value=True,
        help="Ajoute le titre, l'auteur et les métadonnées au début du texte."
    )
    
    clean_audio_tags = st.checkbox(
        "Supprimer les bruits sonores ([Musique], etc.)",
        value=True,
        help="Nettoie les artefacts audio pour un texte fluide."
    )

    st.markdown("---")
    st.markdown("### 🤖 Secours IA (Vidéos sans sous-titres)")
    secret_groq_key = ""
    try:
        secret_groq_key = str(st.secrets.get("GROQ_API_KEY", "")).strip()
    except Exception:
        pass
    if not secret_groq_key:
        secret_groq_key = os.environ.get("GROQ_API_KEY", "").strip()

    if secret_groq_key:
        st.success("✅ Clé Groq configurée (Secrets)")
        manual_groq_key = secret_groq_key
    else:
        manual_groq_key = st.text_input(
            "Clé API Groq (optionnel) :",
            type="password",
            placeholder="gsk_...",
            help="Permet de transcrire les vidéos sans sous-titres et les fichiers audio/vidéo via Groq Whisper (~$0,04/h après palier gratuit)."
        ).strip()

    use_groq_fallback = st.checkbox(
        "Transcrire l'audio via Groq si aucun sous-titre",
        value=bool(manual_groq_key),
        disabled=not bool(manual_groq_key),
        help="Télécharge uniquement l'audio et utilise Whisper Large v3 Turbo sur Groq uniquement quand aucun sous-titre n'est trouvé."
    )
    active_groq_key: Optional[str] = manual_groq_key if (manual_groq_key and use_groq_fallback) else None

    st.markdown("---")
    st.markdown("### 💡 Astuce IA")
    st.info("Le texte extrait est structuré en paragraphes fluides, idéal pour être analysé par ChatGPT, Claude ou Gemini sans surcharger la mémoire.")

    # Section Accès Mobile
    st.markdown("---")
    with st.expander("📱 Ouvrir sur votre Smartphone", expanded=False):
        import socket
        tunnel_file = module_dir / "tunnel_url.txt"
        if tunnel_file.exists():
            public_url = tunnel_file.read_text(encoding="utf-8").strip()
            if public_url:
                st.success("🌍 **Accès 4G / 5G / Partout (Actif)**")
                st.code(public_url, language="text")
                st.caption("Scannez pour ouvrir en 4G/5G :")
                qr_public = f"https://api.qrserver.com/v1/create-qr-code/?size=180x180&data={public_url}"
                st.image(qr_public, width=160)
                st.markdown("---")
        
        try:
            hostname = socket.gethostname()
            _, _, ips = socket.gethostbyname_ex(hostname)
            wifi_ip = next((ip for ip in ips if ip.startswith("192.168.")), None)
            if not wifi_ip:
                wifi_ip = next((ip for ip in ips if ip.startswith("10.")), ips[0] if ips else "localhost")
        except Exception:
            wifi_ip = "192.168.1.58"
            
        mobile_url = f"http://{wifi_ip}:8501"
        st.markdown(f"🏠 **Sur le même Wi-Fi :**")
        st.code(mobile_url, language="text")
        st.caption("Scannez ce QR Code en Wi-Fi :")
        qr_api_url = f"https://api.qrserver.com/v1/create-qr-code/?size=180x180&data={mobile_url}"
        st.image(qr_api_url, width=160)

    # Section Sécurité & Mot de passe
    st.markdown("---")
    with st.expander("🛡️ Sécurité & Mot de passe", expanded=False):
        pin_file = module_dir / "security_pin.txt"
        is_protected = pin_file.exists() and bool(pin_file.read_text(encoding="utf-8").strip())
        if is_protected:
            st.success("🔒 Protection par mot de passe : **ACTIVE**")
            st.caption("L'accès à distance est protégé contre les intrusions.")
            if st.button("Désactiver le mot de passe", key="btn_disable_pwd"):
                pin_file.unlink(missing_ok=True)
                st.session_state["authenticated"] = False
                st.rerun()
        else:
            st.info("🔓 Accès libre (aucun mot de passe requis).")
            new_pwd = st.text_input("Définir un mot de passe secret :", type="password", key="new_pwd_input")
            if st.button("Activer la protection 🔒", key="btn_enable_pwd"):
                if new_pwd.strip():
                    pin_file.write_text(new_pwd.strip(), encoding="utf-8")
                    st.session_state["authenticated"] = True
                    st.success("Mot de passe activé avec succès !")
                    st.rerun()
                else:
                    st.warning("Veuillez saisir un mot de passe.")


# --- VÉRIFICATION DE L'AUTHENTIFICATION ---
def check_auth() -> bool:
    pin_file = module_dir / "security_pin.txt"
    saved_pin = ""
    if pin_file.exists():
        saved_pin = pin_file.read_text(encoding="utf-8").strip()
    
    # Support des Secrets Streamlit Cloud (st.secrets["SECURITY_PIN"])
    if not saved_pin:
        try:
            saved_pin = str(st.secrets.get("SECURITY_PIN", "")).strip()
        except Exception:
            pass

    if not saved_pin:
        return True
    if st.session_state.get("authenticated", False):
        return True

    st.markdown('<div class="main-title">🔒 Accès Sécurisé</div>', unsafe_allow_html=True)
    st.markdown("Cette application est protégée par un mot de passe d'accès pour empêcher toute intrusion à distance.")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        pwd = st.text_input("Mot de passe d'accès :", type="password", key="auth_pwd_input")
    with col2:
        st.write("")
        st.write("")
        if st.button("Déverrouiller 🔓", type="primary", use_container_width=True):
            if pwd == saved_pin:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("❌ Mot de passe incorrect.")
    return False

if not check_auth():
    st.stop()


def render_transcription_result(result: Dict[str, Any], key_prefix: str = "single") -> None:
    """Affiche le résultat d'une transcription (carte, texte et boutons de téléchargement)."""
    meta = result["metadata"]
    clean_text = result["clean_text"]

    st.success("✅ Transcription récupérée avec succès !")

    # Carte descriptive de la vidéo / du média
    col_thumb, col_details = st.columns([1, 3])
    with col_thumb:
        if meta.get("thumbnail_url"):
            st.image(meta["thumbnail_url"], use_container_width=True)
    with col_details:
        video_url = meta.get("video_url", "")
        if video_url.startswith(("http://", "https://")):
            st.markdown(f"### [{meta['title']}]({video_url})")
        else:
            st.markdown(f"### {meta['title']}")
        st.markdown(f"**Chaîne / Source :** {meta['author_name']}")

        source_type = result.get("source_type", "subtitles")
        if source_type == "groq_whisper":
            badge_type = "badge-warning"
            type_label = "Transcription IA (Groq Whisper)"
        elif not result["is_generated"]:
            badge_type = "badge-success"
            type_label = "Sous-titres officiels"
        else:
            badge_type = "badge-primary"
            type_label = "Sous-titres auto-générés"

        st.markdown(f"""
        <span class="badge {badge_type}">🗣️ {result['language']} ({type_label})</span>
        <span class="badge badge-warning">⏱️ Durée : {result['duration_formatted']}</span>
        <span class="badge badge-primary">📝 {result['word_count']:,} mots (~{result['reading_time_min']} min de lecture)</span>
        """, unsafe_allow_html=True)

    # Zone de texte avec le résultat
    st.markdown("#### 📄 Texte de la transcription")
    st.text_area(
        label="Contenu texte :",
        value=clean_text,
        height=350,
        key=f"{key_prefix}_output_textarea"
    )

    # Ligne de boutons d'action
    btn_col1, btn_col2, btn_col3 = st.columns([2, 2, 2])

    safe_title = re.sub(r'[\\/*?:"<>|]', "", meta['title'])[:50].strip() or "transcription"
    file_name = f"Transcription_{safe_title}.txt"

    with btn_col1:
        st.download_button(
            label="📥 Télécharger le texte (.txt)",
            data=clean_text.encode("utf-8"),
            file_name=file_name,
            mime="text/plain; charset=utf-8",
            use_container_width=True,
            key=f"{key_prefix}_dl_txt"
        )

    with btn_col2:
        ia_prompt_text = (
            f"Voici la transcription complète intitulée \"{meta['title']}\".\n"
            f"Consigne : Lis attentivement cette transcription et rédige un résumé détaillé, structuré en grands points clés avec les enseignements majeurs.\n\n"
            f"--- DÉBUT DE LA TRANSCRIPTION ---\n\n"
            f"{clean_text}\n\n"
            f"--- FIN DE LA TRANSCRIPTION ---"
        )
        st.download_button(
            label="🤖 Télécharger pour Prompt IA (.txt)",
            data=ia_prompt_text.encode("utf-8"),
            file_name=f"Prompt_IA_{safe_title}.txt",
            mime="text/plain; charset=utf-8",
            help="Télécharge le texte prêt à être glissé ou collé dans ChatGPT, Claude ou Gemini avec une consigne de résumé structuré.",
            use_container_width=True,
            key=f"{key_prefix}_dl_prompt"
        )

    with btn_col3:
        available_langs = result.get("available_languages", [])
        if len(available_langs) > 1:
            st.caption(f"{len(available_langs)} langues disponibles sur cette vidéo.")


# --- EN-TÊTE PRINCIPAL ---
st.markdown('<div class="main-title">🎙️ Transcripteur YouTube Pro</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Récupérez les sous-titres ou transcrivez l\'audio par IA (vidéos sans sous-titres et fichiers locaux) en texte prêt pour la lecture ou l\'IA.</div>', unsafe_allow_html=True)

# Définition des onglets
tab_single, tab_upload, tab_batch, tab_tips = st.tabs([
    "🎯 Vidéo Unique",
    "📁 Fichier Audio / Vidéo",
    "📋 Traitement par Lot",
    "🤖 Modèles de Prompts IA"
])


# ==========================================================
# ONGLET 1 : VIDÉO UNIQUE
# ==========================================================
with tab_single:
    col_input, col_btn = st.columns([4, 1])
    with col_input:
        youtube_url = st.text_input(
            "Entrez l'adresse de la vidéo (YouTube ou autre lien si Groq est activé) :",
            placeholder="Ex : https://www.youtube.com/watch?v=... ou https://youtu.be/...",
            key="single_url_input"
        )
    with col_btn:
        st.write("") # Espacement
        st.write("")
        extract_button = st.button("🚀 Extraire", use_container_width=True, type="primary")

    # Exemples rapides
    col_ex1, col_ex2 = st.columns([1, 4])
    with col_ex1:
        st.caption("Exemples de test :")
    with col_ex2:
        if st.button("Exemple : Vidéo TED / Conférence", key="btn_example"):
            youtube_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
            st.session_state["single_url_input"] = youtube_url
            st.rerun()

    if extract_button and youtube_url:
        spinner_msg = (
            "🔍 Analyse de la vidéo (sous-titres puis secours audio Groq si nécessaire)..."
            if active_groq_key
            else "🔍 Analyse de la vidéo et récupération de la transcription..."
        )
        with st.spinner(spinner_msg):
            result = get_youtube_transcript(
                url_or_id=youtube_url,
                preferred_languages=preferred_langs,
                include_timestamps=include_timestamps,
                include_header=include_header,
                groq_api_key=active_groq_key
            )

        if not result["success"]:
            st.error(f"❌ Impossible de récupérer la transcription : {result['error']}")
            video_id = result.get("video_id")
            if video_id and "metadata" in result and result["metadata"]:
                meta = result["metadata"]
                st.caption(f"Vidéo détectée : **{meta.get('title')}**")
        else:
            render_transcription_result(result, key_prefix="single")


# ==========================================================
# ONGLET 2 : FICHIER AUDIO / VIDÉO LOCAL
# ==========================================================
with tab_upload:
    st.markdown("### 📁 Transcrire un fichier vidéo ou audio directement")
    st.markdown("Importez un fichier depuis votre téléphone ou ordinateur (MP4, MOV, MKV, MP3, M4A, WAV, OGG). L'audio est extrait et compressé automatiquement avant envoi à Groq.")

    if not manual_groq_key:
        st.warning("⚠️ Veuillez renseigner une clé API Groq dans la barre latérale (ou dans `GROQ_API_KEY` des Secrets Streamlit) pour utiliser cette fonctionnalité.")

    uploaded_media = st.file_uploader(
        "Choisissez un fichier vidéo ou audio :",
        type=["mp4", "mov", "mkv", "webm", "mp3", "m4a", "wav", "ogg", "flac"],
        key="media_file_uploader"
    )

    if uploaded_media is not None:
        size_mb = uploaded_media.size / (1024 * 1024)
        st.caption(f"Fichier sélectionné : **{uploaded_media.name}** ({size_mb:.1f} Mo)")
        if st.button("🎙️ Transcrire ce fichier", type="primary", key="btn_transcribe_file", disabled=not bool(manual_groq_key)):
            with st.spinner("⚙️ Extraction de l'audio et transcription via Groq Whisper..."):
                file_res = transcribe_uploaded_media(
                    file_stream=uploaded_media,
                    filename=uploaded_media.name,
                    groq_api_key=manual_groq_key,
                    preferred_languages=preferred_langs,
                    include_timestamps=include_timestamps,
                    include_header=include_header
                )
            if not file_res["success"]:
                st.error(f"❌ Échec de la transcription : {file_res['error']}")
            else:
                render_transcription_result(file_res, key_prefix="upload")


# ==========================================================
# ONGLET 2 : TRAITEMENT PAR LOT (MULTI-VIDÉOS)
# ==========================================================
with tab_batch:
    st.markdown("### 📋 Extraire les transcriptions de plusieurs vidéos en une seule fois")
    st.markdown("Collez une liste de liens YouTube (un par ligne) ou téléversez un fichier texte contenant les liens.")

    batch_text = st.text_area(
        "Collez les liens ici (un lien par ligne) :",
        height=150,
        placeholder="https://www.youtube.com/watch?v=...\nhttps://youtu.be/...\nhttps://www.youtube.com/watch?v=..."
    )
    
    uploaded_file = st.file_uploader(
        "Ou importez un fichier .txt avec des liens :",
        type=["txt"]
    )

    if uploaded_file is not None:
        file_content = uploaded_file.read().decode("utf-8", errors="ignore")
        batch_text = file_content

    if st.button("🚀 Lancer le traitement par lot", type="primary", key="batch_start_btn"):
        lines = [line.strip() for line in batch_text.splitlines() if line.strip()]
        
        if not lines:
            st.warning("Veuillez renseigner au moins un lien YouTube valide.")
        else:
            st.info(f"Traitement de {len(lines)} lien(s) en cours...")
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            results = []
            combined_text_parts = []
            
            for index, line in enumerate(lines):
                status_text.text(f"Traitement {index + 1}/{len(lines)} : {line[:50]}...")
                res = get_youtube_transcript(
                    url_or_id=line,
                    preferred_languages=preferred_langs,
                    include_timestamps=include_timestamps,
                    include_header=True,
                    groq_api_key=active_groq_key
                )
                results.append((line, res))
                
                if res["success"]:
                    meta = res["metadata"]
                    combined_text_parts.append(
                        f"\n{'='*70}\n"
                        f"VIDÉO {index + 1} : {meta['title']}\n"
                        f"Lien : {meta['video_url']}\n"
                        f"{'='*70}\n\n"
                        f"{res['clean_text']}\n\n"
                    )
                
                progress_bar.progress((index + 1) / len(lines))
                time.sleep(0.1)  # Petite pause respectueuse pour YouTube

            status_text.text("✅ Traitement terminé !")
            
            # Récapitulatif
            success_count = sum(1 for _, r in results if r["success"])
            total_words = sum(r.get("word_count", 0) for _, r in results if r["success"])
            
            st.markdown(f"**Résultat :** {success_count} / {len(lines)} vidéo(s) transcrite(s) avec succès ({total_words:,} mots au total).")
            
            # Téléchargement combiné
            if combined_text_parts:
                combined_full = "".join(combined_text_parts)
                st.download_button(
                    label=f"📥 Télécharger toutes les transcriptions combinées ({success_count} vidéos)",
                    data=combined_full.encode("utf-8"),
                    file_name="Toutes_les_transcriptions_combinees.txt",
                    mime="text/plain; charset=utf-8",
                    type="primary"
                )

            # Tableau détaillé
            st.markdown("#### Détail par vidéo :")
            for idx, (original_url, res) in enumerate(results):
                with st.expander(
                    f"{'✅' if res['success'] else '❌'} Vidéo {idx+1} : {res.get('metadata', {}).get('title', original_url)}"
                ):
                    if res["success"]:
                        st.write(f"**Langue :** {res['language']} | **Mots :** {res['word_count']:,} | **Durée :** {res['duration_formatted']}")
                        st.download_button(
                            label=f"Télécharger cette transcription (.txt)",
                            data=res["clean_text"].encode("utf-8"),
                            file_name=f"Transcription_video_{idx+1}.txt",
                            mime="text/plain; charset=utf-8",
                            key=f"dl_batch_{idx}"
                        )
                        st.text_area("Aperçu :", res["clean_text"][:800] + "\n...", height=150, key=f"preview_{idx}")
                    else:
                        st.error(f"Erreur : {res.get('error')}")


# ==========================================================
# ONGLET 3 : ASTUCES & PROMPTS IA
# ==========================================================
with tab_tips:
    st.markdown("### 🤖 Comment exploiter au mieux vos transcriptions avec une IA ?")
    st.markdown("""
    Une fois le fichier texte téléchargé, vous pouvez le glisser ou le copier-coller directement dans 
    **ChatGPT**, **Claude**, **Google Gemini** ou **Mistral** pour gagner des heures d'écoute.
    """)

    st.markdown("#### 📌 Modèles de prompts à copier-coller :")

    with st.expander("📝 1. Synthèse exécutive & Décisions clés"):
        st.code("""
Agis comme un analyste expert. Voici la transcription d'une vidéo YouTube.
Rédige un compte-rendu clair et synthétique contenant :
1. L'idée principale et le message clé (en 3 phrases maximum)
2. Les 5 points essentiels développés
3. Les données chiffrées, exemples ou anecdotes marquantes citées
4. Les conclusions ou recommandations finales

Voici la transcription :
[Coller le texte ici]
        """, language="markdown")

    with st.expander("📚 2. Fiche de révision / Fiche de cours structurée"):
        st.code("""
Transforme cette transcription de vidéo en une fiche de cours structurée :
- Table des matières thématique
- Définitions des concepts clés mentionnés
- Schéma logique des arguments
- 3 questions pour tester la compréhension du contenu

Voici la transcription :
[Coller le texte ici]
        """, language="markdown")

    with st.expander("✍️ 3. Transformation en article de blog / Post LinkedIn"):
        st.code("""
À partir de la transcription ci-dessous, rédige un article captivant et engageant pour un public professionnel :
- Un titre percutant
- Une introduction qui accroche le lecteur
- 3 sous-parties claires avec des conseils applicables
- Une conclusion inspirante avec un appel à l'action

Voici la transcription :
[Coller le texte ici]
        """, language="markdown")
