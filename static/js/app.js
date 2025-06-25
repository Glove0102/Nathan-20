// AI Conversational Calling System - Frontend JavaScript

class CallManager {
    constructor() {
        this.socket = null;
        this.currentCall = null;
        this.isCallActive = false;
        
        this.initializeSocketIO();
        this.initializeEventListeners();
        this.logMessage('System initialized', 'info');
    }
    
    initializeSocketIO() {
        // Connect to Flask-SocketIO
        this.socket = io();
        
        this.socket.on('connect', () => {
            this.logMessage('Connected to server', 'success');
            this.updateCallStatus('No Active Call', 'secondary');
        });
        
        this.socket.on('disconnect', () => {
            this.logMessage('Disconnected from server', 'warning');
        });
        
        this.socket.on('call_status', (data) => {
            this.handleCallStatusUpdate(data);
        });
        
        this.socket.on('conversation_update', (data) => {
            this.handleConversationUpdate(data);
        });
        
        this.socket.on('status', (data) => {
            this.logMessage(data.message, 'info');
        });
    }
    
    initializeEventListeners() {
        const callForm = document.getElementById('callForm');
        const callButton = document.getElementById('callButton');
        
        callForm.addEventListener('submit', (e) => {
            e.preventDefault();
            this.initiateCall();
        });
    }
    
    async initiateCall() {
        const phoneNumber = document.getElementById('phoneNumber').value.trim();
        const callButton = document.getElementById('callButton');
        
        if (!phoneNumber) {
            this.logMessage('Please enter a phone number', 'error');
            return;
        }
        
        // Validate phone number format
        const phoneRegex = /^\+[1-9]\d{10,14}$/;
        if (!phoneRegex.test(phoneNumber)) {
            this.logMessage('Please enter a valid phone number with country code (e.g., +1234567890)', 'error');
            return;
        }
        
        try {
            // Disable button and show loading
            callButton.disabled = true;
            callButton.innerHTML = '<span class="loading-spinner me-2"></span>Initiating...';
            
            this.logMessage(`Initiating call to ${phoneNumber}`, 'info');
            this.updateCallStatus('Initiating...', 'warning', true);
            
            const response = await fetch('/initiate_call', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    phone_number: phoneNumber
                })
            });
            
            const data = await response.json();
            
            if (response.ok && data.success) {
                this.currentCall = {
                    id: data.call_id,
                    sid: data.call_sid,
                    phone: phoneNumber
                };
                
                this.isCallActive = true;
                this.logMessage(`Call initiated successfully. Call SID: ${data.call_sid}`, 'success');
                this.updateCallStatus('Calling...', 'warning', true);
                this.updateCallDetails();
                this.clearConversation();
                
            } else {
                throw new Error(data.error || 'Failed to initiate call');
            }
            
        } catch (error) {
            this.logMessage(`Error initiating call: ${error.message}`, 'error');
            this.updateCallStatus('Call Failed', 'danger');
            
        } finally {
            // Re-enable button
            callButton.disabled = false;
            callButton.innerHTML = '<i data-feather="phone" class="me-2"></i>Start Call';
            feather.replace();
        }
    }
    
    handleCallStatusUpdate(data) {
        const { status, stream_sid } = data;
        
        switch (status) {
            case 'connected':
                this.updateCallStatus('Connected', 'success');
                this.currentCall.streamSid = stream_sid;
                this.updateCallDetails();
                this.logMessage(`Call connected. Stream SID: ${stream_sid}`, 'success');
                break;
                
            case 'ai_speaking':
                this.updateCallStatus('AI Speaking', 'info', true);
                this.logMessage('AI is speaking', 'info');
                break;
                
            case 'user_speaking':
                this.updateCallStatus('User Speaking', 'primary', true);
                this.logMessage('User is speaking', 'info');
                break;
                
            case 'disconnected':
                this.updateCallStatus('Call Ended', 'secondary');
                this.isCallActive = false;
                this.currentCall = null;
                this.hideCallDetails();
                this.logMessage('Call disconnected', 'warning');
                break;
                
            default:
                this.logMessage(`Call status: ${status}`, 'info');
        }
    }
    
    handleConversationUpdate(data) {
        const { role, content, stream_sid } = data;
        
        // Verify this update is for our current call
        if (this.currentCall && this.currentCall.streamSid === stream_sid) {
            this.addConversationMessage(role, content);
            this.logMessage(`${role === 'user' ? 'User' : 'AI'}: ${content.substring(0, 50)}...`, 'info');
            
            // Update status based on who's speaking
            if (role === 'assistant') {
                this.updateCallStatus('AI Speaking', 'info', true);
            }
        }
    }
    
    updateCallStatus(status, variant, pulse = false) {
        const statusElement = document.getElementById('callStatus');
        const iconName = this.getStatusIcon(status);
        
        statusElement.innerHTML = `
            <div class="badge bg-${variant} fs-6 ${pulse ? 'pulse' : ''}">
                <i data-feather="${iconName}" class="me-2"></i>
                ${status}
            </div>
        `;
        
        feather.replace();
    }
    
    getStatusIcon(status) {
        const iconMap = {
            'No Active Call': 'phone-off',
            'Initiating...': 'phone-outgoing',
            'Calling...': 'phone-call',
            'Connected': 'phone',
            'AI Speaking': 'volume-2',
            'User Speaking': 'mic',
            'Call Ended': 'phone-off',
            'Call Failed': 'phone-missed'
        };
        
        return iconMap[status] || 'activity';
    }
    
    updateCallDetails() {
        if (this.currentCall) {
            document.getElementById('currentPhone').textContent = this.currentCall.phone;
            document.getElementById('currentCallId').textContent = this.currentCall.id;
            document.getElementById('currentStreamId').textContent = this.currentCall.streamSid || 'Pending...';
            document.getElementById('callDetails').style.display = 'block';
        }
    }
    
    hideCallDetails() {
        document.getElementById('callDetails').style.display = 'none';
    }
    
    clearConversation() {
        const container = document.getElementById('conversationContainer');
        container.innerHTML = `
            <div class="text-center text-muted">
                <i data-feather="message-square" class="mb-2" style="width: 48px; height: 48px;"></i>
                <p>Conversation started. Waiting for audio...</p>
            </div>
        `;
        feather.replace();
    }
    
    addConversationMessage(role, content) {
        const container = document.getElementById('conversationContainer');
        
        // Clear placeholder text if this is the first message
        if (container.querySelector('.text-center.text-muted')) {
            container.innerHTML = '';
        }
        
        const timestamp = new Date().toLocaleTimeString();
        const messageElement = document.createElement('div');
        messageElement.className = `conversation-message ${role}`;
        
        messageElement.innerHTML = `
            <div class="message-bubble ${role}">
                ${this.escapeHtml(content)}
            </div>
            <div class="message-timestamp">
                ${role === 'user' ? 'Caller' : 'AI Assistant'} • ${timestamp}
            </div>
        `;
        
        container.appendChild(messageElement);
        
        // Scroll to bottom
        container.scrollTop = container.scrollHeight;
    }
    
    logMessage(message, level = 'info') {
        const logsContainer = document.getElementById('systemLogs');
        const timestamp = new Date().toLocaleTimeString();
        
        const logElement = document.createElement('div');
        logElement.className = `system-log-entry log-${level}`;
        logElement.innerHTML = `
            <span class="text-muted">[${timestamp}]</span> ${this.escapeHtml(message)}
        `;
        
        logsContainer.appendChild(logElement);
        
        // Scroll to bottom
        logsContainer.scrollTop = logsContainer.scrollHeight;
        
        // Keep only last 100 log entries
        const entries = logsContainer.querySelectorAll('.system-log-entry');
        if (entries.length > 100) {
            entries[0].remove();
        }
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Initialize the application when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new CallManager();
});
