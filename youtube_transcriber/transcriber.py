"""
Module d'extraction et de nettoyage de transcriptions YouTube.
Permet d'extraire les sous-titres officiels et auto-générés de vidéos YouTube
et de les formater en texte brut propre, optimisé pour la lecture humaine et les LLM (IA).
"""

import re
import json
import urllib.request
import urllib.error
from typing import Dict, List, Optional, Tuple, Any
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
    available_languages: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """Helper pour formater un résultat de transcription réussi."""
    total_duration_sec = snippets[-1]['start'] + snippets[-1]['duration'] if isinstance(snippets[-1], dict) else (snippets[-1].start + snippets[-1].duration if snippets else 0.0)
    clean_body = build_paragraphs(snippets, include_timestamps=include_timestamps)
    total_words = len(clean_body.split())
    estimated_reading_time_min = max(1, round(total_words / 200))

    header = ""
    if include_header:
        header_lines = [
            f"# {metadata['title']}",
            f"- **Chaîne / Auteur** : {metadata['author_name']}",
            f"- **Lien vidéo** : {metadata['video_url']}",
            f"- **Langue** : {lang_name} ({lang_code})",
            f"- **Type de sous-titres** : {'Générés automatiquement' if is_generated else 'Manuels / Officiels'}",
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
        "duration_formatted": format_seconds(total_duration_sec),
        "word_count": total_words,
        "reading_time_min": estimated_reading_time_min,
        "clean_text": full_text,
        "raw_text_only": clean_body,
        "available_languages": available_languages or [{"code": lang_code, "name": lang_name, "is_generated": is_generated}]
    }


def get_youtube_transcript(
    url_or_id: str,
    preferred_languages: Optional[List[str]] = None,
    include_timestamps: bool = False,
    include_header: bool = True
) -> Dict[str, Any]:
    """
    Extrait et formate la transcription complète d'une vidéo YouTube.
    Bénéficie d'un double moteur (YouTubeTranscriptApi + secours automatique yt-dlp anti-blocage IP).
    """
    if preferred_languages is None:
        preferred_languages = ['fr', 'fr-FR', 'fr-CA', 'en', 'en-US', 'en-GB']

    video_id = extract_video_id(url_or_id)
    if not video_id:
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

    # Si les deux moteurs n'ont rien trouvé
    return {
        "success": False,
        "error": "Aucune transcription ou sous-titre disponible sur cette vidéo.",
        "video_id": video_id,
        "metadata": metadata
    }
