// ============================================
// TTS Reader - Frontend Application
// ============================================

// Global State
const state = {
    voices: [],
    selectedVoice: null,
    textChunks: [],
    currentChunkIndex: 0,
    isPlaying: false,
    audioElement: null,
    rawText: '',
    startPosition: 0,
    readingSpeed: 0.5,  // Default: 0.5x for lecture comprehension (range 0.2-1.0)
    audioQueue: {},  // Prefetched audio URLs: {chunkIndex: audioUrl}
    prefetchCount: 2,  // GPU: Synthesize 2 chunks ahead (GPU is ~10x faster than CPU)
    synthesisInProgress: new Set()  // Track which chunks are currently being synthesized
};

// DOM Elements
const elements = {
    voiceSelect: document.getElementById('voice-select'),
    speedSlider: document.getElementById('speed-slider'),
    speedValue: document.getElementById('speed-value'),
    dropZone: document.getElementById('drop-zone'),
    fileInput: document.getElementById('file-input'),
    textDisplay: document.getElementById('text-display'),
    textLength: document.getElementById('text-length'),
    startBtn: document.getElementById('start-btn'),
    stopBtn: document.getElementById('stop-btn'),
    cleanupBtn: document.getElementById('cleanup-btn'),
    status: document.getElementById('status'),
    position: document.getElementById('position'),
    progress: document.getElementById('progress'),
    progressLabel: document.getElementById('progress-label'),
    // Chunk navigation elements
    currentChunk: document.getElementById('current-chunk'),
    prevChunkBtn: document.getElementById('prev-chunk-btn'),
    nextChunkBtn: document.getElementById('next-chunk-btn'),
    chunkInput: document.getElementById('chunk-input'),
    goChunkBtn: document.getElementById('go-chunk-btn')
};


// ============================================
// Initialization
// ============================================
document.addEventListener('DOMContentLoaded', () => {
    console.log('[INFO] Application initialized');

    // Load voices
    loadVoices();

    // Setup event listeners
    setupEventListeners();

    // Load saved position from localStorage
    loadSavedPosition();
});


// ============================================
// Function: Load Voices
// ============================================
async function loadVoices() {
    try {
        const response = await fetch('/api/voices');
        const voices = await response.json();

        state.voices = voices;

        // Clear and populate dropdown
        elements.voiceSelect.innerHTML = '';

        if (voices.length === 0) {
            elements.voiceSelect.innerHTML = '<option value="">No voices available</option>';
            console.warn('[WARNING] No voices found');
        } else {
            voices.forEach(voice => {
                const option = document.createElement('option');
                option.value = voice.path;
                option.textContent = voice.name;
                elements.voiceSelect.appendChild(option);
            });

            // Select first voice by default
            state.selectedVoice = voices[0].path;
            console.log(`[INFO] Loaded ${voices.length} voices`);
        }
    } catch (error) {
        console.error('[ERROR] Failed to load voices:', error);
        elements.voiceSelect.innerHTML = '<option value="">Error loading voices</option>';
        showErrorNotification('Failed to load voice samples', 'error');
    }
}


// ============================================
// Function: Setup Event Listeners
// ============================================
function setupEventListeners() {
    // Voice selection
    elements.voiceSelect.addEventListener('change', (e) => {
        state.selectedVoice = e.target.value;
        console.log('[INFO] Voice changed:', state.selectedVoice);
    });

    // Speed slider
    elements.speedSlider.addEventListener('input', (e) => {
        state.readingSpeed = parseFloat(e.target.value);
        elements.speedValue.textContent = `${state.readingSpeed.toFixed(1)}x`;
        console.log('[INFO] Speed changed:', state.readingSpeed);

        // Update playback speed of currently playing audio in real-time
        if (state.audioElement && !state.audioElement.paused) {
            state.audioElement.playbackRate = state.readingSpeed;
            console.log('[INFO] Updated playback rate of current audio to', state.readingSpeed);
        }
    });

    // File upload - drop zone
    elements.dropZone.addEventListener('click', () => {
        elements.fileInput.click();
    });

    elements.dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        elements.dropZone.classList.add('drag-over');
    });

    elements.dropZone.addEventListener('dragleave', () => {
        elements.dropZone.classList.remove('drag-over');
    });

    elements.dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        elements.dropZone.classList.remove('drag-over');

        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handleFileUpload(files[0]);
        }
    });

    elements.fileInput.addEventListener('change', (e) => {
        const files = e.target.files;
        if (files.length > 0) {
            handleFileUpload(files[0]);
        }
    });

    // Text display - click to set start position
    elements.textDisplay.addEventListener('click', () => {
        const selection = window.getSelection();
        if (selection.rangeCount > 0) {
            const range = selection.getRangeAt(0);
            state.startPosition = range.startOffset;
            console.log('[INFO] Start position set:', state.startPosition);
        }
    });

    // Playback controls
    elements.startBtn.addEventListener('click', startReading);
    elements.stopBtn.addEventListener('click', stopReading);
    elements.cleanupBtn.addEventListener('click', cleanupAudio);

    // Chunk navigation controls
    elements.prevChunkBtn.addEventListener('click', previousChunk);
    elements.nextChunkBtn.addEventListener('click', nextChunk);
    elements.goChunkBtn.addEventListener('click', goToChunk);
    
    // Enter key in chunk input
    elements.chunkInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            goToChunk();
        }
    });

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        // Only if not typing in input fields
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
            return;
        }

        // Left arrow: previous chunk
        if (e.key === 'ArrowLeft' && !elements.prevChunkBtn.disabled) {
            e.preventDefault();
            previousChunk();
        }
        // Right arrow: next chunk
        else if (e.key === 'ArrowRight' && !elements.nextChunkBtn.disabled) {
            e.preventDefault();
            nextChunk();
        }
        // Space: play/pause
        else if (e.key === ' ' && !elements.startBtn.disabled) {
            e.preventDefault();
            if (state.isPlaying) {
                stopReading();
            } else {
                startReading();
            }
        }
    });
}


// ============================================
// Function: Handle File Upload
// ============================================
async function handleFileUpload(file) {
    if (!file.name.endsWith('.txt')) {
        alert('Please upload a .txt file');
        return;
    }

    try {
        updateStatus('Loading file...');

        const text = await file.text();
        state.rawText = text;

        // Display text
        elements.textDisplay.value = text;
        elements.textLength.textContent = `${text.length} characters`;

        // Process text on backend
        const response = await fetch('/api/process_text', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                text: text,
                start_position: 0
            })
        });

        const result = await response.json();

        if (result.success) {
            state.textChunks = result.chunks;
            state.currentChunkIndex = 0;

            updateStatus('Ready');
            elements.startBtn.disabled = false;

            // Enable chunk navigation
            setChunkNavigationEnabled(true);
            updateChunkNavigation();

            console.log(`[INFO] Text loaded: ${result.total_chunks} chunks`);
        } else {
            throw new Error(result.error);
        }

    } catch (error) {
        console.error('[ERROR] File upload failed:', error);
        showErrorNotification(`Failed to load file: ${error.message}`, 'error');
        updateStatus('Error');
    }
}


// ============================================
// Function: Start Reading
// ============================================
async function startReading() {
    if (state.textChunks.length === 0) {
        alert('Please upload a text file first');
        return;
    }

    if (!state.selectedVoice) {
        alert('Please select a voice');
        return;
    }

    state.isPlaying = true;

    updateStatus('Preparing audio...');
    elements.startBtn.disabled = true;
    elements.stopBtn.disabled = false;

    console.log('[INFO] Starting reading from chunk', state.currentChunkIndex);

    // Clear audio queue and synthesis tracking
    state.audioQueue = {};
    state.synthesisInProgress.clear();

    // Synthesize ONLY the first chunk to start quickly
    console.log('[INFO] Preparing first chunk...');
    const firstAudioUrl = await synthesizeChunk(state.currentChunkIndex);

    if (firstAudioUrl) {
        state.audioQueue[state.currentChunkIndex] = firstAudioUrl;
        console.log('[INFO] First chunk ready, starting playback...');
    }

    updateStatus('Reading...');

    // Play chunks sequentially (prefetch will happen during playback)
    await playNextChunk();
}


// ============================================
// Function: Synthesize Chunk
// ============================================
async function synthesizeChunk(chunkIndex) {
    const chunk = state.textChunks[chunkIndex];

    // Validate chunk is not empty
    if (!chunk || chunk.trim().length === 0) {
        console.warn(`[WARNING] Chunk ${chunkIndex} is empty, skipping`);
        return null;
    }

    // Check if this chunk is already being synthesized
    if (state.synthesisInProgress.has(chunkIndex)) {
        console.log(`[INFO] Chunk ${chunkIndex + 1} synthesis already in progress, skipping duplicate request`);
        return null;
    }

    // Mark as in progress
    state.synthesisInProgress.add(chunkIndex);
    console.log(`[INFO] ⚙️ Synthesizing chunk ${chunkIndex + 1}/${state.textChunks.length}`);

    const startTime = performance.now();
    const response = await fetch('/api/synthesize', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            text: chunk,
            voice_path: state.selectedVoice,
            chunk_index: chunkIndex,
            language: 'ru',
            speed: state.readingSpeed
        })
    });

    const result = await response.json();

    // Remove from in-progress set
    state.synthesisInProgress.delete(chunkIndex);

    if (!result.success) {
        // Log error but return null instead of throwing (skip problematic chunks)
        console.error(`[ERROR] Chunk ${chunkIndex} failed: ${result.error}`);
        console.warn(`[WARNING] Skipping chunk ${chunkIndex} due to synthesis error`);

        // Show user notification about the error
        showErrorNotification(`Chunk ${chunkIndex + 1} failed: ${result.error}`, 'warning');

        return null;
    }

    const synthesisTime = ((performance.now() - startTime) / 1000).toFixed(1);

    // Store in queue
    state.audioQueue[chunkIndex] = result.audio_url;
    console.log(`[SUCCESS] ✓ Chunk ${chunkIndex + 1} ready in ${synthesisTime}s`);

    return result.audio_url;
}


// ============================================
// Function: Prefetch Next Chunks
// ============================================
async function prefetchNextChunks(startIndex, waitForFirst = false) {
    const prefetchPromises = [];

    for (let i = 0; i < state.prefetchCount; i++) {
        const chunkIndex = startIndex + i;

        // Skip if already in queue, in progress, or out of bounds
        if (chunkIndex >= state.textChunks.length ||
            state.audioQueue[chunkIndex] ||
            state.synthesisInProgress.has(chunkIndex)) {
            console.log(`[DEBUG] Skipping prefetch for chunk ${chunkIndex + 1} (already ready or in progress)`);
            continue;
        }

        console.log(`[INFO] 🚀 Starting prefetch for chunk ${chunkIndex + 1}`);

        // Start synthesis (don't await - let it run in background)
        prefetchPromises.push(
            synthesizeChunk(chunkIndex).catch(error => {
                console.error(`[ERROR] Prefetch failed for chunk ${chunkIndex}:`, error);
                state.synthesisInProgress.delete(chunkIndex);
            })
        );
    }

    // If waitForFirst is true, wait for at least the first chunk to be ready
    if (waitForFirst && prefetchPromises.length > 0) {
        await prefetchPromises[0];
        console.log('[INFO] First chunk ready, starting playback...');
    }

    // Return promises for tracking
    return prefetchPromises;
}


// ============================================
// Function: Play Next Chunk
// ============================================
async function playNextChunk() {
    if (!state.isPlaying) {
        return;
    }

    if (state.currentChunkIndex >= state.textChunks.length) {
        // Finished reading
        finishReading();
        return;
    }

    try {
        updateProgress();
        updatePosition();

        let audioUrl;

        // Debug: show queue status
        const queueKeys = Object.keys(state.audioQueue).map(k => parseInt(k));
        console.log(`[DEBUG] Queue status: ${queueKeys.length} chunks ready [${queueKeys.join(', ')}]`);

        // Check if chunk is already in queue (prefetched)
        if (state.audioQueue[state.currentChunkIndex]) {
            console.log(`[INFO] ✓ Using prefetched chunk ${state.currentChunkIndex + 1} (NO WAIT!)`);
            audioUrl = state.audioQueue[state.currentChunkIndex];
            delete state.audioQueue[state.currentChunkIndex];  // Remove from queue
        } else {
            // Not prefetched yet, synthesize now
            console.log(`[WARNING] ✗ Chunk ${state.currentChunkIndex + 1} NOT ready, synthesizing now (WAITING 15-20s)...`);
            audioUrl = await synthesizeChunk(state.currentChunkIndex);
        }

        // Check if chunk is null (empty or error) - skip it
        if (audioUrl === null) {
            console.warn(`[WARNING] Chunk ${state.currentChunkIndex + 1} is invalid, skipping to next`);
            state.currentChunkIndex++;
            await playNextChunk();  // Skip to next chunk
            return;
        }

        // Play audio FIRST
        const playPromise = playAudio(audioUrl);

        // THEN prefetch next chunk (only 1-2 ahead, not all!)
        // This runs in background while audio plays
        prefetchNextChunks(state.currentChunkIndex + 1);

        // Wait for audio to finish
        await playPromise;

        // Reset error counter on successful playback
        state.consecutiveErrors = 0;

        // Move to next chunk
        state.currentChunkIndex++;

        // Auto-cleanup old chunks (keep last 3)
        await cleanupOldChunks(state.currentChunkIndex, 3);

        // Continue with next chunk
        await playNextChunk();

    } catch (error) {
        console.error(`[ERROR] Playback failed for chunk ${state.currentChunkIndex}:`, error);

        // Try to skip to next chunk (limit retries to prevent infinite loop)
        const maxSkips = 5;
        if (!state.consecutiveErrors) state.consecutiveErrors = 0;
        
        state.consecutiveErrors++;
        
        if (state.consecutiveErrors >= maxSkips) {
            console.error(`[ERROR] Too many consecutive errors (${state.consecutiveErrors}), stopping playback`);
            showErrorNotification(`Playback stopped after ${maxSkips} consecutive errors`, 'error');
            stopReading();
            state.consecutiveErrors = 0;
            return;
        }

        console.warn(`[WARNING] Attempting to skip chunk ${state.currentChunkIndex} and continue (error ${state.consecutiveErrors}/${maxSkips})`);
        state.currentChunkIndex++;

        if (state.currentChunkIndex < state.textChunks.length) {
            // Try next chunk
            await playNextChunk();
        } else {
            // No more chunks, stop
            alert('Playback encountered errors and reached the end.');
            stopReading();
            state.consecutiveErrors = 0;
        }
    }
}


// ============================================
// Function: Play Audio
// ============================================
function playAudio(audioUrl) {
    return new Promise((resolve, reject) => {
        // Create audio element
        state.audioElement = new Audio(audioUrl);

        // CRITICAL FIX: Set playback speed (XTTS doesn't support speed parameter, use HTML5 Audio instead)
        state.audioElement.playbackRate = state.readingSpeed;
        console.log(`[INFO] Audio playback rate set to ${state.readingSpeed}x`);

        // Event handlers
        state.audioElement.addEventListener('ended', () => {
            console.log('[INFO] Chunk playback finished');
            resolve();
        });

        state.audioElement.addEventListener('error', (error) => {
            console.error('[ERROR] Audio playback error:', error);
            reject(error);
        });

        // Play audio (prefetch already started in playNextChunk before this)
        state.audioElement.play().catch(reject);
    });
}


// ============================================
// Function: Stop Reading
// ============================================
function stopReading() {
    state.isPlaying = false;

    // Stop current audio
    if (state.audioElement) {
        state.audioElement.pause();
        state.audioElement = null;
    }

    // Clear prefetch queue
    state.audioQueue = {};

    updateStatus('Stopped');
    elements.startBtn.disabled = false;
    elements.stopBtn.disabled = true;

    // Save position
    savePosition();

    console.log('[INFO] Reading stopped at chunk', state.currentChunkIndex);
}


// ============================================
// Function: Finish Reading
// ============================================
function finishReading() {
    state.isPlaying = false;
    state.currentChunkIndex = 0;

    updateStatus('Completed');
    updateProgress();
    updatePosition();

    elements.startBtn.disabled = false;
    elements.stopBtn.disabled = true;

    console.log('[INFO] Reading completed');

    // Show success notification
    showErrorNotification('Reading completed successfully!', 'success');

    // Cleanup audio files
    cleanupAudio();
}


// ============================================
// Function: Cleanup Audio Files
// ============================================
async function cleanupAudio() {
    try {
        const response = await fetch('/api/cleanup', {
            method: 'POST'
        });

        const result = await response.json();

        if (result.success) {
            console.log(`[INFO] Cleaned up ${result.deleted} audio files`);
        }
    } catch (error) {
        console.error('[ERROR] Cleanup failed:', error);
    }
}


// ============================================
// Function: Cleanup Old Chunks
// ============================================
async function cleanupOldChunks(currentChunkIndex, keepCount = 3) {
    try {
        const response = await fetch('/api/cleanup_old_chunks', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                current_chunk_index: currentChunkIndex,
                keep_count: keepCount
            })
        });

        const result = await response.json();

        if (result.success && result.deleted > 0) {
            console.log(`[INFO] Auto-cleanup: deleted ${result.deleted} old chunks`);
        }
    } catch (error) {
        console.error('[ERROR] Auto-cleanup failed:', error);
    }
}


// ============================================
// Function: Update UI Status
// ============================================
function updateStatus(status) {
    elements.status.textContent = status;

    if (status === 'Reading...') {
        elements.status.classList.add('reading');
    } else {
        elements.status.classList.remove('reading');
    }
}


// ============================================
// Function: Update Position Display
// ============================================
function updatePosition() {
    const current = state.currentChunkIndex + 1;
    const total = state.textChunks.length;

    elements.position.textContent = `${current} / ${total}`;
    
    // Do NOT call updateChunkNavigation here - causes recursion
}


// ============================================
// Function: Update Progress Bar
// ============================================
function updateProgress() {
    if (state.textChunks.length === 0) {
        elements.progress.style.width = '0%';
        elements.progressLabel.textContent = 'Ready to start';
        return;
    }

    const percent = ((state.currentChunkIndex + 1) / state.textChunks.length) * 100;
    elements.progress.style.width = `${percent}%`;
    elements.progressLabel.textContent = `Chunk ${state.currentChunkIndex + 1} of ${state.textChunks.length}`;
}


// ============================================
// Function: Save Position to localStorage
// ============================================
function savePosition() {
    localStorage.setItem('tts_reader_position', state.currentChunkIndex);
    console.log('[INFO] Position saved to localStorage');
}


// ============================================
// Function: Load Saved Position
// ============================================
function loadSavedPosition() {
    const savedPosition = localStorage.getItem('tts_reader_position');

    if (savedPosition !== null) {
        state.currentChunkIndex = parseInt(savedPosition, 10);
        console.log('[INFO] Loaded saved position:', state.currentChunkIndex);
    }
}


// ============================================
// Chunk Navigation Functions
// ============================================

// Go to previous chunk
function previousChunk() {
    if (state.currentChunkIndex > 0) {
        state.currentChunkIndex--;
        updateChunkNavigation();
        console.log('[INFO] Moved to previous chunk:', state.currentChunkIndex + 1);
        
        // If playing, play this chunk
        if (state.isPlaying) {
            stopCurrentAudio();
            playNextChunk();
        }
    }
}

// Go to next chunk
function nextChunk() {
    if (state.currentChunkIndex < state.textChunks.length - 1) {
        state.currentChunkIndex++;
        updateChunkNavigation();
        console.log('[INFO] Moved to next chunk:', state.currentChunkIndex + 1);
        
        // If playing, play this chunk
        if (state.isPlaying) {
            stopCurrentAudio();
            playNextChunk();
        }
    }
}

// Go to specific chunk
function goToChunk() {
    const targetChunk = parseInt(elements.chunkInput.value, 10);
    
    if (isNaN(targetChunk)) {
        alert('Please enter a valid chunk number');
        return;
    }
    
    // Convert to 0-based index
    const targetIndex = targetChunk - 1;
    
    if (targetIndex < 0 || targetIndex >= state.textChunks.length) {
        alert(`Please enter a chunk number between 1 and ${state.textChunks.length}`);
        return;
    }
    
    state.currentChunkIndex = targetIndex;
    updateChunkNavigation();
    console.log('[INFO] Jumped to chunk:', targetChunk);
    
    // Clear input
    elements.chunkInput.value = '';
    
    // If playing, play this chunk
    if (state.isPlaying) {
        stopCurrentAudio();
        playNextChunk();
    }
}

// Update chunk navigation UI
function updateChunkNavigation() {
    const current = state.currentChunkIndex + 1;
    const total = state.textChunks.length;
    
    // Update chunk display
    elements.currentChunk.textContent = `${current} / ${total}`;
    
    // Update position display
    updatePosition();
    
    // Update progress
    updateProgress();
    
    // Update navigation buttons state
    elements.prevChunkBtn.disabled = state.currentChunkIndex === 0;
    elements.nextChunkBtn.disabled = state.currentChunkIndex === total - 1;
    
    // Update chunk input max attribute
    elements.chunkInput.max = total;
    
    // Save position
    savePosition();
}

// Enable/disable chunk navigation
function setChunkNavigationEnabled(enabled) {
    elements.prevChunkBtn.disabled = !enabled || state.currentChunkIndex === 0;
    elements.nextChunkBtn.disabled = !enabled || state.currentChunkIndex === state.textChunks.length - 1;
    elements.chunkInput.disabled = !enabled;
    elements.goChunkBtn.disabled = !enabled;
}

// Stop current audio playback
function stopCurrentAudio() {
    if (state.audioElement) {
        state.audioElement.pause();
        state.audioElement.currentTime = 0;
        state.audioElement = null;
    }
}


// ============================================
// Error Notification System
// ============================================
function showErrorNotification(message, type = 'error') {
    // Create notification container if it doesn't exist
    let notificationContainer = document.getElementById('notification-container');
    if (!notificationContainer) {
        notificationContainer = document.createElement('div');
        notificationContainer.id = 'notification-container';
        notificationContainer.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 10000;
            display: flex;
            flex-direction: column;
            gap: 10px;
            max-width: 400px;
        `;
        document.body.appendChild(notificationContainer);
    }

    // Create notification element
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.style.cssText = `
        background: ${type === 'error' ? '#ef4444' : type === 'warning' ? '#f59e0b' : '#10b981'};
        color: white;
        padding: 12px 16px;
        border-radius: 8px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        font-family: system-ui, -apple-system, sans-serif;
        font-size: 14px;
        line-height: 1.5;
        animation: slideIn 0.3s ease-out;
        cursor: pointer;
        word-wrap: break-word;
    `;

    // Add animation styles if not already present
    if (!document.getElementById('notification-styles')) {
        const style = document.createElement('style');
        style.id = 'notification-styles';
        style.textContent = `
            @keyframes slideIn {
                from {
                    transform: translateX(100%);
                    opacity: 0;
                }
                to {
                    transform: translateX(0);
                    opacity: 1;
                }
            }
            @keyframes fadeOut {
                from {
                    opacity: 1;
                }
                to {
                    opacity: 0;
                    transform: translateY(-10px);
                }
            }
        `;
        document.head.appendChild(style);
    }

    // Add close functionality on click
    notification.onclick = function() {
        notification.style.animation = 'fadeOut 0.3s ease-out';
        setTimeout(() => notification.remove(), 300);
    };

    // Set notification content
    notification.innerHTML = `
        <div style="display: flex; align-items: start; gap: 8px;">
            <span style="font-size: 16px;">
                ${type === 'error' ? '❌' : type === 'warning' ? '⚠️' : '✓'}
            </span>
            <div style="flex: 1;">
                <div style="font-weight: 600; margin-bottom: 2px;">
                    ${type === 'error' ? 'Error' : type === 'warning' ? 'Warning' : 'Success'}
                </div>
                <div>${message}</div>
            </div>
        </div>
    `;

    // Add to container
    notificationContainer.appendChild(notification);

    // Auto-remove after 5 seconds for warnings/success, 10 seconds for errors
    const timeout = type === 'error' ? 10000 : 5000;
    setTimeout(() => {
        if (notification.parentNode) {
            notification.style.animation = 'fadeOut 0.3s ease-out';
            setTimeout(() => notification.remove(), 300);
        }
    }, timeout);

    // Log to console as well
    const logMethod = type === 'error' ? 'error' : type === 'warning' ? 'warn' : 'log';
    console[logMethod](`[NOTIFICATION] ${message}`);
}

// Export for global use
window.showErrorNotification = showErrorNotification;


// ============================================
// Console Banner
// ============================================
console.log('%c TTS Reader v1.0 ', 'background: #2563eb; color: white; font-size: 16px; padding: 4px 8px; border-radius: 4px;');
console.log('%c Powered by F5-TTS Russian ', 'color: #64748b; font-size: 12px;');
