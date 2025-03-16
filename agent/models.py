# agent/models.py

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import json
import uuid

class Customer(models.Model):
    """Model to store customer information"""
    
    # Basic information
    phone_number = models.CharField(max_length=20, unique=True, db_index=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    preferred_language = models.CharField(max_length=50, default='english')
    
    # Property and loan details as JSON fields
    property_details = models.JSONField(default=dict, blank=True)
    loan_requirements = models.JSONField(default=dict, blank=True)
    
    # Tracking fields
    conversation_state = models.CharField(max_length=50, default='initial')
    interest_level = models.FloatField(default=0.0)  # 0-1 scale of interest
    last_contacted = models.DateTimeField(default=timezone.now)
    next_contact_date = models.DateTimeField(null=True, blank=True)
    do_not_contact = models.BooleanField(default=False)
    
    # Consent tracking
    consents = models.JSONField(default=dict, blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Customer'
        verbose_name_plural = 'Customers'
        indexes = [
            models.Index(fields=['next_contact_date']),
            models.Index(fields=['conversation_state']),
            models.Index(fields=['interest_level']),
        ]
    
    def __str__(self):
        return f"{self.name or 'Unknown'} ({self.phone_number})"
    
    def get_property_value(self):
        """Get property value if available"""
        return self.property_details.get('property_value', 0)
    
    def get_loan_amount(self):
        """Get requested loan amount if available"""
        return self.loan_requirements.get('loan_amount_needed', 0)
    
    def get_loan_purpose(self):
        """Get loan purpose if available"""
        return self.loan_requirements.get('loan_purpose', 'Not specified')
    
    def get_ltv_ratio(self):
        """Calculate loan-to-value ratio"""
        property_value = self.get_property_value()
        loan_amount = self.get_loan_amount()
        
        if property_value > 0 and loan_amount > 0:
            return (loan_amount / property_value) * 100
        return 0
    
    def record_consent(self, consent_type, given=True):
        """Record customer consent"""
        consents = self.consents or {}
        
        consents[consent_type] = {
            'given': given,
            'timestamp': timezone.now().isoformat(),
            'channel': 'whatsapp'
        }
        
        self.consents = consents
        self.save(update_fields=['consents', 'updated_at'])


class Interaction(models.Model):
    """Model to store customer interactions"""
    
    # Relationship
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='interactions')
    
    # Message details
    timestamp = models.DateTimeField(default=timezone.now)
    direction = models.CharField(max_length=10, choices=[('inbound', 'Inbound'), ('outbound', 'Outbound')])
    message_type = models.CharField(max_length=20, choices=[
        ('text', 'Text'), 
        ('audio', 'Audio'),
        ('template', 'Template'),
        ('system', 'System')
    ])
    
    # Content
    content = models.TextField()
    media_url = models.URLField(max_length=500, blank=True, null=True)
    
    # Metadata
    whatsapp_message_id = models.CharField(max_length=100, blank=True, null=True)
    detected_intent = models.CharField(max_length=50, blank=True, null=True)
    conversation_state = models.CharField(max_length=50, blank=True, null=True)
    language = models.CharField(max_length=50, default='english')
    
    # AI confidence and analysis
    ai_confidence = models.FloatField(default=1.0)
    ai_analysis = models.JSONField(default=dict, blank=True)
    
    class Meta:
        verbose_name = 'Interaction'
        verbose_name_plural = 'Interactions'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['-timestamp']),
            models.Index(fields=['customer', '-timestamp']),
            models.Index(fields=['detected_intent']),
        ]
    
    def __str__(self):
        return f"{self.customer} - {self.timestamp.strftime('%Y-%m-%d %H:%M')}"


class FollowUp(models.Model):
    """Model to schedule and track follow-ups"""
    
    # Relationship
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='followups')
    
    # Follow-up details
    scheduled_date = models.DateTimeField()
    status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled')
    ], default='pending')
    
    # Follow-up content and reason
    follow_up_type = models.CharField(max_length=50, choices=[
        ('general', 'General Follow-up'),
        ('interest_rate_drop', 'Interest Rate Drop'),
        ('property_value_increase', 'Property Value Increase'),
        ('new_product_launch', 'New Product Launch'),
        ('seasonal_promotion', 'Seasonal Promotion')
    ], default='general')
    
    message_template = models.CharField(max_length=100, blank=True, null=True)
    custom_message = models.TextField(blank=True, null=True)
    follow_up_reason = models.CharField(max_length=255, blank=True, null=True)
    
    # Tracking
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    result_notes = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name = 'Follow-up'
        verbose_name_plural = 'Follow-ups'
        ordering = ['-scheduled_date']
        indexes = [
            models.Index(fields=['scheduled_date', 'status']),
            models.Index(fields=['customer', 'status']),
        ]
    
    def __str__(self):
        return f"Follow-up for {self.customer} on {self.scheduled_date.strftime('%Y-%m-%d %H:%M')}"


class Template(models.Model):
    """Model to store WhatsApp message templates"""
    
    name = models.CharField(max_length=100, unique=True)
    language_code = models.CharField(max_length=10, default='en')
    category = models.CharField(max_length=50, choices=[
        ('marketing', 'Marketing'),
        ('utility', 'Utility'),
        ('authentication', 'Authentication')
    ])
    content = models.TextField()
    header_text = models.CharField(max_length=255, blank=True, null=True)
    footer_text = models.CharField(max_length=255, blank=True, null=True)
    
    # Sample values for placeholders
    sample_values = models.JSONField(default=dict, blank=True)
    
    # Tracking
    is_approved = models.BooleanField(default=False)
    approval_date = models.DateTimeField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Template'
        verbose_name_plural = 'Templates'
        unique_together = ('name', 'language_code')
    
    def __str__(self):
        return f"{self.name} ({self.language_code})"


class Campaign(models.Model):
    """Model to store outreach campaigns"""
    
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    
    # Campaign parameters
    template = models.ForeignKey(Template, on_delete=models.PROTECT, related_name='campaigns')
    target_criteria = models.JSONField(default=dict, blank=True)
    
    # Scheduling
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    
    # Status
    status = models.CharField(max_length=20, choices=[
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled')
    ], default='draft')
    
    # Results
    total_targets = models.IntegerField(default=0)
    total_sent = models.IntegerField(default=0)
    total_responses = models.IntegerField(default=0)
    
    # Tracking
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='campaigns')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Campaign'
        verbose_name_plural = 'Campaigns'
        ordering = ['-start_date']
    
    def __str__(self):
        return self.name


class CampaignTarget(models.Model):
    """Model to track campaign targets and outcomes"""
    
    # Relationships
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='targets')
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='campaign_targets')
    
    # Status
    status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('responded', 'Responded'),
        ('failed', 'Failed'),
        ('excluded', 'Excluded')
    ], default='pending')
    
    # Tracking
    scheduled_time = models.DateTimeField(blank=True, null=True)
    sent_time = models.DateTimeField(blank=True, null=True)
    response_time = models.DateTimeField(blank=True, null=True)
    
    # Results
    message_id = models.CharField(max_length=100, blank=True, null=True)
    delivery_status = models.CharField(max_length=50, blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name = 'Campaign Target'
        verbose_name_plural = 'Campaign Targets'
        unique_together = ('campaign', 'customer')
    
    def __str__(self):
        return f"{self.customer} - {self.campaign.name}"


class ConversationState(models.Model):
    """Model to store conversation state transitions"""
    
    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True, null=True)
    
    # Define possible transitions
    possible_transitions = models.JSONField(default=list, blank=True)
    
    # Define prompts for this state
    prompts = models.JSONField(default=dict, blank=True)
    
    # Tracking
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Conversation State'
        verbose_name_plural = 'Conversation States'
    
    def __str__(self):
        return self.name