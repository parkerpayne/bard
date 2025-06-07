import datetime
from flask import Flask, render_template, request, jsonify, redirect, Response, session, url_for, flash
import os
import json
import subprocess
import hashlib
from urllib.parse import urlparse
import shutil
import threading
import time
import uuid
import re
from pathlib import Path
import tempfile
import queue as queue_module
import yt_dlp
from mutagen import File as MutagenFile
from mutagen.id3 import ID3, TIT2, TPE1
import signal
import sys
import discord
from discord.ext import commands
import asyncio
import random
from functools import wraps

# Import configuration
import config

app = Flask(__name__)
app.secret_key = config.SECRET_KEY

# Global music player state
current_playlist = None
current_song_index = 0
shuffled_queue = []
is_playing = False
is_paused = True
current_song_info = None
song_start_time = None
song_duration = 0
paused_at_time = None
song_ended_flag = threading.Event()

# Performance optimization: Cache frequently accessed data
playlist_cache = {}
library_cache = {}
cache_timeout = 300  # 5 minutes
last_cache_update = 0

# Replace manual_song_change with thread-safe tracking
song_change_lock = threading.Lock()
current_song_id = None  # Unique ID for each song playback
manual_skip_ids = set()  # Track which song IDs were manually stopped

# Use configuration from config.py
PLAYLIST_DIR = config.PLAYLIST_DIR
LIBRARY_DIR = config.LIBRARY_DIR
TEMP_DIR = config.TEMP_DIR
SETTINGS_FILE = config.SETTINGS_FILE
AUTH_FILE = config.AUTH_FILE

# Ensure directories exist
os.makedirs(PLAYLIST_DIR, exist_ok=True)
os.makedirs(LIBRARY_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

# Authentication functions
def load_auth_config():
    """Load authentication configuration"""
    if os.path.exists(AUTH_FILE):
        try:
            with open(AUTH_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    
    # Return default config if file doesn't exist or is corrupted
    return {
        'username': config.DEFAULT_USERNAME,
        'password': hashlib.sha256(config.DEFAULT_PASSWORD.encode()).hexdigest()
    }

def save_auth_config(username, password):
    """Save authentication configuration"""
    auth_config = {
        'username': username,
        'password': hashlib.sha256(password.encode()).hexdigest()
    }
    with open(AUTH_FILE, 'w') as f:
        json.dump(auth_config, f, indent=2)

def verify_credentials(username, password):
    """Verify login credentials"""
    auth_config = load_auth_config()
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    return (username == auth_config['username'] and 
            password_hash == auth_config['password'])

def login_required(f):
    """Decorator to require login for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session or not session['logged_in']:
            if request.endpoint and request.endpoint.startswith('api_'):
                return jsonify({'error': 'Authentication required'}), 401
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# Download management
download_registry = {}
download_lock = threading.Lock()
download_threads = {}
active_downloads = {}
sse_clients = set()

class DownloadStatus:
    PENDING = "pending"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    NORMALIZING = "normalizing"
    MOVING = "moving"
    COMPLETED = "completed"
    FAILED = "failed"

class DownloadManager:
    def __init__(self):
        self.downloads = {}
        self.lock = threading.Lock()
        self.max_concurrent = 3
        self.active_count = 0
        self.download_queue = queue_module.Queue()
        self.worker_threads = []
        self.running = True
        
        # Start worker threads
        for i in range(self.max_concurrent):
            thread = threading.Thread(target=self._worker, daemon=True)
            thread.start()
            self.worker_threads.append(thread)
    
    def add_download(self, download_id, url, target_playlist=None):
        """Add a download to the queue"""
        with self.lock:
            download_info = {
                'id': download_id,
                'url': url,
                'target_playlist': target_playlist,
                'status': DownloadStatus.PENDING,
                'progress': 0,
                'message': 'Queued for download',
                'title': None,
                'uploader': None,
                'error': None,
                'created_at': time.time()
            }
            self.downloads[download_id] = download_info
            self.download_queue.put(download_info)
            self._broadcast_update(download_info)
            return download_info
    
    def get_download(self, download_id):
        """Get download info by ID"""
        with self.lock:
            return self.downloads.get(download_id)
    
    def get_all_downloads(self):
        """Get all download info"""
        with self.lock:
            return list(self.downloads.values())
    
    def _update_download(self, download_id, **kwargs):
        """Update download info and broadcast to clients"""
        with self.lock:
            if download_id in self.downloads:
                self.downloads[download_id].update(kwargs)
                self._broadcast_update(self.downloads[download_id])
    
    def _broadcast_update(self, download_info):
        """Broadcast download update to all SSE clients"""
        data = json.dumps(download_info)
        dead_clients = set()
        
        for client in sse_clients.copy():  # Create copy to avoid modification during iteration
            try:
                client.put_nowait(f"data: {data}\n\n")
            except queue_module.Full:
                # Client queue is full, mark as dead
                dead_clients.add(client)
            except:
                # Any other error, mark as dead
                dead_clients.add(client)
        
        # Remove dead clients
        if dead_clients:
            sse_clients.difference_update(dead_clients)
            print(f"Removed {len(dead_clients)} dead download SSE clients")
    
    def _worker(self):
        """Worker thread for processing downloads"""
        while self.running:
            try:
                download_info = self.download_queue.get(timeout=1)
                if download_info:
                    self._process_download(download_info)
                    self.download_queue.task_done()
            except queue_module.Empty:
                continue
            except Exception as e:
                print(f"Worker error: {e}")
    
    def _process_download(self, download_info):
        """Process a single download through all stages"""
        download_id = download_info['id']
        
        try:
            # Stage 1: Download from YouTube
            self._update_download(download_id, 
                                status=DownloadStatus.DOWNLOADING,
                                progress=10,
                                message="Downloading from YouTube...")
            
            temp_file_path = self._download_youtube(download_info)
            if not temp_file_path:
                raise Exception("Failed to download from YouTube")
            
            # Stage 2: Process/Extract audio
            self._update_download(download_id,
                                status=DownloadStatus.PROCESSING,
                                progress=40,
                                message="Extracting audio...")
            
            processed_file_path = self._process_audio(temp_file_path, download_info)
            if not processed_file_path:
                raise Exception("Failed to process audio")
            
            # Stage 3: Normalize audio with ffmpeg
            self._update_download(download_id,
                                status=DownloadStatus.NORMALIZING,
                                progress=70,
                                message="Normalizing audio...")
            
            normalized_file_path = self._normalize_audio(processed_file_path, download_info)
            if not normalized_file_path:
                raise Exception("Failed to normalize audio")
            
            # Stage 4: Move to library
            self._update_download(download_id,
                                status=DownloadStatus.MOVING,
                                progress=90,
                                message="Adding to library...")
            
            final_file_path = self._move_to_library(normalized_file_path, download_info)
            if not final_file_path:
                raise Exception("Failed to move to library")
            
            # Stage 5: Complete
            self._update_download(download_id,
                                status=DownloadStatus.COMPLETED,
                                progress=100,
                                message="Download completed!")
            
            # Add to playlist if specified
            if download_info.get('target_playlist'):
                self._add_to_playlist(final_file_path, download_info)
            
            # Cleanup temp files
            self._cleanup_temp_files(download_id)
            
        except Exception as e:
            print(f"Download {download_id} failed: {e}")
            self._update_download(download_id,
                                status=DownloadStatus.FAILED,
                                message=f"Download failed: {str(e)}",
                                error=str(e))
            self._cleanup_temp_files(download_id)
    
    def _download_youtube(self, download_info):
        """Download video from YouTube using yt-dlp"""
        download_id = download_info['id']
        
        # Create temp directory for this download
        temp_download_dir = os.path.join(TEMP_DIR, download_id)
        os.makedirs(temp_download_dir, exist_ok=True)
        
        # Configure yt-dlp options
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(temp_download_dir, '%(title)s.%(ext)s'),
            'extractaudio': True,
            'audioformat': config.AUDIO_FORMAT,
            'audioquality': config.AUDIO_QUALITY,
            'embed_subs': False,
            'writesubtitles': False,
            'writeautomaticsub': False,
            'ignoreerrors': True,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Extract info first
                info = ydl.extract_info(download_info['url'], download=False)
                if not info:
                    raise Exception("Could not extract video information")
                
                # Update download info with video details
                self._update_download(download_id,
                                    title=info.get('title', 'Unknown Title'),
                                    progress=20)
                
                # Download the video
                ydl.download([download_info['url']])
                
                # Find the downloaded file
                for file in os.listdir(temp_download_dir):
                    if file.endswith(('.mp3', '.m4a', '.webm', '.mp4')):
                        return os.path.join(temp_download_dir, file)
                
                raise Exception("Downloaded file not found")
                
        except Exception as e:
            print(f"YouTube download error: {e}")
            return None
    
    def _process_audio(self, input_file, download_info):
        """Process audio file (convert to mp3 if needed)"""
        download_id = download_info['id']
        temp_dir = os.path.join(TEMP_DIR, download_id)
        
        # If already mp3, return as is
        if input_file.endswith('.mp3'):
            return input_file
        
        # Convert to mp3 using ffmpeg
        output_file = os.path.join(temp_dir, 'processed.mp3')
        
        try:
            cmd = [
                'ffmpeg', '-i', input_file,
                '-acodec', config.FFMPEG_AUDIO_CODEC,
                '-ab', config.FFMPEG_AUDIO_BITRATE,
                '-ar', config.FFMPEG_SAMPLE_RATE,
                '-y',  # Overwrite output file
                output_file
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=config.DOWNLOAD_TIMEOUT)
            if result.returncode != 0:
                raise Exception(f"FFmpeg conversion failed: {result.stderr}")
            
            # Remove original file
            os.remove(input_file)
            
            return output_file
            
        except subprocess.TimeoutExpired:
            raise Exception("Audio processing timed out")
        except Exception as e:
            print(f"Audio processing error: {e}")
            return None
    
    def _normalize_audio(self, input_file, download_info):
        """Normalize audio using ffmpeg"""
        download_id = download_info['id']
        temp_dir = os.path.join(TEMP_DIR, download_id)
        output_file = os.path.join(temp_dir, 'normalized.mp3')
        
        try:
            # Use ffmpeg to normalize audio
            cmd = [
                'ffmpeg', '-i', input_file,
                '-filter:a', 'loudnorm',
                '-acodec', config.FFMPEG_AUDIO_CODEC,
                '-ab', config.FFMPEG_AUDIO_BITRATE,
                '-ar', config.FFMPEG_SAMPLE_RATE,
                '-y',
                output_file
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=config.DOWNLOAD_TIMEOUT)
            if result.returncode != 0:
                raise Exception(f"FFmpeg normalization failed: {result.stderr}")
            
            # Remove processed file
            os.remove(input_file)
            
            return output_file
            
        except subprocess.TimeoutExpired:
            raise Exception("Audio normalization timed out")
        except Exception as e:
            print(f"Audio normalization error: {e}")
            return None
    
    def _move_to_library(self, input_file, download_info):
        """Move file to library with proper naming"""
        download_id = download_info['id']
        
        # Create safe filename
        title = download_info.get('title', 'Unknown Title')
        
        # Sanitize filename
        safe_title = re.sub(r'[<>:"/\\|?*]', '_', title)
        
        filename = f"{safe_title}.mp3"
        final_path = os.path.join(LIBRARY_DIR, filename)
        
        # Ensure unique filename
        counter = 1
        while os.path.exists(final_path):
            name, ext = os.path.splitext(filename)
            filename = f"{name} ({counter}){ext}"
            final_path = os.path.join(LIBRARY_DIR, filename)
            counter += 1
        
        try:
            # Move file to library
            shutil.move(input_file, final_path)
            
            # Add metadata using mutagen
            try:
                audio_file = MutagenFile(final_path)
                if audio_file is not None:
                    # Remove existing tags and add new ones
                    audio_file.delete()
                    audio_file.save()
                    
                    # Add ID3 tags
                    audio_file = ID3(final_path)
                    audio_file.add(TIT2(encoding=3, text=title))
                    audio_file.save()
            except Exception as e:
                print(f"Failed to add metadata: {e}")
            
            # Invalidate library cache when new file is added
            invalidate_library_cache()
            
            return final_path
            
        except Exception as e:
            print(f"Failed to move file to library: {e}")
            return None
    
    def _add_to_playlist(self, file_path, download_info):
        """Add song to specified playlist"""
        playlist_name = download_info.get('target_playlist')
        if not playlist_name:
            return
        
        playlist_file = os.path.join(PLAYLIST_DIR, f"{playlist_name}.json")
        if not os.path.exists(playlist_file):
            return
        
        try:
            with open(playlist_file, 'r') as f:
                playlist_data = json.load(f)
            
            # Add song to playlist
            song_info = {
                'id': str(uuid.uuid4()),
                'title': download_info.get('title', 'Unknown Title'),
                'filename': os.path.basename(file_path),
                'added_at': datetime.datetime.now().isoformat()
            }
            
            playlist_data['songs'].append(song_info)
            
            with open(playlist_file, 'w') as f:
                json.dump(playlist_data, f, indent=2)
                
        except Exception as e:
            print(f"Failed to add to playlist: {e}")
    
    def _cleanup_temp_files(self, download_id):
        """Clean up temporary files for a download"""
        temp_dir = os.path.join(TEMP_DIR, download_id)
        if os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                print(f"Failed to cleanup temp files: {e}")

# Initialize download manager
download_manager = DownloadManager()

# Discord Bot Management
class MusicBot:
    def __init__(self):
        self.bot = None
        self.is_bot_ready = False
        self.voice_client = None
        self.target_channel_id = None
        self.bot_task = None
        self.discord_thread = None
        self.discord_loop = None
        self.command_queue = queue_module.Queue()
        self.response_queue = queue_module.Queue()
        
    def start_discord_thread(self, token):
        """Start the Discord bot in a dedicated thread"""
        if self.discord_thread and self.discord_thread.is_alive():
            return True
        
        self.discord_thread = threading.Thread(target=self._discord_thread_worker, args=(token,), daemon=True)
        self.discord_thread.start()
        
        # Wait for the bot to be ready
        max_wait = 15
        waited = 0
        while not self.is_bot_ready and waited < max_wait:
            time.sleep(0.5)
            waited += 0.5
        
        return self.is_bot_ready
    
    def _discord_thread_worker(self, token):
        """Worker function that runs in the Discord thread"""
        try:
            # Create new event loop for this thread
            self.discord_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.discord_loop)
            
            # Create and start bot
            self.discord_loop.run_until_complete(self._create_and_run_bot(token))
        except Exception as e:
            print(f"Discord thread error: {e}")
        finally:
            try:
                self.discord_loop.close()
            except:
                pass
    
    async def _create_and_run_bot(self, token):
        """Create bot and handle commands"""
        try:
            # Create bot
            intents = discord.Intents.default()
            intents.message_content = True
            intents.voice_states = True
            
            self.bot = commands.Bot(command_prefix='!', intents=intents)
            
            @self.bot.event
            async def on_ready():
                print(f'{self.bot.user} has connected to Discord!')
                self.is_bot_ready = True
            
            @self.bot.event
            async def on_disconnect():
                print('Bot disconnected from Discord')
                self.is_bot_ready = False
                self.voice_client = None
                
                # Reset playback state when bot disconnects
                self._reset_playback_state()
                
            @self.bot.event
            async def on_voice_state_update(member, before, after):
                # Check if the bot was disconnected from voice
                if member == self.bot.user and before.channel and not after.channel:
                    print('Bot was disconnected from voice channel')
                    self.voice_client = None
                    self._reset_playback_state()
            
            # Start bot and command processor concurrently
            bot_task = asyncio.create_task(self.bot.start(token))
            command_task = asyncio.create_task(self._process_commands())
            
            await asyncio.gather(bot_task, command_task, return_exceptions=True)
            
        except Exception as e:
            print(f"Error in bot creation: {e}")
    
    async def _process_commands(self):
        """Process commands from the queue"""
        while True:
            try:
                # Check for commands every 0.1 seconds
                await asyncio.sleep(0.1)
                
                try:
                    command, args, response_id = self.command_queue.get_nowait()
                    
                    if command == 'join_voice':
                        result = await self._join_voice_channel_internal(args['channel_id'])
                        self.response_queue.put((response_id, result))
                    elif command == 'leave_voice':
                        result = await self._leave_voice_channel_internal()
                        self.response_queue.put((response_id, result))
                    elif command == 'play_song':
                        result = await self._play_song_internal(args['file_path'])
                        self.response_queue.put((response_id, result))
                    elif command == 'pause_resume':
                        result = await self._pause_resume_internal()
                        self.response_queue.put((response_id, result))
                    elif command == 'stop_playback':
                        result = await self._stop_playback_internal()
                        self.response_queue.put((response_id, result))
                    elif command == 'song_ended':
                        # Handle automatic progression to next song
                        result = await self._handle_song_ended()
                        if response_id != 'auto_next':
                            self.response_queue.put((response_id, result))
                    elif command == 'stop':
                        break
                        
                except queue_module.Empty:
                    continue
                    
            except Exception as e:
                print(f"Error processing command: {e}")
    
    async def _join_voice_channel_internal(self, channel_id):
        """Internal method to join voice channel (runs in Discord thread)"""
        try:
            if not self.is_bot_ready:
                return False, "Bot is not connected to Discord"
            
            self.target_channel_id = channel_id
            
            # Get the channel
            channel = self.bot.get_channel(int(channel_id))
            if not channel or not hasattr(channel, 'connect'):
                return False, f"Voice channel {channel_id} not found"
            
            # If already connected to a different channel, disconnect first
            if self.voice_client and self.voice_client.is_connected():
                if self.voice_client.channel.id == int(channel_id):
                    return True, f"Already connected to {channel.name}"
                await self.voice_client.disconnect()
            
            # Connect to the new channel
            self.voice_client = await channel.connect()
            print(f"Joined voice channel: {channel.name}")
            return True, f"Joined voice channel: {channel.name}"
            
        except Exception as e:
            print(f"Failed to join voice channel: {e}")
            return False, f"Failed to join voice channel: {str(e)}"
    
    async def _leave_voice_channel_internal(self):
        """Internal method to leave voice channel (runs in Discord thread)"""
        try:
            if self.voice_client and self.voice_client.is_connected():
                channel_name = self.voice_client.channel.name
                await self.voice_client.disconnect()
                self.voice_client = None
                print(f"Left voice channel: {channel_name}")
                return True, f"Left voice channel: {channel_name}"
            else:
                return True, "Not connected to any voice channel"
                
        except Exception as e:
            print(f"Failed to leave voice channel: {e}")
            return False, f"Failed to leave voice channel: {str(e)}"
    
    def join_voice_channel(self, channel_id):
        """Join a voice channel (called from Flask)"""
        try:
            if not self.is_bot_ready:
                return False, "Bot is not connected to Discord"
            
            # Send command to Discord thread
            response_id = str(uuid.uuid4())
            self.command_queue.put(('join_voice', {'channel_id': channel_id}, response_id))
            
            # Wait for response
            max_wait = 10
            waited = 0
            while waited < max_wait:
                try:
                    resp_id, result = self.response_queue.get_nowait()
                    if resp_id == response_id:
                        return result
                except queue_module.Empty:
                    time.sleep(0.1)
                    waited += 0.1
            
            return False, "Operation timed out"
            
        except Exception as e:
            print(f"Error joining voice channel: {e}")
            return False, f"Failed to join voice channel: {str(e)}"
    
    def leave_voice_channel(self):
        """Leave the current voice channel (called from Flask)"""
        try:
            # Send command to Discord thread
            response_id = str(uuid.uuid4())
            self.command_queue.put(('leave_voice', {}, response_id))
            
            # Wait for response
            max_wait = 10
            waited = 0
            while waited < max_wait:
                try:
                    resp_id, result = self.response_queue.get_nowait()
                    if resp_id == response_id:
                        return result
                except queue_module.Empty:
                    time.sleep(0.1)
                    waited += 0.1
            
            return False, "Operation timed out"
            
        except Exception as e:
            print(f"Error leaving voice channel: {e}")
            return False, f"Failed to leave voice channel: {str(e)}"
    
    async def _play_song_internal(self, file_path):
        """Internal method to play a song (runs in Discord thread)"""
        try:
            if not self.voice_client or not self.voice_client.is_connected():
                return False, "Not connected to voice channel"
            
            if self.voice_client.is_playing():
                self.voice_client.stop()
            
            # Check if file exists
            if not os.path.exists(file_path):
                return False, f"Audio file not found: {file_path}"
            
            # Generate unique song ID for this playback instance
            song_id = str(uuid.uuid4())
            
            # Create FFmpeg source with basic options
            source = discord.FFmpegPCMAudio(
                file_path,
                options='-vn'
            )
            
            # Play the audio with callback to trigger next song
            def after_playing(error):
                if error:
                    print(f"Player error: {error}")
                else:
                    print(f"Song {song_id} finished playing")
                    
                    # Check if this song was manually stopped
                    with song_change_lock:
                        was_manual_skip = song_id in manual_skip_ids
                        if was_manual_skip:
                            manual_skip_ids.discard(song_id)  # Clean up
                    
                    # Only trigger auto-advance for natural endings
                    if not was_manual_skip:
                        print(f"Natural song end for {song_id} - triggering auto-advance")
                        self.command_queue.put(('song_ended', {}, 'auto_next'))
                    else:
                        print(f"Manual skip detected for {song_id} - skipping auto-advance")
            
            # Update current song ID globally and start playback
            global current_song_id
            with song_change_lock:
                current_song_id = song_id
            
            self.voice_client.play(source, after=after_playing)
            return True, "Song started playing"
            
        except Exception as e:
            print(f"Failed to play song: {e}")
            return False, f"Failed to play song: {str(e)}"
    
    async def _pause_resume_internal(self):
        """Internal method to pause/resume playback (runs in Discord thread)"""
        try:
            if not self.voice_client or not self.voice_client.is_connected():
                return False, "Not connected to voice channel"
            
            if self.voice_client.is_playing():
                self.voice_client.pause()
                return True, "Playback paused"
            elif self.voice_client.is_paused():
                self.voice_client.resume()
                return True, "Playback resumed"
            else:
                return False, "No audio currently playing"
                
        except Exception as e:
            print(f"Failed to pause/resume: {e}")
            return False, f"Failed to pause/resume: {str(e)}"
    
    async def _stop_playback_internal(self):
        """Internal method to stop playback (runs in Discord thread)"""
        try:
            if not self.voice_client or not self.voice_client.is_connected():
                return False, "Not connected to voice channel"
            
            if self.voice_client.is_playing() or self.voice_client.is_paused():
                # Mark current song as manually stopped before stopping
                global current_song_id
                if current_song_id:
                    with song_change_lock:
                        manual_skip_ids.add(current_song_id)
                        print(f"Marked song {current_song_id} as manually stopped (full stop)")
                
                self.voice_client.stop()
                return True, "Playback stopped"
            else:
                return False, "No audio currently playing"
                
        except Exception as e:
            print(f"Failed to stop playback: {e}")
            return False, f"Failed to stop playback: {str(e)}"
    
    async def _handle_song_ended(self):
        """Internal method to handle when a song ends (runs in Discord thread)"""
        try:
            # Set the global flag to trigger play_next in Flask thread
            global song_ended_flag
            song_ended_flag.set()
            print("Song ended, triggering next song...")
            return True, "Song ended handled"
        except Exception as e:
            print(f"Error handling song end: {e}")
            return False, f"Failed to handle song end: {str(e)}"

    def play_song(self, file_path):
        """Play a song (called from Flask)"""
        try:
            if not self.is_bot_ready:
                return False, "Bot is not connected to Discord"
            
            # Send command to Discord thread
            response_id = str(uuid.uuid4())
            self.command_queue.put(('play_song', {'file_path': file_path}, response_id))
            
            # Wait for response
            max_wait = 10
            waited = 0
            while waited < max_wait:
                try:
                    resp_id, result = self.response_queue.get_nowait()
                    if resp_id == response_id:
                        return result
                except queue_module.Empty:
                    time.sleep(0.1)
                    waited += 0.1
            
            return False, "Operation timed out"
            
        except Exception as e:
            print(f"Error playing song: {e}")
            return False, f"Failed to play song: {str(e)}"
    
    def pause_resume(self):
        """Pause/Resume playback (called from Flask)"""
        try:
            if not self.is_bot_ready:
                return False, "Bot is not connected to Discord"
            
            # Send command to Discord thread
            response_id = str(uuid.uuid4())
            self.command_queue.put(('pause_resume', {}, response_id))
            
            # Wait for response
            max_wait = 10
            waited = 0
            while waited < max_wait:
                try:
                    resp_id, result = self.response_queue.get_nowait()
                    if resp_id == response_id:
                        return result
                except queue_module.Empty:
                    time.sleep(0.1)
                    waited += 0.1
            
            return False, "Operation timed out"
            
        except Exception as e:
            print(f"Error pausing/resuming: {e}")
            return False, f"Failed to pause/resume: {str(e)}"
    
    def stop_playback(self):
        """Stop playback (called from Flask)"""
        try:
            if not self.is_bot_ready:
                return False, "Bot is not connected to Discord"
            
            # Send command to Discord thread
            response_id = str(uuid.uuid4())
            self.command_queue.put(('stop_playback', {}, response_id))
            
            # Wait for response
            max_wait = 10
            waited = 0
            while waited < max_wait:
                try:
                    resp_id, result = self.response_queue.get_nowait()
                    if resp_id == response_id:
                        return result
                except queue_module.Empty:
                    time.sleep(0.1)
                    waited += 0.1
            
            return False, "Operation timed out"
            
        except Exception as e:
            print(f"Error stopping playback: {e}")
            return False, f"Failed to stop playback: {str(e)}"

    def get_status(self):
        """Get current connection status"""
        voice_connected = False
        current_channel_id = None
        is_playing = False
        is_paused = False
        
        if self.voice_client and self.voice_client.is_connected():
            voice_connected = True
            current_channel_id = str(self.voice_client.channel.id)
            is_playing = self.voice_client.is_playing()
            is_paused = self.voice_client.is_paused()
        
        return {
            'bot_ready': self.is_bot_ready,
            'voice_connected': voice_connected,
            'current_channel_id': current_channel_id,
            'target_channel_id': self.target_channel_id,
            'is_playing': is_playing,
            'is_paused': is_paused
        }
    
    def _reset_playback_state(self):
        """Reset global playback state when disconnected"""
        global is_playing, is_paused, current_song_info, current_playlist, shuffled_queue, current_song_index
        
        try:
            is_playing = False
            is_paused = True
            current_song_info = None
            current_playlist = None
            shuffled_queue = []
            current_song_index = 0
            
            # Clean up song tracking
            cleanup_song_tracking()
            
            print("Playback state reset due to Discord disconnect")
            
            # Broadcast state changes to frontend
            broadcast_discord_status_change()
            broadcast_player_state_change()
            
        except Exception as e:
            print(f"Error resetting playback state: {e}")

    def stop_bot(self):
        """Stop the bot completely"""
        try:
            # Send stop command
            self.command_queue.put(('stop', {}, 'stop'))
            
            # Wait for thread to finish
            if self.discord_thread and self.discord_thread.is_alive():
                self.discord_thread.join(timeout=5)
            
            # Clean up
            self.bot = None
            self.voice_client = None
            self.is_bot_ready = False
            self.target_channel_id = None
            self.discord_thread = None
            self.discord_loop = None
            
            print("Discord bot stopped")
            return True
        except Exception as e:
            print(f"Error stopping bot: {e}")
            return False

# Initialize Discord bot manager
discord_bot = MusicBot()

def auto_start_discord_bot():
    """Auto-start Discord bot if credentials are available"""
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r') as f:
                settings = json.load(f)
            
            discord_settings = settings.get('discord', {})
            bot_token = discord_settings.get('botToken', '').strip()
            
            if bot_token and len(bot_token) > 50:
                print("Auto-starting Discord bot...")
                success = discord_bot.start_discord_thread(bot_token)
                if success:
                    print("Discord bot auto-started successfully")
                else:
                    print("Failed to auto-start Discord bot")
            else:
                print("No valid bot token found, skipping auto-start")
        else:
            print("No settings file found, skipping Discord bot auto-start")
    except Exception as e:
        print(f"Error auto-starting Discord bot: {e}")

def start_discord_bot_background():
    """Start Discord bot in background thread"""
    try:
        auto_start_discord_bot()
    except Exception as e:
        print(f"Failed to start Discord bot in background: {e}")

# Auto-start Discord bot when server starts
import threading
discord_startup_thread = threading.Thread(target=start_discord_bot_background, daemon=True)
discord_startup_thread.start()

def song_monitor_worker():
    """Background thread to monitor for song endings and trigger next song"""
    global song_ended_flag
    
    while True:
        try:
            # Wait for song end signal
            song_ended_flag.wait()
            song_ended_flag.clear()  # Reset the flag
            
            print("Song monitor detected song ended")
            print("Natural song end - proceeding with auto-advance...")
            
            # Small delay to ensure Discord voice client is in proper state
            time.sleep(0.5)
            
            # Call auto_advance_next to advance to next song
            success, message = auto_advance_next()
            if success:
                print(f"Auto-advanced to next song: {message}")
            else:
                print(f"Failed to auto-advance: {message}")
                
        except Exception as e:
            print(f"Error in song monitor worker: {e}")
            time.sleep(1)  # Prevent tight loop on errors

# Start song monitor thread
song_monitor_thread = threading.Thread(target=song_monitor_worker, daemon=True)
song_monitor_thread.start()

def cleanup_downloads():
    """Cleanup function for graceful shutdown"""
    download_manager.running = False
    # Wait for workers to finish current downloads
    time.sleep(2)
    
    # Cleanup Discord bot
    try:
        discord_bot.stop_bot()
    except Exception as e:
        print(f"Error cleaning up Discord bot: {e}")

# Register cleanup function
def signal_handler(sig, frame):
    print('Shutting down gracefully...')
    cleanup_downloads()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def create_hash(name):
    return hashlib.sha256(name.encode()).hexdigest()[:16]

def load_playlist(playlist_name):
    """Load playlist data from JSON file"""
    try:
        playlist_path = os.path.join(PLAYLIST_DIR, f"{playlist_name}.json")
        if not os.path.exists(playlist_path):
            return None
        
        with open(playlist_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading playlist {playlist_name}: {e}")
        return None

def shuffle_playlist_songs(songs):
    """Shuffle songs and return a new list"""
    shuffled = songs.copy()
    random.shuffle(shuffled)
    return shuffled

def get_song_file_path(filename):
    """Get full absolute path to song file in library"""
    return os.path.abspath(os.path.join(LIBRARY_DIR, filename))

def cleanup_song_tracking():
    """Clean up song tracking data"""
    global current_song_id
    with song_change_lock:
        current_song_id = None
        manual_skip_ids.clear()
        print("Cleaned up song tracking data")

def get_next_song():
    """Get the next song in the shuffled queue"""
    global current_song_index, shuffled_queue
    
    if not shuffled_queue:
        return None
    
    current_song_index = (current_song_index + 1) % len(shuffled_queue)
    return shuffled_queue[current_song_index]

def get_previous_song():
    """Get the previous song in the shuffled queue"""
    global current_song_index, shuffled_queue
    
    if not shuffled_queue:
        return None
    
    current_song_index = (current_song_index - 1) % len(shuffled_queue)
    return shuffled_queue[current_song_index]

def get_current_song():
    """Get the current song"""
    global current_song_index, shuffled_queue
    
    if not shuffled_queue or current_song_index >= len(shuffled_queue):
        return None
    
    return shuffled_queue[current_song_index]

def get_elapsed_time():
    """Get elapsed time in seconds for current song"""
    global song_start_time, is_playing, is_paused, paused_at_time
    
    if not song_start_time:
        return 0
    
    if is_paused and paused_at_time:
        # If paused, return time up to when we paused
        return paused_at_time - song_start_time
    elif is_playing:
        # If playing, return current elapsed time
        return time.time() - song_start_time
    else:
        return 0

def start_song_timer(duration=0):
    """Start tracking time for a new song"""
    global song_start_time, song_duration, paused_at_time
    
    song_start_time = time.time()
    song_duration = duration
    paused_at_time = None

def pause_song_timer():
    """Pause the song timer"""
    global paused_at_time, song_start_time
    
    if song_start_time and not paused_at_time:
        paused_at_time = time.time()

def resume_song_timer():
    """Resume the song timer"""
    global song_start_time, paused_at_time
    
    if paused_at_time and song_start_time:
        # Calculate how long we were paused and adjust start time
        pause_duration = time.time() - paused_at_time
        song_start_time += pause_duration
        paused_at_time = None

# Global set to track frontend clients
player_state_clients = set()

def broadcast_player_state_change():
    """Broadcast player state change to all connected frontend clients"""
    try:
        # Get current Discord status
        discord_status = discord_bot.get_status()
        
        # Get current player state
        state_data = {
            'type': 'player_state_change',
            'is_playing': is_playing,
            'is_paused': is_paused,
            'current_song': current_song_info,
            'current_playlist': {
                'name': current_playlist['name'] if current_playlist else None,
                'image': current_playlist.get('image') if current_playlist else None
            } if current_playlist else None,
            'queue_position': current_song_index if shuffled_queue else 0,
            'queue_length': len(shuffled_queue) if shuffled_queue else 0,
            'shuffled_queue': shuffled_queue if shuffled_queue else [],
            'elapsed_time': get_elapsed_time(),
            'song_duration': song_duration,
            'discord_status': {
                'bot_ready': discord_status['bot_ready'],
                'voice_connected': discord_status['voice_connected'],
                'current_channel_id': discord_status['current_channel_id']
            }
        }
        
        data = json.dumps(state_data)
        dead_clients = set()
        
        for client in player_state_clients.copy():  # Create copy to avoid modification during iteration
            try:
                client.put_nowait(f"data: {data}\n\n")
            except queue_module.Full:
                # Client queue is full, mark as dead
                dead_clients.add(client)
            except:
                # Any other error, mark as dead
                dead_clients.add(client)
        
        # Remove dead clients
        if dead_clients:
            player_state_clients.difference_update(dead_clients)
            print(f"Removed {len(dead_clients)} dead player SSE clients")
        
        print(f"Broadcasted player state change to {len(player_state_clients)} active clients")
        
    except Exception as e:
        print(f"Error broadcasting player state change: {e}")

def broadcast_discord_status_change():
    """Broadcast Discord status change to all connected frontend clients"""
    try:
        # Get current Discord status
        discord_status = discord_bot.get_status()
        
        state_data = {
            'type': 'discord_status_change',
            'discord_status': {
                'bot_ready': discord_status['bot_ready'],
                'voice_connected': discord_status['voice_connected'],
                'current_channel_id': discord_status['current_channel_id']
            }
        }
        
        data = json.dumps(state_data)
        dead_clients = set()
        
        for client in player_state_clients.copy():  # Create copy to avoid modification during iteration
            try:
                client.put_nowait(f"data: {data}\n\n")
            except queue_module.Full:
                # Client queue is full, mark as dead
                dead_clients.add(client)
            except:
                # Any other error, mark as dead
                dead_clients.add(client)
        
        # Remove dead clients
        if dead_clients:
            player_state_clients.difference_update(dead_clients)
            print(f"Removed {len(dead_clients)} dead Discord SSE clients")
        
        print(f"Broadcasted Discord status change to {len(player_state_clients)} active clients")
        
    except Exception as e:
        print(f"Error broadcasting Discord status change: {e}")

def _play_song_by_direction(direction, is_manual=True):
    """Internal function to play next/previous song with manual flag control"""
    global current_song_info, is_playing, is_paused, current_song_id
    
    try:
        if not shuffled_queue:
            print("No playlist is currently playing")
            return False, "No playlist is currently playing"
        
        if not discord_bot.get_status()['voice_connected']:
            print("Not connected to voice channel")
            return False, "Not connected to voice channel"
        
        # If this is a manual skip, mark the current song as manually stopped
        if is_manual and current_song_id:
            with song_change_lock:
                manual_skip_ids.add(current_song_id)
                print(f"Marked song {current_song_id} as manually stopped")
        
        # Stop current playback if any
        if discord_bot.get_status()['is_playing'] or discord_bot.get_status()['is_paused']:
            discord_bot.stop_playback()
        
        # Get next or previous song based on direction
        if direction == "next":
            target_song = get_next_song()
            action = "next"
        else:
            target_song = get_previous_song()
            action = "previous"
        
        if not target_song:
            print(f"No {action} song available")
            return False, f"No {action} song available"
        
        # Check if song file exists
        song_file_path = get_song_file_path(target_song['filename'])
        print(f"Playing {action} song: {target_song['filename']}")
        print(f"Full file path: {song_file_path}")
        print(f"File exists: {os.path.exists(song_file_path)}")
        
        if not os.path.exists(song_file_path):
            print(f"Song file not found: {target_song['filename']}")
            return False, f"Song file not found: {target_song['filename']}"
        
        # Play target song
        success, message = discord_bot.play_song(song_file_path)
        if success:
            current_song_info = target_song
            is_playing = True
            is_paused = False
            
            # Start song timer for new song
            start_song_timer(target_song.get('duration', 0))
            
            print(f"Successfully started playing: {target_song['title']}")
            
            # Broadcast state change to frontend if not manual
            if not is_manual:
                broadcast_player_state_change()
            
            return True, f"Now playing: {target_song['title']}"
        else:
            print(f"Failed to play {action} song: {message}")
            return False, message
        
    except Exception as e:
        print(f"Error in play_{action}: {str(e)}")
        return False, f"Failed to play {action} song: {str(e)}"

def play_next():
    """Play the next song in the queue (manual action)"""
    return _play_song_by_direction("next", is_manual=True)

def auto_advance_next():
    """Auto-advance to next song (automatic action)"""
    return _play_song_by_direction("next", is_manual=False)

def play_previous():
    """Play the previous song in the queue (manual action)"""
    return _play_song_by_direction("previous", is_manual=True)

# Authentication routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        if verify_credentials(username, password):
            session['logged_in'] = True
            session['username'] = username
            
            # Redirect to next page or default to playlists
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            return redirect(url_for('playlists'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('login'))

@app.route('/')
def index():
    return redirect('/playlists')

# return playlists.html
@app.route('/playlists')
@login_required
def playlists():
    return render_template('playlists.html')

# return playlist view page
@app.route('/playlist/<playlist_name>')
@login_required
def playlist_view(playlist_name):
    return render_template('playlist_view.html', playlist_name=playlist_name)

@app.route('/api/playlists', methods=['GET'])
@login_required
def get_playlists():
    """
    Returns all playlists with their attributes.
    Reads all JSON files from the playlists directory with caching.
    """
    global playlist_cache, last_cache_update
    
    try:
        current_time = time.time()
        
        # Check if cache is still valid
        if (current_time - last_cache_update < cache_timeout and 
            'playlists' in playlist_cache and 'tags' in playlist_cache):
            return jsonify(playlist_cache)
        
        playlists = []
        tags = []
        
        # Check if playlists directory exists
        if not os.path.exists(PLAYLIST_DIR):
            result = {'playlists': [], 'tags': []}
            playlist_cache = result
            last_cache_update = current_time
            return jsonify(result)
        
        # Read all JSON files in the playlists directory
        for filename in os.listdir(PLAYLIST_DIR):
            if filename.endswith('.json'):
                playlist_path = os.path.join(PLAYLIST_DIR, filename)
                try:
                    with open(playlist_path, 'r') as f:
                        playlist_data = json.load(f)
                        
                        # Add the serialized name (filename without .json)
                        playlist_data['serialized_name'] = filename[:-5]  # Remove .json extension
                        
                        # Ensure all required fields exist with defaults
                        playlist_data.setdefault('name', 'Unnamed Playlist')
                        playlist_data.setdefault('tags', [])
                        for tag in playlist_data['tags']:
                            if tag not in tags:
                                tags.append(tag)
                        playlist_data.setdefault('image', None)
                        playlist_data.setdefault('songs', [])
                        playlist_data.setdefault('created_at', datetime.datetime.now().isoformat())
                        
                        # Calculate song count
                        playlist_data['song_count'] = len(playlist_data['songs'])
                        
                        playlists.append(playlist_data)
                        
                except (json.JSONDecodeError, IOError) as e:
                    print(f"Error reading playlist file {filename}: {str(e)}")
                    continue
        
        result = {'playlists': playlists, 'tags': tags}
        
        # Update cache
        playlist_cache = result
        last_cache_update = current_time
        
        return jsonify(result)
        
    except Exception as e:
        print(f"Error getting playlists: {str(e)}")
        return jsonify({'error': 'Failed to retrieve playlists'}), 500

@app.route('/api/playlists/<playlist_name>', methods=['GET'])
@login_required
def get_playlist(playlist_name):
    playlist_path = os.path.join(PLAYLIST_DIR, playlist_name + '.json')
    if not os.path.exists(playlist_path):
        return jsonify({'error': 'Playlist not found'}), 404
    with open(playlist_path, 'r') as f:
        return jsonify(json.load(f))

@app.route('/playlists/<playlist_name>', methods=['POST'])
@login_required
def update_playlist(playlist_name):
    '''
    request will contain name, array of tags.
    if the user uploads an image, it will be saved to static/img/[serialized_playlist_name].jpg
    the endpoint will create a [serialized_playlist_name].json file in the playlists directory if it doesn't exist.
    if it does exist, error will be returned saying that the playlist already exists.
    '''
    try:
        # Get form data
        playlist_name_form = request.form.get('name')
        if not playlist_name_form:
            return jsonify({'message': 'Playlist name is required'}), 400
        
        # Parse tags from JSON string
        tags_json = request.form.get('tags', '[]')
        try:
            tags = json.loads(tags_json)
        except json.JSONDecodeError:
            return jsonify({'message': 'Invalid tags format'}), 400
        
        # Create serialized name for file storage
        serialized_name = create_hash(playlist_name_form)
        
        # Check if playlist already exists
        playlist_file_path = os.path.join(PLAYLIST_DIR, f"{serialized_name}.json")
        if os.path.exists(playlist_file_path):
            return jsonify({'message': 'Playlist already exists'}), 409
        
        # Handle image upload if provided
        image_path = None
        if 'image' in request.files:
            image_file = request.files['image']
            if image_file and image_file.filename:
                # Ensure static/img directory exists
                img_dir = os.path.join('static', 'img')
                os.makedirs(img_dir, exist_ok=True)
                
                # Get file extension
                file_ext = os.path.splitext(image_file.filename)[1].lower()
                if not file_ext:
                    file_ext = '.jpg'  # Default to jpg if no extension
                
                # Save image with serialized name
                image_filename = f"{serialized_name}{file_ext}"
                image_path = os.path.join(img_dir, image_filename)
                image_file.save(image_path)
                
                # Store relative path for JSON
                image_path = f"static/img/{image_filename}"
        
        # Create playlist data
        playlist_data = {
            'name': playlist_name_form,
            'tags': tags,
            'image': image_path,
            'songs': [],
            'created_at': datetime.datetime.now().isoformat()
        }
        
        # Save playlist JSON file
        with open(playlist_file_path, 'w') as f:
            json.dump(playlist_data, f, indent=2)
        
        # Invalidate cache
        invalidate_playlist_cache()
        
        return jsonify({
            'message': 'Playlist created successfully',
            'playlist': {
                'name': playlist_name_form,
                'serialized_name': serialized_name,
                'tags': tags,
                'image': image_path
            }
        }), 201
        
    except Exception as e:
        # Log the error for debugging
        print(f"Error creating playlist: {str(e)}")
        return jsonify({'message': 'An error occurred while creating the playlist'}), 500

@app.route('/playlists/<playlist_name>', methods=['PUT'])
@login_required
def update_playlist_put(playlist_name):
    '''
    Update a playlist by its serialized name.
    Request will contain name, tags, and optionally an image.
    '''
    try:
        # Check if playlist exists
        playlist_file_path = os.path.join(PLAYLIST_DIR, f"{playlist_name}.json")
        if not os.path.exists(playlist_file_path):
            return jsonify({'message': 'Playlist not found'}), 404
        
        # Read existing playlist data
        with open(playlist_file_path, 'r') as f:
            playlist_data = json.load(f)
        
        # Get form data
        new_name = request.form.get('name')
        if not new_name:
            return jsonify({'message': 'Playlist name is required'}), 400
        
        # Parse tags from JSON string
        tags_json = request.form.get('tags', '[]')
        try:
            tags = json.loads(tags_json)
        except json.JSONDecodeError:
            return jsonify({'message': 'Invalid tags format'}), 400
        
        # Handle image upload if provided
        if 'image' in request.files:
            image_file = request.files['image']
            if image_file and image_file.filename:
                # Delete old image if it exists
                old_image_path = playlist_data.get('image')
                if old_image_path and os.path.exists(old_image_path):
                    try:
                        os.remove(old_image_path)
                    except OSError:
                        pass  # Continue even if old image deletion fails
                
                # Ensure static/img directory exists
                img_dir = os.path.join('static', 'img')
                os.makedirs(img_dir, exist_ok=True)
                
                # Get file extension
                file_ext = os.path.splitext(image_file.filename)[1].lower()
                if not file_ext:
                    file_ext = '.jpg'  # Default to jpg if no extension
                
                # Save new image with same serialized name
                image_filename = f"{playlist_name}{file_ext}"
                image_path = os.path.join(img_dir, image_filename)
                image_file.save(image_path)
                
                # Update image path in playlist data
                playlist_data['image'] = f"static/img/{image_filename}"
        
        # Update playlist data
        playlist_data['name'] = new_name
        playlist_data['tags'] = tags
        
        # Save updated playlist JSON file
        with open(playlist_file_path, 'w') as f:
            json.dump(playlist_data, f, indent=2)
        
        # Invalidate cache
        invalidate_playlist_cache()
        
        return jsonify({
            'message': 'Playlist updated successfully',
            'playlist': playlist_data
        }), 200
        
    except Exception as e:
        print(f"Error updating playlist: {str(e)}")
        return jsonify({'message': 'An error occurred while updating the playlist'}), 500

@app.route('/playlists/<playlist_name>', methods=['DELETE'])
@login_required
def delete_playlist(playlist_name):
    '''
    Delete a playlist by its serialized name.
    This will delete both the JSON file and associated image if it exists.
    '''
    try:
        # Check if playlist JSON file exists
        playlist_file_path = os.path.join(PLAYLIST_DIR, f"{playlist_name}.json")
        if not os.path.exists(playlist_file_path):
            return jsonify({'message': 'Playlist not found'}), 404
        
        # Read playlist data to get image path before deletion
        image_path = None
        try:
            with open(playlist_file_path, 'r') as f:
                playlist_data = json.load(f)
                image_path = playlist_data.get('image')
        except (json.JSONDecodeError, IOError):
            # Continue with deletion even if we can't read the file
            pass
        
        # Delete the playlist JSON file
        os.remove(playlist_file_path)
        
        # Delete associated image if it exists
        if image_path and os.path.exists(image_path):
            try:
                os.remove(image_path)
            except OSError as e:
                # Log error but don't fail the deletion
                print(f"Warning: Could not delete image file {image_path}: {str(e)}")
        
        # Invalidate cache
        invalidate_playlist_cache()
        
        return jsonify({'message': 'Playlist deleted successfully'}), 200
        
    except Exception as e:
        print(f"Error deleting playlist: {str(e)}")
        return jsonify({'message': 'An error occurred while deleting the playlist'}), 500

@app.route('/api/playlists/<playlist_name>/songs', methods=['POST'])
@login_required
def add_song_to_playlist(playlist_name):
    """Add a song from library to playlist"""
    try:
        data = request.get_json()
        
        if not data or 'song_id' not in data:
            return jsonify({'success': False, 'error': 'Song ID is required'}), 400
        
        song_id = data['song_id']
        
        # Check if playlist exists
        playlist_file_path = os.path.join(PLAYLIST_DIR, f"{playlist_name}.json")
        if not os.path.exists(playlist_file_path):
            return jsonify({'success': False, 'error': 'Playlist not found'}), 404
        
        # Find the song in library
        song_file = None
        for filename in os.listdir(LIBRARY_DIR):
            if filename.endswith(('.mp3', '.wav', '.flac', '.m4a')):
                if create_hash(filename) == song_id:
                    song_file = filename
                    break
        
        if not song_file:
            return jsonify({'success': False, 'error': 'Song not found in library'}), 404
        
        # Load playlist data
        with open(playlist_file_path, 'r') as f:
            playlist_data = json.load(f)
        
        # Check if song is already in playlist
        for song in playlist_data.get('songs', []):
            if song.get('library_song_id') == song_id:
                return jsonify({'success': False, 'error': 'Song already in playlist'}), 409
        
        # Get song metadata
        file_path = os.path.join(LIBRARY_DIR, song_file)
        title = song_file
        duration = 0
        
        try:
            audio_file = MutagenFile(file_path)
            if audio_file is not None:
                title = str(audio_file.get('TIT2', [song_file])[0]) if audio_file.get('TIT2') else song_file
                duration = int(audio_file.info.length) if hasattr(audio_file, 'info') and hasattr(audio_file.info, 'length') else 0
        except:
            pass
        
        # Clean title (remove file extension)
        title = title.replace('.mp3', '').replace('.wav', '').replace('.flac', '').replace('.m4a', '')
        
        # Create song entry
        song_entry = {
            'id': str(uuid.uuid4()),
            'library_song_id': song_id,
            'title': title,
            'filename': song_file,
            'duration': duration,
            'added_at': datetime.datetime.now().isoformat()
        }
        
        # Add song to playlist
        if 'songs' not in playlist_data:
            playlist_data['songs'] = []
        
        playlist_data['songs'].append(song_entry)
        
        # Save playlist
        with open(playlist_file_path, 'w') as f:
            json.dump(playlist_data, f, indent=2)
        
        return jsonify({
            'success': True,
            'message': 'Song added to playlist successfully',
            'song': song_entry
        })
        
    except Exception as e:
        print(f"Error adding song to playlist: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to add song to playlist'}), 500

@app.route('/api/playlists/<playlist_name>/songs/<song_id>', methods=['DELETE'])
@login_required
def remove_song_from_playlist(playlist_name, song_id):
    """Remove a song from playlist (not from library)"""
    try:
        # Check if playlist exists
        playlist_file_path = os.path.join(PLAYLIST_DIR, f"{playlist_name}.json")
        if not os.path.exists(playlist_file_path):
            return jsonify({'success': False, 'error': 'Playlist not found'}), 404
        
        # Load playlist data
        with open(playlist_file_path, 'r') as f:
            playlist_data = json.load(f)
        
        # Find and remove song
        original_count = len(playlist_data.get('songs', []))
        playlist_data['songs'] = [
            song for song in playlist_data.get('songs', [])
            if song.get('id') != song_id
        ]
        
        if len(playlist_data['songs']) == original_count:
            return jsonify({'success': False, 'error': 'Song not found in playlist'}), 404
        
        # Save playlist
        with open(playlist_file_path, 'w') as f:
            json.dump(playlist_data, f, indent=2)
        
        return jsonify({
            'success': True,
            'message': 'Song removed from playlist successfully'
        })
        
    except Exception as e:
        print(f"Error removing song from playlist: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to remove song from playlist'}), 500


@app.route('/library')
@login_required
def library():
    return render_template('library.html')

@app.route('/api/library', methods=['GET'])
@login_required
def get_library():
    """Get all songs in the library"""
    try:
        songs = []
        
        if not os.path.exists(LIBRARY_DIR):
            return jsonify({'songs': []})
        
        for filename in os.listdir(LIBRARY_DIR):
            if filename.endswith(('.mp3', '.wav', '.flac', '.m4a')):
                file_path = os.path.join(LIBRARY_DIR, filename)
                
                try:
                    # Get file stats
                    stat = os.stat(file_path)
                    
                    # Try to extract metadata
                    title = filename
                    duration = 0
                    
                    try:
                        audio_file = MutagenFile(file_path)
                        if audio_file is not None:
                            title = str(audio_file.get('TIT2', [filename])[0]) if audio_file.get('TIT2') else filename
                            duration = int(audio_file.info.length) if hasattr(audio_file, 'info') and hasattr(audio_file.info, 'length') else 0
                    except:
                        pass
                    
                    song_info = {
                        'id': create_hash(filename),
                        'title': title.replace('.mp3', '').replace('.wav', '').replace('.flac', '').replace('.m4a', ''),
                        'filename': filename,
                        'duration': duration,
                        'size': stat.st_size,
                        'added_date': datetime.datetime.fromtimestamp(stat.st_ctime).isoformat()
                    }
                    
                    songs.append(song_info)
                    
                except Exception as e:
                    print(f"Error processing file {filename}: {e}")
                    continue
        
        # Sort by added date (newest first)
        songs.sort(key=lambda x: x['added_date'], reverse=True)
        
        return jsonify({'songs': songs})
        
    except Exception as e:
        print(f"Error getting library: {str(e)}")
        return jsonify({'error': 'Failed to retrieve library'}), 500

@app.route('/api/library', methods=['POST'])
@login_required
def add_to_library():
    """Download song from YouTube and add to library with real-time progress"""
    try:
        data = request.get_json()
        
        if not data or 'url' not in data:
            return jsonify({'success': False, 'error': 'URL is required'}), 400
        
        url = data['url'].strip()
        target_playlist = data.get('target_playlist')
        
        # Validate YouTube URL
        youtube_patterns = [
            r'https?://(www\.)?youtube\.com/watch\?v=[\w-]+',
            r'https?://(www\.)?youtu\.be/[\w-]+',
            r'https?://(www\.)?youtube\.com/embed/[\w-]+'
        ]
        
        if not any(re.match(pattern, url) for pattern in youtube_patterns):
            return jsonify({'success': False, 'error': 'Invalid YouTube URL'}), 400
        
        # Check if ffmpeg is available
        try:
            subprocess.run(['ffmpeg', '-version'], capture_output=True, timeout=5)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return jsonify({'success': False, 'error': 'FFmpeg is not installed or not available'}), 500
        
        # Generate unique download ID
        download_id = str(uuid.uuid4())
        
        # Add download to manager
        download_info = download_manager.add_download(download_id, url, target_playlist)
        
        return jsonify({
            'success': True,
            'download_id': download_id,
            'message': 'Download started successfully'
        }), 200
        
    except Exception as e:
        print(f"Error starting download: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to start download'}), 500

@app.route('/api/downloads/status')
@login_required
def get_downloads_status():
    """Get status of all downloads"""
    try:
        downloads = download_manager.get_all_downloads()
        # Only return active downloads (not completed or failed older than 30 seconds)
        current_time = time.time()
        active_downloads = []
        
        for download in downloads:
            if download['status'] in [DownloadStatus.PENDING, DownloadStatus.DOWNLOADING, 
                                    DownloadStatus.PROCESSING, DownloadStatus.NORMALIZING, 
                                    DownloadStatus.MOVING]:
                active_downloads.append(download)
            elif download['status'] in [DownloadStatus.COMPLETED, DownloadStatus.FAILED]:
                # Keep recent completed/failed downloads for a short time
                if current_time - download['created_at'] < 30:
                    active_downloads.append(download)
        
        return jsonify({'downloads': active_downloads})
    except Exception as e:
        print(f"Error getting download status: {str(e)}")
        return jsonify({'error': 'Failed to get download status'}), 500

@app.route('/api/downloads/stream')
@login_required
def download_stream():
    """Server-Sent Events stream for download progress"""
    def event_stream():
        client_queue = queue_module.Queue(maxsize=100)  # Limit queue size
        client_id = str(uuid.uuid4())
        sse_clients.add(client_queue)
        
        print(f"Download SSE client {client_id} connected. Total clients: {len(sse_clients)}")
        
        try:
            while True:
                try:
                    data = client_queue.get(timeout=30)  # 30 second timeout
                    # Skip test messages from cleanup
                    if "test" not in data:
                        yield data
                except queue_module.Empty:
                    # Send heartbeat to keep connection alive
                    yield "data: {\"type\": \"heartbeat\"}\n\n"
                except queue_module.Full:
                    # Queue is full, client is probably dead
                    print(f"Download SSE client {client_id} queue full, disconnecting")
                    break
        except GeneratorExit:
            print(f"Download SSE client {client_id} disconnected (GeneratorExit)")
        except Exception as e:
            print(f"Download SSE client {client_id} error: {e}")
        finally:
            sse_clients.discard(client_queue)
            print(f"Download SSE client {client_id} removed. Remaining clients: {len(sse_clients)}")
    
    return Response(event_stream(), mimetype='text/event-stream',
                   headers={'Cache-Control': 'no-cache',
                           'Connection': 'keep-alive',
                           'Access-Control-Allow-Origin': '*'})

@app.route('/api/player/stream')
@login_required
def player_state_stream():
    """Server-Sent Events stream for player state changes"""
    def event_stream():
        client_queue = queue_module.Queue(maxsize=50)  # Limit queue size
        client_id = str(uuid.uuid4())
        player_state_clients.add(client_queue)
        
        print(f"Player SSE client {client_id} connected. Total clients: {len(player_state_clients)}")
        
        # Send initial state immediately
        try:
            initial_state = {
                'type': 'player_state_change',
                'is_playing': is_playing,
                'is_paused': is_paused,
                'current_song': current_song_info,
                'current_playlist': {
                    'name': current_playlist['name'] if current_playlist else None,
                    'image': current_playlist.get('image') if current_playlist else None
                } if current_playlist else None,
                'queue_position': current_song_index if shuffled_queue else 0,
                'queue_length': len(shuffled_queue) if shuffled_queue else 0,
                'shuffled_queue': shuffled_queue if shuffled_queue else [],
                'elapsed_time': get_elapsed_time(),
                'song_duration': song_duration,
                'discord_status': discord_bot.get_status()
            }
            yield f"data: {json.dumps(initial_state)}\n\n"
        except Exception as e:
            print(f"Error sending initial state to player SSE client {client_id}: {e}")
        
        try:
            while True:
                try:
                    data = client_queue.get(timeout=30)  # 30 second timeout
                    # Skip test messages from cleanup
                    if "test" not in data:
                        yield data
                except queue_module.Empty:
                    # Send heartbeat to keep connection alive
                    yield "data: {\"type\": \"heartbeat\"}\n\n"
                except queue_module.Full:
                    # Queue is full, client is probably dead
                    print(f"Player SSE client {client_id} queue full, disconnecting")
                    break
        except GeneratorExit:
            print(f"Player SSE client {client_id} disconnected (GeneratorExit)")
        except Exception as e:
            print(f"Player SSE client {client_id} error: {e}")
        finally:
            player_state_clients.discard(client_queue)
            print(f"Player SSE client {client_id} removed. Remaining clients: {len(player_state_clients)}")
    
    return Response(event_stream(), mimetype='text/event-stream',
                   headers={'Cache-Control': 'no-cache',
                           'Connection': 'keep-alive',
                           'Access-Control-Allow-Origin': '*'})

@app.route('/api/library/<song_id>/rename', methods=['POST'])
@login_required
def rename_song(song_id):
    """Rename a song in the library"""
    try:
        data = request.get_json()
        
        if not data or 'title' not in data:
            return jsonify({'success': False, 'error': 'Title is required'}), 400
        
        new_title = data['title'].strip()
        
        if not new_title:
            return jsonify({'success': False, 'error': 'Title cannot be empty'}), 400
        
        # Find the song file by scanning the library directory
        song_file = None
        for filename in os.listdir(LIBRARY_DIR):
            if filename.endswith(('.mp3', '.wav', '.flac', '.m4a')):
                if create_hash(filename) == song_id:
                    song_file = filename
                    break
        
        if not song_file:
            return jsonify({'success': False, 'error': 'Song not found'}), 404
        
        old_path = os.path.join(LIBRARY_DIR, song_file)
        
        # Create new filename with sanitized title
        safe_title = re.sub(r'[<>:"/\\|?*]', '_', new_title)
        file_extension = os.path.splitext(song_file)[1]
        new_filename = f"{safe_title}{file_extension}"
        new_path = os.path.join(LIBRARY_DIR, new_filename)
        
        # Ensure unique filename
        counter = 1
        while os.path.exists(new_path) and new_path != old_path:
            name, ext = os.path.splitext(new_filename)
            new_filename = f"{safe_title} ({counter}){ext}"
            new_path = os.path.join(LIBRARY_DIR, new_filename)
            counter += 1
        
        # Rename the file
        if old_path != new_path:
            os.rename(old_path, new_path)
        
        # Update ID3 tags
        try:
            audio_file = MutagenFile(new_path)
            if audio_file is not None:
                # Remove existing tags and add new ones
                audio_file.delete()
                audio_file.save()
                
                # Add ID3 tags
                audio_file = ID3(new_path)
                audio_file.add(TIT2(encoding=3, text=new_title))
                audio_file.save()
        except Exception as e:
            print(f"Failed to update metadata: {e}")
        
        return jsonify({
            'success': True, 
            'message': 'Song renamed successfully',
            'new_filename': new_filename
        })
        
    except Exception as e:
        print(f"Error renaming song: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to rename song'}), 500

@app.route('/api/library/<song_id>/delete', methods=['DELETE'])
@login_required
def delete_song(song_id):
    """Delete a song from the library and remove from all playlists"""
    try:
        # Find the song file by scanning the library directory
        song_file = None
        for filename in os.listdir(LIBRARY_DIR):
            if filename.endswith(('.mp3', '.wav', '.flac', '.m4a')):
                if create_hash(filename) == song_id:
                    song_file = filename
                    break
        
        if not song_file:
            return jsonify({'success': False, 'error': 'Song not found'}), 404
        
        file_path = os.path.join(LIBRARY_DIR, song_file)
        
        try:
            # Delete the file
            os.remove(file_path)
            
            # Remove song from all playlists
            removed_from_playlists = []
            if os.path.exists(PLAYLIST_DIR):
                for playlist_filename in os.listdir(PLAYLIST_DIR):
                    if playlist_filename.endswith('.json'):
                        playlist_path = os.path.join(PLAYLIST_DIR, playlist_filename)
                        try:
                            with open(playlist_path, 'r') as f:
                                playlist_data = json.load(f)
                            
                            # Count songs before removal
                            original_count = len(playlist_data.get('songs', []))
                            
                            # Remove songs that match this library song
                            playlist_data['songs'] = [
                                song for song in playlist_data.get('songs', [])
                                if song.get('library_song_id') != song_id and song.get('filename') != song_file
                            ]
                            
                            # If songs were removed, save the playlist and track it
                            if len(playlist_data['songs']) < original_count:
                                with open(playlist_path, 'w') as f:
                                    json.dump(playlist_data, f, indent=2)
                                removed_from_playlists.append(playlist_data.get('name', playlist_filename[:-5]))
                                
                        except (json.JSONDecodeError, IOError) as e:
                            print(f"Error updating playlist {playlist_filename}: {e}")
                            continue
            
            response_message = 'Song deleted successfully'
            if removed_from_playlists:
                response_message += f' and removed from {len(removed_from_playlists)} playlist(s): {", ".join(removed_from_playlists)}'
            
            return jsonify({
                'success': True, 
                'message': response_message,
                'removed_from_playlists': removed_from_playlists
            })
            
        except OSError as e:
            print(f"Failed to delete file {file_path}: {e}")
            return jsonify({'success': False, 'error': 'Failed to delete file from disk'}), 500
        
    except Exception as e:
        print(f"Error deleting song: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to delete song'}), 500

@app.route('/player/play', methods=['POST'])
@login_required
def play_playlist():
    """Start playing a playlist (shuffled)"""
    global current_playlist, shuffled_queue, current_song_index, is_playing, is_paused, current_song_info
    
    try:
        data = request.get_json()
        if not data or 'playlist_name' not in data:
            return jsonify({'success': False, 'error': 'Playlist name is required'}), 400
        
        playlist_name = data['playlist_name']
        
        # Load playlist data
        playlist_data = load_playlist(playlist_name)
        if not playlist_data:
            return jsonify({'success': False, 'error': 'Playlist not found'}), 404
        
        if not playlist_data.get('songs'):
            return jsonify({'success': False, 'error': 'Playlist is empty'}), 400
        
        # Join voice channel if not already connected
        if not discord_bot.get_status()['voice_connected']:
            # Load settings to get channel ID
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, 'r') as f:
                    settings = json.load(f)
                channel_id = settings.get('discord', {}).get('channelId', '').strip()
                
                if channel_id:
                    success, message = discord_bot.join_voice_channel(channel_id)
                    if not success:
                        return jsonify({'success': False, 'error': f'Failed to join voice channel: {message}'}), 500
                    else:
                        # Broadcast Discord status change after successful connection
                        broadcast_discord_status_change()
                else:
                    return jsonify({'success': False, 'error': 'Discord channel not configured'}), 400
        
        # Set up playlist for playback
        current_playlist = playlist_data
        shuffled_queue = shuffle_playlist_songs(playlist_data['songs'])
        current_song_index = 0
        
        # Clean up any previous song tracking
        cleanup_song_tracking()
        
        # Get first song and start playing
        current_song = get_current_song()
        if not current_song:
            return jsonify({'success': False, 'error': 'No songs to play'}), 400
        
        # Check if song file exists
        song_file_path = get_song_file_path(current_song['filename'])
        print(f"Attempting to play song: {current_song['filename']}")
        print(f"Full file path: {song_file_path}")
        print(f"File exists: {os.path.exists(song_file_path)}")
        
        if not os.path.exists(song_file_path):
            return jsonify({'success': False, 'error': f'Song file not found: {current_song["filename"]}'}), 404
        
        # Start playing
        success, message = discord_bot.play_song(song_file_path)
        if success:
            is_playing = True
            is_paused = False
            current_song_info = current_song
            
            # Start song timer
            start_song_timer(current_song.get('duration', 0))
            
            return jsonify({
                'success': True,
                'message': 'Playlist started playing',
                'current_song': current_song,
                'playlist': {
                    'name': playlist_data['name'],
                    'image': playlist_data.get('image')
                },
                'queue_position': current_song_index,
                'queue_length': len(shuffled_queue),
                'shuffled_queue': shuffled_queue
            })
        else:
            return jsonify({'success': False, 'error': message}), 500
        
    except Exception as e:
        print(f"Error playing playlist: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to play playlist'}), 500

@app.route('/player/playpause', methods=['POST'])
@login_required
def toggle_playback():
    """Toggle play/pause state"""
    global is_playing, is_paused
    
    try:
        if not discord_bot.get_status()['voice_connected']:
            return jsonify({'success': False, 'error': 'Not connected to voice channel'}), 400
        
        success, message = discord_bot.pause_resume()
        if success:
            # Update state based on current Discord bot state
            bot_status = discord_bot.get_status()
            was_playing = is_playing
            is_playing = bot_status['is_playing']
            is_paused = bot_status['is_paused']
            
            # Handle timer based on state change
            if was_playing and is_paused:
                pause_song_timer()
            elif not was_playing and is_playing:
                resume_song_timer()
            
            return jsonify({
                'success': True,
                'message': message,
                'is_playing': is_playing,
                'is_paused': is_paused
            })
        else:
            return jsonify({'success': False, 'error': message}), 500
        
    except Exception as e:
        print(f"Error toggling playback: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to toggle playback'}), 500

@app.route('/player/next', methods=['POST'])
@login_required
def skip_to_next():
    """Skip to next song in shuffled queue"""
    try:
        # Use the centralized play_next function
        success, message = play_next()
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Skipped to next song',
                'current_song': current_song_info,
                'playlist': {
                    'name': current_playlist['name'] if current_playlist else None,
                    'image': current_playlist.get('image') if current_playlist else None
                },
                'queue_position': current_song_index,
                'queue_length': len(shuffled_queue),
                'shuffled_queue': shuffled_queue
            })
        else:
            return jsonify({'success': False, 'error': message}), 500
        
    except Exception as e:
        print(f"Error skipping to next song: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to skip to next song'}), 500

@app.route('/player/previous', methods=['POST'])
@login_required
def skip_to_previous():
    """Skip to previous song in shuffled queue"""
    try:
        # Use the centralized play_previous function
        success, message = play_previous()
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Skipped to previous song',
                'current_song': current_song_info,
                'playlist': {
                    'name': current_playlist['name'] if current_playlist else None,
                    'image': current_playlist.get('image') if current_playlist else None
                },
                'queue_position': current_song_index,
                'queue_length': len(shuffled_queue),
                'shuffled_queue': shuffled_queue
            })
        else:
            return jsonify({'success': False, 'error': message}), 500
        
    except Exception as e:
        print(f"Error skipping to previous song: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to skip to previous song'}), 500

@app.route('/api/player/status', methods=['GET'])
@login_required
def get_player_status():
    """Get current player status"""
    try:
        bot_status = discord_bot.get_status()
        
        return jsonify({
            'success': True,
            'is_playing': is_playing,
            'is_paused': is_paused,
            'voice_connected': bot_status['voice_connected'],
            'bot_ready': bot_status['bot_ready'],
            'current_song': current_song_info,
            'current_playlist': {
                'name': current_playlist['name'] if current_playlist else None,
                'image': current_playlist.get('image') if current_playlist else None
            } if current_playlist else None,
            'queue_position': current_song_index if shuffled_queue else 0,
            'queue_length': len(shuffled_queue) if shuffled_queue else 0,
            'shuffled_queue': shuffled_queue if shuffled_queue else [],  # Return full queue for UI
            'elapsed_time': get_elapsed_time(),
            'song_duration': song_duration
        })
        
    except Exception as e:
        print(f"Error getting player status: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to get player status'}), 500

@app.route('/settings')
@login_required
def settings():
    return render_template('settings.html')

@app.route('/api/settings', methods=['GET'])
@login_required
def get_settings():
    """Get current settings"""
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r') as f:
                settings = json.load(f)
        else:
            # Default settings
            settings = {
                'discord': {
                    'botToken': '',
                    'channelId': '',
                    'connected': False
                },
                'general': {
                    'autoPlay': True,
                    'showNotifications': True,
                    'defaultVolume': 50
                }
            }
        
        return jsonify({'success': True, 'settings': settings})
        
    except Exception as e:
        print(f"Error loading settings: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to load settings'}), 500

@app.route('/api/settings', methods=['POST'])
@login_required
def save_settings():
    """Save settings to file"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        # Load existing settings or create new ones
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r') as f:
                settings = json.load(f)
        else:
            settings = {
                'discord': {
                    'botToken': '',
                    'channelId': '',
                    'connected': False
                },
                'general': {
                    'autoPlay': True,
                    'showNotifications': True,
                    'defaultVolume': 50
                }
            }
        
        # Update settings with provided data
        if 'discord' in data:
            settings['discord'].update(data['discord'])
        
        if 'general' in data:
            settings['general'].update(data['general'])
        
        # Save to file
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=2)
        
        return jsonify({'success': True, 'message': 'Settings saved successfully'})
        
    except Exception as e:
        print(f"Error saving settings: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to save settings'}), 500

@app.route('/api/discord/join-voice', methods=['POST'])
@login_required
def join_voice_channel():
    """Join Discord voice channel"""
    try:
        # Load settings to get channel ID
        if not os.path.exists(SETTINGS_FILE):
            return jsonify({'success': False, 'error': 'Discord settings not configured'}), 400
        
        with open(SETTINGS_FILE, 'r') as f:
            settings = json.load(f)
        
        discord_settings = settings.get('discord', {})
        channel_id = discord_settings.get('channelId', '').strip()
        
        if not channel_id:
            return jsonify({'success': False, 'error': 'Channel ID must be configured in settings'}), 400
        
        if not channel_id.isdigit() or len(channel_id) < 17 or len(channel_id) > 19:
            return jsonify({'success': False, 'error': 'Invalid channel ID format'}), 400
        
        # Join voice channel
        success, message = discord_bot.join_voice_channel(channel_id)
        
        if success:
            # Broadcast Discord status change after successful connection
            broadcast_discord_status_change()
            return jsonify({'success': True, 'message': message})
        else:
            return jsonify({'success': False, 'error': message}), 500
        
    except Exception as e:
        print(f"Error joining voice channel: {str(e)}")
        return jsonify({'success': False, 'error': f'Failed to join voice channel: {str(e)}'}), 500

@app.route('/api/discord/leave-voice', methods=['POST'])
@login_required
def leave_voice_channel():
    """Leave Discord voice channel"""
    global is_playing, is_paused, current_song_info, current_playlist, shuffled_queue, current_song_index
    
    try:
        # Leave voice channel
        success, message = discord_bot.leave_voice_channel()
        
        if success:
            # Stop playback and reset player state
            is_playing = False
            is_paused = True
            current_song_info = None
            current_playlist = None
            shuffled_queue = []
            current_song_index = 0
            
            # Clean up song tracking
            cleanup_song_tracking()
            
            print("Playback stopped and player state reset due to voice channel disconnect")
            
            # Broadcast both Discord status change and player state change
            broadcast_discord_status_change()
            broadcast_player_state_change()
            
            return jsonify({'success': True, 'message': message})
        else:
            return jsonify({'success': False, 'error': message}), 500
        
    except Exception as e:
        print(f"Error leaving voice channel: {str(e)}")
        return jsonify({'success': False, 'error': f'Failed to leave voice channel: {str(e)}'}), 500

@app.route('/api/discord/status', methods=['GET'])
@login_required
def get_discord_status():
    """Get current Discord bot status"""
    try:
        # Get bot status
        bot_status = discord_bot.get_status()
        
        # Get target channel from settings
        target_channel_id = None
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r') as f:
                settings = json.load(f)
            target_channel_id = settings.get('discord', {}).get('channelId', '')
        
        print(f"Discord status - Bot Ready: {bot_status['bot_ready']}, Voice Connected: {bot_status['voice_connected']}, Current Channel: {bot_status['current_channel_id']}, Target Channel: {target_channel_id}")
        
        # Return status - green if in voice channel, grey if not
        return jsonify({
            'success': True,
            'bot_ready': bot_status['bot_ready'],
            'voice_connected': bot_status['voice_connected'],
            'current_channel_id': bot_status['current_channel_id'],
            'target_channel_id': target_channel_id
        })
        
    except Exception as e:
        print(f"Error getting Discord status: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to get status'}), 500

@app.route('/api/settings/test-discord', methods=['POST'])
@login_required
def test_discord_connection():
    """Test Discord bot connection"""
    try:
        data = request.get_json()
        
        if not data or 'botToken' not in data or 'channelId' not in data:
            return jsonify({'success': False, 'error': 'Bot token and channel ID are required'}), 400
        
        bot_token = data['botToken'].strip()
        channel_id = data['channelId'].strip()
        
        # Validate inputs
        if not bot_token:
            return jsonify({'success': False, 'error': 'Bot token is required'}), 400
        
        if not channel_id or not channel_id.isdigit() or len(channel_id) < 17 or len(channel_id) > 19:
            return jsonify({'success': False, 'error': 'Valid channel ID is required'}), 400
        
        # Test connection with the provided credentials
        if len(bot_token) < 50:
            return jsonify({'success': False, 'error': 'Invalid bot token format'}), 400
        
        # For testing, we'll create a temporary test bot
        # This is a simplified test that just validates the token format
        # In production, you might want to implement a more comprehensive test
        
        # Update settings file with connection status
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, 'r') as f:
                    settings = json.load(f)
            else:
                settings = {
                    'discord': {'botToken': '', 'channelId': '', 'connected': False},
                    'general': {'autoPlay': True, 'showNotifications': True, 'defaultVolume': 50}
                }
            
            settings['discord']['botToken'] = bot_token
            settings['discord']['channelId'] = channel_id
            settings['discord']['connected'] = False  # Not permanently connected yet
            
            with open(SETTINGS_FILE, 'w') as f:
                json.dump(settings, f, indent=2)
                
        except Exception as e:
            print(f"Error updating settings after test: {e}")
        
        return jsonify({'success': True, 'message': 'Discord credentials saved successfully'})
        
    except Exception as e:
        print(f"Error testing Discord connection: {str(e)}")
        return jsonify({'success': False, 'error': 'Connection test failed'}), 500

@app.route('/api/settings/change-password', methods=['POST'])
@login_required
def change_password():
    """Change user password"""
    try:
        data = request.get_json()
        
        if not data or 'current_password' not in data or 'new_password' not in data:
            return jsonify({'success': False, 'error': 'Current password and new password are required'}), 400
        
        current_password = data['current_password']
        new_password = data['new_password'].strip()
        new_username = data.get('new_username', '').strip()
        
        # Verify current password
        current_username = session.get('username', 'admin')
        if not verify_credentials(current_username, current_password):
            return jsonify({'success': False, 'error': 'Current password is incorrect'}), 400
        
        # Validate new password
        if len(new_password) < 6:
            return jsonify({'success': False, 'error': 'New password must be at least 6 characters long'}), 400
        
        # Use current username if no new username provided
        if not new_username:
            new_username = current_username
        
        # Validate new username
        if len(new_username.strip()) < 3:
            return jsonify({'success': False, 'error': 'Username must be at least 3 characters long'}), 400
        
        # Save new credentials
        save_auth_config(new_username, new_password)
        
        # Update session with new username
        session['username'] = new_username
        
        return jsonify({
            'success': True, 
            'message': 'Login credentials updated successfully'
        })
        
    except Exception as e:
        print(f"Error changing password: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to update credentials'}), 500

# Add cleanup functions for better resource management

def invalidate_playlist_cache():
    """Invalidate playlist cache when playlists are modified"""
    global playlist_cache, last_cache_update
    playlist_cache.clear()
    last_cache_update = 0
    print("Playlist cache invalidated")

def invalidate_library_cache():
    """Invalidate library cache when library is modified"""
    global library_cache
    library_cache.clear()
    print("Library cache invalidated")

def cleanup_old_downloads():
    """Clean up old completed/failed downloads to prevent memory buildup"""
    global download_manager
    
    try:
        current_time = time.time()
        with download_manager.lock:
            # Remove downloads older than 5 minutes if completed/failed
            downloads_to_remove = []
            for download_id, download_info in download_manager.downloads.items():
                if download_info['status'] in [DownloadStatus.COMPLETED, DownloadStatus.FAILED]:
                    if current_time - download_info['created_at'] > 300:  # 5 minutes
                        downloads_to_remove.append(download_id)
            
            for download_id in downloads_to_remove:
                del download_manager.downloads[download_id]
                print(f"Cleaned up old download: {download_id}")
    except Exception as e:
        print(f"Error cleaning up old downloads: {e}")

def cleanup_dead_sse_connections():
    """Remove dead SSE connections"""
    global sse_clients, player_state_clients
    
    try:
        # Clean download SSE clients
        dead_clients = set()
        for client in sse_clients.copy():
            try:
                # Try to put a test message to check if connection is alive
                client.put_nowait("data: {\"type\": \"test\"}\n\n")
            except:
                dead_clients.add(client)
        
        sse_clients.difference_update(dead_clients)
        
        # Clean player state SSE clients
        dead_clients = set()
        for client in player_state_clients.copy():
            try:
                client.put_nowait("data: {\"type\": \"test\"}\n\n")
            except:
                dead_clients.add(client)
        
        player_state_clients.difference_update(dead_clients)
        
        print(f"Cleaned up SSE connections. Active download clients: {len(sse_clients)}, player clients: {len(player_state_clients)}")
        
    except Exception as e:
        print(f"Error cleaning up SSE connections: {e}")

# Periodic cleanup function
def periodic_cleanup():
    """Run periodic cleanup tasks"""
    while True:
        try:
            time.sleep(60)  # Run every minute
            cleanup_old_downloads()
            cleanup_dead_sse_connections()
        except Exception as e:
            print(f"Error in periodic cleanup: {e}")
            time.sleep(10)

# Start periodic cleanup thread
cleanup_thread = threading.Thread(target=periodic_cleanup, daemon=True)
cleanup_thread.start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=9321, debug=True)

