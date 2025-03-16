# simulator/urls.py

from django.urls import path
from . import views

urlpatterns = [
    # Simulator interface
    path('', views.index, name='simulator_index'),
    
    # API endpoints
    path('api/send/', views.send_message, name='simulator_send_message'),
    path('api/responses/', views.get_responses, name='simulator_get_responses'),
    path('api/upload_audio/', views.upload_audio, name='simulator_upload_audio'),
    path('api/reset/', views.reset_simulator, name='simulator_reset'),
]