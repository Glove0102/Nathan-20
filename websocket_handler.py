import json
import logging
import asyncio
import websockets
import threading
from flask_socketio import emit
from app import app, socketio, db
from models import Call
from audio_processor import AudioProcessor
from conversation_manager import ConversationManager

# Store active sessions
active_sessions = {}

class CallSession:
    def __init__(self, stream_sid):
        self.stream_sid = stream_sid
        self.call = None
        self.audio_processor = AudioProcessor()
        self.conversation_manager = ConversationManager()
        self.websocket = None
        
    def set_call(self, call):
        self.call = call
        self.conversation_manager.set_call_id(call.id)

@socketio.on('connect')
def handle_connect():
    """Handle frontend WebSocket connection"""
    logging.info("Frontend client connected")
    emit('status', {'message': 'Connected to server'})

@socketio.on('disconnect')
def handle_disconnect():
    """Handle frontend WebSocket disconnection"""
    logging.info("Frontend client disconnected")

async def handle_twilio_websocket(websocket, path):
    """Handle Twilio Media Stream WebSocket connections"""
    session = None
    
    try:
        logging.info(f"New Twilio WebSocket connection: {path}")
        
        async for message in websocket:
            try:
                data = json.loads(message)
                event_type = data.get('event')
                
                if event_type == 'start':
                    # Initialize session
                    stream_sid = data['start']['streamSid']
                    call_sid = data['start']['callSid']
                    
                    session = CallSession(stream_sid)
                    session.websocket = websocket
                    active_sessions[stream_sid] = session
                    
                    # Find and update call record
                    with app.app_context():
                        call = Call.query.filter_by(call_sid=call_sid).first()
                        if call:
                            call.stream_sid = stream_sid
                            call.status = 'connected'
                            db.session.commit()
                            session.set_call(call)
                    
                    logging.info(f"Stream started - StreamSid: {stream_sid}, CallSid: {call_sid}")
                    
                    # Send initial greeting
                    await send_initial_greeting(session)
                    
                    # Notify frontend
                    socketio.emit('call_status', {
                        'status': 'connected',
                        'stream_sid': stream_sid
                    })
                
                elif event_type == 'media':
                    # Process audio data
                    if session:
                        await process_audio_chunk(session, data['media'])
                
                elif event_type == 'stop':
                    # Clean up session
                    if session:
                        logging.info(f"Stream stopped - StreamSid: {session.stream_sid}")
                        
                        with app.app_context():
                            if session.call:
                                session.call.status = 'completed'
                                db.session.commit()
                        
                        # Remove from active sessions
                        if session.stream_sid in active_sessions:
                            del active_sessions[session.stream_sid]
                        
                        # Notify frontend
                        socketio.emit('call_status', {
                            'status': 'disconnected',
                            'stream_sid': session.stream_sid
                        })
                
            except json.JSONDecodeError:
                logging.error("Invalid JSON received from Twilio")
            except Exception as e:
                logging.error(f"Error processing Twilio message: {str(e)}")
                
    except websockets.exceptions.ConnectionClosed:
        logging.info("Twilio WebSocket connection closed")
    except Exception as e:
        logging.error(f"Twilio WebSocket error: {str(e)}")
    finally:
        # Clean up session
        if session and session.stream_sid in active_sessions:
            del active_sessions[session.stream_sid]

async def send_initial_greeting(session):
    """Send initial AI greeting to the caller"""
    try:
        greeting_text = "Hello! I'm an AI assistant. How can I help you today?"
        
        # Generate TTS audio
        audio_data = await session.conversation_manager.text_to_speech(greeting_text)
        
        if audio_data:
            # Send audio to Twilio
            await send_audio_to_twilio(session, audio_data)
            
            # Add to conversation history
            with app.app_context():
                session.conversation_manager.add_message("assistant", greeting_text)
            
            # Notify frontend
            socketio.emit('conversation_update', {
                'role': 'assistant',
                'content': greeting_text,
                'stream_sid': session.stream_sid
            })
            
    except Exception as e:
        logging.error(f"Error sending initial greeting: {str(e)}")

async def process_audio_chunk(session, media_data):
    """Process incoming audio chunk from caller"""
    try:
        # Add audio chunk to buffer
        session.audio_processor.add_audio_chunk(media_data['payload'])
        
        # Check if we have a complete utterance
        if session.audio_processor.has_complete_utterance():
            audio_buffer = session.audio_processor.get_and_clear_buffer()
            
            # Convert to text using Whisper
            transcript = await session.conversation_manager.speech_to_text(audio_buffer)
            
            if transcript and transcript.strip():
                logging.info(f"User said: {transcript}")
                
                # Add to conversation history
                with app.app_context():
                    session.conversation_manager.add_message("user", transcript)
                
                # Notify frontend
                socketio.emit('conversation_update', {
                    'role': 'user',
                    'content': transcript,
                    'stream_sid': session.stream_sid
                })
                
                # Generate AI response
                response_text = await session.conversation_manager.generate_response()
                
                if response_text:
                    logging.info(f"AI responded: {response_text}")
                    
                    # Add to conversation history
                    with app.app_context():
                        session.conversation_manager.add_message("assistant", response_text)
                    
                    # Convert to speech
                    audio_data = await session.conversation_manager.text_to_speech(response_text)
                    
                    if audio_data:
                        # Send audio to Twilio
                        await send_audio_to_twilio(session, audio_data)
                    
                    # Notify frontend
                    socketio.emit('conversation_update', {
                        'role': 'assistant',
                        'content': response_text,
                        'stream_sid': session.stream_sid
                    })
                    
    except Exception as e:
        logging.error(f"Error processing audio chunk: {str(e)}")

async def send_audio_to_twilio(session, audio_data):
    """Send audio data back to Twilio"""
    try:
        if session.websocket:
            message = {
                "event": "media",
                "streamSid": session.stream_sid,
                "media": {
                    "payload": audio_data
                }
            }
            await session.websocket.send(json.dumps(message))
            
    except Exception as e:
        logging.error(f"Error sending audio to Twilio: {str(e)}")

def start_websocket_server():
    """Start the WebSocket server for Twilio Media Streams"""
    async def server():
        # Start WebSocket server on port 8000 for Twilio
        await websockets.serve(handle_twilio_websocket, "0.0.0.0", 8000)
        logging.info("Twilio WebSocket server started on port 8000")
        
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(server())
    loop.run_forever()

# Start WebSocket server in a separate thread
websocket_thread = threading.Thread(target=start_websocket_server, daemon=True)
websocket_thread.start()
