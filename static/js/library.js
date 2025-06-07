// Library Page JavaScript
let libraryData = [];
let filteredLibraryData = [];
let playlists = [];
let activeDownloads = new Map();
let downloadEventSource = null;

// DOM Elements
const downloadForm = document.getElementById('download-form');
const youtubeUrlInput = document.getElementById('youtube-url');
const downloadBtn = document.getElementById('download-btn');
const autoAddCheckbox = document.getElementById('auto-add-playlist');
const targetPlaylistSelect = document.getElementById('target-playlist');
const librarySearch = document.getElementById('library-search');
const libraryTableBody = document.getElementById('library-table-body');
const emptyLibrary = document.getElementById('empty-library');
const totalSongsEl = document.getElementById('total-songs');
const totalDurationEl = document.getElementById('total-duration');
const totalSizeEl = document.getElementById('total-size');

// Rename Modal Elements
const renameModal = document.getElementById('rename-song-modal');
const renameForm = document.getElementById('rename-song-form');
const renameSongId = document.getElementById('rename-song-id');
const renameSongTitle = document.getElementById('rename-song-title');
const renameCloseBtn = document.getElementById('rename-close-modal-btn');
const renameCancelBtn = document.getElementById('rename-cancel-btn');
const titleCount = document.getElementById('title-count');

// Download stages with progress percentages
const DOWNLOAD_STAGES = {
    'pending': { label: 'Queued', progress: 0, color: '#666' },
    'downloading': { label: 'Downloading', progress: 20, color: '#2196F3' },
    'processing': { label: 'Processing', progress: 40, color: '#FF9800' },
    'normalizing': { label: 'Normalizing', progress: 70, color: '#9C27B0' },
    'moving': { label: 'Finalizing', progress: 90, color: '#4CAF50' },
    'completed': { label: 'Completed', progress: 100, color: '#1db954' },
    'failed': { label: 'Failed', progress: 0, color: '#f44336' }
};

// Initialize page
document.addEventListener('DOMContentLoaded', function() {
    loadLibraryData();
    loadPlaylists();
    setupEventListeners();
    checkActiveDownloads();
    connectToDownloadStream();
});

// Setup event listeners
function setupEventListeners() {
    // Download form
    downloadForm.addEventListener('submit', handleDownload);
    
    // Search functionality
    librarySearch.addEventListener('input', handleSearch);
    
    // Auto-add playlist checkbox
    autoAddCheckbox.addEventListener('change', function() {
        targetPlaylistSelect.style.display = this.checked ? 'block' : 'none';
    });
    
    // Set initial state of playlist dropdown based on checkbox
    targetPlaylistSelect.style.display = autoAddCheckbox.checked ? 'block' : 'none';
    
    // Rename modal
    renameCloseBtn.addEventListener('click', closeRenameModal);
    renameCancelBtn.addEventListener('click', closeRenameModal);
    renameForm.addEventListener('submit', handleRename);
    
    // Character counter
    renameSongTitle.addEventListener('input', function() {
        titleCount.textContent = this.value.length;
    });
    
    // Close modal on backdrop click
    renameModal.addEventListener('click', function(e) {
        if (e.target === this) {
            closeRenameModal();
        }
    });
    
    // Close dropdown when clicking outside
    document.addEventListener('click', function(e) {
        if (!e.target.closest('.edit-btn') && !e.target.closest('.actions-dropdown')) {
            closeAllDropdowns();
        }
    });
    
    // Close dropdown on scroll or resize
    window.addEventListener('scroll', closeAllDropdowns);
    window.addEventListener('resize', closeAllDropdowns);
}

// Load library data from backend
async function loadLibraryData() {
    try {
        const response = await fetch('/api/library');
        if (response.ok) {
            const data = await response.json();
            libraryData = data.songs || [];
            filteredLibraryData = [...libraryData];
            updateLibraryDisplay();
            updateLibraryStats();
        } else {
            console.error('Failed to load library data');
            showEmptyLibrary();
        }
    } catch (error) {
        console.error('Error loading library data:', error);
        showEmptyLibrary();
    }
}

// Load playlists for dropdown
async function loadPlaylists() {
    try {
        const response = await fetch('/api/playlists');
        if (response.ok) {
            const data = await response.json();
            playlists = data.playlists || [];
            populatePlaylistDropdown();
        }
    } catch (error) {
        console.error('Error loading playlists:', error);
    }
}

// Populate playlist dropdown
function populatePlaylistDropdown() {
    targetPlaylistSelect.innerHTML = '<option value="">Select playlist...</option>';
    
    playlists.forEach(playlist => {
        const option = document.createElement('option');
        option.value = playlist.serialized_name;
        option.textContent = playlist.name;
        targetPlaylistSelect.appendChild(option);
    });
}

// Handle YouTube download
async function handleDownload(e) {
    e.preventDefault();
    
    const url = youtubeUrlInput.value.trim();
    if (!url) return;
    
    // Validate YouTube URL
    if (!isValidYouTubeUrl(url)) {
        showNotification('Please enter a valid YouTube URL', 'error');
        return;
    }
    
    // Disable button and show loading state
    downloadBtn.disabled = true;
    downloadBtn.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" class="spin">
            <path d="M12,4V2A10,10 0 0,0 2,12H4A8,8 0 0,1 12,4Z"/>
        </svg>
        Starting...
    `;
    
    try {
        // Send download request to backend
        const response = await fetch('/api/library', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                url: url,
                auto_add_playlist: autoAddCheckbox.checked,
                target_playlist: autoAddCheckbox.checked ? targetPlaylistSelect.value : null
            })
        });
        
        const result = await response.json();
        
        if (response.ok && result.success) {
            showNotification('Download started!', 'success');
            
            // Clear form
            youtubeUrlInput.value = '';
            
            // Reset button
            downloadBtn.disabled = false;
            downloadBtn.innerHTML = `
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/>
                </svg>
                Download
            `;
            
        } else {
            throw new Error(result.error || 'Download failed to start');
        }
        
    } catch (error) {
        showNotification(error.message || 'Failed to start download. Please try again.', 'error');
        console.error('Download error:', error);
        
        // Reset button
        downloadBtn.disabled = false;
        downloadBtn.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                <path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/>
            </svg>
            Download
        `;
    }
}

// Validate YouTube URL
function isValidYouTubeUrl(url) {
    const patterns = [
        /^https?:\/\/(www\.)?youtube\.com\/watch\?v=[\w-]+/,
        /^https?:\/\/(www\.)?youtu\.be\/[\w-]+/,
        /^https?:\/\/(www\.)?youtube\.com\/embed\/[\w-]+/
    ];
    
    return patterns.some(pattern => pattern.test(url));
}

// Handle search
function handleSearch() {
    const searchTerm = librarySearch.value.toLowerCase().trim();
    
    if (searchTerm === '') {
        filteredLibraryData = [...libraryData];
    } else {
        filteredLibraryData = libraryData.filter(song => {
            return song.title.toLowerCase().includes(searchTerm);
        });
    }
    
    updateLibraryDisplay();
}

// Update library display
function updateLibraryDisplay() {
    if (filteredLibraryData.length === 0) {
        showEmptyLibrary();
        return;
    }
    
    hideEmptyLibrary();
    populateLibraryTable();
}

// Show empty library state
function showEmptyLibrary() {
    libraryTableBody.innerHTML = '';
    emptyLibrary.style.display = 'block';
}

// Hide empty library state
function hideEmptyLibrary() {
    emptyLibrary.style.display = 'none';
}

// Populate library table
function populateLibraryTable() {
    libraryTableBody.innerHTML = '';
    
    filteredLibraryData.forEach((song, index) => {
        const row = createSongRow(song, index + 1);
        libraryTableBody.appendChild(row);
    });
}

// Create song row
function createSongRow(song, number) {
    const row = document.createElement('div');
    row.className = 'song-row';
    
    row.innerHTML = `
        <div class="song-number">${number}</div>
        <div class="song-info">
            <div class="song-title">${song.title}</div>
        </div>
        <div class="song-duration">${formatDuration(song.duration)}</div>
        <div class="song-size">${formatFileSize(song.size)}</div>
        <div style="position: relative;">
            <button class="edit-btn" onclick="event.stopPropagation(); toggleSongActions('${song.id}')">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M12 8c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z"/>
                </svg>
            </button>
            <div class="actions-dropdown" id="actions-dropdown-${song.id}" style="display: none;">
                <button class="dropdown-item" onclick="event.stopPropagation(); openRenameModal('${song.id}')">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34c-.39-.39-1.02-.39-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/>
                    </svg>
                    Rename
                </button>
                <button class="dropdown-item delete-item" onclick="event.stopPropagation(); deleteSong('${song.id}')">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M16 9v10H8V9h8m-1.5-6h-5l-1 1H5v2h14V4h-3.5l-1-1zM18 7H6v12c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7z"/>
                    </svg>
                    Delete
                </button>
            </div>
        </div>
    `;
    
    return row;
}

// Toggle song actions dropdown
function toggleSongActions(songId) {
    // Close all other dropdowns first
    const allDropdowns = document.querySelectorAll('.actions-dropdown');
    allDropdowns.forEach(dropdown => {
        if (dropdown.id !== `actions-dropdown-${songId}`) {
            dropdown.style.display = 'none';
        }
    });
    
    // Toggle current dropdown
    const dropdown = document.getElementById(`actions-dropdown-${songId}`);
    if (dropdown) {
        const isVisible = dropdown.style.display === 'block';
        
        if (isVisible) {
            dropdown.style.display = 'none';
        } else {
            // Position dropdown correctly to avoid clipping
            positionLibraryDropdown(dropdown, songId);
            dropdown.style.display = 'block';
        }
    }
}

// Position dropdown using fixed positioning to escape overflow
function positionLibraryDropdown(dropdown, songId) {
    const editBtn = dropdown.parentElement.querySelector('.edit-btn');
    if (!editBtn) return;
    
    // Get the button's position relative to the viewport
    const btnRect = editBtn.getBoundingClientRect();
    
    // Check if dropdown would be clipped by viewport bottom
    const dropdownHeight = 120; // Approximate dropdown height
    const spaceBelow = window.innerHeight - btnRect.bottom;
    const spaceAbove = btnRect.top;
    
    // Position the dropdown using fixed coordinates
    const rightPosition = window.innerWidth - btnRect.right;
    
    // Reset positioning
    dropdown.style.left = 'auto';
    dropdown.style.right = `${rightPosition}px`;
    dropdown.style.top = '';
    dropdown.style.bottom = '';
    
    // Position above if not enough space below
    if (spaceBelow < dropdownHeight && spaceAbove > dropdownHeight) {
        dropdown.style.bottom = `${window.innerHeight - btnRect.top}px`;
        dropdown.style.top = 'auto';
    } else {
        dropdown.style.top = `${btnRect.bottom}px`;
        dropdown.style.bottom = 'auto';
    }
}

// Close all dropdowns
function closeAllDropdowns() {
    const allDropdowns = document.querySelectorAll('.actions-dropdown');
    allDropdowns.forEach(dropdown => {
        dropdown.style.display = 'none';
    });
}

// Open rename modal
function openRenameModal(songId) {
    const song = libraryData.find(s => s.id === songId);
    if (!song) return;
    
    // Close dropdown
    const dropdown = document.getElementById(`actions-dropdown-${songId}`);
    if (dropdown) dropdown.style.display = 'none';
    
    renameSongId.value = songId;
    renameSongTitle.value = song.title;
    
    // Update character counter
    titleCount.textContent = song.title.length;
    
    renameModal.style.display = 'flex';
    document.body.style.overflow = 'hidden';
    
    setTimeout(() => {
        renameSongTitle.focus();
    }, 100);
}

// Close rename modal
function closeRenameModal() {
    renameModal.style.display = 'none';
    document.body.style.overflow = '';
    renameForm.reset();
    titleCount.textContent = '0';
}

// Handle rename form submission
async function handleRename(e) {
    e.preventDefault();
    
    const songId = renameSongId.value;
    const newTitle = renameSongTitle.value.trim();
    
    if (!newTitle) {
        showNotification('Song title is required', 'error');
        return;
    }
    
    try {
        const response = await fetch(`/api/library/${songId}/rename`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                title: newTitle
            })
        });
        
        const data = await response.json();
        
        if (response.ok && data.success) {
            // Update local data
            const songIndex = libraryData.findIndex(s => s.id === songId);
            if (songIndex !== -1) {
                libraryData[songIndex].title = newTitle;
                libraryData[songIndex].filename = data.new_filename;
            }
            
            // Update filtered data if it exists
            const filteredIndex = filteredLibraryData.findIndex(s => s.id === songId);
            if (filteredIndex !== -1) {
                filteredLibraryData[filteredIndex].title = newTitle;
                filteredLibraryData[filteredIndex].filename = data.new_filename;
            }
            
            closeRenameModal();
            showNotification('Song renamed successfully!', 'success');
            
            // Refresh display
            updateLibraryDisplay();
            
        } else {
            showNotification(data.error || 'Failed to rename song', 'error');
        }
        
    } catch (error) {
        showNotification('Failed to rename song', 'error');
        console.error('Rename error:', error);
    }
}

// Delete song
async function deleteSong(songId) {
    const song = libraryData.find(s => s.id === songId);
    if (!song) return;
    
    // Close dropdown
    const dropdown = document.getElementById(`actions-dropdown-${songId}`);
    if (dropdown) dropdown.style.display = 'none';
    
    if (!confirm(`Are you sure you want to delete "${song.title}"?\n\nThis will permanently remove the file from your library and cannot be undone.`)) {
        return;
    }
    
    try {
        const response = await fetch(`/api/library/${songId}/delete`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        
        if (response.ok && data.success) {
            // Remove from local data
            libraryData = libraryData.filter(s => s.id !== songId);
            filteredLibraryData = filteredLibraryData.filter(s => s.id !== songId);
            
            updateLibraryDisplay();
            updateLibraryStats();
            showNotification('Song deleted successfully!', 'success');
            
        } else {
            showNotification(data.error || 'Failed to delete song', 'error');
        }
        
    } catch (error) {
        showNotification('Failed to delete song', 'error');
        console.error('Delete error:', error);
    }
}

// Update library stats
function updateLibraryStats() {
    const totalSongs = libraryData.length;
    const totalDuration = libraryData.reduce((sum, song) => sum + (song.duration || 0), 0);
    const totalSize = libraryData.reduce((sum, song) => sum + (song.size || 0), 0);
    
    totalSongsEl.textContent = totalSongs;
    totalDurationEl.textContent = formatDuration(totalDuration);
    totalSizeEl.textContent = formatFileSize(totalSize);
}

// Format duration (seconds to MM:SS or HH:MM:SS)
function formatDuration(seconds) {
    if (!seconds || seconds === 0) return '0:00';
    
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const remainingSeconds = seconds % 60;
    
    if (hours > 0) {
        return `${hours}:${minutes.toString().padStart(2, '0')}:${remainingSeconds.toString().padStart(2, '0')}`;
    } else {
        return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
    }
}

// Format file size
function formatFileSize(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    const size = (bytes / Math.pow(1024, i)).toFixed(1);
    
    return `${size} ${sizes[i]}`;
}

// Show notification
function showNotification(message, type = 'info') {
    // Remove existing notification
    const existingNotification = document.querySelector('.notification');
    if (existingNotification) {
        existingNotification.remove();
    }
    
    // Create notification
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.innerHTML = `
        <div class="notification-content">
            <span>${message}</span>
            <button class="notification-close" onclick="this.parentElement.parentElement.remove()">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12 19 6.41z"/>
                </svg>
            </button>
        </div>
    `;
    
    document.body.appendChild(notification);
    
    // Show notification
    setTimeout(() => {
        notification.classList.add('show');
    }, 100);
    
    // Auto-hide after 5 seconds
    setTimeout(() => {
        if (notification.parentElement) {
            notification.classList.remove('show');
            setTimeout(() => notification.remove(), 300);
        }
    }, 5000);
}

// Check for active downloads on page load
async function checkActiveDownloads() {
    try {
        const response = await fetch('/api/downloads/status');
        if (response.ok) {
            const data = await response.json();
            if (data.downloads && data.downloads.length > 0) {
                data.downloads.forEach(download => {
                    updateDownloadDisplay(download);
                });
            }
        }
    } catch (error) {
        console.error('Error checking active downloads:', error);
    }
}

// Download SSE connection management
let downloadReconnectAttempts = 0;
const maxDownloadReconnectAttempts = 5;

// Connect to download progress stream
function connectToDownloadStream() {
    // Close existing connection if any
    if (downloadEventSource) {
        console.log('Closing existing download stream');
        downloadEventSource.close();
        downloadEventSource = null;
    }
    
    console.log('Setting up new download stream');
    downloadEventSource = new EventSource('/api/downloads/stream');
    
    downloadEventSource.onmessage = function(event) {
        try {
            const downloadData = JSON.parse(event.data);
            
            // Skip heartbeat and test messages
            if (downloadData.type === 'heartbeat' || downloadData.type === 'test') {
                return;
            }
            
            updateDownloadDisplay(downloadData);
        } catch (error) {
            console.error('Error parsing download data:', error);
        }
    };
    
    downloadEventSource.onerror = function(error) {
        console.error('Download stream error:', error);
        
        // Attempt to reconnect with exponential backoff
        if (downloadReconnectAttempts < maxDownloadReconnectAttempts) {
            const delay = Math.pow(2, downloadReconnectAttempts) * 1000;
            downloadReconnectAttempts++;
            
            console.log(`Attempting to reconnect download stream in ${delay}ms (attempt ${downloadReconnectAttempts})`);
            
            setTimeout(() => {
                if (downloadEventSource && downloadEventSource.readyState === EventSource.CLOSED) {
                    connectToDownloadStream();
                }
            }, delay);
        } else {
            console.error('Max reconnection attempts reached for download stream');
        }
    };
    
    downloadEventSource.onopen = function() {
        console.log('Download stream connected');
        downloadReconnectAttempts = 0; // Reset on successful connection
    };
}

// Update download display
function updateDownloadDisplay(downloadData) {
    const downloadId = downloadData.id;
    activeDownloads.set(downloadId, downloadData);
    
    const downloadsContainer = document.getElementById('downloads-container');
    const activeDownloadsSection = document.getElementById('active-downloads-section');
    
    let downloadItem = document.getElementById(`download-${downloadId}`);
    
    if (!downloadItem) {
        downloadItem = createDownloadItem(downloadData);
        downloadsContainer.appendChild(downloadItem);
    }
    
    updateDownloadItem(downloadItem, downloadData);
    
    // Show/hide the active downloads section
    const hasActiveDownloads = activeDownloads.size > 0;
    activeDownloadsSection.style.display = hasActiveDownloads ? 'block' : 'none';
    
    // Remove completed/failed downloads after 10 seconds
    if (downloadData.status === 'completed' || downloadData.status === 'failed') {
        setTimeout(() => {
            removeDownloadItem(downloadId);
        }, 10000);
    }
    
    // Reload library when download completes
    if (downloadData.status === 'completed') {
        setTimeout(() => {
            loadLibraryData();
        }, 1000);
    }
}

// Create download item element
function createDownloadItem(downloadData) {
    const downloadItem = document.createElement('div');
    downloadItem.className = 'download-item';
    downloadItem.id = `download-${downloadData.id}`;
    
    downloadItem.innerHTML = `
        <div class="download-item-header">
            <div class="download-item-info">
                <div class="download-item-title">${downloadData.title || 'Getting video info...'}</div>
                <div class="download-item-uploader">${downloadData.uploader || ''}</div>
            </div>
            <div class="download-item-status">${downloadData.message}</div>
            <button class="download-remove-btn" onclick="removeDownloadItem('${downloadData.id}')" title="Remove">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12 19 6.41z"/>
                </svg>
            </button>
        </div>
        <div class="download-item-progress">
            <div class="download-steps">
                <div class="download-step" data-step="pending">
                    <div class="step-indicator"></div>
                    <div class="step-label">Queue</div>
                </div>
                <div class="download-step" data-step="downloading">
                    <div class="step-indicator"></div>
                    <div class="step-label">Download</div>
                </div>
                <div class="download-step" data-step="processing">
                    <div class="step-indicator"></div>
                    <div class="step-label">Process</div>
                </div>
                <div class="download-step" data-step="normalizing">
                    <div class="step-indicator"></div>
                    <div class="step-label">Normalize</div>
                </div>
                <div class="download-step" data-step="moving">
                    <div class="step-indicator"></div>
                    <div class="step-label">Finalize</div>
                </div>
            </div>
        </div>
    `;
    
    return downloadItem;
}

// Update download item
function updateDownloadItem(downloadItem, downloadData) {
    const titleEl = downloadItem.querySelector('.download-item-title');
    const uploaderEl = downloadItem.querySelector('.download-item-uploader');
    const statusEl = downloadItem.querySelector('.download-item-status');
    const steps = downloadItem.querySelectorAll('.download-step');
    
    // Update content
    if (downloadData.title) titleEl.textContent = downloadData.title;
    if (downloadData.uploader) uploaderEl.textContent = downloadData.uploader;
    statusEl.textContent = downloadData.message;
    
    // Update step indicators
    const currentStatus = downloadData.status;
    const stageInfo = DOWNLOAD_STAGES[currentStatus];
    
    steps.forEach(step => {
        const stepType = step.dataset.step;
        const indicator = step.querySelector('.step-indicator');
        
        // Reset classes
        step.classList.remove('active', 'completed', 'failed');
        
        if (stepType === currentStatus) {
            step.classList.add('active');
            if (currentStatus === 'failed') {
                step.classList.add('failed');
            }
        } else if (shouldStepBeCompleted(stepType, currentStatus)) {
            step.classList.add('completed');
        }
    });
    
    // Update overall status classes
    downloadItem.className = 'download-item';
    if (downloadData.status === 'completed') {
        downloadItem.classList.add('completed');
    } else if (downloadData.status === 'failed') {
        downloadItem.classList.add('failed');
    }
}

// Helper function to determine if a step should be marked as completed
function shouldStepBeCompleted(stepType, currentStatus) {
    const stepOrder = ['pending', 'downloading', 'processing', 'normalizing', 'moving', 'completed'];
    const stepIndex = stepOrder.indexOf(stepType);
    const currentIndex = stepOrder.indexOf(currentStatus);
    
    return stepIndex < currentIndex || (currentStatus === 'completed' && stepType !== 'completed');
}

// Remove download item
function removeDownloadItem(downloadId) {
    const downloadItem = document.getElementById(`download-${downloadId}`);
    if (downloadItem) {
        downloadItem.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
        downloadItem.style.opacity = '0';
        downloadItem.style.transform = 'translateX(100%)';
        
        setTimeout(() => {
            downloadItem.remove();
        }, 300);
    }
    
    activeDownloads.delete(downloadId);
    
    // Hide section if no active downloads
    const activeDownloadsSection = document.getElementById('active-downloads-section');
    if (activeDownloads.size === 0) {
        setTimeout(() => {
            activeDownloadsSection.style.display = 'none';
        }, 300);
    }
}

// Cleanup on page unload and navigation
function cleanupLibraryConnections() {
    console.log('Cleaning up library SSE connections');
    
    if (downloadEventSource) {
        downloadEventSource.close();
        downloadEventSource = null;
    }
}

// Setup cleanup listeners
window.addEventListener('beforeunload', cleanupLibraryConnections);
window.addEventListener('pagehide', cleanupLibraryConnections);

// Handle visibility change to reconnect when page becomes visible
document.addEventListener('visibilitychange', function() {
    if (!document.hidden && window.location.pathname === '/library') {
        // Page became visible and we're on library page, check if we need to reconnect
        if (!downloadEventSource || downloadEventSource.readyState === EventSource.CLOSED) {
            console.log('Library page became visible, reconnecting download stream');
            connectToDownloadStream();
        }
    }
});

// Make functions globally accessible
window.toggleSongActions = toggleSongActions;
window.openRenameModal = openRenameModal;
window.deleteSong = deleteSong;
window.removeDownloadItem = removeDownloadItem; 