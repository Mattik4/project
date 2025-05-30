# documents/management/commands/init_folders.py

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from documents.models import Folder, Tag


class Command(BaseCommand):
    help = 'Initialize default folders and tags'

    def add_arguments(self, parser):
        parser.add_argument(
            '--admin-email',
            type=str,
            help='Email of admin user to create folders for',
        )

    def handle(self, *args, **options):
        self.stdout.write('Inicjalizacja folderów i tagów...')
        
        # Get admin user
        admin_email = options.get('admin_email')
        if admin_email:
            try:
                admin_user = User.objects.get(email=admin_email, is_superuser=True)
            except User.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'Nie znaleziono użytkownika admin z emailem: {admin_email}')
                )
                return
        else:
            # Get first superuser
            admin_user = User.objects.filter(is_superuser=True).first()
            if not admin_user:
                self.stdout.write(
                    self.style.ERROR('Nie znaleziono użytkownika admin. Najpierw utwórz konto administratora.')
                )
                return
        
        # Create default folders
        default_folders = [
            {
                'nazwa': 'Dokumenty publiczne',
                'opis': 'Dokumenty dostępne dla wszystkich użytkowników'
            },
            {
                'nazwa': 'Szablony',
                'opis': 'Szablony dokumentów do wykorzystania'
            },
            {
                'nazwa': 'Archiwum',
                'opis': 'Starsze dokumenty do przechowywania'
            },
            {
                'nazwa': 'Robocze',
                'opis': 'Dokumenty w trakcie opracowywania'
            }
        ]
        
        created_folders = 0
        for folder_data in default_folders:
            folder, created = Folder.objects.get_or_create(
                nazwa=folder_data['nazwa'],
                wlasciciel=admin_user,
                defaults={
                    'opis': folder_data['opis']
                }
            )
            if created:
                created_folders += 1
                self.stdout.write(
                    self.style.SUCCESS(f'✓ Utworzono folder: {folder.nazwa}')
                )
            else:
                self.stdout.write(f'- Folder już istnieje: {folder.nazwa}')
        
        # Create default tags
        default_tags = [
            {'nazwa': 'Ważne', 'kolor': '#dc3545'},
            {'nazwa': 'Praca', 'kolor': '#0d6efd'},
            {'nazwa': 'Osobiste', 'kolor': '#198754'},
            {'nazwa': 'Projekt', 'kolor': '#fd7e14'},
            {'nazwa': 'Procedura', 'kolor': '#6610f2'},
            {'nazwa': 'Umowa', 'kolor': '#d63384'},
            {'nazwa': 'Faktura', 'kolor': '#20c997'},
            {'nazwa': 'Raport', 'kolor': '#ffc107'}
        ]
        
        created_tags = 0
        for tag_data in default_tags:
            tag, created = Tag.objects.get_or_create(
                nazwa=tag_data['nazwa'],
                defaults={
                    'kolor': tag_data['kolor']
                }
            )
            if created:
                created_tags += 1
                self.stdout.write(
                    self.style.SUCCESS(f'✓ Utworzono tag: {tag.nazwa}')
                )
            else:
                self.stdout.write(f'- Tag już istnieje: {tag.nazwa}')
        
        # Create nested folders example
        try:
            main_folder = Folder.objects.get(nazwa='Dokumenty publiczne', wlasciciel=admin_user)
            nested_folders = [
                {
                    'nazwa': 'Regulaminy',
                    'opis': 'Regulaminy wewnętrzne',
                    'rodzic': main_folder
                },
                {
                    'nazwa': 'Instrukcje',
                    'opis': 'Instrukcje użytkowania',
                    'rodzic': main_folder
                }
            ]
            
            for nested_data in nested_folders:
                nested_folder, created = Folder.objects.get_or_create(
                    nazwa=nested_data['nazwa'],
                    wlasciciel=admin_user,
                    rodzic=nested_data['rodzic'],
                    defaults={
                        'opis': nested_data['opis']
                    }
                )
                if created:
                    created_folders += 1
                    self.stdout.write(
                        self.style.SUCCESS(f'✓ Utworzono podfolder: {nested_folder.get_full_path()}')
                    )
        except Folder.DoesNotExist:
            pass
        
        self.stdout.write(
            self.style.SUCCESS(
                f'\n✅ Inicjalizacja zakończona!'
                f'\n   Utworzono: {created_folders} folderów, {created_tags} tagów'
                f'\n   Właściciel: {admin_user.get_full_name()} ({admin_user.email})'
            )
        )
        
        self.stdout.write('\n📋 Dostępne foldery:')
        for folder in Folder.objects.filter(wlasciciel=admin_user).order_by('rodzic', 'nazwa'):
            prefix = '  └─ ' if folder.rodzic else '• '
            self.stdout.write(f'   {prefix}{folder.get_full_path()}')
        
        self.stdout.write('\n🏷️  Dostępne tagi:')
        for tag in Tag.objects.all().order_by('nazwa'):
            self.stdout.write(f'   • {tag.nazwa} ({tag.kolor})')
        
        self.stdout.write(
            '\n💡 Następne kroki:'
            '\n   1. Uruchom serwer: python manage.py runserver'
            '\n   2. Zaloguj się jako admin i zacznij dodawać dokumenty'
            '\n   3. Utwórz konta dla innych użytkowników w panelu admin'
        )