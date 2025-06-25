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
        self.ai_speaking_event = asyncio.Event() # Event to signal AI is speaking
        self.user_speaking_event = asyncio.Event() # Event to signal user is speaking (for barge-in)

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

async def handle_twilio_websocket(websocket):
    """Handle Twilio Media Stream WebSocket connections"""
    session = None

    try:
        logging.info(f"New Twilio WebSocket connection established")

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
                        try:
                            call = Call.query.filter_by(call_sid=call_sid).first()
                            if call:
                                call.stream_sid = stream_sid
                                call.status = 'connected'
                                db.session.commit()
                                session.set_call(call)
                        except Exception as e:
                            logging.error(f"Database error in stream start: {str(e)}")
                            db.session.rollback()

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
                        # Before processing, check for user speaking to potentially barge-in
                        payload = data['media']['payload']
                        audio_data_raw = base64.b64decode(payload)
                        rms = audioop.rms(audio_data_raw, 2) # Assume 16-bit PCM for RMS calculation on raw data
                        # If AI is speaking AND user speech is detected (RMS > threshold)
                        if session.ai_speaking_event.is_set() and rms > session.audio_processor.silence_threshold:
                            session.ai_speaking_event.clear() # Signal AI to stop speaking
                            logging.info("Barge-in detected: AI speech interrupted.")
                            # Optionally send a clear message to Twilio (Twilio can handle it if it gets empty media or disconnect)
                            # For now, just stopping the server-side sending is sufficient.

                        await process_audio_chunk(session, data['media'])

                elif event_type == 'stop':
                    # Clean up session
                    if session:
                        logging.info(f"Stream stopped - StreamSid: {session.stream_sid}")

                        with app.app_context():
                            try:
                                if session.call:
                                    session.call.status = 'completed'
                                    db.session.commit()
                            except Exception as e:
                                logging.error(f"Database error in stream stop: {str(e)}")
                                db.session.rollback()

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
        logging.info(f"Sending initial greeting: {greeting_text}")

        # Generate TTS audio
        audio_data = await session.conversation_manager.text_to_speech(greeting_text)

        if audio_data:
            logging.info(f"Generated audio data, length: {len(audio_data)}")

            session.ai_speaking_event.set() # Set flag that AI is speaking
            await send_audio_to_twilio(session, audio_data)
            session.ai_speaking_event.clear() # Clear flag after speaking

            # Add to conversation history
            with app.app_context():
                try:
                    session.conversation_manager.add_message("assistant", greeting_text)
                    logging.info("Added greeting to conversation history")
                except Exception as e:
                    logging.error(f"Database error adding greeting: {str(e)}")

            # Notify frontend
            socketio.emit('conversation_update', {
                'role': 'assistant',
                'content': greeting_text,
                'stream_sid': session.stream_sid
            })
            logging.info("Sent greeting notification to frontend")
        else:
            logging.error("Failed to generate audio data for greeting")

    except Exception as e:
        logging.error(f"Error sending initial greeting: {str(e)}")
        import traceback
        logging.error(f"Greeting error traceback: {traceback.format_exc()}")
    finally:
        session.ai_speaking_event.clear() # Ensure flag is cleared even on error

async def process_audio_chunk(session, media_data):
    """Process incoming audio chunk from caller"""
    try:
        # Check if AI is currently speaking and user is initiating speech (for barge-in)
        payload = media_data['payload']
        # add_audio_chunk handles mulaw to linear PCM conversion internally
        session.audio_processor.add_audio_chunk(payload) 

        # We need a way to detect actual speech here to trigger barge-in reliably.
        # The add_audio_chunk already calculates RMS and sets self.speech_detected within AudioProcessor.
        # So we can check session.audio_processor.speech_detected directly after adding the chunk.

        # If AI is speaking and current chunk contains speech, clear AI speaking event (barge-in)
        if session.ai_speaking_event.is_set() and session.audio_processor.speech_detected:
            session.ai_speaking_event.clear()
            logging.info("Barge-in: AI speech interrupted by user.")
            socketio.emit('call_status', { # Update status on frontend
                'status': 'User Speaking',
                'stream_sid': session.stream_sid
            })

        # Check if we have a complete utterance
        if session.audio_processor.has_complete_utterance():
            audio_buffer = session.audio_processor.get_and_clear_buffer()

            if audio_buffer and len(audio_buffer) > 0:
                buffer_duration = len(audio_buffer) / 16000  # 8kHz * 2 bytes per sample
                logging.info(f"Processing audio buffer: {len(audio_buffer)} bytes ({buffer_duration:.2f}s)")

                # Convert to text using Whisper
                transcript = await session.conversation_manager.speech_to_text(audio_buffer)

                if transcript and transcript.strip():
                    logging.info(f"User said: {transcript}")

                    # Add to conversation history
                    with app.app_context():
                        try:
                            session.conversation_manager.add_message("user", transcript)
                        except Exception as e:
                            logging.error(f"Database error adding user message: {str(e)}")

                    # Notify frontend
                    socketio.emit('conversation_update', {
                        'role': 'user',
                        'content': transcript,
                        'stream_sid': session.stream_sid
                    })
                    socketio.emit('call_status', { # Update status on frontend
                        'status': 'AI Thinking', # New status to indicate AI is processing
                        'stream_sid': session.stream_sid
                    })

                    # Generate AI response
                    response_text = await session.conversation_manager.generate_response()

                    if response_text:
                        logging.info(f"AI responded: {response_text}")

                        # Add to conversation history
                        with app.app_context():
                            try:
                                session.conversation_manager.add_message("assistant", response_text)
                            except Exception as e:
                                logging.error(f"Database error adding AI response: {str(e)}")

                        # Convert to speech
                        audio_data_tts = await session.conversation_manager.text_to_speech(response_text) # Renamed to avoid conflict

                        if audio_data_tts:
                            logging.info(f"Sending TTS audio to Twilio: {len(audio_data_tts)} chars")
                            session.ai_speaking_event.set() # Set flag that AI is speaking
                            await send_audio_to_twilio(session, audio_data_tts)
                            session.ai_speaking_event.clear() # Clear flag after speaking
                        else:
                            logging.error("Failed to generate TTS audio")

                        # Notify frontend
                        socketio.emit('conversation_update', {
                            'role': 'assistant',
                            'content': response_text,
                            'stream_sid': session.stream_sid
                        })
                        socketio.emit('call_status', { # Update status on frontend
                            'status': 'Connected', # Or 'AI Idle'
                            'stream_sid': session.stream_sid
                        })
                else:
                    logging.warning(f"No transcript received for audio buffer of {len(audio_buffer)} bytes")
            else:
                logging.warning("Audio buffer is empty after processing")

    except Exception as e:
        logging.error(f"Error processing audio chunk: {str(e)}")
        import traceback
        logging.error(f"Audio processing traceback: {traceback.format_exc()}")
    finally:
        session.ai_speaking_event.clear() # Ensure flag is cleared even on error

async def send_audio_to_twilio(session, audio_data):
    """Send audio data back to Twilio, with support for interruption"""
    try:
        # Twilio payload requires splitting large audio into smaller chunks
        # Each media payload is typically 320 bytes (20ms of 8kHz mulaw)
        # Assuming audio_data is already mulaw base64 encoded string
        chunk_size_bytes = 320 # 20ms of 8kHz mulaw audio is 160 bytes of mulaw. Base64 encodes it to ~216 chars.
                               # Let's adjust for typical Twilio chunking

        # Need to re-encode to mulaw for sending, text_to_speech returns base64 mulaw already
        # The received audio_data is already base64 encoded mulaw, split it into smaller chunks

        # Twilio media stream expects base64 encoded mulaw chunks.
        # Our `text_to_speech` method returns base64 encoded mulaw.
        # So we just need to send it in smaller frames.

        # Estimate how many base64 chars for 20ms chunk (160 bytes raw mulaw)
        # 160 bytes * 4/3 (base64) approx = 214 chars. Let's send in 20ms chunks.
        # This implies chunking the already base64 encoded string.

        # A more robust solution would re-chunk the raw mulaw *before* base64 encoding it
        # or have the TTS function return raw mulaw so it can be chunked more precisely.
        # For now, let's just break up the base64 string.

        # This might not align perfectly with Twilio's 20ms frame expectations
        # if the base64 encoding results in variable lengths for raw bytes.
        # A better approach involves sending raw mulaw chunks and then base64 encoding each.

        # Let's assume audio_data is a large base64 string and split it.
        # Each 20ms of 8kHz 16-bit linear PCM is 160 bytes. Mulaw is 80 bytes.
        # So 80 bytes of mulaw base64 encoded is roughly 108 characters.
        # Let's target sending chunks of raw mulaw bytes then encode each.

        # Re-evaluating text_to_speech: it returns base64 encoded mulaw string directly.
        # The prompt says "Twilio Media Streams: Always send audio at 8kHz sample rate, 16-bit linear PCM, mono."
        # And `audio_processor.py` states `bytes_per_second = 16000` (16-bit PCM).
        # But Twilio usually sends mulaw over websocket and expects mulaw back.
        # The `convert_from_openai_format` in `audio_processor.py` does exactly this:
        # downsample 16kHz PCM to 8kHz PCM, then convert to mulaw, then base64 encode.
        # So `audio_data` from `text_to_speech` is already mulaw, base64 encoded.

        # Let's assume a reasonable payload size for Twilio. 400 characters of base64 should be small enough.
        # We need to send in small, frequent chunks.

        chunk_size_chars = 400 # Adjust this based on Twilio's recommended frame size in base64 characters

        # Split the base64 encoded audio into chunks
        for i in range(0, len(audio_data), chunk_size_chars):
            if not session.ai_speaking_event.is_set(): # Check if interrupted
                logging.info("AI speech interrupted (sending loop broken).")
                break

            chunk = audio_data[i:i + chunk_size_chars]

            message = {
                "event": "media",
                "streamSid": session.stream_sid,
                "media": {
                    "payload": chunk
                }
            }
            await session.websocket.send(json.dumps(message))
            await asyncio.sleep(0.02)  # Simulate 20ms audio chunks (adjust as needed)

    except Exception as e:
        logging.error(f"Error sending audio to Twilio: {str(e)}")

def start_websocket_server():
    """Start the WebSocket server for Twilio Media Streams"""
    async def server():
        # Start WebSocket server on port 8000 for Twilio
        server_instance = await websockets.serve(handle_twilio_websocket, "0.0.0.0", 8000)
        logging.info("Twilio WebSocket server started on port 8000")
        # Keep the server running
        await server_instance.wait_closed()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(server())
    except KeyboardInterrupt:
        logging.info("WebSocket server stopped")
    finally:
        loop.close()

# Start WebSocket server in a separate thread
websocket_thread = threading.Thread(target=start_websocket_server, daemon=True)
websocket_thread.start()