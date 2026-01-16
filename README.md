# Transcriber API

Production-ready API for transcribing media files with YouTube captions fast-path and ASR fallback.

## Features

- **YouTube Transcription**: Two-path strategy (captions fast-path + ASR fallback)
- **Media Transcription**: Support for file uploads, remote URLs, and social media (via yt-dlp)
- **Multiple Formats**: JSON, Text, SRT, VTT output formats
- **Async Processing**: Queue-based processing for long media files
- **Auto Language Detection**: Automatic source language detection
- **Translation Support**: Built-in translation via YouTube captions or Whisper
- **Observability**: Prometheus metrics and structured logging

## Quick Start

### Prerequisites

- Python 3.11+
- Redis (for job queue)
- FFmpeg (for audio processing)

### Installation

```bash
# Clone the repository
git clone <repo-url>
cd transcriber-api

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

# Copy environment file
cp env.example .env

# Edit .env with your settings
```

### Running Locally

```bash
# Start Redis (Docker)
docker run -d -p 6379:6379 redis:alpine

# Run the API
uvicorn app.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

### Running with Docker

```bash
docker-compose up -d
```

## API Endpoints

### Authentication

All endpoints require an API key via `Authorization: Bearer <API_KEY>` header.

In development mode (`DEV_MODE=true`), authentication is bypassed.

### Transcriptions

#### YouTube Transcription

```bash
POST /v1/transcriptions/youtube
```

```json
{
  "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  "translateTo": "es",
  "diarise": false,
  "format": "json"
}
```

**Response:**
```json
{
  "status": "completed",
  "source": "youtube_captions",
  "language": "en",
  "transcript": "Full transcript text...",
  "segments": [
    {"start": 0.0, "end": 2.5, "text": "Hello everyone"}
  ],
  "warnings": []
}
```

#### Media Transcription

```bash
POST /v1/transcriptions/media
```

Supports:
- File upload (multipart/form-data)
- Remote URL
- Social media URLs (TikTok, Twitter, Instagram via yt-dlp)

### Jobs

```bash
GET /v1/jobs/{jobId}
```

Poll job status for async transcriptions.

### Health

```bash
GET /v1/health    # Health check
GET /v1/metrics   # Prometheus metrics
GET /v1/ready     # Readiness probe
GET /v1/live      # Liveness probe
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DEV_MODE` | `false` | Bypass authentication |
| `API_KEYS` | - | Comma-separated valid API keys |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `WHISPER_MODEL` | `base` | Whisper model size (tiny, base, small, medium, large) |
| `WHISPER_DEVICE` | `auto` | Device for inference (auto, cpu, cuda) |
| `ASR_PROVIDER` | `local` | ASR provider (local, openai, deepgram) |
| `ASR_SYNC_MAX_DURATION` | `600` | Max duration (sec) for sync response |
| `MAX_UPLOAD_SIZE_MB` | `500` | Maximum file upload size |

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/test_youtube_service.py -v
```

### Code Quality

```bash
# Lint
ruff check app tests

# Format
ruff format app tests

# Type check
mypy app
```

## Architecture

```
app/
├── api/
│   ├── v1/
│   │   ├── transcriptions.py  # Transcription endpoints
│   │   ├── jobs.py            # Job management
│   │   └── health.py          # Health checks
│   ├── middleware.py          # Request logging, rate limiting
│   └── router.py              # API router
├── core/
│   ├── config.py              # Settings
│   ├── exceptions.py          # Custom exceptions
│   ├── logging.py             # Structured logging
│   └── security.py            # Authentication
├── models/
│   ├── requests.py            # Request models
│   ├── responses.py           # Response models
│   └── jobs.py                # Job models
├── services/
│   ├── youtube.py             # YouTube captions service
│   ├── media.py               # Media download service
│   ├── asr.py                 # ASR/Whisper service
│   ├── formatters.py          # Output formatters
│   └── jobs.py                # Job queue service
└── main.py                    # Application entry point
```

## License

MIT
