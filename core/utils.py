# Create a new file at core/utils.py
import os
from django.conf import settings

def is_simulation_mode():
    """Detect if we're running in simulation mode"""
    # Check the environment variable first
    if os.environ.get('USE_WHATSAPP_SIMULATOR', '').lower() in ('true', '1', 'yes'):
        return True
    
    # Check the Django setting
    return getattr(settings, 'USE_WHATSAPP_SIMULATOR', False)