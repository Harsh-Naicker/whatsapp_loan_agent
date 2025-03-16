# simulator/management/commands/init_simulator.py
from django.core.management.base import BaseCommand
from simulator.simulator import WhatsAppSimulator
from agent.models import Template

class Command(BaseCommand):
    help = 'Initialize the WhatsApp simulator with templates'

    def handle(self, *args, **options):
        self.stdout.write('Initializing WhatsApp simulator...')
        
        # Create simulator instance
        simulator = WhatsAppSimulator()
        
        # Load templates from database
        templates = Template.objects.filter(is_approved=True)
        
        for template in templates:
            simulator.templates[template.name] = {
                'name': template.name,
                'language_code': template.language_code,
                'content': template.content,
                'header_text': template.header_text,
                'footer_text': template.footer_text
            }
            
        # Save simulator state
        simulator.save_state()
        
        self.stdout.write(self.style.SUCCESS(f'Successfully initialized simulator with {len(templates)} templates'))