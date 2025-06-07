// Base template functionality
document.addEventListener('DOMContentLoaded', function() {
    // Sidebar playlist management
    let sidebarPlaylists = [];
    let filteredSidebarPlaylists = [];
    
    // Elements
    const createPlaylistBtn = document.querySelector('.create-playlist-btn');
    const sidebarSearchInput = document.querySelector('.search-input');
    const playlistsList = document.querySelector('.playlists-list');
    
    // Load playlists for sidebar
    loadSidebarPlaylists();
    
    // Create playlist button functionality
    if (createPlaylistBtn) {
        createPlaylistBtn.addEventListener('click', function() {
            // Check if we're on the playlists page
            if (window.location.pathname === '/playlists' || window.location.pathname.includes('playlists')) {
                // If the modal exists on this page, open it
                if (typeof window.openCreatePlaylistModal === 'function') {
                    window.openCreatePlaylistModal();
                } else {
                    // If modal doesn't exist yet, wait for it to load
                    setTimeout(() => {
                        if (typeof window.openCreatePlaylistModal === 'function') {
                            window.openCreatePlaylistModal();
                        }
                    }, 100);
                }
            } else {
                // If not on playlists page, redirect there
                window.location.href = '/playlists';
            }
        });
    }
    
    // Sidebar search functionality
    if (sidebarSearchInput) {
        sidebarSearchInput.addEventListener('input', function() {
            const searchTerm = this.value.toLowerCase().trim();
            filterSidebarPlaylists(searchTerm);
        });
    }
    
    // Function to load playlists for sidebar
    async function loadSidebarPlaylists() {
        try {
            const response = await fetch('/api/playlists');
            if (response.ok) {
                const data = await response.json();
                sidebarPlaylists = data.playlists || [];
                filteredSidebarPlaylists = [...sidebarPlaylists];
                populateSidebarPlaylists();
            } else {
                console.error('Failed to load playlists for sidebar');
            }
        } catch (error) {
            console.error('Error loading sidebar playlists:', error);
        }
    }
    
    // Function to filter sidebar playlists
    function filterSidebarPlaylists(searchTerm) {
        if (searchTerm === '') {
            filteredSidebarPlaylists = [...sidebarPlaylists];
        } else {
            filteredSidebarPlaylists = sidebarPlaylists.filter(playlist => {
                return playlist.name.toLowerCase().includes(searchTerm) ||
                       (playlist.tags && playlist.tags.some(tag => 
                           tag.toLowerCase().includes(searchTerm)
                       ));
            });
        }
        populateSidebarPlaylists();
    }
    
    // Function to populate sidebar playlists
    function populateSidebarPlaylists() {
        if (!playlistsList) return;
        
        // Clear existing playlist items
        playlistsList.innerHTML = '';
        
        // Sort playlists alphabetically
        const sortedPlaylists = [...filteredSidebarPlaylists]
            .sort((a, b) => a.name.toLowerCase().localeCompare(b.name.toLowerCase()));
        
        // Create playlist items
        sortedPlaylists.forEach(playlist => {
            const playlistItem = createSidebarPlaylistItem(playlist);
            playlistsList.appendChild(playlistItem);
        });
        
        // Show message if no playlists found
        if (filteredSidebarPlaylists.length === 0) {
            const emptyMessage = document.createElement('div');
            emptyMessage.className = 'empty-playlists-message';
            emptyMessage.textContent = sidebarPlaylists.length === 0 ? 'No playlists yet' : 'No playlists found';
            playlistsList.appendChild(emptyMessage);
        }
    }
    
    // Function to create sidebar playlist item
    function createSidebarPlaylistItem(playlist) {
        const playlistItem = document.createElement('div');
        playlistItem.className = 'playlist-item';
        playlistItem.onclick = () => {
            // Navigate to specific playlist view page using serialized_name (unique ID)
            window.location.href = `/playlist/${encodeURIComponent(playlist.serialized_name)}`;
        };
        
        // Ensure image path is absolute from web root
        const imagePath = playlist.image && !playlist.image.startsWith('/') ? `/${playlist.image}` : playlist.image;
        
        playlistItem.innerHTML = `
            <div class="playlist-icon">
                ${imagePath ? 
                    `<img src="${imagePath}" alt="${playlist.name}" style="width: 20px; height: 20px; border-radius: 4px; object-fit: cover;">` :
                    `<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/>
                    </svg>`
                }
            </div>
            <span title="${playlist.name}">${playlist.name}</span>
        `;
        
        return playlistItem;
    }
    
    // Make functions globally accessible for other scripts to refresh the sidebar
    window.refreshSidebarPlaylists = loadSidebarPlaylists;
    
    // Music Player functionality
    const playPauseBtn = document.getElementById('play-pause-btn');
    const previousBtn = document.getElementById('previous-btn');
    const nextBtn = document.getElementById('next-btn');
    
    // Player state
    let playerState = {
        isPlaying: false,
        isPaused: true,
        currentSong: null,
        currentPlaylist: null,
        queuePosition: 0,
        queueLength: 0,
        shuffledQueue: [],
        elapsedTime: 0,
        songDuration: 0
    };
    
    // Progress tracking
    let progressTimer = null;
    
    // Music player controls
    if (playPauseBtn) {
        playPauseBtn.addEventListener('click', async function() {
            await togglePlayback();
        });
    }
    
    if (previousBtn) {
        previousBtn.addEventListener('click', async function() {
            await skipToPrevious();
        });
    }
    
    if (nextBtn) {
        nextBtn.addEventListener('click', async function() {
            await skipToNext();
        });
    }
    
    // Play/pause toggle function
    async function togglePlayback() {
        try {
            const response = await fetch('/player/playpause', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            const data = await response.json();
            
            if (data.success) {
                playerState.isPlaying = data.is_playing;
                playerState.isPaused = data.is_paused;
                updatePlayPauseButton();
                
                // Handle timer based on play state
                if (playerState.isPlaying && !playerState.isPaused) {
                    startProgressTimer();
                } else {
                    stopProgressTimer();
                }
            } else {
                console.error('Failed to toggle playback:', data.error);
            }
        } catch (error) {
            console.error('Error toggling playback:', error);
        }
    }
    
    // Skip to next song
    async function skipToNext() {
        try {
            const response = await fetch('/player/next', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
                    const data = await response.json();
        
        if (data.success) {
            playerState.currentSong = data.current_song;
            playerState.currentPlaylist = data.playlist;
            playerState.queuePosition = data.queue_position;
            playerState.queueLength = data.queue_length;
            playerState.shuffledQueue = data.shuffled_queue || [];
            playerState.isPlaying = true;
            playerState.isPaused = false;
            
            updateNowPlaying();
            updatePlayPauseButton();
            updateQueue();
            
            // Reset and start timer for new song
            syncProgressTime(0, data.current_song?.duration || 0);
        } else {
            console.error('Failed to skip to next song:', data.error);
            }
        } catch (error) {
            console.error('Error skipping to next:', error);
        }
    }
    
    // Skip to previous song
    async function skipToPrevious() {
        try {
            const response = await fetch('/player/previous', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
                    const data = await response.json();
        
        if (data.success) {
            playerState.currentSong = data.current_song;
            playerState.currentPlaylist = data.playlist;
            playerState.queuePosition = data.queue_position;
            playerState.queueLength = data.queue_length;
            playerState.shuffledQueue = data.shuffled_queue || [];
            playerState.isPlaying = true;
            playerState.isPaused = false;
            
            updateNowPlaying();
            updatePlayPauseButton();
            updateQueue();
            
            // Reset and start timer for new song
            syncProgressTime(0, data.current_song?.duration || 0);
        } else {
            console.error('Failed to skip to previous song:', data.error);
            }
        } catch (error) {
            console.error('Error skipping to previous:', error);
        }
    }
    
    // Update play/pause button icon
    function updatePlayPauseButton() {
        if (!playPauseBtn) return;
        
        const svg = playPauseBtn.querySelector('svg');
        if (playerState.isPlaying && !playerState.isPaused) {
            // Show pause icon
            svg.innerHTML = '<path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/>';
            playPauseBtn.title = 'Pause';
        } else {
            // Show play icon
            svg.innerHTML = '<path d="M8 5v14l11-7z"/>';
            playPauseBtn.title = 'Play';
        }
    }
    
    // Update now playing information
    function updateNowPlaying() {
        const currentSongTitle = document.getElementById('current-song-title');
        const currentPlaylistName = document.getElementById('current-playlist-name');
        const currentAlbumArt = document.getElementById('current-album-art');
        
        if (playerState.currentSong && playerState.currentPlaylist) {
            if (currentSongTitle) {
                currentSongTitle.textContent = playerState.currentSong.title || 'Unknown Title';
            }
            
            if (currentPlaylistName) {
                currentPlaylistName.textContent = playerState.currentPlaylist.name || 'Unknown Playlist';
            }
            
            if (currentAlbumArt) {
                if (playerState.currentPlaylist.image) {
                    currentAlbumArt.src = playerState.currentPlaylist.image.startsWith('/') 
                        ? playerState.currentPlaylist.image 
                        : `/${playerState.currentPlaylist.image}`;
                } else {
                    currentAlbumArt.src = '/static/img/default.jpg';
                }
            }
        } else {
            // Reset to default state
            if (currentSongTitle) {
                currentSongTitle.textContent = 'No song playing';
            }
            
            if (currentPlaylistName) {
                currentPlaylistName.textContent = '';
            }
            
            if (currentAlbumArt) {
                currentAlbumArt.src = '/static/img/default.jpg';
            }
        }
    }
    
    // Global function to play a playlist (called from other pages)
    window.playPlaylist = async function(playlistName) {
        try {
            const response = await fetch('/player/play', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    playlist_name: playlistName
                })
            });
            
                    const data = await response.json();
        
        if (data.success) {
            playerState.currentSong = data.current_song;
            playerState.currentPlaylist = data.playlist;
            playerState.queuePosition = data.queue_position;
            playerState.queueLength = data.queue_length;
            playerState.shuffledQueue = data.shuffled_queue || [];
            playerState.isPlaying = true;
            playerState.isPaused = false;
            
            updateNowPlaying();
            updatePlayPauseButton();
            updateQueue();
            
            // Reset and start timer for new song
            syncProgressTime(0, data.current_song?.duration || 0);
        } else {
            console.error('Failed to play playlist:', data.error);
            }
        } catch (error) {
            console.error('Error playing playlist:', error);
        }
    };
    
    // Check player status on page load
    async function checkPlayerStatus() {
        try {
            const response = await fetch('/api/player/status');
            const data = await response.json();
            
                    if (data.success) {
            playerState.isPlaying = data.is_playing;
            playerState.isPaused = data.is_paused;
            playerState.currentSong = data.current_song;
            playerState.currentPlaylist = data.current_playlist;
            playerState.queuePosition = data.queue_position;
            playerState.queueLength = data.queue_length;
            playerState.shuffledQueue = data.shuffled_queue || [];
            
            updateNowPlaying();
            updatePlayPauseButton();
            updateQueue();
            
            // Sync progress with backend time
            syncProgressTime(data.elapsed_time || 0, data.song_duration || 0);
        }
        } catch (error) {
            console.error('Error checking player status:', error);
        }
    }
    
    // Update queue display
    function updateQueue() {
        const queueCurrentSong = document.getElementById('queue-current-song');
        const queueList = document.getElementById('queue-list');
        
        if (queueCurrentSong) {
            if (playerState.currentSong) {
                queueCurrentSong.innerHTML = `
                    <div class="song-info">
                        <div class="song-title">${playerState.currentSong.title || 'Unknown Title'}</div>
                        <div class="song-artist">${playerState.currentPlaylist?.name || 'Unknown Playlist'}</div>
                    </div>
                    <div class="song-duration">${formatDuration(playerState.currentSong.duration || 0)}</div>
                `;
            } else {
                queueCurrentSong.innerHTML = `
                    <div class="song-info">
                        <div class="song-title">No song playing</div>
                        <div class="song-artist">Select a song to start</div>
                    </div>
                    <div class="song-duration">0:00</div>
                `;
            }
        }
        
        if (queueList) {
            if (playerState.shuffledQueue && playerState.shuffledQueue.length > 0) {
                // Show upcoming songs (after current song)
                const currentIndex = playerState.queuePosition || 0;
                const upcomingSongs = playerState.shuffledQueue.slice(currentIndex + 1);
                
                if (upcomingSongs.length > 0) {
                    const queueHtml = upcomingSongs.map((song, index) => `
                        <div class="queue-item" data-index="${currentIndex + 1 + index}">
                            <div class="queue-item-number">${index + 1}</div>
                            <div class="queue-item-info">
                                <div class="queue-item-title">${song.title || 'Unknown Title'}</div>
                                <div class="queue-item-artist">${playerState.currentPlaylist?.name || 'Unknown Playlist'}</div>
                            </div>
                            <div class="queue-item-duration">${formatDuration(song.duration || 0)}</div>
                        </div>
                    `).join('');
                    
                    queueList.innerHTML = queueHtml;
                } else {
                    queueList.innerHTML = `
                        <div class="empty-queue-message">
                            <svg width="48" height="48" viewBox="0 0 24 24" fill="currentColor">
                                <path d="M15 6H3v2h12V6zm0 4H3v2h12v-2zM3 16h8v-2H3v2zM17 6v8.18c-.31-.11-.65-.18-1-.18-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3V8h3V6h-5z"/>
                            </svg>
                            <p>Last song in queue</p>
                            <span>This is the final song in the playlist</span>
                        </div>
                    `;
                }
            } else {
                queueList.innerHTML = `
                    <div class="empty-queue-message">
                        <svg width="48" height="48" viewBox="0 0 24 24" fill="currentColor">
                            <path d="M15 6H3v2h12V6zm0 4H3v2h12v-2zM3 16h8v-2H3v2zM17 6v8.18c-.31-.11-.65-.18-1-.18-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3V8h3V6h-5z"/>
                        </svg>
                        <p>No songs in queue</p>
                        <span>Play a playlist to see upcoming songs</span>
                    </div>
                `;
            }
        }
    }
    
    // Format duration from seconds to MM:SS
    function formatDuration(seconds) {
        if (!seconds || seconds === 0) return '0:00';
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    }
    
    // Update progress bar and time displays
    function updateProgress() {
        const currentTimeEl = document.querySelector('.current-time');
        const totalTimeEl = document.querySelector('.total-time');
        const progressFill = document.querySelector('.progress-fill');
        
        if (currentTimeEl) {
            currentTimeEl.textContent = formatDuration(playerState.elapsedTime);
        }
        
        if (totalTimeEl) {
            totalTimeEl.textContent = formatDuration(playerState.songDuration);
        }
        
        if (progressFill && playerState.songDuration > 0) {
            const progressPercent = (playerState.elapsedTime / playerState.songDuration) * 100;
            progressFill.style.width = `${Math.min(progressPercent, 100)}%`;
        }
    }
    
    // Start progress timer
    function startProgressTimer() {
        stopProgressTimer(); // Clear any existing timer
        
        progressTimer = setInterval(() => {
            if (playerState.isPlaying && !playerState.isPaused) {
                playerState.elapsedTime += 1;
                updateProgress();
                
                // Check if song is finished
                if (playerState.elapsedTime >= playerState.songDuration && playerState.songDuration > 0) {
                    // Song finished, could trigger next song automatically
                    console.log('Song finished playing');
                }
            }
        }, 1000);
    }
    
    // Stop progress timer
    function stopProgressTimer() {
        if (progressTimer) {
            clearInterval(progressTimer);
            progressTimer = null;
        }
    }
    
    // Sync with backend time
    function syncProgressTime(elapsedTime, songDuration) {
        playerState.elapsedTime = Math.floor(elapsedTime);
        playerState.songDuration = Math.floor(songDuration);
        updateProgress();
        
        if (playerState.isPlaying && !playerState.isPaused) {
            startProgressTimer();
        }
    }
    
    // Global SSE connection management
    let playerStateEventSource = null;
    let reconnectAttempts = 0;
    const maxReconnectAttempts = 5;
    
    // Improved SSE connection management
    function setupPlayerStateStream() {
        // Close existing connection if any
        if (playerStateEventSource) {
            console.log('Closing existing player state stream');
            playerStateEventSource.close();
            playerStateEventSource = null;
        }
        
        if (typeof EventSource !== 'undefined') {
            console.log('Setting up new player state stream');
            playerStateEventSource = new EventSource('/api/player/stream');
            
            playerStateEventSource.onmessage = function(event) {
                try {
                    const data = JSON.parse(event.data);
                    
                    // Skip heartbeat and test messages
                    if (data.type === 'heartbeat' || data.type === 'test') {
                        return;
                    }
                    
                    if (data.type === 'player_state_change') {
                        console.log('Received player state change:', data);
                        
                        // Update player state
                        playerState.isPlaying = data.is_playing;
                        playerState.isPaused = data.is_paused;
                        playerState.currentSong = data.current_song;
                        playerState.currentPlaylist = data.current_playlist;
                        playerState.queuePosition = data.queue_position;
                        playerState.queueLength = data.queue_length;
                        playerState.shuffledQueue = data.shuffled_queue || [];
                        
                        // Update Discord status if included
                        if (data.discord_status) {
                            updateDiscordStatus(data.discord_status);
                        }
                        
                        // Sync progress time from server
                        syncProgressTime(data.elapsed_time || 0, data.song_duration || 0);
                        
                        // Update UI
                        updatePlayPauseButton();
                        updateNowPlaying();
                        updateQueue();
                        
                        console.log('Updated UI from SSE player state change');
                    } else if (data.type === 'discord_status_change') {
                        console.log('Received Discord status change:', data);
                        
                        // Update Discord status
                        if (data.discord_status) {
                            updateDiscordStatus(data.discord_status);
                        }
                        
                        console.log('Updated Discord status from SSE');
                    }
                } catch (error) {
                    console.error('Error processing player state change:', error);
                }
            };
            
            playerStateEventSource.onerror = function(event) {
                console.error('Player state SSE error:', event);
                
                // Attempt to reconnect with exponential backoff
                if (reconnectAttempts < maxReconnectAttempts) {
                    const delay = Math.pow(2, reconnectAttempts) * 1000; // Exponential backoff
                    reconnectAttempts++;
                    
                    console.log(`Attempting to reconnect player state stream in ${delay}ms (attempt ${reconnectAttempts})`);
                    
                    setTimeout(() => {
                        if (playerStateEventSource && playerStateEventSource.readyState === EventSource.CLOSED) {
                            setupPlayerStateStream();
                        }
                    }, delay);
                } else {
                    console.error('Max reconnection attempts reached for player state stream');
                }
            };
            
            playerStateEventSource.onopen = function(event) {
                console.log('Player state SSE connection opened');
                reconnectAttempts = 0; // Reset on successful connection
            };
        } else {
            console.warn('EventSource not supported, player state updates may not work');
        }
    }
    
    // Clean up SSE connections on page unload
    function cleanupConnections() {
        console.log('Cleaning up SSE connections');
        
        if (playerStateEventSource) {
            playerStateEventSource.close();
            playerStateEventSource = null;
        }
    }
    
    // Setup cleanup listeners
    window.addEventListener('beforeunload', cleanupConnections);
    window.addEventListener('pagehide', cleanupConnections);
    
    // Handle visibility change to reconnect when page becomes visible
    document.addEventListener('visibilitychange', function() {
        if (!document.hidden) {
            // Page became visible, check if we need to reconnect
            if (!playerStateEventSource || playerStateEventSource.readyState === EventSource.CLOSED) {
                console.log('Page became visible, reconnecting player state stream');
                setupPlayerStateStream();
            }
        }
    });
    
    // Initialize player status check
    checkPlayerStatus();
    
    // Setup player state SSE connection
    setupPlayerStateStream();
    
    // Queue functionality
    const queueBtn = document.querySelector('.queue-btn');
    const queuePane = document.getElementById('queue-pane');
    const queueOverlay = document.getElementById('queue-overlay');
    const queueCloseBtn = document.getElementById('queue-close-btn');
    
    // Toggle queue pane
    function toggleQueue() {
        const isOpen = queuePane.classList.contains('show');
        
        if (isOpen) {
            closeQueue();
        } else {
            openQueue();
        }
    }
    
    // Open queue pane
    function openQueue() {
        queuePane.classList.add('show');
        queueOverlay.classList.add('show');
    }
    
    // Close queue pane
    function closeQueue() {
        queuePane.classList.remove('show');
        queueOverlay.classList.remove('show');
    }
    
    // Event listeners for queue
    if (queueBtn) {
        queueBtn.addEventListener('click', toggleQueue);
    }
    
    if (queueCloseBtn) {
        queueCloseBtn.addEventListener('click', closeQueue);
    }
    
    if (queueOverlay) {
        queueOverlay.addEventListener('click', closeQueue);
    }
    
    // Close queue on Escape key
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && queuePane.classList.contains('show')) {
            closeQueue();
        }
    });
    
    // Function to populate queue (now handled by updateQueue in music player section)
    function populateQueue() {
        // This function is now replaced by updateQueue() in the music player section
        updateQueue();
    }
    
    // Discord button functionality
    const discordBtn = document.querySelector('.discord-btn');
    let isInVoiceChannel = false;
    let isConnecting = false;
    
    // Discord voice channel handler
    function toggleDiscordVoiceChannel() {
        if (isConnecting) {
            console.log('Discord toggle ignored: Already processing...');
            return; // Prevent multiple clicks during loading
        }
        
        console.log(`Discord toggle clicked. Current state: ${isInVoiceChannel ? 'In Voice Channel' : 'Not in Voice Channel'}`);
        
        if (isInVoiceChannel) {
            console.log('Attempting to leave voice channel...');
            leaveVoiceChannel();
        } else {
            console.log('Attempting to join voice channel...');
            joinVoiceChannel();
        }
    }
    
    async function joinVoiceChannel() {
        isConnecting = true;
        discordBtn.classList.add('loading');
        discordBtn.title = 'Joining voice channel...';
        
        try {
            const response = await fetch('/api/discord/join-voice', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            const data = await response.json();
            
                    if (data.success) {
            // Note: Discord status will be updated via SSE, but we can update immediately for responsiveness
            isInVoiceChannel = true;
            discordBtn.classList.remove('loading');
            discordBtn.classList.add('connected');
            discordBtn.title = 'In voice channel - Click to leave';
            showNotification(data.message || 'Joined voice channel successfully!', 'success');
        } else {
            discordBtn.classList.remove('loading');
            discordBtn.title = 'Join voice channel';
            showNotification(data.error || 'Failed to join voice channel', 'error');
        }
        } catch (error) {
            discordBtn.classList.remove('loading');
            discordBtn.title = 'Join voice channel';
            showNotification('Join failed: Network error', 'error');
        } finally {
            isConnecting = false;
        }
    }
    
    async function leaveVoiceChannel() {
        isConnecting = true;
        discordBtn.classList.add('loading');
        discordBtn.title = 'Leaving voice channel...';
        
        try {
            const response = await fetch('/api/discord/leave-voice', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            const data = await response.json();
            
                    if (data.success) {
            // Note: Discord status will be updated via SSE, but we can update immediately for responsiveness
            isInVoiceChannel = false;
            discordBtn.classList.remove('loading', 'connected');
            discordBtn.title = 'Join voice channel';
            showNotification(data.message || 'Left voice channel', 'info');
        } else {
            discordBtn.classList.remove('loading');
            showNotification(data.error || 'Failed to leave voice channel', 'error');
        }
        } catch (error) {
            discordBtn.classList.remove('loading');
            showNotification('Leave failed: Network error', 'error');
        } finally {
            isConnecting = false;
        }
    }
    
    // Simple notification function
    function showNotification(message, type = 'info') {
        // Create notification element
        const notification = document.createElement('div');
        notification.className = `notification notification-${type} show`;
        notification.innerHTML = `
            <div class="notification-content">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                    ${type === 'success' 
                        ? '<path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/>'
                        : type === 'error'
                        ? '<path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm5 13.59L15.59 17 12 13.41 8.41 17 7 15.59 10.59 12 7 8.41 8.41 7 12 10.59 15.59 7 17 8.41 13.41 12 17 15.59z"/>'
                        : '<path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z"/>'
                    }
                </svg>
                <span>${message}</span>
            </div>
            <button class="notification-close">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12 19 6.41z"/>
                </svg>
            </button>
        `;
        
        // Add to body
        document.body.appendChild(notification);
        
        // Auto remove after 3 seconds
        setTimeout(() => {
            notification.classList.remove('show');
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
            }, 300);
        }, 3000);
        
        // Close button handler
        const closeBtn = notification.querySelector('.notification-close');
        closeBtn.addEventListener('click', () => {
            notification.classList.remove('show');
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
            }, 300);
        });
    }
    
    // Update Discord status from data
    function updateDiscordStatus(discordStatus) {
        if (!discordBtn) return;
        
        console.log('Updating Discord status:', discordStatus);
        
        if (discordStatus.voice_connected) {
            isInVoiceChannel = true;
            discordBtn.classList.remove('loading');
            discordBtn.classList.add('connected');
            discordBtn.title = 'In voice channel - Click to leave';
            console.log('Discord status updated: In voice channel');
        } else {
            isInVoiceChannel = false;
            discordBtn.classList.remove('loading', 'connected');
            if (discordStatus.bot_ready) {
                discordBtn.title = 'Join voice channel';
                console.log('Discord status updated: Bot ready, not in voice channel');
            } else {
                discordBtn.title = 'Bot not ready';
                console.log('Discord status updated: Bot not ready');
            }
        }
    }

    // Check Discord status on page load
    async function checkDiscordStatus() {
        try {
            const response = await fetch('/api/discord/status');
            const data = await response.json();
            
            console.log('Discord status check:', data);
            
            if (data.success) {
                updateDiscordStatus({
                    bot_ready: data.bot_ready,
                    voice_connected: data.voice_connected,
                    current_channel_id: data.current_channel_id
                });
            } else {
                isInVoiceChannel = false;
                discordBtn.classList.remove('connected');
                discordBtn.title = 'Bot not ready';
            }
        } catch (error) {
            console.error('Failed to check Discord status:', error);
            isInVoiceChannel = false;
            discordBtn.classList.remove('connected');
            discordBtn.title = 'Bot not ready';
        }
    }
    
    // Event listener for Discord button
    if (discordBtn) {
        discordBtn.addEventListener('click', toggleDiscordVoiceChannel);
        // Check status on page load
        checkDiscordStatus();
    }
    
    // Make queue functions globally accessible
    window.toggleQueue = toggleQueue;
    window.openQueue = openQueue;
    window.closeQueue = closeQueue;
    window.populateQueue = populateQueue;
});
