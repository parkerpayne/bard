# 🎵 Bard - D&D Music Bot

**Bard** is a self-hosted web application and Discord bot designed for Dungeon Masters and D&D players to create, organize, and play atmospheric music during their gaming sessions. Download songs from YouTube, organize them into themed playlists, and play them seamlessly through Discord voice channels.

![Bard Interface](https://img.shields.io/badge/Status-Active-brightgreen) ![Python](https://img.shields.io/badge/Python-3.8+-blue) ![Discord](https://img.shields.io/badge/Discord-Bot-7289da) ![Flask](https://img.shields.io/badge/Flask-Web_App-lightgrey)

## ✨ Features

### 🎼 Music Management
- **YouTube Integration**: Download songs directly from YouTube URLs
- **Playlists**: Create themed playlists (Combat, Tavern, Dungeon, etc.)
- **Tag System**: Organize playlists with custom tags for easy filtering
- **Library Management**: Centralized music library with metadata support

### 🎮 Discord Integration
- **Voice Channel Playback**: Play music directly in Discord voice channels
- **Real-time Controls**: Play, pause, skip, and stop from the web interface
- **Queue Management**: See current song and upcoming tracks
- **Auto-advance**: Seamlessly transition between songs

### 🌐 Web Interface
- **Modern UI**: Clean, Spotify-inspired interface
- **Real-time Updates**: Live playback status and download progress
- **Authentication**: Secure login system

### 🔧 Technical Features
- **Audio Processing**: Automatic normalization and format conversion
- **Progress Tracking**: Real-time download and playback status
- **Multi-threaded**: Concurrent downloads
- **Configurable**: Customizable audio quality and settings

## 📋 Requirements

### System Dependencies
- **Python 3.8+**
- **FFmpeg** (for audio processing)
- **Discord Bot Token** (see setup instructions below)

### Python Dependencies
All Python packages are listed in `requirements.txt` and can be installed with `pip install -r requirements.txt`

## 🚀 Installation

### 1. Clone the Repository
```bash
git clone <repository-url>
cd bard
```

### 2. Install System Dependencies
**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install python3 python3-pip ffmpeg
```

**macOS (with Homebrew, untested):**
```bash
brew install python ffmpeg
```

**Windows (untested):**
- Install Python from [python.org](https://python.org)
- Install FFmpeg from [ffmpeg.org](https://ffmpeg.org) or use `winget install ffmpeg`

### 3. Install Python Dependencies
```bash
pip install -r requirements.txt
```

### 4. Run the Application
```
python app.py
```