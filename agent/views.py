# agent/views.py

import json
import logging
import os
import tempfile
from datetime import timedelta

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.conf import settings

from .models import Customer, Interaction, FollowUp, CampaignTarget
from core.client_factory import get_whatsapp_client
from core.utils import is_simulation_mode
from core.whatsapp import WhatsAppClient
from core.conversation import ConversationEngine
from core.language import LanguageProcessor
from core.audio import AudioProcessor

logger = logging.getLogger('agent.views')

# Initialize components
whatsapp_client = get_whatsapp_client()
language_processor = LanguageProcessor()
audio_processor = AudioProcessor()

# Initialize conversation engines for different languages
conversation_engines = {
    "english": ConversationEngine(language="english"),
    "hindi": ConversationEngine(language="hindi"),
    "kannada": ConversationEngine(language="kannada"),
    "tamil": ConversationEngine(language="tamil"),
    "telugu": ConversationEngine(language="telugu")
}

@csrf_exempt
@require_http_methods(["GET", "POST"])
def webhook(request):
    """Handle WhatsApp webhook"""
    if request.method == "GET":
        # In simulation mode, always verify successfully
        if is_simulation_mode():
            challenge = request.GET.get("hub.challenge", "challenge_accepted")
            return HttpResponse(challenge, content_type="text/plain")
        
        # Handle webhook verification
        verify_token = request.GET.get("hub.verify_token")
        mode = request.GET.get("hub.mode")
        challenge = request.GET.get("hub.challenge")
        
        if mode == "subscribe" and verify_token == settings.WHATSAPP_VERIFY_TOKEN:
            logger.info("Webhook verified successfully")
            return HttpResponse(challenge, content_type="text/plain")
        else:
            logger.warning("Webhook verification failed")
            return HttpResponse("Verification failed", status=403)
    
    elif request.method == "POST":
        # Handle incoming messages
        try:
            body = json.loads(request.body)
            logger.info(f"Received webhook: {json.dumps(body)}")
            
            # Verify this is a message notification
            if "entry" not in body:
                return JsonResponse({"status": "success"})
                
            for entry in body["entry"]:
                if "changes" not in entry:
                    continue
                    
                for change in entry["changes"]:
                    if change["field"] != "messages":
                        continue
                        
                    if "value" not in change:
                        continue
                        
                    value = change["value"]
                    if "messages" not in value:
                        continue
                        
                    for message in value["messages"]:
                        sender = message["from"]
                        message_type = message["type"]
                        message_id = message["id"]
                        timestamp = message.get("timestamp")
                        
                        # Mark the message as read
                        whatsapp_client.mark_message_read(message_id)
                        
                        # Process different message types
                        if message_type == "text":
                            message_content = message["text"]["body"]
                            process_text_message(sender, message_content, message_id, timestamp)
                        elif message_type == "audio":
                            # Get the media ID
                            media_id = message["audio"]["id"]
                            # Download the audio
                            process_audio_message(sender, media_id, message_id, timestamp)
                        else:
                            # Skip other message types for now
                            logger.info(f"Received unsupported message type: {message_type}")
            
            return JsonResponse({"status": "processing"})
            
        except Exception as e:
            logger.error(f"Error processing webhook: {str(e)}")
            return JsonResponse({"status": "error", "message": str(e)})


def process_text_message(phone_number, message_content, message_id, timestamp=None):
    """
    Process an incoming text message
    
    Args:
        phone_number: Sender's phone number
        message_content: Message text
        message_id: WhatsApp message ID
        timestamp: Message timestamp (optional)
    """
    try:
        logger.info(f"Processing text message from {phone_number}: {message_content[:50]}...")
        
        # Get or create customer
        customer = get_or_create_customer(phone_number)
        
        # Detect language
        detected_language = language_processor.detect_language(message_content)
        
        # Update customer's preferred language if needed
        if customer.preferred_language != detected_language:
            customer.preferred_language = detected_language
            customer.save(update_fields=["preferred_language", "updated_at"])
        
        # Record the interaction
        interaction = Interaction.objects.create(
            customer=customer,
            timestamp=timezone.now(),
            direction="inbound",
            message_type="text",
            content=message_content,
            whatsapp_message_id=message_id,
            language=detected_language
        )
        
        # Get conversation history
        conversation_history = get_conversation_history(customer)
        
        # Translate to English if needed
        english_text = message_content
        if detected_language != "english":
            english_text = language_processor.translate_to_english(message_content, detected_language)
        
        # Get customer profile as dictionary
        customer_profile = {
            "id": customer.id,
            "name": customer.name,
            "phone_number": customer.phone_number,
            "preferred_language": customer.preferred_language,
            "property_details": customer.property_details,
            "loan_requirements": customer.loan_requirements,
            "conversation_state": customer.conversation_state,
            "interest_level": customer.interest_level,
            "do_not_contact": customer.do_not_contact
        }
        
        # Get appropriate conversation engine
        engine = conversation_engines.get(detected_language, conversation_engines["english"])
        
        # Generate response
        response = engine.generate_response(english_text, customer_profile, conversation_history)
        
        # Update interaction with analysis
        interaction.detected_intent = response["intent"]
        interaction.conversation_state = response["state"]
        interaction.ai_confidence = response["confidence"]
        interaction.ai_analysis = response["analysis"]
        interaction.save(update_fields=["detected_intent", "conversation_state", "ai_confidence", "ai_analysis"])
        
        # Update customer profile with extracted information
        update_customer_profile(customer, response["extracted_info"], response["intent"], response["state"])
        
        # Translate response if needed
        response_text = response["text"]
        if detected_language != "english":
            response_text = language_processor.translate_from_english(response["text"], detected_language)
        
        # Send text response
        whatsapp_result = whatsapp_client.send_text(phone_number, response_text)

        logger.info(f"whatsapp_result: {whatsapp_result}")
        
        # Record the outbound interaction
        outbound_interaction = Interaction.objects.create(
            customer=customer,
            timestamp=timezone.now(),
            direction="outbound",
            message_type="text",
            content=response_text,
            language=detected_language,
            whatsapp_message_id=whatsapp_result.get("messages", [{}])[0].get("id") if "messages" in whatsapp_result else None,
            detected_intent=response["intent"],
            conversation_state=response["state"],
            ai_confidence=response["confidence"],
            ai_analysis=response["analysis"]
        )
        
        # Generate and send audio response if appropriate
        if response.get("should_generate_audio", False):
            audio_result = audio_processor.generate_audio_response(response_text, detected_language)
            
            if audio_result["success"]:
                # Send audio message
                whatsapp_client.send_audio(phone_number, audio_result["audio_path"])
                
                # Record the audio interaction
                Interaction.objects.create(
                    customer=customer,
                    timestamp=timezone.now(),
                    direction="outbound",
                    message_type="audio",
                    content=f"Audio version of: {response_text[:100]}...",
                    media_url=audio_result["audio_path"],
                    language=detected_language,
                    detected_intent=response["intent"],
                    conversation_state=response["state"]
                )
        
        # Schedule follow-up if needed
        if response.get("follow_up_date"):
            schedule_followup(customer, response["follow_up_date"])
        
        # Update any campaign targets
        update_campaign_targets(customer, "responded")
        
        logger.info(f"Successfully processed message from {phone_number}")
    
    except Exception as e:
        logger.error(f"Error processing text message: {str(e)}")


def process_audio_message(phone_number, media_id, message_id, timestamp=None):
    """
    Process an incoming audio message
    
    Args:
        phone_number: Sender's phone number
        media_id: WhatsApp media ID
        message_id: WhatsApp message ID
        timestamp: Message timestamp (optional)
    """
    try:
        logger.info(f"Processing audio message from {phone_number}")
        
        # Get or create customer
        customer = get_or_create_customer(phone_number)
        
        # Download the audio
        audio_content = whatsapp_client.download_media(media_id)
        
        if not audio_content:
            logger.error(f"Failed to download audio for {phone_number}")
            return
        
        # Save audio to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as temp_file:
            temp_file.write(audio_content)
            audio_file = temp_file.name
        
        # Process audio
        audio_result = audio_processor.process_audio_message(audio_content)
        
        if not audio_result["success"]:
            logger.error(f"Failed to process audio: {audio_result.get('error')}")
            os.unlink(audio_file)
            return
        
        transcribed_text = audio_result["transcription"]
        detected_language = audio_result["language"]
        
        # Update customer's preferred language if needed
        if customer.preferred_language != detected_language:
            customer.preferred_language = detected_language
            customer.save(update_fields=["preferred_language", "updated_at"])
        
        # Record the interaction
        interaction = Interaction.objects.create(
            customer=customer,
            timestamp=timezone.now(),
            direction="inbound",
            message_type="audio",
            content=transcribed_text,
            media_url=audio_result["storage_path"],
            whatsapp_message_id=message_id,
            language=detected_language
        )
        
        # Process the transcribed text like a regular text message
        # Get conversation history
        conversation_history = get_conversation_history(customer)
        
        # Translate to English if needed
        english_text = transcribed_text
        if detected_language != "english":
            english_text = language_processor.translate_to_english(transcribed_text, detected_language)
        
        # Get customer profile as dictionary
        customer_profile = {
            "id": customer.id,
            "name": customer.name,
            "phone_number": customer.phone_number,
            "preferred_language": customer.preferred_language,
            "property_details": customer.property_details,
            "loan_requirements": customer.loan_requirements,
            "conversation_state": customer.conversation_state,
            "interest_level": customer.interest_level,
            "do_not_contact": customer.do_not_contact
        }
        
        # Get appropriate conversation engine
        engine = conversation_engines.get(detected_language, conversation_engines["english"])
        
        # Generate response
        response = engine.generate_response(english_text, customer_profile, conversation_history)
        
        # Update interaction with analysis
        interaction.detected_intent = response["intent"]
        interaction.conversation_state = response["state"]
        interaction.ai_confidence = response["confidence"]
        interaction.ai_analysis = response["analysis"]
        interaction.save(update_fields=["detected_intent", "conversation_state", "ai_confidence", "ai_analysis"])
        
        # Update customer profile with extracted information
        update_customer_profile(customer, response["extracted_info"], response["intent"], response["state"])
        
        # Translate response if needed
        response_text = response["text"]
        if detected_language != "english":
            response_text = language_processor.translate_from_english(response["text"], detected_language)
        
        # Send text response
        whatsapp_result = whatsapp_client.send_text(phone_number, response_text)
        
        # Record the outbound interaction
        outbound_interaction = Interaction.objects.create(
            customer=customer,
            timestamp=timezone.now(),
            direction="outbound",
            message_type="text",
            content=response_text,
            language=detected_language,
            whatsapp_message_id=whatsapp_result.get("messages", [{}])[0].get("id") if "messages" in whatsapp_result else None,
            detected_intent=response["intent"],
            conversation_state=response["state"],
            ai_confidence=response["confidence"],
            ai_analysis=response["analysis"]
        )
        
        # Generate and send audio response
        # For audio messages, we always respond with audio
        audio_result = audio_processor.generate_audio_response(response_text, detected_language)
        
        if audio_result["success"]:
            # Send audio message
            whatsapp_client.send_audio(phone_number, audio_result["audio_path"])
            
            # Record the audio interaction
            Interaction.objects.create(
                customer=customer,
                timestamp=timezone.now(),
                direction="outbound",
                message_type="audio",
                content=f"Audio version of: {response_text[:100]}...",
                media_url=audio_result["audio_path"],
                language=detected_language,
                detected_intent=response["intent"],
                conversation_state=response["state"]
            )
        
        # Schedule follow-up if needed
        if response.get("follow_up_date"):
            schedule_followup(customer, response["follow_up_date"])
        
        # Clean up temporary file
        os.unlink(audio_file)
        
        logger.info(f"Successfully processed audio message from {phone_number}")
    
    except Exception as e:
        logger.error(f"Error processing audio message: {str(e)}")


def get_or_create_customer(phone_number):
    """
    Get or create a customer record
    
    Args:
        phone_number: Customer's phone number
        
    Returns:
        Customer object
    """
    try:
        customer = Customer.objects.get(phone_number=phone_number)
        customer.last_contacted = timezone.now()
        customer.save(update_fields=["last_contacted"])
        return customer
    except Customer.DoesNotExist:
        return Customer.objects.create(
            phone_number=phone_number,
            last_contacted=timezone.now()
        )


def get_conversation_history(customer, limit=20):
    """
    Get conversation history for a customer
    
    Args:
        customer: Customer object
        limit: Maximum number of interactions to retrieve
        
    Returns:
        List of interaction dictionaries
    """
    interactions = Interaction.objects.filter(customer=customer).order_by('timestamp')[:limit]
    
    history = []
    for interaction in interactions:
        history.append({
            "timestamp": interaction.timestamp,
            "direction": interaction.direction,
            "content": interaction.content,
            "message_type": interaction.message_type,
            "language": interaction.language
        })
    
    return history


def update_customer_profile(customer, extracted_info, intent, state):
    """
    Update customer profile with extracted information
    
    Args:
        customer: Customer object
        extracted_info: Dictionary of extracted information
        intent: Detected intent
        state: New conversation state
    """
    # Update property details
    property_details = customer.property_details or {}
    loan_requirements = customer.loan_requirements or {}
    
    # Update fields
    for key, value in extracted_info.items():
        if key in ["property_type", "property_location", "property_value", "ownership_status"]:
            property_details[key] = value
        elif key in ["loan_amount_needed", "loan_purpose", "current_loans", "monthly_income", "urgency"]:
            loan_requirements[key] = value
        elif key == "name" and customer.name is None:
            customer.name = value
        elif key == "concerns":
            # Add concerns to loan requirements
            if "concerns" not in loan_requirements:
                loan_requirements["concerns"] = []
            if isinstance(value, list):
                loan_requirements["concerns"].extend(value)
            else:
                loan_requirements["concerns"].append(value)
    
    # Update customer record
    customer.property_details = property_details
    customer.loan_requirements = loan_requirements
    customer.conversation_state = state
    
    # Update interest level based on intent and state
    if intent == "interested":
        customer.interest_level = min(1.0, customer.interest_level + 0.2)
    elif intent == "needs_more_info":
        customer.interest_level = min(0.8, customer.interest_level + 0.1)
    elif intent == "objection":
        customer.interest_level = max(0.1, customer.interest_level - 0.1)
    elif intent == "not_interested":
        customer.interest_level = max(0.0, customer.interest_level - 0.3)
        
    # Update do_not_contact flag
    if "do_not_contact" in extracted_info and extracted_info["do_not_contact"]:
        customer.do_not_contact = True
    
    # Save the updated customer
    customer.save()


def schedule_followup(customer, time_frame):
    """
    Schedule a follow-up based on time frame
    
    Args:
        customer: Customer object
        time_frame: Time frame string (e.g., "30d", "2w", "3m")
    """
    # Parse time frame (e.g., "30d", "2w", "3m")
    unit = time_frame[-1]
    value = int(time_frame[:-1])
    
    now = timezone.now()
    
    if unit == 'd':
        next_contact = now + timedelta(days=value)
    elif unit == 'w':
        next_contact = now + timedelta(weeks=value)
    elif unit == 'm':
        # Approximate months as 30 days
        next_contact = now + timedelta(days=value*30)
    else:
        # Default to 30 days if unit not recognized
        next_contact = now + timedelta(days=30)
    
    # Update customer's next contact date
    customer.next_contact_date = next_contact
    customer.save(update_fields=["next_contact_date"])
    
    # Create a follow-up record
    FollowUp.objects.create(
        customer=customer,
        scheduled_date=next_contact,
        follow_up_type="general",
        follow_up_reason="Scheduled based on conversation"
    )


def update_campaign_targets(customer, status):
    """
    Update campaign targets for a customer
    
    Args:
        customer: Customer object
        status: New status for campaign targets
    """
    # Update any pending campaign targets
    targets = CampaignTarget.objects.filter(customer=customer, status="sent")
    
    for target in targets:
        target.status = status
        target.response_time = timezone.now()
        target.save(update_fields=["status", "response_time"])
        
        # Update campaign statistics
        campaign = target.campaign
        if status == "responded":
            campaign.total_responses += 1
            campaign.save(update_fields=["total_responses"])


@csrf_exempt
@require_http_methods(["POST"])
def send_campaign(request):
    """
    API endpoint to start a campaign
    
    Request format:
    {
        "campaign_id": 123
    }
    """
    try:
        data = json.loads(request.body)
        
        if "campaign_id" not in data:
            return JsonResponse({"status": "error", "message": "Missing campaign_id"})
            
        from .tasks import process_campaign
        process_campaign.delay(data["campaign_id"])
        
        return JsonResponse({
            "status": "started",
            "message": "Campaign processing started"
        })
    except Exception as e:
        logger.error(f"Error starting campaign: {str(e)}")
        return JsonResponse({"status": "error", "message": str(e)})


@csrf_exempt
@require_http_methods(["POST"])
def process_followups(request):
    """API endpoint to process scheduled follow-ups"""
    try:
        from .tasks import process_scheduled_followups
        task = process_scheduled_followups.delay()
        
        return JsonResponse({
            "status": "started",
            "task_id": task.id,
            "message": "Follow-up processing started"
        })
    except Exception as e:
        logger.error(f"Error starting follow-up processing: {str(e)}")
        return JsonResponse({"status": "error", "message": str(e)})