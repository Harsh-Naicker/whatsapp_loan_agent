# agent/tasks.py

import logging
import time
from datetime import timedelta

from django.utils import timezone
from django.db.models import Q

from celery import shared_task

from .models import Customer, Interaction, FollowUp, Campaign, CampaignTarget, Template
from core.client_factory import get_whatsapp_client
from core.conversation import ConversationEngine
from core.language import LanguageProcessor
from core.audio import AudioProcessor

logger = logging.getLogger('agent.tasks')

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

@shared_task
def process_scheduled_followups():
    """Process all follow-ups scheduled for today"""
    logger.info("Starting scheduled follow-up processing")
    
    # Find all pending follow-ups that are due
    now = timezone.now()
    followups = FollowUp.objects.filter(
        status="pending",
        scheduled_date__lte=now
    ).select_related('customer')
    
    logger.info(f"Found {followups.count()} follow-ups to process")
    
    for followup in followups:
        try:
            # Skip if customer has do_not_contact flag
            if followup.customer.do_not_contact:
                followup.status = "cancelled"
                followup.result_notes = "Customer has do_not_contact flag"
                followup.save(update_fields=["status", "result_notes"])
                continue
            
            # Get customer's preferred language
            language = followup.customer.preferred_language or "english"
            
            # Get appropriate conversation engine
            engine = conversation_engines.get(language, conversation_engines["english"])
            
            # Prepare follow-up context
            followup_context = {
                "customer_name": followup.customer.name or "there",
                "last_state": followup.customer.conversation_state,
                "follow_up_reason": followup.follow_up_reason,
                "days_since_contact": (now - followup.customer.last_contacted).days,
                "property_details": followup.customer.property_details,
                "loan_requirements": followup.customer.loan_requirements
            }
            
            # Generate follow-up message
            response = engine.generate_followup(followup_context, language)
            
            # Send the message
            result = whatsapp_client.send_text(followup.customer.phone_number, response["text"])
            
            # If message was sent successfully
            if "error" not in result:
                # Record the interaction
                Interaction.objects.create(
                    customer=followup.customer,
                    timestamp=now,
                    direction="outbound",
                    message_type="text",
                    content=response["text"],
                    language=language,
                    whatsapp_message_id=result.get("messages", [{}])[0].get("id") if "messages" in result else None,
                    conversation_state=response.get("new_state", followup.customer.conversation_state),
                    detected_intent="follow_up"
                )
                
                # If audio message would be more effective, send that too
                if response.get("should_generate_audio", False):
                    audio_result = audio_processor.generate_audio_response(response["text"], language)
                    
                    if audio_result["success"]:
                        # Send audio message
                        whatsapp_client.send_audio(followup.customer.phone_number, audio_result["audio_path"])
                        
                        # Record the audio interaction
                        Interaction.objects.create(
                            customer=followup.customer,
                            timestamp=timezone.now(),
                            direction="outbound",
                            message_type="audio",
                            content=f"Audio version of: {response['text'][:100]}...",
                            media_url=audio_result["audio_path"],
                            language=language,
                            conversation_state=response.get("new_state", followup.customer.conversation_state),
                            detected_intent="follow_up"
                        )
                
                # Update follow-up status
                followup.status = "sent"
                followup.result_notes = "Follow-up message sent successfully"
                
                # Update customer record
                followup.customer.last_contacted = now
                followup.customer.conversation_state = response.get("new_state", followup.customer.conversation_state)
                followup.customer.save(update_fields=["last_contacted", "conversation_state"])
            else:
                # Record failure
                followup.status = "failed"
                followup.result_notes = f"Failed to send follow-up: {result.get('error', 'Unknown error')}"
            
            # Save the updated follow-up
            followup.save(update_fields=["status", "result_notes"])
            
            # Delay between follow-ups to respect rate limits
            time.sleep(1)
            
        except Exception as e:
            logger.error(f"Error processing follow-up {followup.id}: {str(e)}")
            followup.status = "failed"
            followup.result_notes = f"Error: {str(e)}"
            followup.save(update_fields=["status", "result_notes"])
    
    return {"processed": followups.count()}


@shared_task
def process_campaign(campaign_id):
    """
    Process a campaign and send messages to targets
    
    Args:
        campaign_id: ID of the campaign to process
    """
    logger.info(f"Starting campaign processing for campaign {campaign_id}")
    
    try:
        # Get the campaign
        campaign = Campaign.objects.get(pk=campaign_id)
        
        # Verify campaign status
        if campaign.status not in ["scheduled", "running"]:
            logger.error(f"Campaign {campaign_id} is not scheduled or running")
            return {"error": "Campaign is not scheduled or running"}
        
        # Update campaign status
        campaign.status = "running"
        campaign.save(update_fields=["status"])
        
        # Get the campaign template
        template = campaign.template
        
        # Get pending targets
        targets = CampaignTarget.objects.filter(
            campaign=campaign,
            status="pending"
        ).select_related('customer')
        
        logger.info(f"Found {targets.count()} pending targets for campaign {campaign_id}")
        
        # Process each target
        for target in targets:
            try:
                # Skip if customer has do_not_contact flag
                if target.customer.do_not_contact:
                    target.status = "excluded"
                    target.error_message = "Customer has do_not_contact flag"
                    target.save(update_fields=["status", "error_message"])
                    continue
                
                # Get customer's preferred language
                language = target.customer.preferred_language or "english"
                language_code = language[:2] if language != "english" else "en"
                
                # Prepare template parameters
                template_params = {
                    "name": target.customer.name or "there",
                    "property_type": target.customer.property_details.get("property_type", "property") if target.customer.property_details else "property"
                }
                
                # Send the template message
                result = whatsapp_client.send_template(
                    target.customer.phone_number,
                    template.name,
                    template_params
                )
                
                # Update target status
                if "error" not in result:
                    message_id = result.get("messages", [{}])[0].get("id") if "messages" in result else None
                    
                    target.status = "sent"
                    target.message_id = message_id
                    target.sent_time = timezone.now()
                    target.delivery_status = "sent"
                    
                    # Record the interaction
                    Interaction.objects.create(
                        customer=target.customer,
                        timestamp=timezone.now(),
                        direction="outbound",
                        message_type="template",
                        content=f"Campaign: {campaign.name}, Template: {template.name}",
                        whatsapp_message_id=message_id,
                        language=language,
                        detected_intent="campaign"
                    )
                    
                    # Update campaign statistics
                    campaign.total_sent += 1
                else:
                    target.status = "failed"
                    target.error_message = result.get("error", "Unknown error")
                
                # Save the updated target
                target.save()
                
                # Update customer record
                target.customer.last_contacted = timezone.now()
                target.customer.save(update_fields=["last_contacted"])
                
                # Respect rate limits
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"Error processing target {target.id}: {str(e)}")
                target.status = "failed"
                target.error_message = str(e)
                target.save(update_fields=["status", "error_message"])
        
        # Check if all targets have been processed
        pending_count = CampaignTarget.objects.filter(
            campaign=campaign,
            status="pending"
        ).count()
        
        if pending_count == 0:
            campaign.status = "completed"
        
        # Save campaign statistics
        campaign.save(update_fields=["status", "total_sent"])
        
        return {
            "campaign_id": campaign_id,
            "processed": targets.count(),
            "sent": campaign.total_sent
        }
        
    except Campaign.DoesNotExist:
        logger.error(f"Campaign {campaign_id} not found")
        return {"error": "Campaign not found"}
    except Exception as e:
        logger.error(f"Error processing campaign {campaign_id}: {str(e)}")
        return {"error": str(e)}


@shared_task
def cleanup_old_data():
    """Cleanup old data according to retention policies"""
    logger.info("Starting data cleanup task")
    
    # Retention periods (in days)
    retention_periods = {
        "prospect_interactions": 180,  # 6 months for interactions with prospects
        "completed_interactions": 730,  # 2 years for interactions with completed customers
        "not_interested_interactions": 365,  # 1 year for interactions with not interested customers
    }
    
    now = timezone.now()
    
    # Delete old interactions for prospects
    prospect_cutoff = now - timedelta(days=retention_periods["prospect_interactions"])
    prospect_customers = Customer.objects.filter(
        ~Q(conversation_state__in=["completed", "not_interested"]),
        interactions__timestamp__lt=prospect_cutoff
    )
    
    for customer in prospect_customers:
        old_interactions = Interaction.objects.filter(
            customer=customer,
            timestamp__lt=prospect_cutoff
        )
        count = old_interactions.count()
        old_interactions.delete()
        logger.info(f"Deleted {count} old interactions for prospect {customer.id}")
    
    # Delete old interactions for completed customers
    completed_cutoff = now - timedelta(days=retention_periods["completed_interactions"])
    old_completed_interactions = Interaction.objects.filter(
        customer__conversation_state="completed",
        timestamp__lt=completed_cutoff
    )
    count = old_completed_interactions.count()
    old_completed_interactions.delete()
    logger.info(f"Deleted {count} old interactions for completed customers")
    
    # Delete old interactions for not interested customers
    not_interested_cutoff = now - timedelta(days=retention_periods["not_interested_interactions"])
    old_not_interested_interactions = Interaction.objects.filter(
        customer__conversation_state="not_interested",
        timestamp__lt=not_interested_cutoff
    )
    count = old_not_interested_interactions.count()
    old_not_interested_interactions.delete()
    logger.info(f"Deleted {count} old interactions for not interested customers")
    
    # Delete old completed follow-ups
    old_followups = FollowUp.objects.filter(
        status__in=["sent", "cancelled", "failed"],
        scheduled_date__lt=not_interested_cutoff
    )
    count = old_followups.count()
    old_followups.delete()
    logger.info(f"Deleted {count} old follow-ups")
    
    return {"status": "completed"}


@shared_task
def update_customer_interest_levels():
    """Update customer interest levels based on recent activity"""
    logger.info("Starting customer interest level update task")
    
    # Get customers with recent activity
    recent_cutoff = timezone.now() - timedelta(days=30)
    active_customers = Customer.objects.filter(
        interactions__timestamp__gte=recent_cutoff
    ).distinct()
    
    for customer in active_customers:
        try:
            # Get recent interactions
            recent_interactions = Interaction.objects.filter(
                customer=customer,
                timestamp__gte=recent_cutoff
            ).order_by('timestamp')
            
            if not recent_interactions:
                continue
            
            # Calculate interest level based on recent intents
            interest_factor = 0
            
            for interaction in recent_interactions:
                if interaction.direction == "inbound":
                    if interaction.detected_intent == "interested":
                        interest_factor += 0.2
                    elif interaction.detected_intent == "needs_more_info":
                        interest_factor += 0.1
                    elif interaction.detected_intent == "objection":
                        interest_factor -= 0.1
                    elif interaction.detected_intent == "not_interested":
                        interest_factor -= 0.3
            
            # Normalize interest factor
            interest_factor = max(-1.0, min(1.0, interest_factor))
            
            # Update customer interest level
            new_interest_level = max(0.0, min(1.0, customer.interest_level + interest_factor))
            
            if new_interest_level != customer.interest_level:
                customer.interest_level = new_interest_level
                customer.save(update_fields=["interest_level"])
                logger.info(f"Updated interest level for customer {customer.id} to {new_interest_level}")
            
        except Exception as e:
            logger.error(f"Error updating interest level for customer {customer.id}: {str(e)}")
    
    return {"processed": active_customers.count()}