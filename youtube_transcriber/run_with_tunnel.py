"""
Lanceur avec tunnel sécurisé Cloudflare.
Permet d'accéder à l'application depuis n'importe où dans le monde (4G, 5G, extérieur)
sans aucune configuration de box ou de routeur, 100% gratuit et chiffré en HTTPS.
"""

import sys
import os
import re
import time
import subprocess
import threading
from pathlib import Path

# Assurer l'encodage UTF-8 sous Windows pour les caractères spéciaux et emojis
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

# Chemins de base
BASE_DIR = Path(__file__).resolve().parent
CLOUDFLARED_EXE = BASE_DIR / "cloudflared.exe"
TUNNEL_URL_FILE = BASE_DIR / "tunnel_url.txt"
APP_FILE = BASE_DIR / "app.py"


def clean_exit():
    if TUNNEL_URL_FILE.exists():
        try:
            TUNNEL_URL_FILE.unlink()
        except Exception:
            pass


def main():
    if not CLOUDFLARED_EXE.exists():
        print(f"❌ Erreur : {CLOUDFLARED_EXE.name} est introuvable dans {BASE_DIR}")
        sys.exit(1)

    print("=" * 70)
    print("      🚀 LANCEMENT DU TRANSSCRIPTEUR AVEC ACCÈS MOBILE 4G/5G")
    print("=" * 70)
    print("\n1. Démarrage du serveur local Streamlit (port 8501)...")

    # Démarrage de Streamlit si pas déjà en cours
    streamlit_proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", str(APP_FILE), "--server.port", "8501", "--server.headless", "true"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    time.sleep(2)

    print("2. Création du tunnel sécurisé Cloudflare (accès 4G/5G)...")
    
    # Lancement de cloudflared
    cloudflared_proc = subprocess.Popen(
        [str(CLOUDFLARED_EXE), "tunnel", "--url", "http://localhost:8501", "--no-autoupdate"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="ignore",
        bufsize=1
    )

    public_url = None
    url_pattern = re.compile(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com')

    # Lecture des logs de cloudflared pour extraire l'URL publique
    def monitor_cloudflared():
        nonlocal public_url
        for line in cloudflared_proc.stdout:
            match = url_pattern.search(line)
            if match and not public_url:
                public_url = match.group(0)
                # Sauvegarder l'URL pour l'interface Streamlit
                TUNNEL_URL_FILE.write_text(public_url, encoding="utf-8")
                
                print("\n" + "=" * 70)
                print("🎉 SUCCÈS ! VOTRE APPLICATION EST EN LIGNE ET ACCESSIBLE EN 4G/5G !")
                print("=" * 70)
                print("\n👉 LIEN UNIQUE POUR VOTRE MOBILE :")
                print(f"   {public_url}")
                print("\n📱 Comment l'utiliser sur smartphone :")
                print("   1. Ouvrez Safari ou Chrome sur votre téléphone (en 4G/5G ou Wi-Fi).")
                print(f"   2. Collez l'adresse : {public_url}")
                print("   3. (Astuce) Ajoutez la page à l'écran d'accueil de votre téléphone")
                print("      pour l'utiliser comme une vraie application native !")
                print("\n" + "-" * 70)
                print("🖥️ Accès sur votre ordinateur : http://localhost:8501")
                print("=" * 70)
                print("\n(Laissez cette fenêtre ouverte pendant l'utilisation. Appuyez sur Ctrl+C pour arrêter)\n")

    t = threading.Thread(target=monitor_cloudflared, daemon=True)
    t.start()

    # Attendre que l'URL soit détectée ou timeout
    timeout = 30
    start_t = time.time()
    while not public_url and (time.time() - start_t) < timeout:
        time.sleep(0.5)

    if not public_url:
        print("⚠️ Le tunnel met plus de temps que prévu à s'initialiser. Vérifiez votre connexion Internet.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\nArrêt du serveur et fermeture du tunnel...")
    finally:
        clean_exit()
        cloudflared_proc.terminate()
        streamlit_proc.terminate()
        print("Fermeture terminée. À bientôt !")


if __name__ == "__main__":
    main()
