# agent/urls.py

from django.urls import path
from . import views

urlpatterns = [
    # WhatsApp webhook
    path('webhook/', views.webhook, name='whatsapp_webhook'),
    
    # Campaign management
    path('api/campaign/send/', views.send_campaign, name='send_campaign'),
    
    # Follow-up processing
    path('api/followups/process/', views.process_followups, name='process_followups'),
]