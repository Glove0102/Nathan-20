# AI Conversational Calling System

## Overview

This is a Python web application that enables automated outbound phone calls to senior citizens, facilitating real-time voice conversations powered by OpenAI's GPT models. The system uses Twilio for telephony services and provides a web interface for call management and monitoring.

## System Architecture

The application follows a multi-tier architecture:

**Frontend Layer:**
- Bootstrap-based web interface for call initiation and monitoring
- Real-time WebSocket communication with backend for status updates
- Live conversation transcript display

**Backend Layer:**
- Flask web framework with SocketIO for WebSocket support
- SQLAlchemy ORM with SQLite database (configurable for PostgreSQL)
- Gunicorn WSGI server for production deployment

**External Integrations:**
- Twilio Programmable Voice API for telephony
- OpenAI API for conversational AI (GPT-4o model)
- WebSocket connections for real-time audio streaming

## Key Components

### Core Application (`app.py`)
- Flask application factory with SQLAlchemy database integration
- SocketIO configuration for real-time communication
- Environment-based configuration with fallback defaults
- Automatic database table creation on startup

### Database Models (`models.py`)
- **Call**: Tracks phone calls with Twilio SIDs and status
- **ConversationTurn**: Stores conversation history with role-based messages

### Audio Processing (`audio_processor.py`)
- Real-time audio chunk processing with voice activity detection
- Base64 audio decoding and μ-law to PCM conversion
- Silence detection and speech boundary identification
- Configurable thresholds for speech detection

### Conversation Management (`conversation_manager.py`)
- OpenAI GPT-4o integration for conversational AI
- Senior-friendly system prompt with clear communication guidelines
- Database persistence of conversation turns
- Audio processing pipeline coordination

### Telephony Integration (`routes.py`)
- Twilio API client configuration
- Call initiation endpoint with database tracking
- Webhook endpoints for Twilio call events
- TwiML response generation for media streaming

### WebSocket Handler (`websocket_handler.py`)
- Dual WebSocket support (frontend and Twilio Media Streams)
- Session management for active calls
- Real-time audio and conversation data flow
- Call state management and cleanup

## Data Flow

1. **Call Initiation**: Frontend sends phone number to backend API
2. **Twilio Call**: Backend uses Twilio API to initiate outbound call
3. **Media Stream Setup**: Twilio establishes WebSocket connection for audio
4. **Audio Processing**: Real-time audio chunks processed for speech detection
5. **Speech-to-Text**: Audio converted to text via OpenAI Whisper
6. **AI Response**: GPT-4o generates conversational response
7. **Text-to-Speech**: Response converted back to audio
8. **Audio Delivery**: Audio streamed back through Twilio to caller
9. **Frontend Updates**: Real-time status and transcript updates via SocketIO

## External Dependencies

### Core Technologies
- **Flask**: Web framework with SocketIO for WebSocket support
- **SQLAlchemy**: Database ORM with support for SQLite and PostgreSQL
- **Gunicorn**: Production WSGI server with autoscaling deployment

### Third-Party APIs
- **Twilio**: Programmable Voice API for telephony services
- **OpenAI**: GPT-4o for conversational AI, Whisper for STT, TTS for voice synthesis

### Required Environment Variables
- `OPENAI_API_KEY`: OpenAI API authentication
- `TWILIO_ACCOUNT_SID`: Twilio account identifier
- `TWILIO_AUTH_TOKEN`: Twilio authentication token
- `TWILIO_PHONE_NUMBER`: Twilio phone number for outbound calls
- `WEBHOOK_URL`: Public URL for Twilio webhooks
- `DATABASE_URL`: Database connection string (optional, defaults to SQLite)
- `SESSION_SECRET`: Flask session encryption key (optional, defaults to dev key)

## Deployment Strategy

**Development Environment:**
- Uses Replit with automatic Python 3.11 environment setup
- SQLite database for local development
- Flask development server with hot reload

**Production Environment:**
- Gunicorn WSGI server with autoscale deployment target
- PostgreSQL database support via environment configuration
- ProxyFix middleware for proper request handling behind reverse proxy
- Connection pooling with health checks for database reliability

**Infrastructure Requirements:**
- Public HTTPS endpoint for Twilio webhook callbacks
- WebSocket support for real-time communication
- SSL/TLS termination for secure connections

## User Preferences

Preferred communication style: Simple, everyday language.

## Changelog

Changelog:
- June 25, 2025. Initial setup