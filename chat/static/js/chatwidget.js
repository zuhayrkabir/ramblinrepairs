// Chat Widget JavaScript with Markdown Support
// Include marked.js for markdown parsing
const markedScript = document.createElement('script');
markedScript.src = 'https://cdn.jsdelivr.net/npm/marked/marked.min.js';
document.head.appendChild(markedScript);

// Include DOMPurify for XSS prevention
const purifyScript = document.createElement('script');
purifyScript.src = 'https://cdn.jsdelivr.net/npm/dompurify@3.0.6/dist/purify.min.js';
document.head.appendChild(purifyScript);

document.addEventListener('DOMContentLoaded', function() {
    // Create chat widget container
    const chatWidget = document.createElement('div');
    chatWidget.id = 'chat-widget';
    chatWidget.innerHTML = `
        <div id="chat-button" class="chat-button">
            <i class="fas fa-comments"></i>
        </div>
        <div id="chat-context-menu" class="chat-context-menu" style="display: none;">
            <div class="context-menu-item" id="clear-history">Clear Chat History</div>
        </div>
        <div id="chat-modal" class="chat-modal">
            <div class="chat-header">
                <h5>Ramblin' Repairs Assistant</h5>
                <button id="chat-close" class="chat-close">&times;</button>
            </div>
            <div id="chat-messages" class="chat-messages"></div>
            <div class="chat-input-container">
                <div class="input-group">
                    <input type="text" id="chat-input" class="form-control" placeholder="Ask me anything about repairs...">
                    <button id="chat-send" class="btn btn-primary">Send</button>
                </div>
                <div id="chat-typing" class="chat-typing" style="display: none;">
                    <span>Assistant is typing</span>
                </div>
            </div>
        </div>
    `;
    document.body.appendChild(chatWidget);

    // Elements
    const chatButton = document.getElementById('chat-button');
    const chatModal = document.getElementById('chat-modal');
    const chatClose = document.getElementById('chat-close');
    const chatInput = document.getElementById('chat-input');
    const chatSend = document.getElementById('chat-send');
    const chatMessages = document.getElementById('chat-messages');
    const chatTyping = document.getElementById('chat-typing');
    const contextMenu = document.getElementById('chat-context-menu');
    const clearHistoryItem = document.getElementById('clear-history');

    // Get current order ID from data attribute (set by template)
    let currentOrderId = document.body.dataset.orderId || null;

    // Configure marked.js for compact spacing
    if (window.marked) {
        const renderer = new marked.Renderer();
        renderer.paragraph = function(text) {
            return '<p style="margin: 0rem 0;">' + text + '</p>';
        };
        renderer.listitem = function(text) {
            return '<li style="margin: 0rem 0;">' + text + '</li>';
        };
        renderer.list = function(body, ordered, start) {
            const tag = ordered ? 'ol' : 'ul';
            const startAttr = ordered && start !== 1 ? ` start="${start}"` : '';
            return `<${tag}${startAttr} style="margin: 0rem 0; padding-left: 1.5rem;">${body}</${tag}>`;
        };
        marked.setOptions({ renderer: renderer });
    }

    // Load conversation history will be called when chat opens

    // Event listeners
    chatButton.addEventListener('click', toggleChat);
    chatButton.addEventListener('contextmenu', showContextMenu);
    chatClose.addEventListener('click', toggleChat);
    chatSend.addEventListener('click', sendMessage);
    chatInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            sendMessage();
        }
    });
    clearHistoryItem.addEventListener('click', clearChatHistory);

    // Hide context menu when clicking elsewhere
    document.addEventListener('click', function(e) {
        if (!contextMenu.contains(e.target) && e.target !== chatButton) {
            contextMenu.style.display = 'none';
        }
    });

    function toggleChat() {
        const isOpening = chatModal.style.display !== 'flex';
        chatModal.style.display = isOpening ? 'flex' : 'none';

        if (isOpening) {
            chatInput.focus();
            loadChatHistory(); // Load history when opening chat
        }
    }

    function sendMessage() {
        const message = chatInput.value.trim();
        if (!message) return;

        // Add user message to UI
        addMessage(message, 'user');

        // Clear input
        chatInput.value = '';

        // Show typing indicator
        chatTyping.style.display = 'block';

        // Send to server
        fetch('/chat/send/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify({
                message: message,
                order_id: currentOrderId
            })
        })
        .then(response => response.json())
        .then(data => {
            chatTyping.style.display = 'none';
            if (data.status === 'success') {
                addMessage(data.response, 'bot', data.source_url, data.source_title);
            } else {
                addMessage('Sorry, I encountered an error. Please try again.', 'bot');
            }
        })
        .catch(error => {
            chatTyping.style.display = 'none';
            addMessage('Sorry, I\'m having trouble connecting. Please try again later.', 'bot');
            console.error('Chat error:', error);
        });
    }

    function addMessage(text, sender, source_url, source_title) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `chat-message ${sender}`;
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        
        // Append source link as text to the message content for bot messages
        let displayText = text;
        if (sender === 'bot' && source_url) {
            const sourceLink = source_title || source_url;
            displayText += `<br><br> Source: [${sourceLink}](${source_url})`;
        }
        
        if (sender === 'bot' && window.marked && window.DOMPurify) {
            // Render markdown for bot messages
            try {
                const htmlContent = window.marked.parse(displayText);
                const cleanHTML = window.DOMPurify.sanitize(htmlContent);
                contentDiv.innerHTML = cleanHTML;
            } catch (e) {
                // Fallback to text if markdown parsing fails
                contentDiv.textContent = displayText;
            }
        } else {
            // User messages: use text content to prevent any HTML injection
            contentDiv.textContent = displayText;
        }
        
        messageDiv.appendChild(contentDiv);

        chatMessages.appendChild(messageDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function loadChatHistory() {
        // Load chat history from the server
        fetch('/chat/history/', {
            method: 'GET',
            headers: {
                'X-CSRFToken': getCSRFToken()
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success' && data.history.length > 0) {
                // Clear any existing messages
                chatMessages.innerHTML = '';

                // Add each message from history
                data.history.forEach(msg => {
                    addMessage(msg.message, msg.sender, msg.source_url, msg.source_title);
                });
            }
        })
        .catch(error => {
            console.error('Error loading chat history:', error);
        });
    }

    function showContextMenu(e) {
        e.preventDefault();
        const x = e.pageX;
        const y = e.pageY;
        
        // Ensure menu doesn't go off-screen
        const menuWidth = 150;
        const menuHeight = 40; // Approximate height for one item
        const windowWidth = window.innerWidth;
        const windowHeight = window.innerHeight;
        
        let left = x;
        let top = y;
        
        if (x + menuWidth > windowWidth) {
            left = windowWidth - menuWidth - 10;
        }
        if (y + menuHeight > windowHeight) {
            top = windowHeight - menuHeight - 10;
        }
        
        contextMenu.style.display = 'block';
        contextMenu.style.left = left + 'px';
        contextMenu.style.top = top + 'px';
    }

    function clearChatHistory() {
        contextMenu.style.display = 'none';
        
        // Send request to clear history
        fetch('/chat/clear/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                // Clear messages from UI
                chatMessages.innerHTML = '';
                // Optionally show a confirmation message
                addMessage('Chat history cleared.', 'bot');
            } else {
                addMessage('Failed to clear chat history. Please try again.', 'bot');
            }
        })
        .catch(error => {
            console.error('Error clearing chat history:', error);
            addMessage('Failed to clear chat history. Please try again.', 'bot');
        });
    }

    function getCSRFToken() {
        // Get CSRF token from cookie
        const name = 'csrftoken';
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }
});