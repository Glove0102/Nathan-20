import base64
import audioop
import logging
from collections import deque
import time

class AudioProcessor:
    def __init__(self):
        self.audio_buffer = deque()
        self.silence_threshold = 500  # RMS threshold for silence detection
        self.min_speech_duration = 1.0  # Minimum speech duration in seconds
        self.max_speech_duration = 10.0  # Maximum speech duration in seconds
        self.silence_duration = 1.5  # Required silence duration to end utterance
        
        self.last_speech_time = 0
        self.utterance_start_time = 0
        self.consecutive_silence_count = 0
        
    def add_audio_chunk(self, payload):
        """Add audio chunk to buffer and process"""
        try:
            # Decode base64 audio data
            audio_data = base64.b64decode(payload)
            
            # Convert mulaw to linear PCM
            linear_audio = audioop.ulaw2lin(audio_data, 2)
            
            # Calculate RMS for voice activity detection
            rms = audioop.rms(linear_audio, 2)
            
            current_time = time.time()
            
            # Voice activity detection
            is_speech = rms > self.silence_threshold
            
            if is_speech:
                self.last_speech_time = current_time
                self.consecutive_silence_count = 0
                
                # Mark start of utterance
                if not self.audio_buffer:
                    self.utterance_start_time = current_time
                    
            else:
                self.consecutive_silence_count += 1
            
            # Add to buffer
            self.audio_buffer.append(linear_audio)
            
            logging.debug(f"Audio chunk processed - RMS: {rms}, Speech: {is_speech}")
            
        except Exception as e:
            logging.error(f"Error processing audio chunk: {str(e)}")
    
    def has_complete_utterance(self):
        """Check if we have a complete utterance ready for processing"""
        if not self.audio_buffer:
            return False
            
        current_time = time.time()
        utterance_duration = current_time - self.utterance_start_time
        silence_duration = current_time - self.last_speech_time
        
        # Check conditions for complete utterance
        conditions = [
            # Minimum speech duration reached and sufficient silence
            utterance_duration >= self.min_speech_duration and silence_duration >= self.silence_duration,
            # Maximum speech duration reached
            utterance_duration >= self.max_speech_duration
        ]
        
        return any(conditions)
    
    def get_and_clear_buffer(self):
        """Get buffered audio and clear the buffer"""
        if not self.audio_buffer:
            return None
            
        try:
            # Concatenate all audio chunks
            combined_audio = b''.join(self.audio_buffer)
            
            # Clear buffer
            self.audio_buffer.clear()
            
            # Reset timing variables
            self.last_speech_time = 0
            self.utterance_start_time = 0
            self.consecutive_silence_count = 0
            
            logging.info(f"Audio buffer cleared - Size: {len(combined_audio)} bytes")
            
            return combined_audio
            
        except Exception as e:
            logging.error(f"Error getting audio buffer: {str(e)}")
            return None
    
    def convert_to_wav_format(self, audio_data):
        """Convert PCM audio to WAV format for OpenAI"""
        try:
            # Convert to 16kHz sample rate if needed (OpenAI prefers 16kHz)
            # Twilio sends 8kHz, so we need to upsample
            upsampled_audio = audioop.ratecv(audio_data, 2, 1, 8000, 16000, None)[0]
            
            return upsampled_audio
            
        except Exception as e:
            logging.error(f"Error converting audio format: {str(e)}")
            return audio_data
    
    def convert_from_openai_format(self, audio_data):
        """Convert audio from OpenAI format back to Twilio format"""
        try:
            # Convert from 16kHz back to 8kHz
            downsampled_audio = audioop.ratecv(audio_data, 2, 1, 16000, 8000, None)[0]
            
            # Convert back to mulaw
            mulaw_audio = audioop.lin2ulaw(downsampled_audio, 2)
            
            # Encode to base64
            encoded_audio = base64.b64encode(mulaw_audio).decode('utf-8')
            
            return encoded_audio
            
        except Exception as e:
            logging.error(f"Error converting audio from OpenAI format: {str(e)}")
            return None
