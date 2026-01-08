/**
 * ContextDock Web Chat Interface JavaScript Client (T184)
 * 
 * Features:
 * - Query submission with keyboard navigation
 * - Real-time message rendering
 * - Citation expansion and deep links
 * - Keyboard shortcuts (Enter to send, Escape to close)
 * - Accessibility support (ARIA live regions, focus management)
 */

// Application State
const state = {
    messages: [],
    conversationId: null,
    isLoading: false,
    workspaceId: null,
    userId: null
};

// DOM Elements
const elements = {
    chatMessages: null,
    messageForm: null,
    messageInput: null,
    sendButton: null,
    loadingIndicator: null,
    citationModal: null,
    modalBody: null,
    modalClose: null,
    errorAlert: null,
    errorMessage: null,
    errorClose: null,
    charCount: null
};

// Initialize Application
function init() {
    // Cache DOM elements
    elements.chatMessages = document.getElementById('chat-messages');
    elements.messageForm = document.getElementById('message-form');
    elements.messageInput = document.getElementById('message-input');
    elements.sendButton = document.getElementById('send-button');
    elements.loadingIndicator = document.getElementById('loading-indicator');
    elements.citationModal = document.getElementById('citation-modal');
    elements.modalBody = document.getElementById('modal-body');
    elements.modalClose = document.getElementById('modal-close');
    elements.errorAlert = document.getElementById('error-alert');
    elements.errorMessage = document.getElementById('error-message');
    elements.errorClose = document.getElementById('error-close');
    elements.charCount = document.getElementById('char-count');
    
    // Setup event listeners
    elements.messageForm.addEventListener('submit', handleSubmit);
    elements.messageInput.addEventListener('input', handleInput);
    elements.messageInput.addEventListener('keydown', handleKeyDown);
    elements.modalClose.addEventListener('click', closeModal);
    elements.errorClose.addEventListener('click', closeError);
    
    // Close modal on overlay click
    elements.citationModal.addEventListener('click', (e) => {
        if (e.target === elements.citationModal || e.target.classList.contains('modal-overlay')) {
            closeModal();
        }
    });
    
    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeModal();
            closeError();
        }
    });
    
    // Auto-resize textarea
    elements.messageInput.addEventListener('input', autoResizeTextarea);
    
    // Load workspace and user info (from localStorage or API)
    loadUserContext();
    
    // Focus input on load
    elements.messageInput.focus();
}

// Load user context (workspace ID, user ID)
function loadUserContext() {
    // In production, this would come from authentication
    // For demo, use localStorage or default values
    state.workspaceId = localStorage.getItem('workspaceId') || 'demo-workspace';
    state.userId = localStorage.getItem('userId') || 'demo-user';
}

// Handle form submission
async function handleSubmit(e) {
    e.preventDefault();
    
    const query = elements.messageInput.value.trim();
    if (!query || state.isLoading) {
        return;
    }
    
    // Add user message to UI
    addMessage({
        role: 'user',
        content: query,
        timestamp: new Date().toISOString()
    });
    
    // Clear input
    elements.messageInput.value = '';
    updateCharCount();
    autoResizeTextarea();
    
    // Show loading indicator
    showLoading();
    
    try {
        // Send query to API
        const response = await fetch('/v1/conversations/query', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Workspace-ID': state.workspaceId,
                'X-User-ID': state.userId
            },
            body: JSON.stringify({
                query: query,
                conversation_id: state.conversationId
            })
        });
        
        if (!response.ok) {
            throw new Error(`API error: ${response.status} ${response.statusText}`);
        }
        
        const data = await response.json();
        
        // Update conversation ID
        if (data.conversation_id) {
            state.conversationId = data.conversation_id;
        }
        
        // Add assistant message to UI
        addMessage({
            role: 'assistant',
            content: data.answer,
            citations: data.citations || [],
            timestamp: new Date().toISOString()
        });
        
    } catch (error) {
        console.error('Error sending message:', error);
        showError(`Failed to get response: ${error.message}`);
    } finally {
        hideLoading();
        elements.messageInput.focus();
    }
}

// Handle input changes
function handleInput(e) {
    updateCharCount();
}

// Handle keyboard shortcuts
function handleKeyDown(e) {
    // Enter to send (without Shift)
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        elements.messageForm.requestSubmit();
    }
}

// Update character count
function updateCharCount() {
    const length = elements.messageInput.value.length;
    elements.charCount.textContent = `${length} / 5000`;
}

// Auto-resize textarea
function autoResizeTextarea() {
    elements.messageInput.style.height = 'auto';
    elements.messageInput.style.height = elements.messageInput.scrollHeight + 'px';
}

// Add message to chat
function addMessage(message) {
    state.messages.push(message);
    
    const messageElement = createMessageElement(message);
    elements.chatMessages.appendChild(messageElement);
    
    // Scroll to bottom
    elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
}

// Create message element
function createMessageElement(message) {
    const div = document.createElement('div');
    div.className = `message message-${message.role}`;
    div.setAttribute('role', 'article');
    
    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.setAttribute('aria-hidden', 'true');
    avatar.textContent = message.role === 'user' ? '👤' : '🤖';
    
    const content = document.createElement('div');
    content.className = 'message-content';
    
    const header = document.createElement('div');
    header.className = 'message-header';
    
    const author = document.createElement('span');
    author.className = 'message-author';
    author.textContent = message.role === 'user' ? 'You' : 'ContextDock Assistant';
    
    const time = document.createElement('time');
    time.className = 'message-time';
    time.setAttribute('datetime', message.timestamp);
    time.textContent = formatTime(message.timestamp);
    
    header.appendChild(author);
    header.appendChild(time);
    
    const text = document.createElement('div');
    text.className = 'message-text';
    text.innerHTML = formatText(message.content);
    
    content.appendChild(header);
    content.appendChild(text);
    
    // Add citations if present
    if (message.citations && message.citations.length > 0) {
        const citations = createCitationsElement(message.citations);
        content.appendChild(citations);
    }
    
    div.appendChild(avatar);
    div.appendChild(content);
    
    return div;
}

// Create citations element
function createCitationsElement(citations) {
    const container = document.createElement('div');
    container.className = 'citations';
    
    const title = document.createElement('div');
    title.className = 'citations-title';
    title.textContent = `Sources (${citations.length})`;
    container.appendChild(title);
    
    citations.forEach((citation, index) => {
        const citationElement = createCitationElement(citation, index + 1);
        container.appendChild(citationElement);
    });
    
    return container;
}

// Create citation element
function createCitationElement(citation, number) {
    const div = document.createElement('div');
    div.className = 'citation';
    div.setAttribute('role', 'button');
    div.setAttribute('tabindex', '0');
    div.setAttribute('aria-label', `Citation ${number}: ${citation.title || citation.source}`);
    
    const citationNumber = document.createElement('div');
    citationNumber.className = 'citation-number';
    citationNumber.textContent = `[${number}]`;
    
    const citationContent = document.createElement('div');
    citationContent.className = 'citation-content';
    
    const source = document.createElement('div');
    source.className = 'citation-source';
    source.textContent = citation.title || citation.source;
    
    const excerpt = document.createElement('div');
    excerpt.className = 'citation-excerpt';
    excerpt.textContent = truncate(citation.excerpt || citation.content, 150);
    
    citationContent.appendChild(source);
    citationContent.appendChild(excerpt);
    
    if (citation.url) {
        const link = document.createElement('a');
        link.className = 'citation-link';
        link.href = citation.url;
        link.textContent = 'View source →';
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        link.setAttribute('aria-label', `Open ${citation.title || citation.source} in new tab`);
        citationContent.appendChild(link);
    }
    
    div.appendChild(citationNumber);
    div.appendChild(citationContent);
    
    // Click handler to show full citation
    div.addEventListener('click', (e) => {
        if (e.target.tagName !== 'A') {
            showCitationModal(citation, number);
        }
    });
    
    // Keyboard handler
    div.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            showCitationModal(citation, number);
        }
    });
    
    return div;
}

// Show citation modal
function showCitationModal(citation, number) {
    const html = `
        <div class="citation-modal-content">
            <h3>Citation ${number}</h3>
            <div class="citation-details">
                <div class="citation-field">
                    <strong>Source:</strong>
                    <p>${citation.title || citation.source}</p>
                </div>
                ${citation.author ? `
                    <div class="citation-field">
                        <strong>Author:</strong>
                        <p>${citation.author}</p>
                    </div>
                ` : ''}
                ${citation.created_at ? `
                    <div class="citation-field">
                        <strong>Date:</strong>
                        <p>${formatDate(citation.created_at)}</p>
                    </div>
                ` : ''}
                <div class="citation-field">
                    <strong>Excerpt:</strong>
                    <p>${citation.excerpt || citation.content}</p>
                </div>
                ${citation.url ? `
                    <div class="citation-field">
                        <a href="${citation.url}" target="_blank" rel="noopener noreferrer" class="citation-link">
                            Open in ${citation.connector_type || 'original source'} →
                        </a>
                    </div>
                ` : ''}
            </div>
        </div>
    `;
    
    elements.modalBody.innerHTML = html;
    elements.citationModal.style.display = 'flex';
    
    // Focus close button for accessibility
    elements.modalClose.focus();
}

// Close citation modal
function closeModal() {
    elements.citationModal.style.display = 'none';
}

// Show loading indicator
function showLoading() {
    state.isLoading = true;
    elements.loadingIndicator.style.display = 'flex';
    elements.sendButton.disabled = true;
}

// Hide loading indicator
function hideLoading() {
    state.isLoading = false;
    elements.loadingIndicator.style.display = 'none';
    elements.sendButton.disabled = false;
}

// Show error alert
function showError(message) {
    elements.errorMessage.textContent = message;
    elements.errorAlert.style.display = 'flex';
    
    // Auto-hide after 5 seconds
    setTimeout(() => {
        closeError();
    }, 5000);
}

// Close error alert
function closeError() {
    elements.errorAlert.style.display = 'none';
}

// Format text (basic markdown-like formatting)
function formatText(text) {
    return text
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/\n/g, '<br>')
        .replace(/`(.*?)`/g, '<code>$1</code>');
}

// Format timestamp
function formatTime(timestamp) {
    const date = new Date(timestamp);
    const now = new Date();
    const diff = now - date;
    
    if (diff < 60000) {
        return 'Just now';
    } else if (diff < 3600000) {
        const minutes = Math.floor(diff / 60000);
        return `${minutes} minute${minutes > 1 ? 's' : ''} ago`;
    } else if (diff < 86400000) {
        const hours = Math.floor(diff / 3600000);
        return `${hours} hour${hours > 1 ? 's' : ''} ago`;
    } else {
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }
}

// Format date
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString(undefined, {
        year: 'numeric',
        month: 'long',
        day: 'numeric'
    });
}

// Truncate text
function truncate(text, maxLength) {
    if (text.length <= maxLength) {
        return text;
    }
    return text.substring(0, maxLength) + '...';
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
