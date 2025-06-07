// Playlist View JavaScript
let currentPlaylist = null;
let editModalSelectedTags = [];

// Get playlist name from URL
function getPlaylistNameFromUrl() {
    const pathParts = window.location.pathname.split('/');
    return pathParts[pathParts.length - 1];
}

// Load playlist data
async function loadPlaylist() {
    const playlistName = getPlaylistNameFromUrl();
    
    try {
        const response = await fetch(`/api/playlists/${encodeURIComponent(playlistName)}`);
        if (!response.ok) {
            throw new Error('Playlist not found');
        }
        
        const playlist = await response.json();
        currentPlaylist = playlist;
        displayPlaylist(playlist);
    } catch (error) {
        console.error('Error loading playlist:', error);
        showError('Failed to load playlist');
    }
}

// Display playlist information
function displayPlaylist(playlist) {
    // Update title
    document.getElementById('playlist-title').textContent = playlist.name;
    document.title = `${playlist.name} - Bard Music Player`;
    
    // Update cover art
    const coverArt = document.getElementById('playlist-cover-art');
    if (playlist.image) {
        // Ensure image path starts with / for proper web root relative path
        const imageSrc = playlist.image.startsWith('/') ? playlist.image : `/${playlist.image}`;
        coverArt.innerHTML = `
            <img src="${imageSrc}" alt="${playlist.name}" style="width: 100%; height: 100%; object-fit: cover; border-radius: 12px;">
            <div class="play-overlay">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M8 5v14l11-7z"/>
                </svg>
            </div>
        `;
    } else {
        coverArt.innerHTML = `
            <svg width="64" height="64" viewBox="0 0 24 24" fill="currentColor" style="color: #000000;">
                <path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/>
            </svg>
            <div class="play-overlay">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M8 5v14l11-7z"/>
                </svg>
            </div>
        `;
    }
    
    // Update song count
    const songCount = playlist.songs ? playlist.songs.length : 0;
    document.getElementById('playlist-song-count').textContent = `${songCount} song${songCount !== 1 ? 's' : ''}`;
    
    // Update tags
    displayTags(playlist.tags || []);
    
    // Display songs
    displaySongs(playlist.songs || []);
}

// Display tags
function displayTags(tags) {
    const tagsContainer = document.getElementById('playlist-tags');
    
    if (tags.length === 0) {
        tagsContainer.innerHTML = '';
        return;
    }
    
    tagsContainer.innerHTML = tags.map(tag => 
        `<span class="tag">${tag}</span>`
    ).join('');
}

// Display songs
function displaySongs(songs) {
    const songsContainer = document.getElementById('songs-list');
    const emptyMessage = document.getElementById('empty-playlist-message');
    
    if (songs.length === 0) {
        songsContainer.innerHTML = '';
        emptyMessage.style.display = 'block';
        return;
    }
    
    emptyMessage.style.display = 'none';
    
    const songsHtml = songs.map((song, index) => `
        <div class="library-song-row" data-song-index="${index}" onclick="playSong(${index})">
            <div class="library-song-title">${song.title || 'Unknown Title'}</div>
            <div class="library-song-duration">${formatDuration(song.duration || 0)}</div>
            <div class="library-song-size">${formatAddedDate(song.added_at)}</div>
            <div class="library-song-actions">
                <button class="remove-song-btn" 
                        onclick="event.stopPropagation(); removeSongFromPlaylist('${song.id}')"
                        title="Remove from playlist">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12 19 6.41z"/>
                    </svg>
                </button>
            </div>
        </div>
    `).join('');
    
    songsContainer.innerHTML = songsHtml;
}

// Format duration (seconds to MM:SS)
function formatDuration(seconds) {
    if (!seconds || seconds === 0) return '0:00';
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
}

// Format added date
function formatAddedDate(dateString) {
    if (!dateString) return 'Unknown';
    
    const date = new Date(dateString);
    const now = new Date();
    const diffTime = Math.abs(now - date);
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
    
    if (diffDays === 1) return 'Today';
    if (diffDays === 2) return 'Yesterday';
    if (diffDays <= 7) return `${diffDays - 1} days ago`;
    if (diffDays <= 30) return `${Math.ceil(diffDays / 7)} weeks ago`;
    
    return date.toLocaleDateString();
}

// Play playlist functionality
function playPlaylist() {
    if (!currentPlaylist) return;
    
    // Use the global playPlaylist function from base_template.js
    if (window.playPlaylist) {
        const playlistName = getPlaylistNameFromUrl();
        if (playlistName) {
            window.playPlaylist(playlistName);
        }
    } else {
    showPlayNotification(`Playing "${currentPlaylist.name}"`);
    console.log('Playing playlist:', currentPlaylist.name);
    }
}

// Play individual song
function playSong(index) {
    if (!currentPlaylist || !currentPlaylist.songs || !currentPlaylist.songs[index]) return;
    
    const song = currentPlaylist.songs[index];
    showPlayNotification(`Playing "${song.title}"`);
    console.log('Playing song:', song);
}

// Show song menu (placeholder for future functionality)
function showSongMenu(index, event) {
    event.stopPropagation();
    console.log('Show menu for song:', index);
    // Future: Implement song context menu
}

// Show play notification
function showPlayNotification(message) {
    // Remove existing notification
    const existingNotification = document.querySelector('.play-notification');
    if (existingNotification) {
        existingNotification.remove();
    }
    
    // Create notification
    const notification = document.createElement('div');
    notification.className = 'play-notification';
    notification.innerHTML = `
        <div class="notification-content">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                <path d="M8 5v14l11-7z"/>
            </svg>
            <span>${message}</span>
        </div>
    `;
    
    document.body.appendChild(notification);
    
    // Show notification
    setTimeout(() => notification.classList.add('show'), 100);
    
    // Hide notification after 3 seconds
    setTimeout(() => {
        notification.classList.remove('show');
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// Show error message
function showError(message) {
    console.error(message);
    // You could implement a toast/notification system here
    alert(message);
}

// Edit Modal Functions
function openEditModal() {
    if (!currentPlaylist) return;
    
    const modal = document.getElementById('edit-playlist-modal');
    
    // Populate form with current data
    document.getElementById('edit-playlist-id').value = currentPlaylist.serialized_name || currentPlaylist.name;
    document.getElementById('edit-playlist-name').value = currentPlaylist.name;
    
    // Set up tags
    editModalSelectedTags = [...(currentPlaylist.tags || [])];
    updateEditSelectedTags();
    
    // Set up image
    const previewImg = document.getElementById('edit-preview-image');
    const placeholder = document.querySelector('#edit-image-preview .image-placeholder');
    const removeBtn = document.getElementById('edit-remove-image-btn');
    
    if (currentPlaylist.image) {
        // Ensure image path starts with / for proper web root relative path
        const imageSrc = currentPlaylist.image.startsWith('/') ? currentPlaylist.image : `/${currentPlaylist.image}`;
        previewImg.src = imageSrc;
        previewImg.style.display = 'block';
        placeholder.style.display = 'none';
        removeBtn.style.display = 'flex';
    } else {
        previewImg.style.display = 'none';
        placeholder.style.display = 'flex';
        removeBtn.style.display = 'none';
    }
    
    // Update character count
    updateEditCharacterCount();
    
    modal.classList.add('show');
}

function closeEditModal() {
    const modal = document.getElementById('edit-playlist-modal');
    modal.classList.remove('show');
    resetEditForm();
}

function resetEditForm() {
    document.getElementById('edit-playlist-form').reset();
    editModalSelectedTags = [];
    updateEditSelectedTags();
    
    // Reset image preview
    const previewImg = document.getElementById('edit-preview-image');
    const placeholder = document.querySelector('#edit-image-preview .image-placeholder');
    const removeBtn = document.getElementById('edit-remove-image-btn');
    
    previewImg.style.display = 'none';
    placeholder.style.display = 'flex';
    removeBtn.style.display = 'none';
}

// Edit form handlers
function updateEditCharacterCount() {
    const nameInput = document.getElementById('edit-playlist-name');
    const countSpan = document.getElementById('edit-name-count');
    countSpan.textContent = nameInput.value.length;
}

function addEditTag() {
    const tagInput = document.getElementById('edit-tag-input');
    const tagValue = tagInput.value.trim();
    
    if (tagValue && !editModalSelectedTags.includes(tagValue) && editModalSelectedTags.length < 10) {
        editModalSelectedTags.push(tagValue);
        updateEditSelectedTags();
        tagInput.value = '';
    }
}

function removeEditTag(tagToRemove) {
    editModalSelectedTags = editModalSelectedTags.filter(tag => tag !== tagToRemove);
    updateEditSelectedTags();
}

function updateEditSelectedTags() {
    const container = document.getElementById('edit-selected-tags-container');
    container.innerHTML = editModalSelectedTags.map(tag => `
        <span class="selected-tag">
            ${tag}
            <button type="button" class="remove-tag-btn" onclick="removeEditTag('${tag}')">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12 19 6.41z"/>
                </svg>
            </button>
        </span>
    `).join('');
}

// Handle edit form submission
async function handleEditSubmit(event) {
    event.preventDefault();
    
    const formData = new FormData();
    const playlistId = document.getElementById('edit-playlist-id').value;
    const name = document.getElementById('edit-playlist-name').value.trim();
    const imageFile = document.getElementById('edit-playlist-image').files[0];
    
    if (!name) {
        alert('Please enter a playlist name');
        return;
    }
    
    formData.append('name', name);
    formData.append('tags', JSON.stringify(editModalSelectedTags));
    
    if (imageFile) {
        formData.append('image', imageFile);
    }
    
    try {
        const response = await fetch(`/playlists/${getPlaylistNameFromUrl()}`, {
            method: 'PUT',
            body: formData
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || 'Failed to update playlist');
        }
        
        // const updatedPlaylist = await response.json();
        
        // // Update current playlist and refresh display
        // currentPlaylist = updatedPlaylist;
        // displayPlaylist(updatedPlaylist);
        
        // // Close modal
        // closeEditModal();
        
        // // Refresh sidebar if function exists
        // if (typeof refreshSidebarPlaylists === 'function') {
        //     refreshSidebarPlaylists();
        // }
        
        console.log('Playlist updated successfully');

        window.location.reload();
        
    } catch (error) {
        console.error('Error updating playlist:', error);
        alert('Failed to update playlist: ' + error.message);
    }
}

// Image upload handling
function handleEditImageUpload(event) {
    const file = event.target.files[0];
    if (!file) return;
    
    // Validate file
    const maxSize = 5 * 1024 * 1024; // 5MB
    if (file.size > maxSize) {
        alert('File size must be less than 5MB');
        event.target.value = '';
        return;
    }
    
    if (!file.type.startsWith('image/')) {
        alert('Please select an image file');
        event.target.value = '';
        return;
    }
    
    // Show preview
    const reader = new FileReader();
    reader.onload = function(e) {
        const previewImg = document.getElementById('edit-preview-image');
        const placeholder = document.querySelector('#edit-image-preview .image-placeholder');
        const removeBtn = document.getElementById('edit-remove-image-btn');
        
        previewImg.src = e.target.result;
        previewImg.style.display = 'block';
        placeholder.style.display = 'none';
        removeBtn.style.display = 'flex';
    };
    reader.readAsDataURL(file);
}

function removeEditImage() {
    const fileInput = document.getElementById('edit-playlist-image');
    const previewImg = document.getElementById('edit-preview-image');
    const placeholder = document.querySelector('#edit-image-preview .image-placeholder');
    const removeBtn = document.getElementById('edit-remove-image-btn');
    
    fileInput.value = '';
    previewImg.style.display = 'none';
    placeholder.style.display = 'flex';
    removeBtn.style.display = 'none';
}

// Event Listeners
document.addEventListener('DOMContentLoaded', function() {
    // Load playlist data
    loadPlaylist();
    
    // Play all button
    document.getElementById('play-all-btn').addEventListener('click', playPlaylist);
    
    // Edit button
    document.getElementById('edit-playlist-btn').addEventListener('click', openEditModal);
    
    // Playlist cover play functionality
    document.getElementById('playlist-cover-art').addEventListener('click', playPlaylist);
    
    // Modal close handlers
    document.getElementById('edit-close-modal-btn').addEventListener('click', closeEditModal);
    document.getElementById('edit-cancel-btn').addEventListener('click', closeEditModal);
    
    // Close modal on backdrop click
    document.getElementById('edit-playlist-modal').addEventListener('click', function(e) {
        if (e.target === this) {
            closeEditModal();
        }
    });
    
    // Edit form submission
    document.getElementById('edit-playlist-form').addEventListener('submit', handleEditSubmit);
    
    // Character count for name input
    document.getElementById('edit-playlist-name').addEventListener('input', updateEditCharacterCount);
    
    // Tag input handlers
    document.getElementById('edit-tag-input').addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            addEditTag();
        }
    });
    
    document.getElementById('edit-add-tag-btn').addEventListener('click', addEditTag);
    
    // Image upload handlers
    document.getElementById('edit-playlist-image').addEventListener('change', handleEditImageUpload);
    document.getElementById('edit-remove-image-btn').addEventListener('click', removeEditImage);
    
    // Image preview click handler
    document.getElementById('edit-image-preview').addEventListener('click', function() {
        document.getElementById('edit-playlist-image').click();
    });
    
    // Keyboard shortcuts
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            const modal = document.getElementById('edit-playlist-modal');
            if (modal.classList.contains('show')) {
                closeEditModal();
            }
        }
    });
    
    // Load library songs
    loadLibrarySongs();
    
    // Library search functionality
    document.getElementById('library-search').addEventListener('input', function(e) {
        searchLibrarySongs(e.target.value);
    });
});

// Library Songs Functionality
let allLibrarySongs = [];
let filteredLibrarySongs = [];
let currentPlaylistSongs = [];

// Load library songs
async function loadLibrarySongs() {
    try {
        const response = await fetch('/api/library');
        if (!response.ok) {
            throw new Error('Failed to load library');
        }
        
        const data = await response.json();
        allLibrarySongs = data.songs || [];
        filteredLibrarySongs = [...allLibrarySongs];
        
        displayLibrarySongs();
        
    } catch (error) {
        console.error('Error loading library songs:', error);
        document.getElementById('empty-library-message').style.display = 'block';
    }
}

// Display library songs
function displayLibrarySongs() {
    const libraryContainer = document.getElementById('library-songs-list');
    const emptyMessage = document.getElementById('empty-library-message');
    
    if (filteredLibrarySongs.length === 0) {
        libraryContainer.innerHTML = '';
        emptyMessage.style.display = 'block';
        return;
    }
    
    emptyMessage.style.display = 'none';
    
    // Get current playlist song IDs to check if already added
    currentPlaylistSongs = currentPlaylist && currentPlaylist.songs ? 
        currentPlaylist.songs.map(song => song.library_song_id || song.id) : [];
    
    const songsHtml = filteredLibrarySongs.map(song => {
        const isInPlaylist = currentPlaylistSongs.includes(song.id);
        
        return `
            <div class="library-song-row" data-song-id="${song.id}">
                <div class="library-song-title">${song.title}</div>
                <div class="library-song-duration">${formatDuration(song.duration)}</div>
                <div class="library-song-size">${formatFileSize(song.size)}</div>
                <div class="library-song-actions">
                    <button class="add-song-btn" 
                            onclick="addSongToPlaylist('${song.id}')"
                            ${isInPlaylist ? 'disabled' : ''}
                            title="${isInPlaylist ? 'Already in playlist' : 'Add to playlist'}">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                            <path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/>
                        </svg>
                    </button>
                </div>
            </div>
        `;
    }).join('');
    
    libraryContainer.innerHTML = songsHtml;
}

// Search library songs
function searchLibrarySongs(query) {
    if (!query.trim()) {
        filteredLibrarySongs = [...allLibrarySongs];
    } else {
        const searchTerm = query.toLowerCase();
        filteredLibrarySongs = allLibrarySongs.filter(song =>
            song.title.toLowerCase().includes(searchTerm)
        );
    }
    
    displayLibrarySongs();
}

// Add song to playlist
async function addSongToPlaylist(songId) {
    const playlistName = getPlaylistNameFromUrl();
    
    try {
        const response = await fetch(`/api/playlists/${encodeURIComponent(playlistName)}/songs`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                song_id: songId
            })
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || 'Failed to add song');
        }
        
        const result = await response.json();
        
        // Refresh playlist data
        await loadPlaylist();
        
        // Refresh library display to update button states
        displayLibrarySongs();
        
        showSuccessNotification(`Song added to playlist successfully`);
        
    } catch (error) {
        console.error('Error adding song to playlist:', error);
        showError(`Failed to add song: ${error.message}`);
    }
}

// Remove song from playlist
async function removeSongFromPlaylist(songId) {
    const playlistName = getPlaylistNameFromUrl();
    
    try {
        const response = await fetch(`/api/playlists/${encodeURIComponent(playlistName)}/songs/${encodeURIComponent(songId)}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || 'Failed to remove song');
        }
        
        // Refresh playlist data
        await loadPlaylist();
        
        // Refresh library display to update button states
        displayLibrarySongs();
        
        showSuccessNotification(`Song removed from playlist successfully`);
        
    } catch (error) {
        console.error('Error removing song from playlist:', error);
        showError(`Failed to remove song: ${error.message}`);
    }
}



// Format file size
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// Show success notification
function showSuccessNotification(message) {
    // Remove existing notification
    const existingNotification = document.querySelector('.success-notification');
    if (existingNotification) {
        existingNotification.remove();
    }
    
    // Create notification
    const notification = document.createElement('div');
    notification.className = 'success-notification';
    notification.innerHTML = `
        <div class="notification-content">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/>
            </svg>
            <span>${message}</span>
        </div>
    `;
    
    document.body.appendChild(notification);
    
    // Show notification
    setTimeout(() => notification.classList.add('show'), 100);
    
    // Hide notification after 3 seconds
    setTimeout(() => {
        notification.classList.remove('show');
        setTimeout(() => notification.remove(), 300);
    }, 3000);
} 