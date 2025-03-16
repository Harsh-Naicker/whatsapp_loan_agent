# simulator/views.py

import json
import logging
import tempfile
from typing import Dict, Any

from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.files.base import ContentFile

from .simulator import WhatsAppSimulator

logger = logging.getLogger('simulator.views')

# Create a global simulator instance
whatsapp_simulator = WhatsAppSimulator()

def index(request):
    """Render the simulator interface"""
    return render(request, 'simulator/index.html')

@csrf_exempt
@require_http_methods(["POST"])
def send_message(request):
    """
    Handle sending a message to the AI agent
    
    Request format:
    {
        "phone": "911234567890",
        "message": "Hello, I need a loan",
        "type": "text"  # or "audio"
    }
    """
    try:
        data = json.loads(request.body)
        phone = data.get('phone', '911234567890')
        message = data.get('message', '')
        message_type = data.get('type', 'text')
        
        # Generate webhook data
        webhook_data = whatsapp_simulator.simulate_incoming_message(
            phone, message, message_type
        )
        
        # Send to Django webhook handler
        from agent.views import webhook as webhook_handler
        
        # Create a mock request object
        class MockRequest:
            def __init__(self):
                self.body = json.dumps(webhook_data).encode('utf-8')
                self.method = "POST"
        
        # Process through webhook handler
        response = webhook_handler(MockRequest())
        
        return JsonResponse({'status': 'processing', 'webhook_status': response.status_code})
        
    except Exception as e:
        logger.error(f"Error sending message: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)})

@require_http_methods(["GET"])
def get_responses(request):
    """
    Get recent responses from the AI agent
    
    Query parameters:
    - phone: Filter by phone number
    - since: Only get messages after this timestamp
    """
    try:
        phone = request.GET.get('phone')
        since = float(request.GET.get('since', 0))
        
        # Get message history from simulator
        messages = whatsapp_simulator.get_message_history(phone)
        
        # Filter by timestamp if provided
        if since > 0:
            messages = [msg for msg in messages if msg['timestamp'] > since]
        
        # Format responses
        responses = []
        for msg in messages:
            responses.append({
                'type': msg['type'],
                'content': msg['content'] if msg['type'] == 'text' else '[MEDIA]',
                'timestamp': msg['timestamp'],
                'template_name': msg.get('template_name'),
                'params': msg.get('params')
            })
        
        return JsonResponse(responses, safe=False)
        
    except Exception as e:
        logger.error(f"Error getting responses: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)})

@csrf_exempt
@require_http_methods(["POST"])
def upload_audio(request):
    """Handle uploading audio for simulation"""
    try:
        if 'audio' not in request.FILES:
            return JsonResponse({'status': 'error', 'message': 'No audio file provided'})
        
        audio_file = request.FILES['audio']
        phone = request.POST.get('phone', '911234567890')
        
        # Save the audio to a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.ogg') as temp_file:
            for chunk in audio_file.chunks():
                temp_file.write(chunk)
            audio_path = temp_file.name
        
        # Read the audio data
        with open(audio_path, 'rb') as f:
            audio_data = f.read()
        
        # Generate webhook data
        webhook_data = whatsapp_simulator.simulate_incoming_message(
            phone, audio_data, "audio"
        )
        
        # Send to Django webhook handler
        from agent.views import webhook as webhook_handler
        
        # Create a mock request object
        class MockRequest:
            def __init__(self):
                self.body = json.dumps(webhook_data).encode('utf-8')
                self.method = "POST"
        
        # Process through webhook handler
        response = webhook_handler(MockRequest())
        
        return JsonResponse({'status': 'processing', 'webhook_status': response.status_code})
        
    except Exception as e:
        logger.error(f"Error uploading audio: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)})

@csrf_exempt
@require_http_methods(["POST"])
def reset_simulator(request):
    """Reset the simulator state"""
    try:
        whatsapp_simulator.reset()
        return JsonResponse({'status': 'success', 'message': 'Simulator reset successfully'})
    except Exception as e:
        logger.error(f"Error resetting simulator: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)})