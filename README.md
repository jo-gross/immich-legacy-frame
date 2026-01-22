# Immich Slideshow

Eine einfache Slideshow-Anwendung, die Bilder aus Immich lädt und anzeigt. Optimiert für alte Browser und den Einsatz in Docker.

## Features

- ✅ Läuft auf alten Browsern (Vanilla JavaScript, keine modernen Features)
- ✅ Zeigt alle Bilder aus Immich an
- ✅ Automatische Bildkonvertierung für Kompatibilität
- ✅ Passwort-Schutz via Umgebungsvariable
- ✅ Docker-ready
- ✅ Bilder werden mit schwarzem Hintergrund skaliert (contain-Modus)
- ✅ Konfigurierbares Intervall via Query-Parameter

## Voraussetzungen

- Docker und Docker Compose (oder Python 3.11+)
- Immich-Instanz mit API-Zugriff

## Installation und Start

### Mit Docker Compose

1. Erstelle eine `.env` Datei im Projektverzeichnis:

```env
IMMICH_URL=https://deine-immich-instanz.de
IMMICH_API_KEY=dein-api-key
PASSWORD=dein-passwort  # Optional: Wenn leer, kein Passwort-Schutz
```

2. Starte den Container:

```bash
docker-compose up -d
```

3. Öffne im Browser: `http://localhost:5000`

### Ohne Docker

1. Installiere Abhängigkeiten:

```bash
pip install -r requirements.txt
```

2. Setze Umgebungsvariablen:

```bash
export IMMICH_URL=https://deine-immich-instanz.de
export IMMICH_API_KEY=dein-api-key
export PASSWORD=dein-passwort  # Optional
```

3. Starte die Anwendung:

```bash
python app.py
```

## Verwendung

### Basis-URL

```
http://localhost:5000/
```

### Mit Passwort (wenn PASSWORD gesetzt ist)

```
http://localhost:5000/?password=dein-passwort
```

### Mit Intervall (Sekunden)

```
http://localhost:5000/?password=dein-passwort&interval=10
```

Standard-Intervall: 5 Sekunden

## Umgebungsvariablen

| Variable | Beschreibung | Erforderlich |
|----------|-------------|--------------|
| `IMMICH_URL` | URL zu deiner Immich-Instanz (ohne trailing slash) | Ja |
| `IMMICH_API_KEY` | API-Key von Immich | Ja |
| `PASSWORD` | Passwort für Zugriffsschutz (optional) | Nein |

## Technologie-Stack

- **Backend**: Python 3.11 + Flask
- **Frontend**: Vanilla HTML/CSS/JavaScript (altbrowser-kompatibel)
- **Bildverarbeitung**: Pillow (für Konvertierung)
- **Server**: Gunicorn (Produktion)

## Browser-Kompatibilität

Die Anwendung ist kompatibel mit:
- Internet Explorer 11+
- Chrome/Edge (alte Versionen)
- Firefox (alte Versionen)
- Safari (alte Versionen)

Verwendet keine modernen JavaScript-Features wie:
- ES6+ Syntax (Arrow Functions, Template Literals, etc.)
- Fetch API (verwendet XMLHttpRequest)
- Modern CSS Features (nur Basis-Features)

## API Endpoints

- `GET /` - Hauptseite mit Slideshow
- `GET /api/images` - Liste aller Bilder von Immich
- `GET /api/image/<id>` - Einzelnes Bild (mit optionaler Konvertierung)

## Entwicklung

Für lokale Entwicklung:

```bash
python app.py
```

Die Anwendung läuft dann im Debug-Modus auf `http://localhost:5000`.

## Lizenz

MIT

