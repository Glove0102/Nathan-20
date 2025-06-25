import os
import logging
import asyncio
import io
import tempfile
from openai import OpenAI
from app import db
from models import ConversationTurn
from audio_processor import AudioProcessor

class ConversationManager:
    def __init__(self):
        # the newest OpenAI model is "gpt-4o" which was released May 13, 2024.
        # do not change this unless explicitly requested by the user
        self.openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        self.call_id = None
        self.audio_processor = AudioProcessor()
        
        # System prompt for the AI assistant
        self.system_prompt = """You are a helpful and friendly AI assistant designed to have conversations with senior citizens over the phone. 

Key guidelines:
- Speak clearly and at a moderate pace
- Use simple, everyday language
- Be patient and understanding
- Keep responses concise (1-2 sentences typically)
- Be warm and engaging
- If you don't understand something, politely ask for clarification
- Show genuine interest in what they're sharing
- Avoid technical jargon

Remember, this is a voice conversation, so be conversational and natural."""

    def set_call_id(self, call_id):
        """Set the call ID for this conversation"""
        self.call_id = call_id

    def add_message(self, role, content):
        """Add a message to the conversation history"""
        if not self.call_id:
            logging.warning("No call ID set for conversation manager")
            return
            
        try:
            turn = ConversationTurn()
            turn.call_id = self.call_id
            turn.role = role
            turn.content = content
            db.session.add(turn)
            db.session.commit()
            
            logging.info(f"Added {role} message to conversation: {content[:50]}...")
            
        except Exception as e:
            logging.error(f"Error adding message to conversation: {str(e)}")

    def get_conversation_history(self, limit=10):
        """Get recent conversation history"""
        if not self.call_id:
            return []
            
        try:
            turns = ConversationTurn.query.filter_by(call_id=self.call_id)\
                                        .order_by(ConversationTurn.timestamp.desc())\
                                        .limit(limit)\
                                        .all()
            
            # Reverse to get chronological order
            turns.reverse()
            
            history = []
            for turn in turns:
                history.append({
                    "role": turn.role,
                    "content": turn.content
                })
            
            return history
            
        except Exception as e:
            logging.error(f"Error getting conversation history: {str(e)}")
            return []

    async def speech_to_text(self, audio_data):
        """Convert speech to text using OpenAI Whisper"""
        try:
            # Convert audio to proper format
            wav_audio = self.audio_processor.convert_to_wav_format(audio_data)
            
            # Create temporary file for Whisper API
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                # Write WAV header and audio data
                self._write_wav_file(temp_file, wav_audio)
                temp_file_path = temp_file.name
            
            # Call Whisper API
            with open(temp_file_path, 'rb') as audio_file:
                response = self.openai_client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language="en"
                )
            
            # Clean up temporary file
            os.unlink(temp_file_path)
            
            transcript = response.text.strip()
            logging.info(f"Transcribed: {transcript}")
            
            return transcript
            
        except Exception as e:
            logging.error(f"Error in speech to text: {str(e)}")
            return None

    async def generate_response(self):
        """Generate AI response using OpenAI GPT"""
        try:
            # Get conversation history
            history = self.get_conversation_history()
            
            # Build messages for OpenAI
            messages = [{"role": "system", "content": self.system_prompt}]
            messages.extend(history)
            
            # Generate response
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",  # Using gpt-4o-mini as specified in PRD
                messages=messages,
                max_tokens=150,  # Keep responses concise
                temperature=0.7
            )
            
            response_text = response.choices[0].message.content
            if response_text:
                response_text = response_text.strip()
                logging.info(f"Generated response: {response_text}")
                return response_text
            else:
                logging.warning("Empty response from OpenAI")
                return "I'm sorry, I didn't catch that. Could you please repeat?"
            
        except Exception as e:
            logging.error(f"Error generating response: {str(e)}")
            return "I'm sorry, I didn't catch that. Could you please repeat?"

    async def text_to_speech(self, text):
        """Convert text to speech using OpenAI TTS"""
        try:
            # Generate speech using OpenAI TTS
            response = self.openai_client.audio.speech.create(
                model="tts-1",
                voice="alloy",
                input=text,
                response_format="pcm"  # Use PCM format for better compatibility
            )
            
            # Get raw PCM audio data (OpenAI TTS outputs 24kHz, 16-bit, mono)
            pcm_audio = response.content
            
            import audioop
            import base64
            
            # Convert from OpenAI's 24kHz to Twilio's 8kHz
            # OpenAI TTS outputs 24kHz, 16-bit, mono PCM
            downsampled_audio = audioop.ratecv(pcm_audio, 2, 1, 24000, 8000, None)[0]
            
            # Convert to mulaw format for Twilio
            mulaw_audio = audioop.lin2ulaw(downsampled_audio, 2)
            
            # Encode to base64 for Twilio WebSocket
            encoded_audio = base64.b64encode(mulaw_audio).decode('utf-8')
            
            audio_duration = len(pcm_audio) / (24000 * 2)  # Original duration at 24kHz
            logging.info(f"Generated TTS for: {text[:50]}... (duration: {audio_duration:.2f}s, size: {len(encoded_audio)} chars)")
            
            return encoded_audio
            
        except Exception as e:
            logging.error(f"Error in text to speech: {str(e)}")
            import traceback
            logging.error(f"TTS Error traceback: {traceback.format_exc()}")
            return None

    def _write_wav_file(self, file, audio_data):
        """Write audio data as WAV file"""
        import struct
        
        # WAV file parameters
        sample_rate = 16000
        bits_per_sample = 16
        channels = 1
        
        # Calculate file size
        data_length = len(audio_data)
        file_length = data_length + 36
        
        # Write WAV header
        file.write(b'RIFF')
        file.write(struct.pack('<I', file_length))
        file.write(b'WAVE')
        file.write(b'fmt ')
        file.write(struct.pack('<I', 16))  # fmt chunk size
        file.write(struct.pack('<H', 1))   # PCM format
        file.write(struct.pack('<H', channels))
        file.write(struct.pack('<I', sample_rate))
        file.write(struct.pack('<I', sample_rate * channels * bits_per_sample // 8))
        file.write(struct.pack('<H', channels * bits_per_sample // 8))
        file.write(struct.pack('<H', bits_per_sample))
        file.write(b'data')
        file.write(struct.pack('<I', data_length))
        file.write(audio_data)
