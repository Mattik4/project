from django.core.management.base import BaseCommand
from documents.models import SystemSettings


class Command(BaseCommand):
    help = 'Initialize default system settings'

    def handle(self, *args, **options):
        self.stdout.write('Inicjalizacja ustawień systemowych...')
        
        default_settings = [
            {
                'key': 'CONTACT_EMAIL',
                'value': 'admin@docmanager.com',
                'description': 'Email kontaktowy wyświetlany na stronie logowania',
                'category': 'contact'
            },
            {
                'key': 'COMPANY_NAME',
                'value': 'Document Manager',
                'description': 'Nazwa firmy/systemu',
                'category': 'general'
            },
            {
                'key': 'SUPPORT_EMAIL',
                'value': 'support@docmanager.com',
                'description': 'Email do wsparcia technicznego',
                'category': 'contact'
            },
            {
                'key': 'SYSTEM_TITLE',
                'value': 'Document Manager - System Zarządzania Dokumentami',
                'description': 'Tytuł systemu wyświetlany w przeglądarce',
                'category': 'general'
            }
        ]
        
        created_count = 0
        updated_count = 0
        
        for setting_data in default_settings:
            setting, created = SystemSettings.objects.get_or_create(
                key=setting_data['key'],
                defaults={
                    'value': setting_data['value'],
                    'description': setting_data['description'],
                    'category': setting_data['category']
                }
            )
            
            if created:
                created_count += 1
                self.stdout.write(f'✓ Utworzono: {setting.key} = {setting.value}')
            else:
                # Update description if empty
                if not setting.description and setting_data['description']:
                    setting.description = setting_data['description']
                    setting.category = setting_data['category']
                    setting.save()
                    updated_count += 1
                    self.stdout.write(f'↻ Zaktualizowano opis: {setting.key}')
                else:
                    self.stdout.write(f'- Już istnieje: {setting.key} = {setting.value}')
        
        self.stdout.write(
            self.style.SUCCESS(
                f'\n✅ Inicjalizacja zakończona!'
                f'\n   Utworzono: {created_count} nowych ustawień'
                f'\n   Zaktualizowano: {updated_count} ustawień'
            )
        )
        
        if created_count > 0 or updated_count > 0:
            self.stdout.write('\n📋 Dostępne ustawienia:')
            for setting in SystemSettings.objects.all().order_by('category', 'key'):
                self.stdout.write(f'   {setting.category}/{setting.key}: {setting.value}')
            
            self.stdout.write(f'\n🔧 Możesz je edytować w: /admin/documents/systemsettings/')
        
        self.stdout.write(
            '\n💡 Wskazówka: Zmień CONTACT_EMAIL aby zaktualizować email kontaktowy na stronie logowania'
        )
