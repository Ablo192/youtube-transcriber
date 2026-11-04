import sys
from pathlib import Path

# Ajouter le sous-dossier youtube_transcriber au chemin de recherche Python
base_dir = Path(__file__).resolve().parent
pkg_dir = base_dir / "youtube_transcriber"
if str(pkg_dir) not in sys.path:
    sys.path.insert(0, str(pkg_dir))

# Exécuter l'application principale
import runpy
app_script = pkg_dir / "app.py"
runpy.run_path(str(app_script), run_name="__main__")
