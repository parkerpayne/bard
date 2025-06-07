// Settings Page JavaScript
let currentSettings = {
    discord: {
        botToken: '',
        channelId: '',
        connected: false
    },
    general: {
        autoPlay: true,
        showNotifications: true,
        defaultVolume: 50
    }
};

// DOM Elements
const discordForm = document.getElementById('discord-settings-form');
const generalForm = document.getElementById('general-settings-form');

// Discord Elements
const botTokenInput = document.getElementById('discord-bot-token');
const channelIdInput = document.getElementById('discord-channel-id');
const toggleTokenBtn = document.getElementById('toggle-token-visibility');
const testConnectionBtn = document.getElementById('test-connection-btn');
const saveDiscordBtn = document.getElementById('save-discord-settings-btn');
const statusIndicator = document.getElementById('status-indicator');
const statusText = document.getElementById('status-text');

// General Elements
const autoPlayCheckbox = document.getElementById('auto-play');
const showNotificationsCheckbox = document.getElementById('show-notifications');
const volumeSlider = document.getElementById('default-volume');
const volumeValue = document.getElementById('volume-value');
const saveGeneralBtn = document.getElementById('save-general-settings-btn');

// Initialize page
document.addEventListener('DOMContentLoaded', function() {
    loadSettings();
    setupEventListeners();
});

// Setup event listeners
function setupEventListeners() {
    // Discord form events
    if (discordForm) {
        discordForm.addEventListener('submit', handleDiscordSave);
    }
    
    if (generalForm) {
        generalForm.addEventListener('submit', handleGeneralSave);
    }
    
    // Toggle password visibility
    if (toggleTokenBtn) {
        toggleTokenBtn.addEventListener('click', toggleTokenVisibility);
    }
    
    // Test connection
    if (testConnectionBtn) {
        testConnectionBtn.addEventListener('click', testDiscordConnection);
    }
    
    // Volume slider
    if (volumeSlider) {
        volumeSlider.addEventListener('input', updateVolumeDisplay);
    }
    
    // Form validation
    if (botTokenInput) {
        botTokenInput.addEventListener('input', validateDiscordForm);
    }
    
    if (channelIdInput) {
        channelIdInput.addEventListener('input', validateDiscordForm);
    }
}

// Load settings from server
async function loadSettings() {
    try {
        const response = await fetch('/api/settings');
        
        if (response.ok) {
            const data = await response.json();
            if (data.success) {
                currentSettings = { ...currentSettings, ...data.settings };
            }
        } else {
            console.error('Failed to load settings from server');
        }
        
        populateFormFields();
        updateConnectionStatus();
        
    } catch (error) {
        console.error('Error loading settings:', error);
        showNotification('Failed to load settings', 'error');
    }
}

// Populate form fields with current settings
function populateFormFields() {
    // Discord settings
    if (botTokenInput && currentSettings.discord.botToken) {
        botTokenInput.value = currentSettings.discord.botToken;
    }
    
    if (channelIdInput && currentSettings.discord.channelId) {
        channelIdInput.value = currentSettings.discord.channelId;
    }
    
    // General settings
    if (autoPlayCheckbox) {
        autoPlayCheckbox.checked = currentSettings.general.autoPlay;
    }
    
    if (showNotificationsCheckbox) {
        showNotificationsCheckbox.checked = currentSettings.general.showNotifications;
    }
    
    if (volumeSlider) {
        volumeSlider.value = currentSettings.general.defaultVolume;
        updateVolumeDisplay();
    }
    
    validateDiscordForm();
}

// Update connection status display
function updateConnectionStatus() {
    if (!statusIndicator || !statusText) return;
    
    if (currentSettings.discord.connected) {
        statusIndicator.className = 'status-indicator online';
        statusText.textContent = 'Connected';
    } else {
        statusIndicator.className = 'status-indicator offline';
        statusText.textContent = 'Disconnected';
    }
}

// Toggle token visibility
function toggleTokenVisibility() {
    const isPassword = botTokenInput.type === 'password';
    const eyeOpen = toggleTokenBtn.querySelector('.eye-open');
    const eyeClosed = toggleTokenBtn.querySelector('.eye-closed');
    
    botTokenInput.type = isPassword ? 'text' : 'password';
    eyeOpen.style.display = isPassword ? 'none' : 'block';
    eyeClosed.style.display = isPassword ? 'block' : 'none';
}

// Validate Discord form
function validateDiscordForm() {
    const token = botTokenInput?.value?.trim() || '';
    const channelId = channelIdInput?.value?.trim() || '';
    
    const isTokenValid = token.length > 0;
    const isChannelValid = /^\d{17,19}$/.test(channelId);
    
    if (testConnectionBtn) {
        testConnectionBtn.disabled = !isTokenValid || !isChannelValid;
    }
    
    if (saveDiscordBtn) {
        saveDiscordBtn.disabled = !isTokenValid || !isChannelValid;
    }
    
    return isTokenValid && isChannelValid;
}

// Test Discord connection
async function testDiscordConnection() {
    if (!validateDiscordForm()) {
        showNotification('Please fill in all required fields correctly', 'error');
        return;
    }
    
    const token = botTokenInput.value.trim();
    const channelId = channelIdInput.value.trim();
    
    // Update status to testing
    statusIndicator.className = 'status-indicator testing';
    statusText.textContent = 'Testing...';
    
    // Disable button and show loading
    testConnectionBtn.disabled = true;
    testConnectionBtn.classList.add('loading');
    
    try {
        const response = await fetch('/api/settings/test-discord', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                botToken: token,
                channelId: channelId
            })
        });
        
        const data = await response.json();
        
        if (response.ok && data.success) {
            statusIndicator.className = 'status-indicator online';
            statusText.textContent = 'Connected';
            currentSettings.discord.connected = true;
            showNotification('Discord connection successful!', 'success');
        } else {
            statusIndicator.className = 'status-indicator offline';
            statusText.textContent = 'Connection Failed';
            currentSettings.discord.connected = false;
            showNotification(data.error || 'Failed to connect to Discord. Please check your credentials.', 'error');
        }
        
    } catch (error) {
        statusIndicator.className = 'status-indicator offline';
        statusText.textContent = 'Connection Failed';
        currentSettings.discord.connected = false;
        showNotification('Connection test failed', 'error');
        console.error('Discord connection test error:', error);
    } finally {
        testConnectionBtn.disabled = false;
        testConnectionBtn.classList.remove('loading');
        validateDiscordForm();
    }
}

// Handle Discord settings save
async function handleDiscordSave(e) {
    e.preventDefault();
    
    if (!validateDiscordForm()) {
        showNotification('Please fill in all required fields correctly', 'error');
        return;
    }
    
    const formData = {
        botToken: botTokenInput.value.trim(),
        channelId: channelIdInput.value.trim()
    };
    
    // Show loading state
    saveDiscordBtn.disabled = true;
    saveDiscordBtn.classList.add('loading');
    
    try {
        const response = await fetch('/api/settings', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                discord: formData
            })
        });
        
        const data = await response.json();
        
        if (response.ok && data.success) {
            // Update current settings
            currentSettings.discord.botToken = formData.botToken;
            currentSettings.discord.channelId = formData.channelId;
            
            showNotification('Discord settings saved successfully!', 'success');
        } else {
            showNotification(data.error || 'Failed to save Discord settings', 'error');
        }
        
    } catch (error) {
        showNotification('Failed to save Discord settings', 'error');
        console.error('Discord save error:', error);
    } finally {
        saveDiscordBtn.disabled = false;
        saveDiscordBtn.classList.remove('loading');
        validateDiscordForm();
    }
}

// Handle general settings save
async function handleGeneralSave(e) {
    e.preventDefault();
    
    const formData = {
        autoPlay: autoPlayCheckbox?.checked || false,
        showNotifications: showNotificationsCheckbox?.checked || false,
        defaultVolume: parseInt(volumeSlider?.value) || 50
    };
    
    // Show loading state
    saveGeneralBtn.disabled = true;
    saveGeneralBtn.classList.add('loading');
    
    try {
        const response = await fetch('/api/settings', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                general: formData
            })
        });
        
        const data = await response.json();
        
        if (response.ok && data.success) {
            // Update current settings
            currentSettings.general = { ...currentSettings.general, ...formData };
            
            showNotification('General settings saved successfully!', 'success');
        } else {
            showNotification(data.error || 'Failed to save general settings', 'error');
        }
        
    } catch (error) {
        showNotification('Failed to save general settings', 'error');
        console.error('General save error:', error);
    } finally {
        saveGeneralBtn.disabled = false;
        saveGeneralBtn.classList.remove('loading');
    }
}

// Update volume display
function updateVolumeDisplay() {
    if (volumeValue && volumeSlider) {
        volumeValue.textContent = `${volumeSlider.value}%`;
    }
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

// Export settings for use by other modules
window.musicPlayerSettings = currentSettings; 