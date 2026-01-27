<div align="center">

# Immich Slideshow

**A lightweight slideshow application that displays photos from your Immich library**

[![Docker Build](https://github.com/jo-gross/immich-legacy-frame/actions/workflows/docker-build.yml/badge.svg)](https://github.com/jo-gross/immich-legacy-frame/actions/workflows/docker-build.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

*Perfect for old tablets, digital photo frames, or any legacy browser*

</div>

---

## Features

- **Legacy Browser Support** — Works on Internet Explorer 11+, old Chrome, Firefox, and Safari versions
- **Immich Integration** — Displays all photos from your Immich library
- **Automatic Image Conversion** — Converts images for maximum compatibility
- **Password Protection** — Optional access control via environment variable
- **Docker Ready** — Easy deployment with Docker Compose
- **Responsive Display** — Images scale with black letterboxing (contain mode)
- **Configurable Interval** — Adjust slideshow timing via URL parameter

---

## Quick Start

### Using Docker Compose (Recommended)

1. **Create a `.env` file** in your project directory:

   ```env
   IMMICH_URL=https://your-immich-instance.com
   IMMICH_API_KEY=your-api-key
   PASSWORD=your-password  # Optional: Leave empty to disable protection
   ```

2. **Start the container:**

   ```bash
   docker-compose up -d
   ```

3. **Open in your browser:** `http://localhost:8080`

### Using Pre-built Image

```bash
docker run -d \
  -p 8080:5000 \
  -e IMMICH_URL=https://your-immich-instance.com \
  -e IMMICH_API_KEY=your-api-key \
  -e PASSWORD=your-password \
  ghcr.io/jo-gross/immich-legacy-frame:latest
```

### Without Docker

1. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

2. **Set environment variables:**

   ```bash
   export IMMICH_URL=https://your-immich-instance.com
   export IMMICH_API_KEY=your-api-key
   export PASSWORD=your-password  # Optional
   ```

3. **Run the application:**

   ```bash
   python app.py
   ```

---

## Configuration

### Environment Variables

| Variable         | Description                                          | Required |
|------------------|------------------------------------------------------|:--------:|
| `IMMICH_URL`     | URL to your Immich instance (without trailing slash) |   Yes    |
| `IMMICH_API_KEY` | API key from Immich                                  |   Yes    |
| `PASSWORD`       | Password for access protection                       |    No    |

### URL Parameters

| Parameter  | Description                      | Default |
|------------|----------------------------------|---------|
| `password` | Authentication password          | —       |
| `interval` | Time between slides (in seconds) | `5`     |

**Examples:**

```
http://localhost:8080/
http://localhost:8080/?interval=10
http://localhost:8080/?password=secret&interval=15
```

---

## API Endpoints

| Endpoint              | Description                             |
|-----------------------|-----------------------------------------|
| `GET /`               | Main slideshow page                     |
| `GET /api/images`     | List of all images from Immich          |
| `GET /api/image/<id>` | Single image (with optional conversion) |

---

## Tech Stack

| Component         | Technology                  |
|-------------------|-----------------------------|
| Backend           | Python 3.11, Flask          |
| Frontend          | Vanilla HTML/CSS/JavaScript |
| Image Processing  | Pillow                      |
| Production Server | Gunicorn                    |
| Container         | Docker                      |

---

## Browser Compatibility

Designed for legacy browsers — no modern JavaScript features used:

| Feature                             | Status                         |
|-------------------------------------|--------------------------------|
| ES6+ Syntax (Arrow Functions, etc.) | Not used                       |
| Fetch API                           | Not used (uses XMLHttpRequest) |
| Modern CSS (Flexbox, Grid)          | Not used                       |

**Tested on:**
- Internet Explorer 11+
- Chrome (legacy versions)
- Firefox (legacy versions)
- Safari (legacy versions)

---

## Development

For local development with hot reload:

```bash
python app.py
```

The application runs in debug mode at `http://localhost:5000`.

---

## License

This project is licensed under the [MIT License](https://opensource.org/licenses/MIT).
