# simulator/simulator.py

import time
import logging
import tempfile
import os
import uuid
from typing import Dict, Any, List
import pickle

from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

logger = logging.getLogger('simulator.whatsapp')

class WhatsAppSimulator:
    """Simulates WhatsApp Business API for testing"""
    # Singleton instance
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(WhatsAppSimulator, cls).__new__(cls)
            cls._instance.message_log = []
            cls._instance.media_store = {}
            cls._instance.conversation_windows = {}
            cls._instance.templates = {}
        return cls._instance
    
    def __init__(self):
        """Initialize the simulator"""
        # self.message_log = []
        # self.media_store = {}
        # self.conversation_windows = {}
        # self.templates = {}
        pass
    
    def send_text(self, recipient_phone: str, text: str) -> Dict[str, Any]:
        """
        Simulate sending a text message
        
        Args:
            recipient_phone: Recipient's phone number
            text: Message text
            
        Returns:
            API response
        """
        logger.info("Calling send_text")
        message_id = f"sim_{uuid.uuid4()}"
        
        self.message_log.append({
            "type": "text",
            "recipient": recipient_phone,
            "content": text,
            "timestamp": time.time(),
            "message_id": message_id
        })
        
        logger.info(f"[SIMULATOR] Text message sent to {recipient_phone}: {text[:50]}...")

        return {
            "messaging_product": "whatsapp",
            "contacts": [{"input": recipient_phone, "wa_id": recipient_phone}],
            "messages": [{"id": message_id}]
        }
    
    def send_audio(self, recipient_phone: str, audio_path: str) -> Dict[str, Any]:
        """
        Simulate sending an audio message
        
        Args:
            recipient_phone: Recipient's phone number
            audio_path: Path to audio file
            
        Returns:
            API response
        """
        message_id = f"sim_{uuid.uuid4()}"
        
        self.message_log.append({
            "type": "audio",
            "recipient": recipient_phone,
            "content": f"Audio: {audio_path}",
            "timestamp": time.time(),
            "message_id": message_id
        })
        
        logger.info(f"[SIMULATOR] Audio message sent to {recipient_phone}: {audio_path}")
        return {
            "messaging_product": "whatsapp",
            "contacts": [{"input": recipient_phone, "wa_id": recipient_phone}],
            "messages": [{"id": message_id}]
        }
    
    def send_template(self, recipient_phone: str, template_name: str, template_params: Dict[str, str]) -> Dict[str, Any]:
        """
        Simulate sending a template message
        
        Args:
            recipient_phone: Recipient's phone number
            template_name: Name of the template
            template_params: Template parameters
            
        Returns:
            API response
        """
        message_id = f"sim_{uuid.uuid4()}"
        
        self.message_log.append({
            "type": "template",
            "recipient": recipient_phone,
            "template_name": template_name,
            "params": template_params,
            "timestamp": time.time(),
            "message_id": message_id
        })
        
        logger.info(f"[SIMULATOR] Template '{template_name}' sent to {recipient_phone}")
        return {
            "messaging_product": "whatsapp",
            "contacts": [{"input": recipient_phone, "wa_id": recipient_phone}],
            "messages": [{"id": message_id}]
        }
    
    def simulate_incoming_message(self, phone_number: str, message_content: str, message_type: str = "text") -> Dict[str, Any]:
        """
        Simulate an incoming message from a customer
        
        Args:
            phone_number: Sender's phone number
            message_content: Message content
            message_type: Message type ("text" or "audio")
            
        Returns:
            Webhook data structure
        """
        timestamp = int(time.time())
        message_id = f"sim_in_{uuid.uuid4()}"
        
        message = {
            "from": phone_number,
            "id": message_id,
            "timestamp": timestamp,
            "type": message_type
        }
        
        if message_type == "text":
            message["text"] = {"body": message_content}
        elif message_type == "audio":
            # Save audio to temp file if it's actual audio data
            if isinstance(message_content, bytes):
                with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as temp_file:
                    temp_file.write(message_content)
                    audio_file = temp_file.name
                    
                media_id = f"sim_media_{uuid.uuid4()}"
                message["audio"] = {"id": media_id}
                self.media_store[media_id] = audio_file
            else:
                # If it's just test data (a string)
                media_id = f"sim_media_{uuid.uuid4()}"
                message["audio"] = {"id": media_id}
                
                # Store the text as media content
                # In a real scenario, this would be used for speech-to-text testing
                self.media_store[media_id] = message_content
        
        # Return webhook-like data structure
        webhook_data = {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "12345",
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "display_phone_number": "1234567890",
                            "phone_number_id": "1234567890"
                        },
                        "contacts": [
                            {
                                "profile": {
                                    "name": "Test User"
                                },
                                "wa_id": phone_number
                            }
                        ],
                        "messages": [message]
                    },
                    "field": "messages"
                }]
            }]
        }
        
        logger.info(f"[SIMULATOR] Incoming {message_type} message from {phone_number}")
        return webhook_data
    
    def download_media(self, media_id: str) -> bytes:
        """
        Simulate downloading media content
        
        Args:
            media_id: ID of the media to download
            
        Returns:
            Media content as bytes
        """
        if media_id in self.media_store:
            content = self.media_store[media_id]
            
            # If it's a file path, read the file
            if isinstance(content, str):
                if os.path.exists(content):
                    with open(content, "rb") as f:
                        return f.read()
                else:
                    # It's a text string for speech-to-text simulation
                    # Return some dummy audio data
                    return b"DUMMY_AUDIO_DATA"
            
            # If it's already bytes
            if isinstance(content, bytes):
                return content
            
            # Default
            return b"DUMMY_AUDIO_DATA"
        
        logger.error(f"[SIMULATOR] Media ID {media_id} not found")
        return None
    
    def mark_message_read(self, message_id: str) -> Dict[str, Any]:
        """
        Simulate marking a message as read
        
        Args:
            message_id: ID of the message to mark
            
        Returns:
            API response
        """
        logger.info(f"[SIMULATOR] Marked message {message_id} as read")
        return {"success": True}
    
    def get_message_history(self, phone_number: str = None) -> List[Dict[str, Any]]:
        """
        Get message history for testing and verification
        
        Args:
            phone_number: Filter by phone number
            
        Returns:
            List of message dictionaries
        """
        if phone_number:
            return [msg for msg in self.message_log if msg["recipient"] == phone_number]
        return self.message_log
    
    def reset(self):
        """Reset the simulator state"""
        self.message_log = []
        self.media_store = {}
        self.conversation_windows = {}
        
        # Clean up any temporary files
        for media_id, content in self.media_store.items():
            if isinstance(content, str) and os.path.exists(content):
                try:
                    os.unlink(content)
                except:
                    pass
    
    def save_state(self, filename='simulator_state.pkl'):
        """Save the simulator state to disk"""
        try:
            with open(filename, 'wb') as f:
                pickle.dump({
                    'message_log': self.message_log,
                    'conversation_windows': self.conversation_windows,
                    'templates': self.templates
                }, f)
            return True
        except Exception as e:
            logger.error(f"Failed to save simulator state: {str(e)}")
            return False
    
    def load_state(self, filename='simulator_state.pkl'):
        """Load the simulator state from disk"""
        try:
            if os.path.exists(filename):
                with open(filename, 'rb') as f:
                    state = pickle.load(f)
                    self.message_log = state.get('message_log', [])
                    self.conversation_windows = state.get('conversation_windows', {})
                    self.templates = state.get('templates', {})
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to load simulator state: {str(e)}")
            return False