// Modal functionality
document.addEventListener('DOMContentLoaded', function() {
    const modal = document.getElementById('create-playlist-modal');
    const createPlaylistCard = document.getElementById('create-playlist-card');
    const closeModalBtn = document.getElementById('close-modal-btn');
    const cancelBtn = document.getElementById('cancel-btn');
    const createBtn = document.getElementById('create-btn');
    const form = document.getElementById('create-playlist-form');
    
    // Form elements
    const playlistNameInput = document.getElementById('playlist-name');
    const nameCountSpan = document.getElementById('name-count');
    const tagInput = document.getElementById('tag-input');
    const addTagBtn = document.getElementById('add-tag-btn');
    const selectedTagsContainer = document.getElementById('selected-tags-container');
    
    // Image upload elements
    const imageInput = document.getElementById('playlist-image');
    const imagePreview = document.getElementById('image-preview');
    const previewImage = document.getElementById('preview-image');
    const imagePlaceholder = imagePreview.querySelector('.image-placeholder');
    const removeImageBtn = document.getElementById('remove-image-btn');
    
    let selectedImageFile = null;
    let allPlaylists = [];
    let selectedTags = [];
    
    // Edit modal elements
    let editModal, editPlaylistNameInput, editNameCountSpan, editTagInput, editAddTagBtn, editSelectedTagsContainer;
    let editImageInput, editImagePreview, editPreviewImage, editImagePlaceholder, editRemoveImageBtn;
    let editSelectedImageFile = null;
    let editSelectedTags = [];
    let currentEditingPlaylist = null;
    
    // Initialize edit modal elements
    editModal = document.getElementById('edit-playlist-modal');
    editPlaylistNameInput = document.getElementById('edit-playlist-name');
    editNameCountSpan = document.getElementById('edit-name-count');
    editTagInput = document.getElementById('edit-tag-input');
    editAddTagBtn = document.getElementById('edit-add-tag-btn');
    editSelectedTagsContainer = document.getElementById('edit-selected-tags-container');
    editImageInput = document.getElementById('edit-playlist-image');
    editImagePreview = document.getElementById('edit-image-preview');
    editPreviewImage = document.getElementById('edit-preview-image');
    editImagePlaceholder = editImagePreview.querySelector('.image-placeholder');
    editRemoveImageBtn = document.getElementById('edit-remove-image-btn');
    
    // Load playlists on page load
    loadPlaylists();
    
    // Clear filters functionality
    const clearFiltersBtn = document.querySelector('.clear-filters');
    if (clearFiltersBtn) {
        clearFiltersBtn.addEventListener('click', function() {
            // Remove active class from all filter tags
            const activeFilterTags = document.querySelectorAll('.filter-tags .tag.active');
            activeFilterTags.forEach(tag => tag.classList.remove('active'));
            
            // Clear search
            const searchInput = document.getElementById('playlist-search');
            if (searchInput) searchInput.value = '';
            
            // Show all playlists
            populatePlaylistSections();
        });
    }
    
    // Playlist search functionality
    const playlistSearchInput = document.getElementById('playlist-search');
    if (playlistSearchInput) {
        playlistSearchInput.addEventListener('input', function() {
            performSearch();
        });
    }
    
    function performSearch() {
        const searchTerm = playlistSearchInput.value.toLowerCase().trim();
        const activeTags = Array.from(document.querySelectorAll('.filter-tags .tag.active'))
            .map(tag => tag.textContent.toLowerCase());
        
        if (searchTerm === '' && activeTags.length === 0) {
            // Show all playlists if no search term and no filters
            populatePlaylistSections();
            return;
        }
        
        // Filter playlists based on search term and active tags
        let filteredPlaylists = allPlaylists;
        
        // Apply tag filters first
        if (activeTags.length > 0) {
            filteredPlaylists = filteredPlaylists.filter(playlist => {
                if (!playlist.tags || playlist.tags.length === 0) return false;
                return activeTags.every(activeTag => 
                    playlist.tags.some(tag => tag.toLowerCase() === activeTag)
                );
            });
        }
        
        // Apply search term filter
        if (searchTerm !== '') {
            filteredPlaylists = filteredPlaylists.filter(playlist => {
                return playlist.name.toLowerCase().includes(searchTerm) ||
                       (playlist.tags && playlist.tags.some(tag => 
                           tag.toLowerCase().includes(searchTerm)
                       ));
            });
        }
        
        // Update displays with filtered playlists
        updatePlaylistDisplays(filteredPlaylists);
    }
    
    // Function to load playlists from API
    async function loadPlaylists() {
        try {
            const response = await fetch('/api/playlists');
            if (response.ok) {
                const data = await response.json();
                allPlaylists = data.playlists || [];
                populatePlaylistSections();
            } else {
                console.error('Failed to load playlists');
            }
        } catch (error) {
            console.error('Error loading playlists:', error);
        }
    }
    
    // Function to populate playlist sections
    function populatePlaylistSections() {
        populateFilterTags();
        populateRecentlyCreated();
        populateAllPlaylists();
    }
    
    // Function to populate recently created section (sorted by timestamp, newest first)
    function populateRecentlyCreated() {
        const cardGrid = document.querySelector('.card-grid');
        const createCard = cardGrid.querySelector('.create-playlist-card');
        
        // Clear existing cards (except create card)
        const existingCards = cardGrid.querySelectorAll('.card:not(.create-playlist-card)');
        existingCards.forEach(card => card.remove());
        
        // Sort by created_at (newest first)
        const recentPlaylists = [...allPlaylists]
            .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
            .slice(0, 4); // Show only 4 most recent
        
        // Create cards for recent playlists
        recentPlaylists.forEach(playlist => {
            const card = buildPlaylistCard(playlist);
            cardGrid.insertBefore(card, createCard);
        });
    }
    
    // Function to populate all playlists section (sorted alphabetically)
    function populateAllPlaylists() {
        const tableContainer = document.querySelector('.playlist-table');
        const header = tableContainer.querySelector('.playlist-table-header');
        
        // Clear existing rows
        const existingRows = tableContainer.querySelectorAll('.playlist-table-row');
        existingRows.forEach(row => row.remove());
        
        // Sort alphabetically by name
        const sortedPlaylists = [...allPlaylists]
            .sort((a, b) => a.name.toLowerCase().localeCompare(b.name.toLowerCase()));
        
        // Create rows for all playlists
        sortedPlaylists.forEach(playlist => {
            const row = buildPlaylistRow(playlist);
            tableContainer.appendChild(row);
        });
    }
    
    // Function to create a playlist card
    function buildPlaylistCard(playlist) {
        const card = document.createElement('div');
        card.className = 'card';
        
        // Use default gradient background for card image area
        const gradientBg = 'linear-gradient(135deg, #1a1a1a, #0f0f0f)';
        
        card.innerHTML = `
            <div class="card-image">
                <div class="playlist-album-art" onclick="event.stopPropagation(); playPlaylist('${playlist.serialized_name}', '${playlist.name}')" style="width: 100%; height: 160px; background: ${gradientBg}; border-radius: 8px; margin-bottom: 16px; display: flex; align-items: center; justify-content: center; position: relative; cursor: pointer;">
                    ${playlist.image ? 
                        `<img src="${playlist.image}" alt="${playlist.name}" style="width: 100%; height: 100%; object-fit: cover; border-radius: 8px;">` :
                        `<svg width="48" height="48" viewBox="0 0 24 24" fill="rgba(255,255,255,0.8)">
                            <path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/>
                        </svg>`
                    }
                    <div class="play-overlay card-play-overlay">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
                            <path d="M8 5v14l11-7z"/>
                        </svg>
                    </div>
                </div>
            </div>
            <h3 style="color: #ffffff; font-size: 16px; font-weight: 600; margin-bottom: 8px;">${playlist.name}</h3>
            <p style="color: #b3b3b3; font-size: 14px; margin-bottom: 12px;">${playlist.song_count} songs</p>
            <div class="tags-container">
                ${playlist.tags && playlist.tags.length > 0 ? 
                    playlist.tags.map(tag => `<span class="tag">${tag.charAt(0).toUpperCase() + tag.slice(1)}</span>`).join('') :
                    '<span class="tag">Music</span>'
                }
            </div>
        `;
        
        // Add click handler for navigation (excluding the album art)
        card.addEventListener('click', function(e) {
            // Don't navigate if clicking on the album art (play button)
            if (!e.target.closest('.playlist-album-art')) {
                window.location.href = `/playlist/${encodeURIComponent(playlist.serialized_name)}`;
            }
        });
        
        return card;
    }
    
    // Function to create a playlist table row
    function buildPlaylistRow(playlist) {
        const row = document.createElement('div');
        row.className = 'playlist-table-row';
        row.style.cssText = 'padding: 12px 20px; border-bottom: 1px solid rgba(255,255,255,0.05); display: grid; grid-template-columns: 60px 1fr 120px 120px; gap: 16px; align-items: center; transition: background-color 0.2s ease; cursor: pointer;';
        
        // Use default gradient background for table row image area
        const gradientBg = 'linear-gradient(135deg, #1a1a1a, #0f0f0f)';
        
        row.innerHTML = `
            <div class="playlist-album-art" onclick="event.stopPropagation(); playPlaylist('${playlist.serialized_name}', '${playlist.name}')" style="width: 48px; height: 48px; background: ${gradientBg}; border-radius: 6px; display: flex; align-items: center; justify-content: center; position: relative; cursor: pointer;">
                ${playlist.image ? 
                    `<img src="${playlist.image}" alt="${playlist.name}" style="width: 100%; height: 100%; object-fit: cover; border-radius: 6px;">` :
                    `<svg width="20" height="20" viewBox="0 0 24 24" fill="rgba(255,255,255,0.9)">
                        <path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/>
                    </svg>`
                }
                <div class="play-overlay">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M8 5v14l11-7z"/>
                    </svg>
                </div>
            </div>
            <div>
                <div style="color: #ffffff; font-weight: 500; margin-bottom: 4px;">${playlist.name}</div>
                <div class="tags-container">
                    ${playlist.tags && playlist.tags.length > 0 ? 
                        playlist.tags.map(tag => `<span class="tag">${tag.charAt(0).toUpperCase() + tag.slice(1)}</span>`).join('') :
                        '<span class="tag">Music</span>'
                    }
                </div>
            </div>
            <div style="color: #b3b3b3;">${playlist.song_count}</div>
            <div style="position: relative;">
                <button class="edit-btn" onclick="event.stopPropagation(); toggleActionsDropdown('${playlist.serialized_name}')">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M12 8c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z"/>
                    </svg>
                </button>
                <div class="actions-dropdown" id="actions-dropdown-${playlist.serialized_name}" style="display: none;">
                    <button class="dropdown-item" onclick="event.stopPropagation(); openEditModal('${playlist.serialized_name}')">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                            <path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34c-.39-.39-1.02-.39-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/>
                        </svg>
                        Edit
                    </button>
                    <button class="dropdown-item delete-item" onclick="event.stopPropagation(); deletePlaylist('${playlist.serialized_name}', '${playlist.name}')">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                            <path d="M16 9v10H8V9h8m-1.5-6h-5l-1 1H5v2h14V4h-3.5l-1-1zM18 7H6v12c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7z"/>
                        </svg>
                        Delete
                    </button>
                </div>
            </div>
        `;
        
        // Add click handler for navigation (excluding album art and actions)
        row.addEventListener('click', function(e) {
            // Don't navigate if clicking on album art, edit button, or dropdown
            if (!e.target.closest('.playlist-album-art') && !e.target.closest('.edit-btn') && !e.target.closest('.actions-dropdown')) {
                window.location.href = `/playlist/${encodeURIComponent(playlist.serialized_name)}`;
            }
        });
        
        return row;
    }
    
    // Function to populate filter tags dynamically
    function populateFilterTags() {
        const filterTagsContainer = document.querySelector('.filter-tags');
        if (!filterTagsContainer) return;
        
        // Get all unique tags from playlists
        const allTags = new Set();
        allPlaylists.forEach(playlist => {
            if (playlist.tags && playlist.tags.length > 0) {
                playlist.tags.forEach(tag => allTags.add(tag.toLowerCase()));
            }
        });
        
        // Clear existing filter tags
        filterTagsContainer.innerHTML = '';
        
        // Create filter tags for all unique tags found
        const sortedTags = Array.from(allTags).sort();
        sortedTags.forEach(tag => {
            const tagElement = document.createElement('span');
            tagElement.className = 'tag';
            tagElement.textContent = tag.charAt(0).toUpperCase() + tag.slice(1);
            tagElement.addEventListener('click', () => toggleFilterTag(tagElement, tag));
            filterTagsContainer.appendChild(tagElement);
        });
    }
    
    // Function to toggle filter tag
    function toggleFilterTag(tagElement, tagName) {
        tagElement.classList.toggle('active');
        filterPlaylists();
    }
    
    // Function to filter playlists based on active tags
    function filterPlaylists() {
        performSearch(); // Use the unified search function
    }
    
    // Function to update playlist displays with filtered data
    function updatePlaylistDisplays(playlists) {
        updateRecentlyCreated(playlists);
        updateAllPlaylists(playlists);
    }
    
    // Function to update recently created section with filtered data
    function updateRecentlyCreated(playlists) {
        const cardGrid = document.querySelector('.card-grid');
        const createCard = cardGrid.querySelector('.create-playlist-card');
        
        // Clear existing cards (except create card)
        const existingCards = cardGrid.querySelectorAll('.card:not(.create-playlist-card)');
        existingCards.forEach(card => card.remove());
        
        // Sort by created_at (newest first)
        const recentPlaylists = [...playlists]
            .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
            .slice(0, 4); // Show only 4 most recent
        
        // Create cards for recent playlists
        recentPlaylists.forEach(playlist => {
            const card = buildPlaylistCard(playlist);
            cardGrid.insertBefore(card, createCard);
        });
    }
    
    // Function to update all playlists section with filtered data
    function updateAllPlaylists(playlists) {
        const tableContainer = document.querySelector('.playlist-table');
        const header = tableContainer.querySelector('.playlist-table-header');
        
        // Clear existing rows
        const existingRows = tableContainer.querySelectorAll('.playlist-table-row');
        existingRows.forEach(row => row.remove());
        
        // Sort alphabetically by name
        const sortedPlaylists = [...playlists]
            .sort((a, b) => a.name.toLowerCase().localeCompare(b.name.toLowerCase()));
        
        // Create rows for all playlists
        sortedPlaylists.forEach(playlist => {
            const row = buildPlaylistRow(playlist);
            tableContainer.appendChild(row);
        });
    }
    
    // Open modal function
    function openModal() {
        modal.classList.add('show');
        document.body.style.overflow = 'hidden';
        
        // Focus on the name input
        setTimeout(() => {
            playlistNameInput.focus();
        }, 100);
    }
    
    // Close modal function
    function closeModal() {
        modal.classList.remove('show');
        document.body.style.overflow = '';
        
        // Reset form
        form.reset();
        updateCharacterCounts();
        clearSelectedTags();
        clearSelectedImage();
        updateCreateButtonState();
    }
    
    // Update character counts
    function updateCharacterCounts() {
        nameCountSpan.textContent = playlistNameInput.value.length;
    }
    
    // Add a tag
    function addTag(tagText) {
        const trimmedTag = tagText.trim();
        
        // Validate tag
        if (!trimmedTag) return;
        if (trimmedTag.length > 20) {
            alert('Tags must be 20 characters or less');
            return;
        }
        if (selectedTags.includes(trimmedTag.toLowerCase())) {
            alert('Tag already added');
            return;
        }
        
        // Add to selectedTags array
        selectedTags.push(trimmedTag.toLowerCase());
        
        // Create tag element
        const tagElement = document.createElement('div');
        tagElement.className = 'selected-tag';
        tagElement.innerHTML = `
            <span>${trimmedTag}</span>
            <button type="button" class="remove-tag-btn" onclick="removeTag('${trimmedTag.toLowerCase()}')">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12 19 6.41z"/>
                </svg>
            </button>
        `;
        
        selectedTagsContainer.appendChild(tagElement);
        tagInput.value = '';
    }
    
    // Remove a tag
    function removeTag(tagName) {
        // Remove from selectedTags array
        selectedTags = selectedTags.filter(tag => tag !== tagName);
        
        // Remove from DOM
        const tagElements = selectedTagsContainer.querySelectorAll('.selected-tag');
        tagElements.forEach(element => {
            if (element.querySelector('span').textContent.toLowerCase() === tagName) {
                element.remove();
            }
        });
    }
    
    // Clear selected tags
    function clearSelectedTags() {
        selectedTags = [];
        selectedTagsContainer.innerHTML = '';
    }
    
    // Edit modal helper functions
    function addEditTag(tagText) {
        const trimmedTag = tagText.trim();
        
        // Validate tag
        if (!trimmedTag) return;
        if (trimmedTag.length > 20) {
            alert('Tags must be 20 characters or less');
            return;
        }
        if (editSelectedTags.includes(trimmedTag.toLowerCase())) {
            alert('Tag already added');
            return;
        }
        
        // Add to editSelectedTags array
        editSelectedTags.push(trimmedTag.toLowerCase());
        populateEditTags();
        editTagInput.value = '';
    }
    
    function removeEditTag(tagName) {
        editSelectedTags = editSelectedTags.filter(tag => tag !== tagName);
        populateEditTags();
    }
    
    function populateEditTags() {
        editSelectedTagsContainer.innerHTML = '';
        editSelectedTags.forEach(tag => {
            const tagElement = document.createElement('div');
            tagElement.className = 'selected-tag';
            tagElement.innerHTML = `
                <span>${tag}</span>
                <button type="button" class="remove-tag-btn" onclick="removeEditTag('${tag}')">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12 19 6.41z"/>
                    </svg>
                </button>
            `;
            editSelectedTagsContainer.appendChild(tagElement);
        });
    }
    
    function updateEditCharacterCounts() {
        editNameCountSpan.textContent = editPlaylistNameInput.value.length;
    }
    
    function clearEditSelectedTags() {
        editSelectedTags = [];
        populateEditTags();
    }
    
    function clearEditSelectedImage() {
        editSelectedImageFile = null;
        editPreviewImage.style.display = 'none';
        editImagePlaceholder.style.display = 'flex';
        editRemoveImageBtn.style.display = 'none';
        editImageInput.value = '';
    }
    
    function updateEditCreateButtonState() {
        // Always enable save button - removed validation logic
        document.getElementById('edit-save-btn').disabled = false;
    }
    
    function handleEditImageFile(file) {
        // Validate file type
        if (!file.type.startsWith('image/')) {
            alert('Please select a valid image file (JPG, PNG, etc.)');
            return;
        }
        
        // Validate file size (5MB limit)
        if (file.size > 5 * 1024 * 1024) {
            alert('File size must be less than 5MB');
            return;
        }
        
        editSelectedImageFile = file;
        
        // Create preview
        const reader = new FileReader();
        reader.onload = function(e) {
            editPreviewImage.src = e.target.result;
            editPreviewImage.style.display = 'block';
            editImagePlaceholder.style.display = 'none';
            editRemoveImageBtn.style.display = 'flex';
        };
        reader.readAsDataURL(file);
    }
    
    function closeEditModal() {
        editModal.classList.remove('show');
        document.body.style.overflow = '';
        
        // Reset form
        document.getElementById('edit-playlist-form').reset();
        updateEditCharacterCounts();
        clearEditSelectedTags();
        clearEditSelectedImage();
        currentEditingPlaylist = null;
    }
    
    // Make edit functions globally accessible
    window.removeEditTag = removeEditTag;
    
    // Playlist play functionality
    window.playPlaylist = async function(playlistId, playlistName) {
        // Prevent the click from bubbling up to parent elements
        if (event) event.stopPropagation();
        
        try {
            const response = await fetch('/player/play', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    playlist_name: playlistId
                })
            });
            
            const data = await response.json();
            
            if (data.success) {
                console.log(`Now playing: ${playlistName}`);
            } else {
                console.error('Failed to play playlist:', data.error);
            }
        } catch (error) {
            console.error('Error playing playlist:', error);
        }
    };
    

    
    // Clear selected image
    function clearSelectedImage() {
        selectedImageFile = null;
        previewImage.style.display = 'none';
        imagePlaceholder.style.display = 'flex';
        removeImageBtn.style.display = 'none';
        imageInput.value = '';
    }
    
    // Update create button state
    function updateCreateButtonState() {
        const isNameValid = playlistNameInput.value.trim().length > 0;
        createBtn.disabled = !isNameValid;
    }
    
    // Handle image file selection
    function handleImageFile(file) {
        // Validate file type
        if (!file.type.startsWith('image/')) {
            alert('Please select a valid image file (JPG, PNG, etc.)');
            return;
        }
        
        // Validate file size (5MB limit)
        if (file.size > 5 * 1024 * 1024) {
            alert('File size must be less than 5MB');
            return;
        }
        
        selectedImageFile = file;
        
        // Create preview
        const reader = new FileReader();
        reader.onload = function(e) {
            previewImage.src = e.target.result;
            previewImage.style.display = 'block';
            imagePlaceholder.style.display = 'none';
            removeImageBtn.style.display = 'flex';
        };
        reader.readAsDataURL(file);
    }
    
    // Event listeners
    createPlaylistCard.addEventListener('click', openModal);
    closeModalBtn.addEventListener('click', closeModal);
    cancelBtn.addEventListener('click', closeModal);
    
    // Close modal when clicking backdrop
    modal.addEventListener('click', function(e) {
        if (e.target === modal) {
            closeModal();
        }
    });
    
    // Close modal with Escape key
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && modal.classList.contains('show')) {
            closeModal();
        }
    });
    
    // Character counting
    playlistNameInput.addEventListener('input', function() {
        updateCharacterCounts();
        updateCreateButtonState();
    });
    
    // Tag input event listeners
    addTagBtn.addEventListener('click', function() {
        addTag(tagInput.value);
    });
    
    tagInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            addTag(tagInput.value);
        }
    });
    
    // Make removeTag function globally accessible
    window.removeTag = removeTag;
    
    // Actions dropdown functionality
    window.toggleActionsDropdown = function(playlistId) {
        // Close all other dropdowns first
        const allDropdowns = document.querySelectorAll('.actions-dropdown');
        allDropdowns.forEach(dropdown => {
            if (dropdown.id !== `actions-dropdown-${playlistId}`) {
                dropdown.style.display = 'none';
            }
        });
        
        // Toggle current dropdown
        const dropdown = document.getElementById(`actions-dropdown-${playlistId}`);
        if (dropdown) {
            const isVisible = dropdown.style.display === 'block';
            
            if (isVisible) {
                dropdown.style.display = 'none';
            } else {
                // Position dropdown correctly to escape overflow container
                positionPlaylistDropdown(dropdown, playlistId);
                dropdown.style.display = 'block';
            }
        }
    };
    
    // Position dropdown using fixed positioning to escape overflow
    function positionPlaylistDropdown(dropdown, playlistId) {
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
    
    // Close dropdowns when clicking outside
    document.addEventListener('click', function(e) {
        if (!e.target.closest('.edit-btn') && !e.target.closest('.actions-dropdown')) {
            const allDropdowns = document.querySelectorAll('.actions-dropdown');
            allDropdowns.forEach(dropdown => {
                dropdown.style.display = 'none';
            });
        }
    });
    
    // Edit modal functionality
    window.openEditModal = function(playlistId) {
        const playlist = allPlaylists.find(p => p.serialized_name == playlistId);
        if (!playlist) return;
        
        currentEditingPlaylist = playlist;
        
        // Close dropdown
        const dropdown = document.getElementById(`actions-dropdown-${playlistId}`);
        if (dropdown) dropdown.style.display = 'none';
        
        // Populate form with existing data
        document.getElementById('edit-playlist-id').value = playlist.serialized_name;
        editPlaylistNameInput.value = playlist.name;
        updateEditCharacterCounts();
        
        // Populate tags
        editSelectedTags = [...(playlist.tags || [])];
        populateEditTags();
        
        // Populate image if exists
        if (playlist.image) {
            editPreviewImage.src = playlist.image;
            editPreviewImage.style.display = 'block';
            editImagePlaceholder.style.display = 'none';
            editRemoveImageBtn.style.display = 'flex';
        } else {
            clearEditSelectedImage();
        }
        
        // Show modal
        editModal.classList.add('show');
        document.body.style.overflow = 'hidden';
        
        setTimeout(() => {
            editPlaylistNameInput.focus();
        }, 100);
    };
    
    // Delete playlist functionality
    window.deletePlaylist = function(playlistId, playlistName) {
        // Close dropdown
        const dropdown = document.getElementById(`actions-dropdown-${playlistId}`);
        if (dropdown) dropdown.style.display = 'none';
        
        // Show confirmation dialog
        if (confirm(`Are you sure you want to delete "${playlistName}"? This action cannot be undone.`)) {
            // Make delete request
            deletePlaylistRequest(playlistId);
        }
    };
    
            async function deletePlaylistRequest(playlistId) {
        try {
            const response = await fetch(`/playlists/${playlistId}`, {
                method: 'DELETE'
            });
            
            if (response.ok) {
                alert('Playlist deleted successfully!');
                await loadPlaylists();
                // Refresh sidebar playlists
                if (typeof window.refreshSidebarPlaylists === 'function') {
                    window.refreshSidebarPlaylists();
                }
            } else {
                const error = await response.json();
                alert(error.message || 'Failed to delete playlist');
            }
        } catch (error) {
            console.error('Error deleting playlist:', error);
            alert('An error occurred while deleting the playlist');
        }
    }
    
    // Image upload event listeners
    imagePreview.addEventListener('click', function() {
        imageInput.click();
    });
    
    imageInput.addEventListener('change', function(e) {
        const file = e.target.files[0];
        if (file) {
            handleImageFile(file);
        }
    });
    
    removeImageBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        clearSelectedImage();
    });
    
    // Drag and drop functionality
    imagePreview.addEventListener('dragover', function(e) {
        e.preventDefault();
        this.classList.add('dragover');
    });
    
    imagePreview.addEventListener('dragleave', function(e) {
        e.preventDefault();
        this.classList.remove('dragover');
    });
    
    imagePreview.addEventListener('drop', function(e) {
        e.preventDefault();
        this.classList.remove('dragover');
        
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handleImageFile(files[0]);
        }
    });
    
    // Form submission
    form.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const playlistName = playlistNameInput.value.trim();
        
        // Disable the create button to prevent double submission
        createBtn.disabled = true;
        createBtn.textContent = 'Creating...';
        
        try {
            // Prepare form data
            const formData = new FormData();
            formData.append('name', playlistName);
            formData.append('tags', JSON.stringify(selectedTags));
            
            if (selectedImageFile) {
                formData.append('image', selectedImageFile);
            }
            
            // Encode playlist name for URL
            const encodedPlaylistName = encodeURIComponent(playlistName);
            
            // Make request to the server
            const response = await fetch(`/playlists/${encodedPlaylistName}`, {
                method: 'POST',
                body: formData
            });
            
            if (response.ok) {
                const result = await response.json();
                alert('Playlist created successfully!');
                closeModal();
                // Reload playlists instead of full page refresh
                await loadPlaylists();
                // Refresh sidebar playlists
                if (typeof window.refreshSidebarPlaylists === 'function') {
                    window.refreshSidebarPlaylists();
                }
            } else {
                const error = await response.json();
                alert(error.message || 'Failed to create playlist');
            }
        } catch (error) {
            console.error('Error creating playlist:', error);
            alert('An error occurred while creating the playlist');
        } finally {
            // Re-enable the create button
            createBtn.disabled = false;
            createBtn.textContent = 'Create Playlist';
        }
    });
    
    // Edit modal event listeners
    const editCloseModalBtn = document.getElementById('edit-close-modal-btn');
    const editCancelBtn = document.getElementById('edit-cancel-btn');
    const editForm = document.getElementById('edit-playlist-form');
    
    editCloseModalBtn.addEventListener('click', closeEditModal);
    editCancelBtn.addEventListener('click', closeEditModal);
    
    // Close edit modal when clicking backdrop
    editModal.addEventListener('click', function(e) {
        if (e.target === editModal) {
            closeEditModal();
        }
    });
    
    // Close edit modal with Escape key
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && editModal.classList.contains('show')) {
            closeEditModal();
        }
    });
    
    // Edit modal character counting
    editPlaylistNameInput.addEventListener('input', function() {
        updateEditCharacterCounts();
    });
    
    // Edit modal tag input event listeners
    editAddTagBtn.addEventListener('click', function() {
        addEditTag(editTagInput.value);
    });
    
    editTagInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            addEditTag(editTagInput.value);
        }
    });
    
    // Edit modal image upload event listeners
    editImagePreview.addEventListener('click', function() {
        editImageInput.click();
    });
    
    editImageInput.addEventListener('change', function(e) {
        const file = e.target.files[0];
        if (file) {
            handleEditImageFile(file);
        }
    });
    
    editRemoveImageBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        clearEditSelectedImage();
    });
    
    // Edit modal drag and drop functionality
    editImagePreview.addEventListener('dragover', function(e) {
        e.preventDefault();
        this.classList.add('dragover');
    });
    
    editImagePreview.addEventListener('dragleave', function(e) {
        e.preventDefault();
        this.classList.remove('dragover');
    });
    
    editImagePreview.addEventListener('drop', function(e) {
        e.preventDefault();
        this.classList.remove('dragover');
        
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handleEditImageFile(files[0]);
        }
    });
    
    // Edit form submission
    editForm.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const playlistName = editPlaylistNameInput.value.trim();
        const playlistId = document.getElementById('edit-playlist-id').value;
        
        // Disable the save button to prevent double submission
        const saveBtn = document.getElementById('edit-save-btn');
        saveBtn.disabled = true;
        saveBtn.textContent = 'Saving...';
        
        try {
            // Prepare form data
            const formData = new FormData();
            formData.append('name', playlistName);
            formData.append('tags', JSON.stringify(editSelectedTags));
            
            if (editSelectedImageFile) {
                formData.append('image', editSelectedImageFile);
            }
            
            // Make request to the server
            const response = await fetch(`/playlists/${playlistId}`, {
                method: 'PUT',
                body: formData
            });
            
            if (response.ok) {
                const result = await response.json();
                alert('Playlist updated successfully!');
                closeEditModal();
                // Reload playlists
                await loadPlaylists();
                // Refresh sidebar playlists
                if (typeof window.refreshSidebarPlaylists === 'function') {
                    window.refreshSidebarPlaylists();
                }
            } else {
                const error = await response.json();
                alert(error.message || 'Failed to update playlist');
            }
        } catch (error) {
            console.error('Error updating playlist:', error);
            alert('An error occurred while updating the playlist');
        } finally {
            // Re-enable the save button
            saveBtn.disabled = false;
            saveBtn.textContent = 'Save Changes';
        }
    });
    
    // Initialize
    updateCharacterCounts();
    updateCreateButtonState();
});

// Function to open modal from external calls (e.g., from base template)
window.openCreatePlaylistModal = function() {
    const modal = document.getElementById('create-playlist-modal');
    if (modal) {
        modal.classList.add('show');
        document.body.style.overflow = 'hidden';
        
        setTimeout(() => {
            const nameInput = document.getElementById('playlist-name');
            if (nameInput) nameInput.focus();
        }, 100);
    }
};
