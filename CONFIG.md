# Configuration Guide

## Overview
The Bard Music Player uses a modular configuration system that separates credentials and settings from the main application code for better security and maintainability.

## Configuration Files

### `config.py`
Contains all default configuration values including:
- Default credentials
- Directory paths
- Audio processing settings
- Download settings

### `example.env`
Template for environment variables. Copy this to `.env` and customize:
```bash
cp example.env .env
```

### Environment Variable Override
You can override default credentials and settings using environment variables:
- `SECRET_KEY` - Flask secret key (REQUIRED in production)
- `DEFAULT_USERNAME` - Override default username
- `DEFAULT_PASSWORD` - Override default password

## Security Best Practices

### 1. Change Default Credentials
The default credentials (`skibidi`/`sigma`) should be changed immediately:

**Option A: Edit config.py directly**
```python
DEFAULT_USERNAME = "your_new_username"
DEFAULT_PASSWORD = "your_new_password"
```

**Option B: Use environment variables (recommended)**
```bash
# In your .env file
DEFAULT_USERNAME=your_new_username
DEFAULT_PASSWORD=your_new_password
```

### 2. Set a Strong Secret Key
```bash
# Generate a secure secret key
python -c "import secrets; print(secrets.token_hex(32))"

# Add to .env file
SECRET_KEY=your_generated_secret_key_here
```

### 3. File Security
- The application will create `auth.json` to store hashed passwords
- Never commit `.env`, `auth.json`, or `settings.json` to version control
- These files are already included in `.gitignore`

## Audio Settings
You can customize audio processing settings in `config.py`:
```python
AUDIO_QUALITY = '192'           # Audio bitrate
AUDIO_FORMAT = 'mp3'            # Output format
FFMPEG_AUDIO_CODEC = 'libmp3lame'
FFMPEG_AUDIO_BITRATE = '192k'
FFMPEG_SAMPLE_RATE = '44100'
DOWNLOAD_TIMEOUT = 300          # 5 minutes
```

## Directory Structure
The application uses these directories (created automatically):
- `library/` - Downloaded music files
- `playlists/` - Playlist JSON files
- `temp_downloads/` - Temporary files during download
- `static/` - Web assets
- `templates/` - HTML templates

## First Time Setup
1. Copy environment template: `cp example.env .env`
2. Edit `.env` with your credentials and secret key
3. Run the application: `python app.py`
4. Access via browser and log in with your credentials

## Production Deployment
- Always set a strong `SECRET_KEY` environment variable
- Consider using a secrets management system
- Ensure proper file permissions on config files
- Use HTTPS in production 