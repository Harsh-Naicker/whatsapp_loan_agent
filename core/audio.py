# core/audio.py

import logging
import tempfile
import os
from typing import Dict, Any, Optional
import uuid

from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

from .language import LanguageProcessor

logger = logging.getLogger('core.audio')

class AudioProcessor:
    """Process audio for speech recognition and text-to-speech"""
    
    def __init__(self):
        """Initialize the audio processor"""
        self.language_processor = LanguageProcessor()
        self.media_root = settings.MEDIA_ROOT
        
        # Create media directory if it doesn't exist
        os.makedirs(os.path.join(self.media_root, 'audio'), exist_ok=True)
    
    def process_audio_message(self, audio_content: bytes, filename: str = None) -> Dict[str, Any]:
        """
        Process an audio message
        
        Args:
            audio_content: Audio content as bytes
            filename: Optional filename
            
        Returns:
            Dictionary with processing results
        """
        if not audio_content:
            logger.error("No audio content provided")
            return {
                "success": False,
                "error": "No audio content provided"
            }
        
        try:
            # Generate a filename if not provided
            if not filename:
                filename = f"audio_{uuid.uuid4()}.ogg"
            
            # Save audio to temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1]) as temp_file:
                temp_file.write(audio_content)
                audio_path = temp_file.name
            
            # Process speech to text
            speech_result = self.language_processor.speech_to_text(audio_path)
            
            # Save audio to storage
            storage_path = self._save_to_storage(audio_content, filename)
            
            # Clean up temporary file
            os.unlink(audio_path)
            
            return {
                "success": True,
                "transcription": speech_result.get("text", ""),
                "language": speech_result.get("language", "english"),
                "storage_path": storage_path
            }
            
        except Exception as e:
            logger.error(f"Error processing audio message: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def generate_audio_response(self, text: str, language: str) -> Dict[str, Any]:
        """
        Generate an audio response from text
        
        Args:
            text: Text to convert to speech
            language: Language of the text
            
        Returns:
            Dictionary with generation results
        """
        if not text:
            logger.error("No text provided for audio generation")
            return {
                "success": False,
                "error": "No text provided"
            }
        
        try:
            # Generate speech
            audio_path = self.language_processor.text_to_speech(text, language)
            
            if not audio_path:
                return {
                    "success": False,
                    "error": "Failed to generate audio"
                }
            
            # Read the generated audio file
            with open(audio_path, "rb") as audio_file:
                audio_content = audio_file.read()
            
            # Save to storage
            filename = f"response_{uuid.uuid4()}.mp3"
            storage_path = self._save_to_storage(audio_content, filename)
            
            # Clean up temporary file
            os.unlink(audio_path)
            
            return {
                "success": True,
                "audio_path": storage_path,
                "audio_content": audio_content
            }
            
        except Exception as e:
            logger.error(f"Error generating audio response: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _save_to_storage(self, content: bytes, filename: str) -> str:
        """
        Save content to storage
        
        Args:
            content: Content to save
            filename: Filename to use
            
        Returns:
            Storage path
        """
        # Ensure the filename has proper extension
        base, ext = os.path.splitext(filename)
        if not ext:
            ext = ".ogg"  # Default extension
        
        # Create a storage path
        storage_path = os.path.join('audio', f"{base}{ext}")
        
        # Save to Django's default storage
        path = default_storage.save(storage_path, ContentFile(content))
        
        return path
    
    def enhance_audio_quality(self, audio_content: bytes) -> bytes:
        """
        Enhance audio quality for better processing
        
        Args:
            audio_content: Audio content as bytes
            
        Returns:
            Enhanced audio content
        """
        # This is a placeholder - in a real implementation, you would use audio processing libraries
        # For now, we'll just return the original content
        return audio_content