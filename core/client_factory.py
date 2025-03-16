# Create a new file at core/client_factory.py
from django.conf import settings
from .utils import is_simulation_mode
from .whatsapp import WhatsAppClient
from simulator.simulator import WhatsAppSimulator

def get_whatsapp_client():
    """Factory to get the appropriate WhatsApp client"""
    if is_simulation_mode():
        return WhatsAppSimulator()
    else:
        return WhatsAppClient(
            api_key=settings.WHATSAPP_API_KEY,
            phone_number_id=settings.WHATSAPP_PHONE_NUMBER_ID,
            business_account_id=settings.WHATSAPP_BUSINESS_ACCOUNT_ID,
            version=getattr(settings, 'WHATSAPP_API_VERSION', 'v17.0')
        )