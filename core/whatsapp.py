# core/whatsapp.py

import logging
import requests
import json
import time
import os
import tempfile
from urllib.parse import urljoin
import backoff

from django.conf import settings
from django.utils import timezone
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

logger = logging.getLogger('core.whatsapp')

class WhatsAppClient:
    """Client for interacting with WhatsApp Business API"""
    
    def __init__(self, api_key=None, phone_number_id=None, business_account_id=None, version=None):
        """
        Initialize WhatsApp Business API client
        
        Args:
            api_key: WhatsApp Business API key (defaults to settings.WHATSAPP_API_KEY)
            phone_number_id: WhatsApp Business phone number ID (defaults to settings.WHATSAPP_PHONE_NUMBER_ID)
            business_account_id: WhatsApp Business account ID (defaults to settings.WHATSAPP_BUSINESS_ACCOUNT_ID)
            version: API version to use (defaults to settings.WHATSAPP_API_VERSION)
        """
        self.api_key = api_key or settings.WHATSAPP_API_KEY
        self.phone_number_id = phone_number_id or settings.WHATSAPP_PHONE_NUMBER_ID
        self.business_account_id = business_account_id or settings.WHATSAPP_BUSINESS_ACCOUNT_ID
        self.version = version or settings.WHATSAPP_API_VERSION
        self.base_url = f"https://graph.facebook.com/{self.version}/{self.phone_number_id}"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # Track message counts for rate limiting
        self.message_counts = {}
        self.rate_limit = 1000  # Default daily limit per recipient
        
        # Track conversation windows
        self.conversation_windows = {}
        self.window_duration = 24 * 60 * 60  # 24 hours in seconds
    
    @backoff.on_exception(backoff.expo, 
                         requests.exceptions.RequestException,
                         max_tries=5)
    def send_text(self, recipient_phone, text):
        """
        Send a text message to a recipient
        
        Args:
            recipient_phone: Recipient's phone number in international format (e.g., "918123456789")
            text: Message text
            
        Returns:
            API response
        """
        # Check rate limits
        if not self._check_rate_limit(recipient_phone):
            logger.warning(f"Rate limit exceeded for {recipient_phone}")
            return {"error": "Rate limit exceeded"}
        
        # Check conversation window
        if not self._check_conversation_window(recipient_phone):
            # Need to use a template instead
            logger.info(f"Conversation window expired for {recipient_phone}, using template instead")
            return self.send_template(
                recipient_phone,
                "loan_follow_up",  # Default template name
                {"default_text": text}  # Use the text as a parameter
            )
        
        url = f"{self.base_url}/messages"
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient_phone,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": text
            }
        }
        
        try:
            response = requests.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            result = response.json()
            
            # Update rate limit counter
            self._update_message_count(recipient_phone)
            # Update conversation window
            self._update_conversation_window(recipient_phone)
            
            logger.info(f"Successfully sent text message to {recipient_phone}")
            return result
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send text message to {recipient_phone}: {str(e)}")
            
            # Try to get response details if available
            try:
                error_details = e.response.json()
                logger.error(f"Error details: {json.dumps(error_details)}")
            except:
                pass
                
            raise
    
    @backoff.on_exception(backoff.expo, 
                         requests.exceptions.RequestException,
                         max_tries=5)
    def send_audio(self, recipient_phone, audio_path):
        """
        Send an audio message to a recipient
        
        Args:
            recipient_phone: Recipient's phone number in international format
            audio_path: Path to audio file
            
        Returns:
            API response
        """
        # Check rate limits
        if not self._check_rate_limit(recipient_phone):
            logger.warning(f"Rate limit exceeded for {recipient_phone}")
            return {"error": "Rate limit exceeded"}
        
        # Check conversation window
        if not self._check_conversation_window(recipient_phone):
            logger.warning(f"Conversation window expired for {recipient_phone}, cannot send audio")
            return {"error": "Conversation window expired"}
        
        # First, upload the media
        media_id = self._upload_media(audio_path, "audio/mpeg")
        
        if not media_id:
            logger.error(f"Failed to upload audio for {recipient_phone}")
            return {"error": "Failed to upload audio"}
        
        # Now send the audio message
        url = f"{self.base_url}/messages"
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient_phone,
            "type": "audio",
            "audio": {
                "id": media_id
            }
        }
        
        try:
            response = requests.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            result = response.json()
            
            # Update rate limit counter
            self._update_message_count(recipient_phone)
            # Update conversation window
            self._update_conversation_window(recipient_phone)
            
            logger.info(f"Successfully sent audio message to {recipient_phone}")
            return result
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send audio message to {recipient_phone}: {str(e)}")
            raise
    
    @backoff.on_exception(backoff.expo, 
                         requests.exceptions.RequestException,
                         max_tries=5)
    def send_template(self, recipient_phone, template_name, template_params):
        """
        Send a template message to a recipient
        
        Args:
            recipient_phone: Recipient's phone number in international format
            template_name: Name of the approved template
            template_params: Template parameters
            
        Returns:
            API response
        """
        # Templates can be sent even if conversation window has expired
        # Check rate limits only
        if not self._check_rate_limit(recipient_phone):
            logger.warning(f"Rate limit exceeded for {recipient_phone}")
            return {"error": "Rate limit exceeded"}
        
        url = f"{self.base_url}/messages"
        
        # Format the components based on template parameters
        components = []
        
        # Add parameters
        if template_params:
            parameter_list = []
            for key, value in template_params.items():
                parameter_list.append({
                    "type": "text",
                    "text": value
                })
            
            if parameter_list:
                components.append({
                    "type": "body",
                    "parameters": parameter_list
                })
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient_phone,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {
                    "code": "en"  # Default to English
                },
                "components": components
            }
        }
        
        try:
            response = requests.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            result = response.json()
            
            # Update rate limit counter
            self._update_message_count(recipient_phone)
            # If sending a template, this initiates a new conversation window
            self._update_conversation_window(recipient_phone)
            
            logger.info(f"Successfully sent template message to {recipient_phone}")
            return result
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send template message to {recipient_phone}: {str(e)}")
            raise
    
    def download_media(self, media_id):
        """
        Download media content
        
        Args:
            media_id: ID of the media to download
            
        Returns:
            Media content as bytes
        """
        # First, get the media URL
        url = f"https://graph.facebook.com/{self.version}/{media_id}"
        
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            media_info = response.json()
            
            if "url" not in media_info:
                logger.error(f"No URL in media info for ID {media_id}")
                return None
            
            media_url = media_info["url"]
            
            # Now download the actual media
            media_response = requests.get(media_url, headers=self.headers)
            media_response.raise_for_status()
            
            return media_response.content
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to download media ID {media_id}: {str(e)}")
            return None
    
    def _upload_media(self, file_path, mime_type):
        """
        Upload media to WhatsApp servers
        
        Args:
            file_path: Path to the file
            mime_type: MIME type of the file
            
        Returns:
            Media ID if successful, None otherwise
        """
        url = f"https://graph.facebook.com/{self.version}/{self.phone_number_id}/media"
        
        try:
            with open(file_path, "rb") as file:
                files = {
                    "file": (os.path.basename(file_path), file, mime_type)
                }
                
                response = requests.post(
                    url, 
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    data={"messaging_product": "whatsapp"},
                    files=files
                )
                
                response.raise_for_status()
                result = response.json()
                
                return result.get("id")
        except Exception as e:
            logger.error(f"Exception while uploading media: {str(e)}")
            return None
    
    def _check_rate_limit(self, recipient_phone):
        """
        Check if rate limit has been exceeded for this recipient
        
        Args:
            recipient_phone: Recipient's phone number
            
        Returns:
            True if under limit, False if exceeded
        """
        today = time.strftime("%Y-%m-%d")
        key = f"{recipient_phone}:{today}"
        
        count = self.message_counts.get(key, 0)
        return count < self.rate_limit
    
    def _update_message_count(self, recipient_phone):
        """
        Update message count for rate limiting
        
        Args:
            recipient_phone: Recipient's phone number
        """
        today = time.strftime("%Y-%m-%d")
        key = f"{recipient_phone}:{today}"
        
        self.message_counts[key] = self.message_counts.get(key, 0) + 1
    
    def _check_conversation_window(self, recipient_phone):
        """
        Check if there is an active conversation window with this recipient
        
        Args:
            recipient_phone: Recipient's phone number
            
        Returns:
            True if window is active, False otherwise
        """
        now = time.time()
        window_start = self.conversation_windows.get(recipient_phone, 0)
        
        return (now - window_start) < self.window_duration
    
    def _update_conversation_window(self, recipient_phone):
        """
        Update the conversation window for this recipient
        
        Args:
            recipient_phone: Recipient's phone number
        """
        self.conversation_windows[recipient_phone] = time.time()
    
    def mark_message_read(self, message_id):
        """
        Mark a message as read
        
        Args:
            message_id: ID of the message to mark
            
        Returns:
            API response
        """
        url = f"{self.base_url}/messages"
        
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id
        }
        
        try:
            response = requests.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            result = response.json()
            
            logger.info(f"Successfully marked message {message_id} as read")
            return result
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to mark message {message_id} as read: {str(e)}")
            return {"error": str(e)}
    
    def save_media_to_storage(self, media_id, filename=None):
        """
        Download media and save to storage
        
        Args:
            media_id: ID of the media to download
            filename: Optional filename to use
            
        Returns:
            Storage path if successful, None otherwise
        """
        media_content = self.download_media(media_id)
        
        if not media_content:
            return None
            
        if not filename:
            # Generate a unique filename
            filename = f"whatsapp/media/{media_id}_{int(time.time())}"
            
        # Save to Django's default storage
        storage_path = default_storage.save(filename, ContentFile(media_content))
        
        return storage_path