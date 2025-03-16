# core/language.py

import logging
import tempfile
from typing import Dict, Any, Optional
import os

from django.conf import settings
import requests
import openai

logger = logging.getLogger('core.language')

class LanguageProcessor:
    """Module for language detection, translation, and processing"""
    
    def __init__(self):
        """Initialize the language processor"""
        self.supported_languages = {
            "english": "en",
            "hindi": "hi",
            "kannada": "kn",
            "tamil": "ta",
            "telugu": "te"
        }
        
        # Inverse mapping from codes to language names
        self.language_codes = {code: name for name, code in self.supported_languages.items()}
        
        # Initialize OpenAI client
        self.openai_client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.DEFAULT_AI_MODEL
    
    def detect_language(self, text: str) -> str:
        """
        Detect the language of the input text
        
        Args:
            text: Text to detect language for
            
        Returns:
            Language name (e.g., "english", "hindi")
        """
        if not text or len(text.strip()) < 5:
            return "english"  # Default to English for very short or empty text
        
        try:
            # Use OpenAI for language detection
            prompt = f"Identify the language of this text. Respond with only the language name, e.g., 'english', 'hindi', 'kannada', 'tamil', or 'telugu'.\n\nText: {text}\n\nLanguage:"
            
            response = self.openai_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You identify languages."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=10
            )
            
            detected_language = response.choices[0].message.content.strip().lower()
            
            # Normalize language name
            if detected_language in self.supported_languages:
                return detected_language
            
            # Try to match partial language names
            for lang in self.supported_languages:
                if lang in detected_language:
                    return lang
            
            # Check for language codes
            for code, lang in self.language_codes.items():
                if code in detected_language:
                    return lang
            
            logger.info(f"Detected unsupported language: {detected_language}, defaulting to English")
            return "english"
        
        except Exception as e:
            logger.error(f"Error detecting language: {str(e)}")
            return "english"  # Default to English on error
    
    def translate_to_english(self, text: str, source_language: str = None) -> str:
        """
        Translate text from source language to English
        
        Args:
            text: Text to translate
            source_language: Source language (if known)
            
        Returns:
            Translated text
        """
        if not text:
            return text
            
        if source_language == "english" or not source_language:
            # Detect language if not provided
            if not source_language:
                source_language = self.detect_language(text)
                
            # Skip translation if already English
            if source_language == "english":
                return text
        
        try:
            # Use OpenAI for translation
            prompt = f"Translate the following {source_language} text to English. Preserve the meaning and tone.\n\nText: {text}\n\nEnglish translation:"
            
            response = self.openai_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a professional translator."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=len(text) * 2  # Allow for expansion during translation
            )
            
            translated_text = response.choices[0].message.content.strip()
            
            logger.info(f"Translated {len(text)} chars from {source_language} to English")
            return translated_text
            
        except Exception as e:
            logger.error(f"Error translating to English: {str(e)}")
            return text  # Return original text on error
    
    def translate_from_english(self, text: str, target_language: str) -> str:
        """
        Translate text from English to target language
        
        Args:
            text: Text in English
            target_language: Target language to translate to
            
        Returns:
            Translated text
        """
        if not text or target_language == "english":
            return text
            
        if target_language not in self.supported_languages:
            logger.warning(f"Unsupported target language: {target_language}, defaulting to English")
            return text
        
        try:
            # Use OpenAI for translation
            prompt = f"Translate the following English text to {target_language}. Preserve the meaning and tone.\n\nText: {text}\n\n{target_language.capitalize()} translation:"
            
            response = self.openai_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a professional translator."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=len(text) * 2  # Allow for expansion during translation
            )
            
            translated_text = response.choices[0].message.content.strip()
            
            logger.info(f"Translated {len(text)} chars from English to {target_language}")
            return translated_text
            
        except Exception as e:
            logger.error(f"Error translating from English: {str(e)}")
            return text  # Return original text on error
    
    def speech_to_text(self, audio_file: str) -> Dict[str, Any]:
        """
        Convert speech audio to text and detect language
        
        Args:
            audio_file: Path to the audio file
            
        Returns:
            Dictionary with transcribed text and detected language
        """
        try:
            # Use OpenAI Whisper API for speech-to-text
            with open(audio_file, "rb") as audio:
                response = self.openai_client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio,
                    response_format="verbose_json"
                )
            
            # Extract text and language
            transcribed_text = response.text
            language_code = response.language
            
            # Map language code to our language names
            detected_language = self.language_codes.get(language_code, "english")
            
            logger.info(f"Transcribed audio to text, detected language: {detected_language}")
            
            return {
                "text": transcribed_text,
                "language": detected_language
            }
            
        except Exception as e:
            logger.error(f"Error converting speech to text: {str(e)}")
            return {
                "text": "",
                "language": "english"
            }
    
    def text_to_speech(self, text: str, language: str) -> str:
        """
        Convert text to speech in specified language
        
        Args:
            text: Text to convert to speech
            language: Language of the text
            
        Returns:
            Path to the generated audio file
        """
        if not text:
            return None
            
        # Get language code
        language_code = self.supported_languages.get(language, "en")
        
        try:
            # Use OpenAI TTS API for text-to-speech
            response = self.openai_client.audio.speech.create(
                model="tts-1",
                voice="alloy",  # Available voices: alloy, echo, fable, onyx, nova, shimmer
                input=text
            )
            
            # Save the audio to a temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_file:
                temp_file.write(response.content)
                audio_path = temp_file.name
            
            logger.info(f"Generated speech audio for {len(text)} chars in {language}")
            return audio_path
            
        except Exception as e:
            logger.error(f"Error converting text to speech: {str(e)}")
            return None