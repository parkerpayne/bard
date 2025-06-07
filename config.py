import os

# Authentication credentials (can be overridden by environment variables)
DEFAULT_USERNAME = os.environ.get('DEFAULT_USERNAME', "admin")
DEFAULT_PASSWORD = os.environ.get('DEFAULT_PASSWORD', "admin")

# Flask secret key - change this in production!
SECRET_KEY = os.environ.get('SECRET_KEY', 'your-secret-key-change-this-in-production')

# Directory configurations
PLAYLIST_DIR = "playlists"
LIBRARY_DIR = "library"
TEMP_DIR = "temp_downloads"
SETTINGS_FILE = "settings.json"
AUTH_FILE = "auth.json"

# Download settings
DOWNLOAD_TIMEOUT = 300  # 5 minutes
AUDIO_QUALITY = '192'
AUDIO_FORMAT = 'mp3'

# Audio processing settings
FFMPEG_AUDIO_CODEC = 'libmp3lame'
FFMPEG_AUDIO_BITRATE = '192k'
FFMPEG_SAMPLE_RATE = '44100' 