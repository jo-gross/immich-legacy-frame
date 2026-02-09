import os
import random
import requests
from flask import Flask, render_template, request, jsonify, send_file
from io import BytesIO
from PIL import Image

app = Flask(__name__)

# Umgebungsvariablen (Standard-Werte)
DEFAULT_IMMICH_URL = os.getenv('IMMICH_URL', '').rstrip('/')
DEFAULT_IMMICH_API_KEY = os.getenv('IMMICH_API_KEY', '')
PASSWORD = os.getenv('PASSWORD', '')

# Globaler Cache für Asset IDs und Alben
asset_ids_cache = []
albums_cache = []
cache_loaded = False
cache_immich_url = None
cache_immich_api_key = None


def get_immich_config():
    """Gibt Immich URL und API Key zurück, Query-Parameter überschreiben Umgebungsvariablen"""
    immich_url = request.args.get('immich_url', DEFAULT_IMMICH_URL).rstrip('/')
    immich_api_key = request.args.get('immich_api_key', DEFAULT_IMMICH_API_KEY)
    return immich_url, immich_api_key


def check_password():
    """Prüft ob Passwort-Schutz aktiv ist und ob das Passwort korrekt ist"""
    if not PASSWORD:
        return True  # Kein Passwort gesetzt, Zugriff erlaubt
    
    provided_password = request.args.get('password', '')
    return provided_password == PASSWORD


def load_asset_ids(immich_url=None, immich_api_key=None):
    """Lädt alle Asset IDs von Immich und cached sie mit Album-Zuordnung"""
    global asset_ids_cache, albums_cache, cache_loaded, cache_immich_url, cache_immich_api_key
    
    # Verwende übergebene Parameter oder Defaults
    if immich_url is None:
        immich_url = DEFAULT_IMMICH_URL
    if immich_api_key is None:
        immich_api_key = DEFAULT_IMMICH_API_KEY
    
    # Wenn Cache bereits für genau diese Konfiguration geladen wurde, wiederverwenden
    if cache_loaded and cache_immich_url == immich_url and cache_immich_api_key == immich_api_key:
        return asset_ids_cache
    
    if not immich_url or not immich_api_key:
        app.logger.error('Immich configuration missing, cannot load assets')
        return []
    
    headers = {
        'x-api-key': immich_api_key
    }
    
    # Dictionary: album_id -> [asset_ids]
    assets_by_album = {}
    all_asset_ids = []
    asset_ids_seen = set()
    albums_list = []
    
    try:
        # Schritt 1: Lade alle Alben – zuerst eigene, dann geteilte und zusammenführen
        app.logger.info(f'Loading asset IDs from Immich: {immich_url}/api/albums (owned + shared)')
        albums = []
        album_ids_seen = set()

        # 1) Eigene Alben (ohne Parameter)
        try:
            owned_response = requests.get(
                f'{immich_url}/api/albums',
                headers=headers,
                timeout=30
            )
            if owned_response.status_code == 200:
                owned_data = owned_response.json()
                owned_albums = owned_data if isinstance(owned_data, list) else owned_data.get('items', owned_data.get('albums', []))
                for album in owned_albums:
                    album_id = album.get('id')
                    if not album_id or album_id in album_ids_seen:
                        continue
                    albums.append(album)
                    album_ids_seen.add(album_id)
            else:
                app.logger.error(f'Failed to load owned albums: {owned_response.status_code}')
        except requests.exceptions.RequestException as e:
            app.logger.error(f'Error loading owned albums: {str(e)}')

        # 2) Geteilte Alben (shared = true)
        try:
            shared_response = requests.get(
                f'{immich_url}/api/albums',
                headers=headers,
                params={'shared': 'true'},
                timeout=30
            )
            if shared_response.status_code == 200:
                shared_data = shared_response.json()
                shared_albums = shared_data if isinstance(shared_data, list) else shared_data.get('items', shared_data.get('albums', []))
                for album in shared_albums:
                    album_id = album.get('id')
                    if not album_id or album_id in album_ids_seen:
                        continue
                    albums.append(album)
                    album_ids_seen.add(album_id)
            else:
                app.logger.error(f'Failed to load shared albums: {shared_response.status_code}')
        except requests.exceptions.RequestException as e:
            app.logger.error(f'Error loading shared albums: {str(e)}')

        if not albums:
            app.logger.error('No albums found (owned or shared)')
            return []

        app.logger.info(f'Found {len(albums)} albums (owned + shared)')
        
        # Schritt 2: Lade Assets aus jedem Album
        for album in albums:
            album_id = album.get('id')
            album_name = album.get('albumName', 'Unbenannt')
            if not album_id:
                continue
            
            albums_list.append({
                'id': album_id,
                'name': album_name
            })
            
            album_asset_ids = []
            
            try:
                # Versuche zuerst, ob das Album-Objekt bereits Assets enthält
                album_assets = album.get('assets', [])
                
                # Falls nicht, hole das Album-Detail
                if not album_assets:
                    album_detail_response = requests.get(
                        f'{immich_url}/api/albums/{album_id}',
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
                            album_asset_ids.append(asset_id)
                            asset_ids_seen.add(asset_id)
                            
            except requests.exceptions.RequestException:
                continue
            
            # Merke Asset-IDs pro Album (derzeit nicht weiter genutzt, aber vollständig)
            assets_by_album[album_id] = album_asset_ids
        
        # Cache aktualisieren: Daten und zugehörige Konfiguration merken
        asset_ids_cache = all_asset_ids
        albums_cache = albums_list
        cache_loaded = True
        cache_immich_url = immich_url
        cache_immich_api_key = immich_api_key
        app.logger.info(f'Loaded {len(asset_ids_cache)} image asset IDs from {len(albums_list)} albums into cache')
        
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
    immich_url, immich_api_key = get_immich_config()
    debug_info = {
        'immich_url_set': bool(immich_url),
        'immich_url': immich_url if immich_url else 'NOT SET',
        'api_key_set': bool(immich_api_key),
        'password_set': bool(PASSWORD),
        'password_provided': bool(request.args.get('password')),
        'password_match': check_password() if PASSWORD else 'N/A (no password required)',
        'using_query_params': bool(request.args.get('immich_url') or request.args.get('immich_api_key'))
    }
    return jsonify(debug_info)


@app.route('/api/albums')
def get_albums():
    """Gibt alle Alben zurück"""
    if not check_password():
        return jsonify({'error': 'Unauthorized'}), 401
    
    immich_url, immich_api_key = get_immich_config()
    
    # Stelle sicher, dass Cache geladen ist
    ensure_cache_loaded(immich_url, immich_api_key)
    
    return jsonify({'albums': albums_cache})


@app.route('/api/random-image')
@app.route('/api/next-image')
def get_next_image():
    """Gibt das nächste Bild zurück, entweder zufällig oder sequentiell"""
    if not check_password():
        return jsonify({'error': 'Unauthorized'}), 401
    
    immich_url, immich_api_key = get_immich_config()
    
    # Stelle sicher, dass Cache geladen ist
    ensure_cache_loaded(immich_url, immich_api_key)
    
    # Hole Parameter
    order = request.args.get('order', 'random')  # 'random' oder 'sequential'
    current_index = int(request.args.get('index', 0))
    
    # Hole ausgewählte Alben aus Query-Parameter
    selected_albums = request.args.get('albums', '')
    if selected_albums:
        selected_album_ids = [aid for aid in selected_albums.split(',') if aid]
    else:
        # Standard: Alle Alben
        selected_album_ids = [album['id'] for album in albums_cache]
    
    # Sammle Assets aus ausgewählten Alben mit Album-Zuordnung und Datum
    available_assets = []
    asset_ids_seen = set()
    headers = {
        'x-api-key': immich_api_key
    }
    
    # Erstelle Album-ID zu Name Mapping
    album_id_to_name = {album['id']: album['name'] for album in albums_cache}
    
    for album_id in selected_album_ids:
        album_name = album_id_to_name.get(album_id, 'Unbenannt')
        try:
            album_detail_response = requests.get(
                f'{immich_url}/api/albums/{album_id}',
                headers=headers,
                timeout=10
            )
            if album_detail_response.status_code == 200:
                album_detail = album_detail_response.json()
                album_assets = album_detail.get('assets', album_detail.get('assetIds', []))
                for asset in album_assets:
                    asset_id = None
                    asset_date = None
                    if isinstance(asset, dict):
                        asset_id = asset.get('id')
                        asset_type = asset.get('type') or asset.get('mimeType', '')
                        # Hole Datum für Sortierung
                        asset_date = asset.get('fileCreatedAt') or asset.get('createdAt')
                    elif isinstance(asset, str):
                        asset_id = asset
                        asset_type = None
                    
                    if asset_id:
                        is_image = False
                        if asset_type == 'IMAGE':
                            is_image = True
                        elif isinstance(asset_type, str) and asset_type.startswith('image/'):
                            is_image = True
                        elif not asset_type:
                            is_image = True
                        
                        if is_image and asset_id not in asset_ids_seen:
                            available_assets.append({
                                'id': asset_id,
                                'album_id': album_id,
                                'album_name': album_name,
                                'date': asset_date
                            })
                            asset_ids_seen.add(asset_id)
        except Exception:
            continue
    
    if not available_assets:
        return jsonify({'error': 'No images available in selected albums'}), 404
    
    # Wähle Asset basierend auf Reihenfolge
    next_index = 0
    if order == 'sequential':
        # Sortiere nach Album-Name, dann nach Datum (alt nach neu)
        available_assets.sort(key=lambda x: (x['album_name'].lower(), x['date'] or ''))
        
        # Verwende aktuellen Index, wrap around wenn am Ende
        if current_index >= len(available_assets):
            current_index = 0
        
        selected_asset = available_assets[current_index]
        next_index = (current_index + 1) % len(available_assets)
    else:
        # Zufällige Auswahl
        selected_asset = random.choice(available_assets)
    
    selected_asset_id = selected_asset['id']
    album_name = selected_asset['album_name']
    
    # Hole Asset-Details für Datum und Location
    date_taken = None
    location = None
    try:
        asset_response = requests.get(
            f'{immich_url}/api/assets/{selected_asset_id}',
            headers=headers,
            timeout=10
        )
        if asset_response.status_code == 200:
            asset_data = asset_response.json()
            date_taken = asset_data.get('exifInfo', {}).get('dateTimeOriginal') or asset_data.get('createdAt') or asset_data.get('fileCreatedAt')
            
            # Hole Location aus EXIF-Daten
            exif_info = asset_data.get('exifInfo', {})
            city = exif_info.get('city', '')
            state = exif_info.get('state', '')
            country = exif_info.get('country', '')
            
            # Baue Location-String zusammen
            location_parts = []
            if city:
                location_parts.append(city)
            if state and state != city:
                location_parts.append(state)
            if country:
                location_parts.append(country)
            
            if location_parts:
                location = ', '.join(location_parts)
    except Exception:
        pass
    
    # Erstelle URLs
    image_url = f"{immich_url}/api/assets/{selected_asset_id}/thumbnail?size=preview"
    
    response_data = {
        'id': selected_asset_id,
        'url': image_url,
        'date': date_taken,
        'album': album_name,
        'location': location
    }
    
    # Füge next_index für sequentiellen Modus hinzu
    if order == 'sequential':
        response_data['next_index'] = next_index
        response_data['total'] = len(available_assets)
        response_data['current'] = current_index + 1
    
    return jsonify(response_data)


@app.route('/api/images')
def get_images():
    """API Endpoint zum Abrufen der Bilderliste von Immich"""
    if not check_password():
        return jsonify({'error': 'Unauthorized'}), 401
    
    immich_url, immich_api_key = get_immich_config()
    
    if not immich_url or not immich_api_key:
        return jsonify({'error': 'Immich configuration missing'}), 500
    
    try:
        headers = {
            'x-api-key': immich_api_key
        }
        
        # Hole alle Assets von Immich über Alben
        # Ansatz: Zuerst alle Alben laden, dann Assets aus jedem Album
        all_assets = []
        asset_ids_seen = set()  # Um Duplikate zu vermeiden
        
        try:
            # Schritt 1: Lade alle Alben – zuerst eigene, dann geteilte und zusammenführen
            app.logger.info(f'Fetching albums from Immich: {immich_url}/api/albums (owned + shared)')
            albums = []
            album_ids_seen = set()

            # 1) Eigene Alben (ohne Parameter)
            try:
                owned_response = requests.get(
                    f'{immich_url}/api/albums',
                    headers=headers,
                    timeout=10
                )
                if owned_response.status_code == 200:
                    owned_data = owned_response.json()
                    owned_albums = owned_data if isinstance(owned_data, list) else owned_data.get('items', owned_data.get('albums', []))
                    for album in owned_albums:
                        album_id = album.get('id')
                        if not album_id or album_id in album_ids_seen:
                            continue
                        albums.append(album)
                        album_ids_seen.add(album_id)
                else:
                    error_msg = f'{immich_url}/api/albums returned {owned_response.status_code}'
                    try:
                        error_data = owned_response.json()
                        if isinstance(error_data, dict) and 'message' in error_data:
                            error_msg += f" - {error_data['message']}"
                    except Exception:
                        error_msg += f" - {owned_response.text[:200]}"
                    app.logger.error(f'Immich API error (owned): {immich_url}/api/albums - {error_msg}')
            except requests.exceptions.RequestException as e:
                app.logger.error(f'Failed to connect to Immich API for owned albums: {str(e)}')

            # 2) Geteilte Alben (shared = true)
            try:
                shared_response = requests.get(
                    f'{immich_url}/api/albums',
                    headers=headers,
                    params={'shared': 'true'},
                    timeout=10
                )
                if shared_response.status_code == 200:
                    shared_data = shared_response.json()
                    shared_albums = shared_data if isinstance(shared_data, list) else shared_data.get('items', shared_data.get('albums', []))
                    for album in shared_albums:
                        album_id = album.get('id')
                        if not album_id or album_id in album_ids_seen:
                            continue
                        albums.append(album)
                        album_ids_seen.add(album_id)
                else:
                    error_msg = f'{immich_url}/api/albums?shared=true returned {shared_response.status_code}'
                    try:
                        error_data = shared_response.json()
                        if isinstance(error_data, dict) and 'message' in error_data:
                            error_msg += f" - {error_data['message']}"
                    except Exception:
                        error_msg += f" - {shared_response.text[:200]}"
                    app.logger.error(f'Immich API error (shared): {immich_url}/api/albums - {error_msg}')
            except requests.exceptions.RequestException as e:
                app.logger.error(f'Failed to connect to Immich API for shared albums: {str(e)}')

            if not albums:
                error_msg = 'No albums found (owned or shared)'
                app.logger.error(error_msg)
                return jsonify({'error': error_msg}), 500

            app.logger.info(f'Found {len(albums)} albums (owned + shared)')
            
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
                            f'{immich_url}/api/albums/{album_id}',
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
                                        f'{immich_url}/api/assets/{asset}',
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
                # GET /api/assets/{id}/thumbnail?size=preview& - für Konvertierte Bilder (singular "asset")
                thumbnail_url = f"{immich_url}/api/assets/{asset_id}/thumbnail"
                file_url = f"{immich_url}/api/assets/{asset_id}/thumbnail?size=preview"
                
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
    
    immich_url, immich_api_key = get_immich_config()
    
    if not immich_url or not immich_api_key:
        return jsonify({'error': 'Immich configuration missing'}), 500
    
    try:
        headers = {
            'x-api-key': immich_api_key
        }
        
        # Hole das Bild von Immich
        # Verwende korrekten Immich API-Endpunkt
        # GET /api/assets/{id}/thumbnail?size=preview - für Konvertierte Bilder (singular "asset")
        image_url = f'{immich_url}/api/assets/{image_id}/thumbnail?size=preview'
        
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
def ensure_cache_loaded(immich_url=None, immich_api_key=None):
    """Stellt sicher, dass der Cache für die aktuelle Immich-Konfiguration geladen ist"""
    # Verwende übergebene Parameter oder Defaults
    if immich_url is None:
        immich_url = DEFAULT_IMMICH_URL
    if immich_api_key is None:
        immich_api_key = DEFAULT_IMMICH_API_KEY
    
    # Nur laden, wenn Konfiguration vorhanden ist; die eigentliche Cache-Logik
    # (inkl. Wiederverwendung bei gleicher Konfiguration) steckt in load_asset_ids.
    if immich_url and immich_api_key:
        app.logger.info('Ensuring asset cache is loaded for current Immich configuration...')
        load_asset_ids(immich_url, immich_api_key)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

