# agent/admin.py

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.template.defaultfilters import truncatechars
import json
from .models import (
    Customer, Interaction, FollowUp, 
    Template, Campaign, CampaignTarget,
    ConversationState
)

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name_display', 'phone_number', 'preferred_language', 
                   'conversation_state', 'interest_level', 'last_contacted_display', 
                   'next_contact_date_display', 'do_not_contact')
    list_filter = ('preferred_language', 'conversation_state', 'do_not_contact', 'created_at')
    search_fields = ('name', 'phone_number')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'phone_number', 'preferred_language', 'do_not_contact')
        }),
        ('Conversation Status', {
            'fields': ('conversation_state', 'interest_level', 'last_contacted', 'next_contact_date')
        }),
        ('Property Details', {
            'fields': ('property_details_formatted',),
            'classes': ('collapse',)
        }),
        ('Loan Requirements', {
            'fields': ('loan_requirements_formatted',),
            'classes': ('collapse',)
        }),
        ('Consent Information', {
            'fields': ('consents_formatted',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def name_display(self, obj):
        return obj.name or 'Unknown'
    name_display.short_description = 'Name'
    
    def last_contacted_display(self, obj):
        if obj.last_contacted:
            return obj.last_contacted.strftime('%Y-%m-%d %H:%M')
        return 'Never'
    last_contacted_display.short_description = 'Last Contacted'
    
    def next_contact_date_display(self, obj):
        if obj.next_contact_date:
            return obj.next_contact_date.strftime('%Y-%m-%d %H:%M')
        return 'Not scheduled'
    next_contact_date_display.short_description = 'Next Contact'
    
    def property_details_formatted(self, obj):
        if not obj.property_details:
            return 'No property details available'
        return format_html('<pre>{}</pre>', json.dumps(obj.property_details, indent=4))
    property_details_formatted.short_description = 'Property Details'
    
    def loan_requirements_formatted(self, obj):
        if not obj.loan_requirements:
            return 'No loan requirements available'
        return format_html('<pre>{}</pre>', json.dumps(obj.loan_requirements, indent=4))
    loan_requirements_formatted.short_description = 'Loan Requirements'
    
    def consents_formatted(self, obj):
        if not obj.consents:
            return 'No consent information available'
        return format_html('<pre>{}</pre>', json.dumps(obj.consents, indent=4))
    consents_formatted.short_description = 'Consent Information'


class InteractionInline(admin.TabularInline):
    model = Interaction
    extra = 0
    fields = ('timestamp', 'direction', 'message_type', 'content_short', 'language')
    readonly_fields = ('timestamp', 'direction', 'message_type', 'content_short', 'language')
    ordering = ('-timestamp',)
    max_num = 10
    
    def content_short(self, obj):
        return truncatechars(obj.content, 100)
    content_short.short_description = 'Content'
    
    def has_add_permission(self, request, obj=None):
        return False


class FollowUpInline(admin.TabularInline):
    model = FollowUp
    extra = 0
    fields = ('scheduled_date', 'status', 'follow_up_type', 'follow_up_reason')
    readonly_fields = ('scheduled_date', 'status', 'follow_up_type', 'follow_up_reason')
    ordering = ('-scheduled_date',)
    max_num = 5
    
    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Interaction)
class InteractionAdmin(admin.ModelAdmin):
    list_display = ('customer_link', 'timestamp', 'direction', 'message_type', 
                    'content_short', 'detected_intent', 'conversation_state', 'language')
    list_filter = ('direction', 'message_type', 'detected_intent', 'conversation_state', 'language')
    search_fields = ('content', 'customer__name', 'customer__phone_number')
    readonly_fields = ('timestamp', 'ai_analysis_formatted')
    date_hierarchy = 'timestamp'
    
    fieldsets = (
        ('Message Details', {
            'fields': ('customer', 'timestamp', 'direction', 'message_type', 'content')
        }),
        ('Analysis', {
            'fields': ('detected_intent', 'conversation_state', 'language', 'ai_confidence')
        }),
        ('AI Analysis', {
            'fields': ('ai_analysis_formatted',),
            'classes': ('collapse',)
        }),
        ('Media', {
            'fields': ('media_url', 'whatsapp_message_id'),
            'classes': ('collapse',)
        }),
    )
    
    def customer_link(self, obj):
        url = reverse('admin:agent_customer_change', args=[obj.customer.id])
        return format_html('<a href="{}">{}</a>', url, obj.customer)
    customer_link.short_description = 'Customer'
    
    def content_short(self, obj):
        return truncatechars(obj.content, 50)
    content_short.short_description = 'Content'
    
    def ai_analysis_formatted(self, obj):
        if not obj.ai_analysis:
            return 'No AI analysis available'
        return format_html('<pre>{}</pre>', json.dumps(obj.ai_analysis, indent=4))
    ai_analysis_formatted.short_description = 'AI Analysis'


@admin.register(FollowUp)
class FollowUpAdmin(admin.ModelAdmin):
    list_display = ('customer_link', 'scheduled_date', 'status', 'follow_up_type', 'follow_up_reason_short')
    list_filter = ('status', 'follow_up_type', 'scheduled_date')
    search_fields = ('customer__name', 'customer__phone_number', 'follow_up_reason', 'custom_message')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'scheduled_date'
    
    fieldsets = (
        ('Follow-up Details', {
            'fields': ('customer', 'scheduled_date', 'status', 'follow_up_type')
        }),
        ('Message Content', {
            'fields': ('message_template', 'custom_message', 'follow_up_reason')
        }),
        ('Results', {
            'fields': ('result_notes',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def customer_link(self, obj):
        url = reverse('admin:agent_customer_change', args=[obj.customer.id])
        return format_html('<a href="{}">{}</a>', url, obj.customer)
    customer_link.short_description = 'Customer'
    
    def follow_up_reason_short(self, obj):
        return truncatechars(obj.follow_up_reason or '', 50)
    follow_up_reason_short.short_description = 'Reason'


@admin.register(Template)
class TemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'language_code', 'category', 'is_approved', 'approval_date')
    list_filter = ('language_code', 'category', 'is_approved')
    search_fields = ('name', 'content', 'header_text', 'footer_text')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Template Details', {
            'fields': ('name', 'language_code', 'category', 'is_approved', 'approval_date')
        }),
        ('Content', {
            'fields': ('header_text', 'content', 'footer_text')
        }),
        ('Sample Values', {
            'fields': ('sample_values_formatted',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def sample_values_formatted(self, obj):
        if not obj.sample_values:
            return 'No sample values available'
        return format_html('<pre>{}</pre>', json.dumps(obj.sample_values, indent=4))
    sample_values_formatted.short_description = 'Sample Values'


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ('name', 'template', 'status', 'start_date', 'end_date', 
                   'total_targets', 'total_sent', 'total_responses')
    list_filter = ('status', 'start_date', 'template')
    search_fields = ('name', 'description')
    readonly_fields = ('created_at', 'updated_at', 'created_by', 
                      'total_targets', 'total_sent', 'total_responses')
    
    fieldsets = (
        ('Campaign Details', {
            'fields': ('name', 'description', 'template', 'status')
        }),
        ('Schedule', {
            'fields': ('start_date', 'end_date')
        }),
        ('Target Criteria', {
            'fields': ('target_criteria_formatted',),
            'classes': ('collapse',)
        }),
        ('Results', {
            'fields': ('total_targets', 'total_sent', 'total_responses')
        }),
        ('Tracking', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def target_criteria_formatted(self, obj):
        if not obj.target_criteria:
            return 'No target criteria defined'
        return format_html('<pre>{}</pre>', json.dumps(obj.target_criteria, indent=4))
    target_criteria_formatted.short_description = 'Target Criteria'
    
    def save_model(self, request, obj, form, change):
        if not change:  # If creating a new object
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(CampaignTarget)
class CampaignTargetAdmin(admin.ModelAdmin):
    list_display = ('customer_link', 'campaign_link', 'status', 
                   'scheduled_time', 'sent_time', 'response_time')
    list_filter = ('status', 'scheduled_time', 'sent_time', 'campaign')
    search_fields = ('customer__name', 'customer__phone_number', 'campaign__name', 'error_message')
    readonly_fields = ('scheduled_time', 'sent_time', 'response_time', 
                      'message_id', 'delivery_status', 'error_message')
    
    def customer_link(self, obj):
        url = reverse('admin:agent_customer_change', args=[obj.customer.id])
        return format_html('<a href="{}">{}</a>', url, obj.customer)
    customer_link.short_description = 'Customer'
    
    def campaign_link(self, obj):
        url = reverse('admin:agent_campaign_change', args=[obj.campaign.id])
        return format_html('<a href="{}">{}</a>', url, obj.campaign.name)
    campaign_link.short_description = 'Campaign'


@admin.register(ConversationState)
class ConversationStateAdmin(admin.ModelAdmin):
    list_display = ('name', 'description_short', 'transitions_count')
    search_fields = ('name', 'description')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('State Details', {
            'fields': ('name', 'description')
        }),
        ('Transitions', {
            'fields': ('possible_transitions_formatted',),
            'classes': ('collapse',)
        }),
        ('Prompts', {
            'fields': ('prompts_formatted',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def description_short(self, obj):
        return truncatechars(obj.description or '', 100)
    description_short.short_description = 'Description'
    
    def transitions_count(self, obj):
        return len(obj.possible_transitions) if obj.possible_transitions else 0
    transitions_count.short_description = 'Transitions'
    
    def possible_transitions_formatted(self, obj):
        if not obj.possible_transitions:
            return 'No transitions defined'
        return format_html('<pre>{}</pre>', json.dumps(obj.possible_transitions, indent=4))
    possible_transitions_formatted.short_description = 'Possible Transitions'
    
    def prompts_formatted(self, obj):
        if not obj.prompts:
            return 'No prompts defined'
        return format_html('<pre>{}</pre>', json.dumps(obj.prompts, indent=4))
    prompts_formatted.short_description = 'Prompts'