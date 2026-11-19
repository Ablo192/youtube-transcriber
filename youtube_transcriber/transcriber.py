"""
Module d'extraction et de nettoyage de transcriptions YouTube.
Permet d'extraire les sous-titres officiels et auto-générés de vidéos YouTube
et de les formater en texte brut propre, optimisé pour la lecture humaine et les LLM (IA).
"""

import os
import re
import json
import shutil
import subprocess
import tempfile
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import requests
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
    InvalidVideoId,
    IpBlocked,
    RequestBlocked
)


def extract_video_id(url_or_id: str) -> Optional[str]:
    """
    Extrait l'identifiant (ID) YouTube (11 caractères) à partir de n'importe quel format d'URL ou ID brut.
    Supporte :
    - https://www.youtube.com/watch?v=ID
    - https://youtu.be/ID
    - https://www.youtube.com/shorts/ID
    - https://www.youtube.com/live/ID
    - https://www.youtube.com/embed/ID
    - ID brut de 11 caractères
    """
    if not url_or_id:
        return None
        
    candidate = url_or_id.strip()
    
    # Si c'est déjà un ID brut valide de 11 caractères
    if re.match(r'^[a-zA-Z0-9_-]{11}$', candidate):
        return candidate

    patterns = [
        r'(?:v=|\/v\/|youtu\.be\/|\/embed\/|\/shorts\/|\/live\/)([a-zA-Z0-9_-]{11})',
        r'[?&]v=([a-zA-Z0-9_-]{11})'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, candidate)
        if match:
            return match.group(1)
            
    return None


def get_video_metadata(video_id: str) -> Dict[str, Any]:
    """
    Récupère les métadonnées publiques de la vidéo via l'API oEmbed officielle de YouTube (sans clé API requise).
    Retourne le titre, l'auteur, et l'URL de la miniature.
    """
    oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
    metadata = {
        "title": f"Vidéo YouTube ({video_id})",
        "author_name": "Auteur inconnu",
        "author_url": "",
        "thumbnail_url": f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
        "video_url": f"https://www.youtube.com/watch?v={video_id}"
    }
    
    try:
        req = urllib.request.Request(
            oembed_url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                metadata["title"] = data.get("title", metadata["title"])
                metadata["author_name"] = data.get("author_name", metadata["author_name"])
                metadata["author_url"] = data.get("author_url", "")
                metadata["thumbnail_url"] = data.get("thumbnail_url", metadata["thumbnail_url"])
    except Exception:
        # En cas d'erreur réseau oEmbed, on garde les métadonnées de secours
        pass
        
    return metadata


def format_seconds(seconds: float) -> str:
    """Formate des secondes en format lisible HH:MM:SS ou MM:SS."""
    total_sec = int(round(seconds))
    hours = total_sec // 3600
    minutes = (total_sec % 3600) // 60
    sec = total_sec % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{sec:02d}"
    return f"{minutes:02d}:{sec:02d}"


def clean_snippet_text(text: str, remove_music_tags: bool = True) -> str:
    """Nettoie le texte d'un fragment de sous-titre."""
    t = text.replace('\n', ' ').strip()
    if remove_music_tags:
        # Supprime toutes les indications sonores entre crochets
        # (ex: [Musique], [Applaudissements], [Rires], [grognement], [raclement de gorge], etc.)
        t = re.sub(r'\[[^\]]*\]', '', t)
        # Supprime les notes de musique isolées
        t = t.replace('♪', '').replace('♫', '')
    
    # Nettoie les espaces multiples
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def build_paragraphs(
    snippets: List[Any],
    pause_threshold_sec: float = 2.0,
    max_words_per_paragraph: int = 90,
    include_timestamps: bool = False
) -> str:
    """
    Assemble les snippets de sous-titres en paragraphes naturels et fluides.
    Évite l'effet haché des sous-titres d'une phrase par ligne.
    """
    paragraphs = []
    current_sentences = []
    current_word_count = 0
    para_start_time = None
    prev_end_time = None

    for item in snippets:
        # Compatible avec les objets FetchedTranscriptSnippet ou les dictionnaires
        text = getattr(item, 'text', None) or (item.get('text') if isinstance(item, dict) else "")
        start = getattr(item, 'start', None) or (item.get('start') if isinstance(item, dict) else 0.0)
        duration = getattr(item, 'duration', None) or (item.get('duration') if isinstance(item, dict) else 0.0)
        
        cleaned = clean_snippet_text(text)
        if not cleaned:
            continue
            
        if para_start_time is None:
            para_start_time = start

        # Détection d'une pause marquée dans l'élocution
        pause_detected = False
        if prev_end_time is not None and (start - prev_end_time) >= pause_threshold_sec:
            pause_detected = True

        words = cleaned.split()
        current_word_count += len(words)

        # Nouvelle coupure de paragraphe si pause ou nombre de mots suffisant
        if (pause_detected or current_word_count >= max_words_per_paragraph) and current_sentences:
            para_text = " ".join(current_sentences)
            if include_timestamps and para_start_time is not None:
                paragraphs.append(f"[{format_seconds(para_start_time)}] {para_text}")
            else:
                paragraphs.append(para_text)
                
            current_sentences = [cleaned]
            current_word_count = len(words)
            para_start_time = start
        else:
            current_sentences.append(cleaned)

        prev_end_time = start + duration

    # Dernier paragraphe
    if current_sentences:
        para_text = " ".join(current_sentences)
        if include_timestamps and para_start_time is not None:
            paragraphs.append(f"[{format_seconds(para_start_time)}] {para_text}")
        else:
            paragraphs.append(para_text)

    return "\n\n".join(paragraphs)


def get_transcript_via_ytdlp(
    video_id: str,
    preferred_languages: List[str]
) -> Optional[Tuple[List[Dict[str, Any]], str, bool]]:
    """
    Moteur de secours de haute fiabilité basé sur yt-dlp.
    Contourne le rate limiting et les blocages IP temporaires de YouTube en simulant un client légitime.
    """
    try:
        import yt_dlp
        ydl_opts = {
            'skip_download': True,
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
            if not info:
                return None

            subtitles = info.get('subtitles') or {}
            auto_captions = info.get('automatic_captions') or {}

            selected_url = None
            selected_lang = None
            is_generated = False

            # Recherche dans les sous-titres officiels puis auto-générés
            for pool, gen_flag in [(subtitles, False), (auto_captions, True)]:
                for lang in preferred_languages:
                    for code in [lang, lang.split('-')[0]]:
                        if code in pool:
                            formats = pool[code]
                            target = next((f for f in formats if f.get('ext') == 'json3'), None) or formats[0]
                            selected_url = target.get('url')
                            selected_lang = code
                            is_generated = gen_flag
                            break
                    if selected_url:
                        break
                if selected_url:
                    break

            # Si aucune langue préférée, prendre la première disponible
            if not selected_url:
                for pool, gen_flag in [(subtitles, False), (auto_captions, True)]:
                    if pool:
                        first_code = next(iter(pool.keys()))
                        formats = pool[first_code]
                        target = next((f for f in formats if f.get('ext') == 'json3'), None) or formats[0]
                        selected_url = target.get('url')
                        selected_lang = first_code
                        is_generated = gen_flag
                        break

            if not selected_url:
                return None

            req = urllib.request.Request(
                selected_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw_bytes = resp.read()

            snippets = []
            try:
                data = json.loads(raw_bytes.decode('utf-8'))
                for ev in data.get('events', []):
                    t_start = ev.get('tStartMs', 0) / 1000.0
                    d_dur = ev.get('dDurationMs', 0) / 1000.0
                    segs = ev.get('segs', [])
                    text = "".join(s.get('utf8', '') for s in segs).strip()
                    if text:
                        snippets.append({'text': text, 'start': t_start, 'duration': d_dur})
            except Exception:
                raw_str = raw_bytes.decode('utf-8', errors='ignore')
                lines = [l.strip() for l in raw_str.splitlines() if l.strip() and not l.startswith('WEBVTT') and '-->' not in l and not l.isdigit()]
                for l in lines:
                    snippets.append({'text': l, 'start': 0.0, 'duration': 0.0})

            if snippets:
                return snippets, selected_lang, is_generated

    except Exception:
        pass
    return None


def _format_success_result(
    video_id: str,
    metadata: Dict[str, Any],
    snippets: List[Any],
    lang_name: str,
    lang_code: str,
    is_generated: bool,
    include_timestamps: bool,
    include_header: bool,
    available_languages: Optional[List[Dict[str, Any]]] = None,
    source_type: str = "subtitles"
) -> Dict[str, Any]:
    """Helper pour formater un résultat de transcription réussi."""
    if snippets:
        last = snippets[-1]
        total_duration_sec = (
            last['start'] + last['duration']
            if isinstance(last, dict)
            else last.start + last.duration
        )
    else:
        total_duration_sec = 0.0

    clean_body = build_paragraphs(snippets, include_timestamps=include_timestamps)
    total_words = len(clean_body.split())
    estimated_reading_time_min = max(1, round(total_words / 200))

    if source_type == "groq_whisper":
        source_label = "Transcription IA (Groq Whisper)"
    elif is_generated:
        source_label = "Générés automatiquement"
    else:
        source_label = "Manuels / Officiels"

    header = ""
    if include_header:
        header_lines = [
            f"# {metadata['title']}",
            f"- **Chaîne / Auteur** : {metadata['author_name']}",
            f"- **Lien vidéo** : {metadata['video_url']}",
            f"- **Langue** : {lang_name} ({lang_code})",
            f"- **Source** : {source_label}",
            f"- **Durée estimée** : {format_seconds(total_duration_sec)} (~{estimated_reading_time_min} min de lecture)",
            f"- **Nombre de mots** : {total_words:,}",
            "=" * 60,
            ""
        ]
        header = "\n".join(header_lines)

    full_text = f"{header}\n{clean_body}" if header else clean_body

    return {
        "success": True,
        "video_id": video_id,
        "metadata": metadata,
        "language": lang_name,
        "language_code": lang_code,
        "is_generated": is_generated,
        "source_type": source_type,
        "duration_formatted": format_seconds(total_duration_sec),
        "word_count": total_words,
        "reading_time_min": estimated_reading_time_min,
        "clean_text": full_text,
        "raw_text_only": clean_body,
        "available_languages": available_languages or [{"code": lang_code, "name": lang_name, "is_generated": is_generated}]
    }


GROQ_MAX_FILE_BYTES = 24 * 1024 * 1024  # Marge de sécurité sous la limite de 25 Mo (palier gratuit Groq)
GROQ_SUPPORTED_EXTS = {'.mp3', '.m4a', '.webm', '.mp4', '.mpga', '.wav', '.mpeg', '.ogg', '.flac'}


def _get_media_duration(file_path: Path) -> float:
    """Retourne la durée d'un fichier audio/vidéo en secondes via ffprobe, ou 0.0."""
    ffprobe_bin = shutil.which("ffprobe")
    if not ffprobe_bin:
        return 0.0
    try:
        proc = subprocess.run(
            [
                ffprobe_bin, "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(file_path)
            ],
            capture_output=True, text=True, timeout=15
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return float(proc.stdout.strip())
    except Exception:
        pass
    return 0.0


def _prepare_audio_chunks(input_path: Path, work_dir: Path) -> Tuple[List[Tuple[Path, float]], Optional[str]]:
    """
    Prépare un ou plusieurs fichiers audio <= 24 Mo pour l'API Groq.
    Utilise ffmpeg pour compresser en MP3 mono 16kHz 32kbps (~14 Mo/h) et découper si nécessaire.
    """
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        if input_path.suffix.lower() in GROQ_SUPPORTED_EXTS and input_path.stat().st_size <= GROQ_MAX_FILE_BYTES:
            return [(input_path, 0.0)], None
        return [], (
            "ffmpeg n'est pas installé sur ce système : impossible de compresser ou découper "
            "l'audio dépassant 24 Mo. Installez ffmpeg (ou utilisez Streamlit Cloud avec packages.txt)."
        )

    compressed_mp3 = work_dir / "audio_compressed.mp3"
    cmd = [
        ffmpeg_bin, "-y", "-i", str(input_path),
        "-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k",
        str(compressed_mp3)
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0 or not compressed_mp3.exists():
        return [], f"Échec de la conversion audio avec ffmpeg : {proc.stderr[-300:] if proc.stderr else 'erreur inconnue'}"

    if compressed_mp3.stat().st_size <= GROQ_MAX_FILE_BYTES:
        return [(compressed_mp3, 0.0)], None

    # Si l'audio dépasse 24 Mo (ex: vidéo > ~1h40), découper en segments de 40 minutes
    segment_seconds = 2400
    chunk_pattern = str(work_dir / "chunk_%03d.mp3")
    seg_cmd = [
        ffmpeg_bin, "-y", "-i", str(compressed_mp3),
        "-f", "segment", "-segment_time", str(segment_seconds),
        "-c", "copy", chunk_pattern
    ]
    seg_proc = subprocess.run(seg_cmd, capture_output=True, text=True, timeout=300)
    if seg_proc.returncode != 0:
        return [], f"Échec du découpage audio : {seg_proc.stderr[-300:] if seg_proc.stderr else 'erreur inconnue'}"

    chunk_files = sorted(work_dir.glob("chunk_*.mp3"))
    if not chunk_files:
        return [], "Aucun segment audio généré lors du découpage."

    chunks_with_offsets: List[Tuple[Path, float]] = []
    running_offset = 0.0
    for cf in chunk_files:
        chunks_with_offsets.append((cf, running_offset))
        dur = _get_media_duration(cf)
        running_offset += dur if dur > 0 else float(segment_seconds)

    return chunks_with_offsets, None


def _transcribe_chunks_with_groq(
    chunks: List[Tuple[Path, float]],
    api_key: str,
    language_hint: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], str, Optional[str]]:
    """
    Envoie les segments audio à l'API Groq (whisper-large-v3-turbo) et assemble les snippets horodatés.
    """
    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {api_key.strip()}"}

    all_snippets: List[Dict[str, Any]] = []
    detected_language = language_hint or "auto"

    for chunk_path, offset_sec in chunks:
        data: Dict[str, Any] = {
            "model": "whisper-large-v3-turbo",
            "response_format": "verbose_json",
            "temperature": "0",
        }
        if language_hint:
            data["language"] = language_hint

        with open(chunk_path, "rb") as f:
            files = {"file": (chunk_path.name, f, "audio/mpeg")}
            resp = requests.post(url, headers=headers, files=files, data=data, timeout=180)

        if resp.status_code == 401:
            return [], detected_language, "Clé API Groq invalide ou expirée (erreur 401)."
        if resp.status_code == 429:
            return [], detected_language, "Quota ou limite de requêtes Groq atteint (erreur 429). Réessayez dans un instant."
        if resp.status_code >= 400:
            return [], detected_language, f"Erreur API Groq ({resp.status_code}) : {resp.text[:300]}"

        payload = resp.json()
        if payload.get("language"):
            detected_language = str(payload["language"])

        segments = payload.get("segments") or []
        if segments:
            for seg in segments:
                text = (seg.get("text") or "").strip()
                if not text:
                    continue
                start = float(seg.get("start", 0.0)) + offset_sec
                end = float(seg.get("end", start)) + offset_sec
                all_snippets.append({
                    "text": text,
                    "start": start,
                    "duration": max(0.0, end - start)
                })
        else:
            full_text = (payload.get("text") or "").strip()
            if full_text:
                chunk_dur = _get_media_duration(chunk_path)
                all_snippets.append({
                    "text": full_text,
                    "start": offset_sec,
                    "duration": chunk_dur
                })

    if not all_snippets:
        return [], detected_language, "L'API Groq n'a retourné aucune parole détectable dans cet audio."

    return all_snippets, detected_language, None


def _language_hint_from_prefs(preferred_languages: Optional[List[str]]) -> Optional[str]:
    if not preferred_languages:
        return None
    first = preferred_languages[0].split("-")[0].lower()
    return first if len(first) == 2 else None


def _lang_display_name(code: str) -> str:
    c = (code or "").lower()
    if c.startswith("fr") or c == "french":
        return "Français"
    if c.startswith("en") or c == "english":
        return "Anglais"
    return code or "Auto"


def _transcribe_url_via_groq(
    url: str,
    api_key: str,
    preferred_languages: Optional[List[str]],
    include_timestamps: bool,
    include_header: bool,
    metadata: Optional[Dict[str, Any]] = None,
    video_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Télécharge uniquement la piste audio d'une URL via yt-dlp puis la transcrit avec Groq Whisper.
    """
    try:
        import yt_dlp
    except ImportError:
        return {"success": False, "error": "yt-dlp n'est pas installé.", "video_id": video_id, "metadata": metadata}

    with tempfile.TemporaryDirectory() as tmp_dir:
        work_dir = Path(tmp_dir)
        out_template = str(work_dir / "source_audio.%(ext)s")

        # Plusieurs profils clients YouTube pour contourner les erreurs 403 sur IP cloud
        client_profiles = [
            {"youtube": {"player_client": ["android_vr", "tv"]}},
            {"youtube": {"player_client": ["ios", "mweb"]}},
            {},
        ]

        info = None
        last_error = ""
        downloaded_files: List[Path] = []

        for profile in client_profiles:
            # Nettoyer d'éventuels fichiers partiels d'une tentative précédente
            for old in work_dir.glob("source_audio.*"):
                old.unlink(missing_ok=True)

            ydl_opts: Dict[str, Any] = {
                "format": "bestaudio[ext=m4a]/bestaudio/best",
                "outtmpl": out_template,
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
                "nocheckcertificate": True,
            }
            if profile:
                ydl_opts["extractor_args"] = profile

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                downloaded_files = [
                    p for p in work_dir.glob("source_audio.*")
                    if p.is_file() and not p.name.endswith(".part")
                ]
                if downloaded_files:
                    break
            except Exception as e:
                last_error = str(e)
                continue

        if metadata is None and info:
            metadata = {
                "title": info.get("title") or "Vidéo en ligne",
                "author_name": info.get("uploader") or info.get("channel") or "Auteur inconnu",
                "author_url": info.get("uploader_url") or "",
                "thumbnail_url": info.get("thumbnail") or "",
                "video_url": url
            }

        if not downloaded_files:
            hint = (
                " (YouTube bloque le téléchargement audio depuis l'IP du serveur cloud. "
                "Astuce : téléchargez l'audio/vidéo sur votre appareil et importez-le dans l'onglet « 📁 Fichier Audio / Vidéo ».)"
                if "403" in last_error
                else ""
            )
            return {
                "success": False,
                "error": f"Impossible de télécharger l'audio de cette vidéo : {last_error[:220]}{hint}",
                "video_id": video_id,
                "metadata": metadata
            }

        chunks, prep_err = _prepare_audio_chunks(downloaded_files[0], work_dir)
        if prep_err:
            return {"success": False, "error": prep_err, "video_id": video_id, "metadata": metadata}

        lang_hint = _language_hint_from_prefs(preferred_languages)
        snippets, detected_lang, groq_err = _transcribe_chunks_with_groq(chunks, api_key, language_hint=lang_hint)
        if groq_err:
            return {"success": False, "error": groq_err, "video_id": video_id, "metadata": metadata}

        return _format_success_result(
            video_id=video_id or "url",
            metadata=metadata or {"title": "Vidéo en ligne", "author_name": "Inconnu", "video_url": url},
            snippets=snippets,
            lang_name=_lang_display_name(detected_lang),
            lang_code=detected_lang,
            is_generated=True,
            include_timestamps=include_timestamps,
            include_header=include_header,
            source_type="groq_whisper"
        )


def transcribe_uploaded_media(
    file_bytes: bytes,
    filename: str,
    groq_api_key: str,
    preferred_languages: Optional[List[str]] = None,
    include_timestamps: bool = False,
    include_header: bool = True
) -> Dict[str, Any]:
    """
    Extrait l'audio d'un fichier vidéo ou audio importé et le transcrit via Groq Whisper.
    """
    if not groq_api_key or not groq_api_key.strip():
        return {"success": False, "error": "Clé API Groq requise pour transcrire un fichier audio/vidéo."}

    metadata = {
        "title": Path(filename).stem or "Fichier média",
        "author_name": "Fichier local importé",
        "author_url": "",
        "thumbnail_url": "",
        "video_url": filename
    }

    with tempfile.TemporaryDirectory() as tmp_dir:
        work_dir = Path(tmp_dir)
        suffix = Path(filename).suffix or ".mp4"
        input_path = work_dir / f"upload{suffix}"
        input_path.write_bytes(file_bytes)

        chunks, prep_err = _prepare_audio_chunks(input_path, work_dir)
        if prep_err:
            return {"success": False, "error": prep_err, "metadata": metadata}

        lang_hint = _language_hint_from_prefs(preferred_languages)
        snippets, detected_lang, groq_err = _transcribe_chunks_with_groq(chunks, groq_api_key, language_hint=lang_hint)
        if groq_err:
            return {"success": False, "error": groq_err, "metadata": metadata}

        return _format_success_result(
            video_id="local_file",
            metadata=metadata,
            snippets=snippets,
            lang_name=_lang_display_name(detected_lang),
            lang_code=detected_lang,
            is_generated=True,
            include_timestamps=include_timestamps,
            include_header=include_header,
            source_type="groq_whisper"
        )


def get_youtube_transcript(
    url_or_id: str,
    preferred_languages: Optional[List[str]] = None,
    include_timestamps: bool = False,
    include_header: bool = True,
    groq_api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Extrait et formate la transcription complète d'une vidéo YouTube (ou autre lien vidéo si Groq est activé).
    1. Sous-titres via YouTubeTranscriptApi (gratuit, instantané)
    2. Secours sous-titres via yt-dlp (gratuit, instantané)
    3. Secours audio IA via Groq Whisper si aucun sous-titre n'existe et qu'une clé Groq est fournie
    """
    if preferred_languages is None:
        preferred_languages = ['fr', 'fr-FR', 'fr-CA', 'en', 'en-US', 'en-GB']

    candidate = (url_or_id or "").strip()
    video_id = extract_video_id(candidate)
    if not video_id:
        # Support de n'importe quelle URL vidéo (TikTok, Vimeo, Instagram, etc.) si Groq est configuré
        if candidate.startswith(("http://", "https://")) and groq_api_key and groq_api_key.strip():
            return _transcribe_url_via_groq(
                url=candidate,
                api_key=groq_api_key,
                preferred_languages=preferred_languages,
                include_timestamps=include_timestamps,
                include_header=include_header
            )
        return {
            "success": False,
            "error": "Lien YouTube invalide. Veuillez vérifier l'URL ou l'identifiant.",
            "video_id": None
        }

    metadata = get_video_metadata(video_id)
    ytt = YouTubeTranscriptApi()

    # Tentative 1 : via youtube_transcript_api
    try:
        transcript_list = ytt.list(video_id)
        
        available_langs = []
        for t in transcript_list:
            available_langs.append({
                "code": t.language_code,
                "name": t.language,
                "is_generated": t.is_generated
            })

        selected_transcript = None
        for lang in preferred_languages:
            try:
                selected_transcript = transcript_list.find_transcript([lang])
                break
            except Exception:
                continue

        if selected_transcript is None:
            try:
                for t in transcript_list:
                    selected_transcript = t
                    break
            except Exception:
                pass

        if selected_transcript is not None:
            snippets = list(selected_transcript.fetch())
            if snippets:
                return _format_success_result(
                    video_id=video_id,
                    metadata=metadata,
                    snippets=snippets,
                    lang_name=selected_transcript.language,
                    lang_code=selected_transcript.language_code,
                    is_generated=selected_transcript.is_generated,
                    include_timestamps=include_timestamps,
                    include_header=include_header,
                    available_languages=available_langs
                )

    except (IpBlocked, RequestBlocked, Exception):
        # En cas de blocage IP ou toute erreur réseau, passer au moteur de secours
        pass

    # Tentative 2 (Moteur de secours) : via yt-dlp
    fallback_res = get_transcript_via_ytdlp(video_id, preferred_languages)
    if fallback_res is not None:
        snippets, lang_code, is_generated = fallback_res
        lang_name = "Français" if lang_code.startswith("fr") else ("Anglais" if lang_code.startswith("en") else lang_code)
        return _format_success_result(
            video_id=video_id,
            metadata=metadata,
            snippets=snippets,
            lang_name=lang_name,
            lang_code=lang_code,
            is_generated=is_generated,
            include_timestamps=include_timestamps,
            include_header=include_header
        )

    # Tentative 3 (Secours IA) : téléchargement audio + Groq Whisper si aucun sous-titre
    if groq_api_key and groq_api_key.strip():
        return _transcribe_url_via_groq(
            url=f"https://www.youtube.com/watch?v={video_id}",
            api_key=groq_api_key,
            preferred_languages=preferred_languages,
            include_timestamps=include_timestamps,
            include_header=include_header,
            metadata=metadata,
            video_id=video_id
        )

    # Si aucun moteur n'a réussi
    return {
        "success": False,
        "error": "Aucune transcription ou sous-titre disponible sur cette vidéo. Activez le secours IA Groq dans la barre latérale pour la transcrire depuis l'audio.",
        "video_id": video_id,
        "metadata": metadata
    }
