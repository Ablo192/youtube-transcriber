# 🎙️ Transcripteur YouTube Pro

Outil complet pour extraire, nettoyer et formater les transcriptions de vidéos YouTube à partir de simples liens.

Le texte généré est **parfaitement structuré en paragraphes fluides**, débarrassé des coupures hachées et des bruits parasites (`[Musique]`, etc.), optimisé pour la lecture ou pour être injecté directement dans des modèles d'IA (**ChatGPT**, **Claude**, **Google Gemini**, **Mistral**).

---

## 🚀 1. Lancement rapide (Interface Web)

### Méthode 1 : Double-clic (Recommandé)
- Double-cliquez simplement sur le fichier **`Lancer_Transcripteur_YouTube.bat`** situé à la racine du dossier.
- Votre navigateur par défaut s'ouvrira automatiquement à l'adresse `http://localhost:8501`.

### Méthode 2 : En ligne de commande
```bash
python -m streamlit run youtube_transcriber/app.py
```

---

## 🛠️ 2. Utilisation en Ligne de Commande (CLI)

Pour les automatisations ou une utilisation rapide dans le terminal :

```bash
# Afficher la transcription d'une vidéo dans le terminal
python youtube_transcriber/cli.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# Sauvegarder dans un fichier texte
python youtube_transcriber/cli.py "https://youtu.be/dQw4w9WgXcQ" -o transcription.txt

# Inclure les horodatages [MM:SS]
python youtube_transcriber/cli.py "https://youtu.be/dQw4w9WgXcQ" --timestamps -o avec_temps.txt

# Traiter une liste de plusieurs vidéos (fichier texte contenant un lien par ligne)
python youtube_transcriber/cli.py --file mes_liens.txt --out-dir mes_transcriptions/
```

---

## ✨ Fonctionnalités incluses

1. **Extraction instantanée sans clé API** : Utilise les pistes officielles et auto-générées fournies par YouTube.
2. **Nettoyage intelligent** :
   - Regroupement des fragments en paragraphes cohérents selon les pauses orales.
   - Suppression des balises non verbales (`[Musique]`, `[Applaudissements]`, notes de musique).
   - En-tête informatif avec titre, chaîne, URL, durée et nombre de mots.
3. **Traitement par lot (Batch)** : Collez 10 ou 50 liens à la suite pour tout récupérer d'un seul coup et télécharger un fichier combiné ou individuel.
4. **Téléchargement 1-clic** : Format texte brut `.txt` ou format avec prompt IA intégré.
5. **Support de tous les formats d'URL** : `watch?v=...`, `youtu.be/...`, `shorts/...`, `live/...`, ou identifiant seul.
