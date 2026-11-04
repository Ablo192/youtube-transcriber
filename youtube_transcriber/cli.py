"""
Interface en ligne de commande (CLI) pour le transcripteur YouTube.
Exemples d'utilisation :
  python cli.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
  python cli.py "https://youtu.be/dQw4w9WgXcQ" -o transcription.txt
  python cli.py --file liste_videos.txt --out-dir transcriptions/
"""

import sys
import argparse
from pathlib import Path
from transcriber import get_youtube_transcript


def main():
    parser = argparse.ArgumentParser(
        description="Récupère la transcription d'une ou plusieurs vidéos YouTube en texte brut propre pour l'IA."
    )
    parser.add_argument(
        "url",
        nargs="?",
        help="Lien ou identifiant de la vidéo YouTube (ex: https://www.youtube.com/watch?v=...)"
    )
    parser.add_argument(
        "-f", "--file",
        help="Chemin vers un fichier texte contenant une liste de liens YouTube (un par ligne)"
    )
    parser.add_argument(
        "-o", "--output",
        help="Fichier de sortie (.txt) pour sauvegarder la transcription"
    )
    parser.add_argument(
        "--out-dir",
        default="transcriptions",
        help="Dossier de sortie lors du traitement par lot (défaut: 'transcriptions')"
    )
    parser.add_argument(
        "-t", "--timestamps",
        action="store_true",
        help="Inclure les horodatages [MM:SS] dans la transcription"
    )
    parser.add_argument(
        "--no-header",
        action="store_true",
        help="Ne pas inclure l'en-tête informatif (titre, URL, auteur)"
    )
    parser.add_argument(
        "-l", "--lang",
        default="fr,en",
        help="Codes de langues prioritaires séparés par une virgule (défaut: 'fr,en')"
    )

    args = parser.parse_args()

    # Reconfigurer la sortie pour gérer l'UTF-8 sur Windows
    if sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass

    preferred_langs = [code.strip() for code in args.lang.split(",") if code.strip()]

    # Cas 1 : Traitement par fichier de liens
    if args.file:
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"❌ Erreur : Le fichier '{args.file}' est introuvable.")
            sys.exit(1)

        urls = [line.strip() for line in file_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        print(f"📁 Traitement de {len(urls)} vidéo(s)...")
        for i, url in enumerate(urls, start=1):
            print(f"\n[{i}/{len(urls)}] Récupération : {url}")
            res = get_youtube_transcript(
                url_or_id=url,
                preferred_languages=preferred_langs,
                include_timestamps=args.timestamps,
                include_header=not args.no_header
            )
            if res["success"]:
                vid_id = res["video_id"]
                out_path = out_dir / f"transcription_{vid_id}.txt"
                out_path.write_text(res["clean_text"], encoding="utf-8")
                print(f"  ✅ Succès : {res['metadata']['title'][:50]} ({res['word_count']} mots) -> {out_path.name}")
            else:
                print(f"  ❌ Échec : {res['error']}")
        return

    # Cas 2 : URL unique
    if args.url:
        print(f"🔍 Analyse de la vidéo : {args.url} ...")
        res = get_youtube_transcript(
            url_or_id=args.url,
            preferred_languages=preferred_langs,
            include_timestamps=args.timestamps,
            include_header=not args.no_header
        )
        if res["success"]:
            print(f"✅ Transcription récupérée avec succès !")
            print(f"   Titre : {res['metadata']['title']}")
            print(f"   Langue : {res['language']} | Mots : {res['word_count']} | Durée : {res['duration_formatted']}")
            print("-" * 60)

            if args.output:
                out_file = Path(args.output)
                out_file.parent.mkdir(parents=True, exist_ok=True)
                out_file.write_text(res["clean_text"], encoding="utf-8")
                print(f"💾 Sauvegardé dans : {out_file.resolve()}")
            else:
                print(res["clean_text"])
        else:
            print(f"❌ Erreur : {res['error']}")
            sys.exit(1)
        return

    # Si aucun argument n'est fourni
    parser.print_help()


if __name__ == "__main__":
    main()
