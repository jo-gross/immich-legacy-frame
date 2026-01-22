import os
import random
import requests
from flask import Flask, render_template, request, jsonify, send_file
from io import BytesIO
from PIL import Image

app = Flask(__name__)

# Umgebungsvariablen
IMMICH_URL = os.getenv('IMMICH_URL', '').rstrip('/')
IMMICH_API_KEY = os.getenv('IMMICH_API_KEY', '')
PASSWORD = os.getenv('PASSWORD', '')

# Globaler Cache für Asset IDs
asset_ids_cache = []
cache_loaded = False


def check_password():
    """Prüft ob Passwort-Schutz aktiv ist und ob das Passwort korrekt ist"""
    if not PASSWORD:
        return True  # Kein Passwort gesetzt, Zugriff erlaubt
    
    provided_password = request.args.get('password', '')
    return provided_password == PASSWORD


def load_asset_ids():
    """Lädt alle Asset IDs von Immich und cached sie"""
    global asset_ids_cache, cache_loaded
    
    if cache_loaded:
        return asset_ids_cache
    
    if not IMMICH_URL or not IMMICH_API_KEY:
        app.logger.error('Immich configuration missing, cannot load assets')
        return []
    
    headers = {
        'x-api-key': IMMICH_API_KEY
    }
    
    all_asset_ids = []
    asset_ids_seen = set()
    
    try:
        # Schritt 1: Lade alle Alben
        app.logger.info(f'Loading asset IDs from Immich: {IMMICH_URL}/api/albums')
        albums_response = requests.get(
            f'{IMMICH_URL}/api/albums',
            headers=headers,
            timeout=30
        )
        
        if albums_response.status_code != 200:
            app.logger.error(f'Failed to load albums: {albums_response.status_code}')
            return []
        
        albums_data = albums_response.json()
        albums = albums_data if isinstance(albums_data, list) else albums_data.get('items', albums_data.get('albums', []))
        
        app.logger.info(f'Found {len(albums)} albums')
        
        # Schritt 2: Lade Assets aus jedem Album
        for album in albums:
            album_id = album.get('id')
            if not album_id:
                continue
            
            try:
                # Versuche zuerst, ob das Album-Objekt bereits Assets enthält
                album_assets = album.get('assets', [])
                
                # Falls nicht, hole das Album-Detail
                if not album_assets:
                    album_detail_response = requests.get(
                        f'{IMMICH_URL}/api/albums/{album_id}',
                        headers=headers,
                        timeout=10
                    )
                    
                    if album_detail_response.status_code == 200:
                        album_detail = album_detail_response.json()
                        album_assets = album_detail.get('assets', album_detail.get('assetIds', []))
                    else:
                        continue
                
                # Extrahiere Asset IDs
                for asset in album_assets:
                    asset_id = None
                    if isinstance(asset, dict):
                        asset_id = asset.get('id')
                        asset_type = asset.get('type') or asset.get('mimeType', '')
                    elif isinstance(asset, str):
                        asset_id = asset
                        asset_type = None
                    
                    # Nur Bilder hinzufügen
                    if asset_id and asset_id not in asset_ids_seen:
                        # Prüfe ob es ein Bild ist
                        is_image = False
                        if asset_type == 'IMAGE':
                            is_image = True
                        elif isinstance(asset_type, str) and asset_type.startswith('image/'):
                            is_image = True
                        elif not asset_type:  # Wenn kein Typ, versuche es als Bild
                            is_image = True
                        
                        if is_image:
                            all_asset_ids.append(asset_id)
                            asset_ids_seen.add(asset_id)
                            
            except requests.exceptions.RequestException:
                continue
        
        asset_ids_cache = all_asset_ids
        cache_loaded = True
        app.logger.info(f'Loaded {len(asset_ids_cache)} image asset IDs into cache')
        
    except Exception as e:
        app.logger.error(f'Error loading asset IDs: {str(e)}')
        return []
    
    return asset_ids_cache


@app.route('/')
def index():
    """Hauptseite mit Slideshow"""
    if not check_password():
        return render_template('password.html'), 401
    
    interval = request.args.get('interval', '5')
    try:
        interval = int(interval)
        if interval < 1:
            interval = 5
    except ValueError:
        interval = 5
    
    return render_template('index.html', interval=interval)


@app.route('/api/debug')
def debug():
    """Debug-Endpoint zum Prüfen der Konfiguration"""
    debug_info = {
        'immich_url_set': bool(IMMICH_URL),
        'immich_url': IMMICH_URL if IMMICH_URL else 'NOT SET',
        'api_key_set': bool(IMMICH_API_KEY),
        'password_set': bool(PASSWORD),
        'password_provided': bool(request.args.get('password')),
        'password_match': check_password() if PASSWORD else 'N/A (no password required)'
    }
    return jsonify(debug_info)


@app.route('/api/random-image')
def get_random_image():
    """Gibt ein zufälliges Bild zurück"""
    if not check_password():
        return jsonify({'error': 'Unauthorized'}), 401
    
    # Stelle sicher, dass Cache geladen ist
    ensure_cache_loaded()
    
    asset_ids = asset_ids_cache
    
    if not asset_ids:
        return jsonify({'error': 'No images available'}), 404
    
    # Wähle zufälliges Asset
    random_asset_id = random.choice(asset_ids)
    
    # Erstelle URLs
    image_url = f"{IMMICH_URL}/api/assets/{random_asset_id}/original"
    
    return jsonify({
        'id': random_asset_id,
        'url': image_url
    })


@app.route('/api/images')
def get_images():
    """API Endpoint zum Abrufen der Bilderliste von Immich"""
    if not check_password():
        return jsonify({'error': 'Unauthorized'}), 401
    
    if not IMMICH_URL or not IMMICH_API_KEY:
        return jsonify({'error': 'Immich configuration missing'}), 500
    
    try:
        headers = {
            'x-api-key': IMMICH_API_KEY
        }
        
        # Hole alle Assets von Immich über Alben
        # Ansatz: Zuerst alle Alben laden, dann Assets aus jedem Album
        all_assets = []
        asset_ids_seen = set()  # Um Duplikate zu vermeiden
        
        try:
            # Schritt 1: Lade alle Alben
            app.logger.info(f'Fetching albums from Immich: {IMMICH_URL}/api/albums')
            albums_response = requests.get(
                f'{IMMICH_URL}/api/albums',
                headers=headers,
                timeout=10
            )
            
            if albums_response.status_code != 200:
                error_msg = f'{IMMICH_URL}/api/albums returned {albums_response.status_code}'
                try:
                    error_data = albums_response.json()
                    if isinstance(error_data, dict) and 'message' in error_data:
                        error_msg += f" - {error_data['message']}"
                except Exception:
                    error_msg += f" - {albums_response.text[:200]}"
                
                app.logger.error(f'Immich API error: {IMMICH_URL}/api/albums - {error_msg}')
                return jsonify({'error': error_msg}), 500
            
            albums_data = albums_response.json()
            albums = albums_data if isinstance(albums_data, list) else albums_data.get('items', albums_data.get('albums', []))
            
            app.logger.info(f'Found {len(albums)} albums')
            
            # Schritt 2: Lade Assets aus jedem Album
            # Das Album-Objekt enthält bereits die Assets, oder wir müssen das Album-Detail abrufen
            for album in albums:
                album_id = album.get('id')
                if not album_id:
                    continue
                
                try:
                    app.logger.info(f'Fetching album details for {album_id}')
                    
                    # Versuche zuerst, ob das Album-Objekt bereits Assets enthält
                    album_assets = album.get('assets', [])
                    
                    # Falls nicht, hole das Album-Detail
                    if not album_assets:
                        album_detail_response = requests.get(
                            f'{IMMICH_URL}/api/albums/{album_id}',
                            headers=headers,
                            timeout=10
                        )
                        
                        if album_detail_response.status_code == 200:
                            album_detail = album_detail_response.json()
                            album_assets = album_detail.get('assets', album_detail.get('assetIds', []))
                        else:
                            app.logger.warning(f'Failed to fetch album detail {album_id}: {album_detail_response.status_code}')
                            continue
                    
                    # Füge Assets hinzu, wenn sie noch nicht vorhanden sind
                    for asset in album_assets:
                        # Asset könnte ein Objekt oder nur eine ID sein
                        if isinstance(asset, dict):
                            asset_id = asset.get('id')
                            if asset_id and asset_id not in asset_ids_seen:
                                all_assets.append(asset)
                                asset_ids_seen.add(asset_id)
                        elif isinstance(asset, str):
                            # Wenn es nur eine ID ist, müssen wir das Asset separat laden
                            if asset not in asset_ids_seen:
                                try:
                                    asset_detail_response = requests.get(
                                        f'{IMMICH_URL}/api/assets/{asset}',
                                        headers=headers,
                                        timeout=10
                                    )
                                    if asset_detail_response.status_code == 200:
                                        asset_detail = asset_detail_response.json()
                                        all_assets.append(asset_detail)
                                        asset_ids_seen.add(asset)
                                except requests.exceptions.RequestException:
                                    continue
                    
                    app.logger.info(f'Found {len(album_assets)} assets in album {album_id}')
                        
                except requests.exceptions.RequestException as e:
                    app.logger.warning(f'Error fetching assets from album {album_id}: {str(e)}')
                    continue
            
            app.logger.info(f'Total unique assets found: {len(all_assets)}')
            
        except requests.exceptions.RequestException as e:
            app.logger.error(f'Failed to connect to Immich API: {str(e)}')
            return jsonify({'error': f'Failed to connect to Immich: {str(e)}'}), 500
        
        # Extrahiere Bild-URLs
        images = []
        for asset in all_assets:
            # Prüfe verschiedene mögliche Typ-Felder
            asset_type = asset.get('type') or asset.get('mimeType', '') or asset.get('exifInfo', {}).get('mimeType', '')
            asset_id = asset.get('id')
            
            # Akzeptiere IMAGE oder wenn mimeType mit 'image/' beginnt
            is_image = False
            if asset_type == 'IMAGE':
                is_image = True
            elif isinstance(asset_type, str) and asset_type.startswith('image/'):
                is_image = True
            # Fallback: Wenn kein Typ gesetzt ist, aber es ein Asset ist, versuche es als Bild
            elif not asset_type and asset_id:
                is_image = True
            
            if is_image and asset_id:
                # Verwende korrekte Immich API-Endpunkte
                # GET /api/assets/{id}/thumbnail - für Thumbnails (singular "asset")
                # GET /api/assets/{id}/original - für Originaldateien (singular "asset")
                thumbnail_url = f"{IMMICH_URL}/api/assets/{asset_id}/thumbnail"
                file_url = f"{IMMICH_URL}/api/assets/{asset_id}/original"
                
                images.append({
                    'id': asset_id,
                    'url': thumbnail_url,
                    'originalUrl': file_url
                })
        
        # Zufällige Auswahl von Bildern
        max_images = 5  # Maximale Anzahl zufälliger Bilder
        if len(images) > max_images:
            images = random.sample(images, max_images)
        else:
            # Mische die Liste für zufällige Reihenfolge
            random.shuffle(images)
        
        # Debug-Logging
        app.logger.info(f"Selected {len(images)} random images from {len(all_assets)} total assets")
        
        return jsonify({'images': images})
    
    except requests.exceptions.RequestException as e:
        app.logger.error(f'Failed to fetch images from Immich: {str(e)}')
        return jsonify({'error': f'Failed to fetch images: {str(e)}'}), 500
    except Exception as e:
        app.logger.error(f'Unexpected error in get_images: {str(e)}')
        return jsonify({'error': f'Unexpected error: {str(e)}'}), 500


@app.route('/api/image/<image_id>')
def get_image(image_id):
    """Proxy für Bilder mit optionaler Konvertierung"""
    if not check_password():
        return jsonify({'error': 'Unauthorized'}), 401
    
    if not IMMICH_URL or not IMMICH_API_KEY:
        return jsonify({'error': 'Immich configuration missing'}), 500
    
    try:
        headers = {
            'x-api-key': IMMICH_API_KEY
        }
        
        # Hole das Bild von Immich
        # Verwende korrekten Immich API-Endpunkt
        # GET /api/assets/{id}/original - für Originaldateien (singular "asset")
        image_url = f'{IMMICH_URL}/api/assets/{image_id}/original'
        
        try:
            response = requests.get(image_url, headers=headers, timeout=30)
            
            if response.status_code != 200:
                error_msg = f'Failed to fetch image: {response.status_code}'
                try:
                    error_data = response.json()
                    if isinstance(error_data, dict) and 'message' in error_data:
                        error_msg += f" - {error_data['message']}"
                except Exception:
                    error_msg += f" - {response.text[:200]}"
                app.logger.error(error_msg)
                return jsonify({'error': error_msg}), 500
                
        except requests.exceptions.RequestException as e:
            app.logger.error(f'Failed to fetch image from Immich: {str(e)}')
            return jsonify({'error': f'Failed to fetch image: {str(e)}'}), 500
        
        # Prüfe ob Konvertierung gewünscht ist
        convert = request.args.get('convert', 'false').lower() == 'true'
        
        # Prüfe Content-Type für HEIF/HEIC Bilder
        content_type = response.headers.get('Content-Type', '').lower()
        is_heif = 'heif' in content_type or 'heic' in content_type
        
        # Versuche HEIF-Format zu erkennen (Magic Bytes)
        if not is_heif:
            try:
                # HEIF/HEIC Magic Bytes: ftyp + heic/heif
                content_start = response.content[:12]
                if b'ftyp' in content_start and (b'heic' in content_start or b'heif' in content_start or b'mif1' in content_start):
                    is_heif = True
            except Exception:
                pass
        
        # Konvertiere immer, wenn HEIF oder wenn explizit gewünscht
        if convert or is_heif:
            try:
                # Versuche HEIF mit pillow-heif zu öffnen (falls installiert)
                if is_heif:
                    try:
                        from pillow_heif import register_heif_opener
                        register_heif_opener()
                    except ImportError:
                        app.logger.warning('pillow-heif not installed, HEIF conversion may fail')
                
                # Öffne das Bild mit Pillow
                img = Image.open(BytesIO(response.content))
                
                # Maximale Auflösung für Performance (optional, kann angepasst werden)
                max_size = 1920  # Max Breite oder Höhe
                if img.width > max_size or img.height > max_size:
                    # Berechne neue Größe unter Beibehaltung des Seitenverhältnisses
                    ratio = min(max_size / img.width, max_size / img.height)
                    new_size = (int(img.width * ratio), int(img.height * ratio))
                    # Verwende LANCZOS für beste Qualität (kompatibel mit älteren Pillow-Versionen)
                    try:
                        img = img.resize(new_size, Image.Resampling.LANCZOS)
                    except AttributeError:
                        # Fallback für ältere Pillow-Versionen
                        img = img.resize(new_size, Image.LANCZOS)
                
                # Konvertiere zu RGB falls nötig (für JPEG)
                if img.mode in ('RGBA', 'LA', 'P'):
                    # Erstelle schwarzen Hintergrund
                    background = Image.new('RGB', img.size, (0, 0, 0))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                    img = background
                elif img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Speichere als JPEG
                output = BytesIO()
                img.save(output, format='JPEG', quality=85)
                output.seek(0)
                
                return send_file(output, mimetype='image/jpeg')
            except Exception:
                # Falls Konvertierung fehlschlägt, sende Original
                return send_file(BytesIO(response.content), mimetype=response.headers.get('Content-Type', 'image/jpeg'))
        else:
            # Sende Original
            return send_file(
                BytesIO(response.content),
                mimetype=response.headers.get('Content-Type', 'image/jpeg')
            )
    
    except requests.exceptions.RequestException as e:
        return jsonify({'error': f'Failed to fetch image: {str(e)}'}), 500


# Lade Asset IDs beim ersten Request (lazy loading)
def ensure_cache_loaded():
    """Stellt sicher, dass der Cache geladen ist"""
    if not cache_loaded and IMMICH_URL and IMMICH_API_KEY:
        app.logger.info('Loading asset cache on first request...')
        load_asset_ids()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

