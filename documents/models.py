from django.db import models
from django.contrib.auth.models import User
from django.core.validators import FileExtensionValidator
from django.core.exceptions import ValidationError
import os
import uuid
from users.models import Role, UserProfile


def document_upload_path(instance, filename):
    """Generate upload path for documents"""
    # Create unique path: documents/user_id/year/month/uuid_filename
    ext = filename.split('.')[-1]
    filename = f"{uuid.uuid4().hex}.{ext}"
    
    from datetime import datetime
    now = datetime.now()
    
    return f"documents/{instance.wlasciciel.id}/{now.year}/{now.month:02d}/{filename}"


class Folder(models.Model):
    """Folder structure for documents"""
    nazwa = models.CharField(max_length=255)
    opis = models.TextField(blank=True)
    data_utworzenia = models.DateTimeField(auto_now_add=True)
    rodzic = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='podkatalogi')
    wlasciciel = models.ForeignKey(User, on_delete=models.CASCADE, related_name='folders')
    
    def __str__(self):
        return self.nazwa
    
    def get_full_path(self):
        """Get full folder path"""
        if self.rodzic:
            return f"{self.rodzic.get_full_path()}/{self.nazwa}"
        return self.nazwa
    
    class Meta:
        db_table = 'folder'
        unique_together = ['nazwa', 'rodzic', 'wlasciciel']
        permissions = (
            ('browse_folder', 'Can browse folder'),
            ('share_folder', 'Can share folder'),
            ('manage_folder', 'Can manage folder permissions'),
        )


class Tag(models.Model):
    """Tags for document categorization"""
    nazwa = models.CharField(max_length=50, unique=True)
    kolor = models.CharField(max_length=20, default='#007bff')
    
    def __str__(self):
        return self.nazwa
    
    class Meta:
        db_table = 'tag'


class Document(models.Model):
    """Main document model"""
    ALLOWED_EXTENSIONS = ['pdf', 'docx', 'doc', 'xlsx', 'xls', 'txt', 'png', 'jpg', 'jpeg']
    
    STATUS_CHOICES = [
        ('draft', 'Szkic'),
        ('published', 'Opublikowany'),
        ('archived', 'Zarchiwizowany'),
    ]
    
    # Basic information
    nazwa = models.CharField(max_length=255)
    typ_pliku = models.CharField(max_length=100)
    rozmiar_pliku = models.PositiveIntegerField()
    
    # File storage
    plik = models.FileField(
        upload_to=document_upload_path,
        validators=[FileExtensionValidator(allowed_extensions=ALLOWED_EXTENSIONS)],
        help_text="Obsługiwane formaty: PDF, DOCX, DOC, XLSX, XLS, TXT, PNG, JPG, JPEG",
        blank=True,  # Dodane: pozwala na puste wartości
        null=True    # Dodane: pozwala na NULL w bazie danych
    )
    
    # Metadata
    data_utworzenia = models.DateTimeField(auto_now_add=True)
    ostatnia_modyfikacja = models.DateTimeField(auto_now=True)
    wlasciciel = models.ForeignKey(User, on_delete=models.CASCADE, related_name='documents')
    folder = models.ForeignKey(Folder, on_delete=models.CASCADE, related_name='documents')
    usunieto = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    
    # Simple many-to-many relationship with tags
    tagi = models.ManyToManyField(Tag, blank=True)
    
    # Additional metadata
    opis = models.TextField(blank=True, help_text="Opcjonalny opis dokumentu")
    hash_pliku = models.CharField(max_length=64, blank=True, help_text="SHA-256 hash for file integrity")
    
    def __str__(self):
        return self.nazwa
    
    def clean(self):
        """Validate document"""
        super().clean()
        
        # Validate file size (max 50MB) - only if file exists
        if self.plik and self.plik.size > 50 * 1024 * 1024:
            raise ValidationError("Plik nie może być większy niż 50MB.")
        
        # Auto-set file properties if plik is present
        if self.plik:
            if not self.nazwa:
                self.nazwa = self.plik.name
            if not self.typ_pliku:
                # Get content type or guess from extension
                import mimetypes
                self.typ_pliku = mimetypes.guess_type(self.plik.name)[0] or 'application/octet-stream'
            if not self.rozmiar_pliku:
                self.rozmiar_pliku = self.plik.size
    
    def save(self, *args, **kwargs):
        """Override save to set metadata and calculate hash"""
        if self.plik:
            # Set file metadata
            if not self.nazwa:
                self.nazwa = os.path.basename(self.plik.name)
            if not self.typ_pliku:
                import mimetypes
                self.typ_pliku = mimetypes.guess_type(self.plik.name)[0] or 'application/octet-stream'
            if not self.rozmiar_pliku:
                self.rozmiar_pliku = self.plik.size
            
            # Calculate file hash for integrity checking
            if not self.hash_pliku:
                import hashlib
                self.plik.seek(0)
                file_hash = hashlib.sha256()
                for chunk in iter(lambda: self.plik.read(4096), b""):
                    file_hash.update(chunk)
                self.hash_pliku = file_hash.hexdigest()
                self.plik.seek(0)  # Reset file pointer
        
        super().save(*args, **kwargs)
    
    def delete(self, *args, **kwargs):
        """Override delete to remove file from storage"""
        if self.plik:
            # Delete file from storage
            try:
                if os.path.isfile(self.plik.path):
                    os.remove(self.plik.path)
            except (ValueError, OSError):
                pass  # File doesn't exist or can't be deleted
        super().delete(*args, **kwargs)
    
    def get_file_size_display(self):
        """Human readable file size"""
        if not self.rozmiar_pliku:
            return "0 B"
        
        size = self.rozmiar_pliku
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"
    
    def get_file_extension(self):
        """Get file extension"""
        if not self.nazwa:
            return ""
        return os.path.splitext(self.nazwa)[1].lower()
    
    def get_file_icon(self):
        """Get Bootstrap icon class for file type"""
        ext = self.get_file_extension()
        icon_map = {
            '.pdf': 'bi-file-earmark-pdf',
            '.doc': 'bi-file-earmark-word',
            '.docx': 'bi-file-earmark-word',
            '.xls': 'bi-file-earmark-excel',
            '.xlsx': 'bi-file-earmark-excel',
            '.txt': 'bi-file-earmark-text',
            '.png': 'bi-file-earmark-image',
            '.jpg': 'bi-file-earmark-image',
            '.jpeg': 'bi-file-earmark-image',
        }
        return icon_map.get(ext, 'bi-file-earmark')
    
    def is_image(self):
        """Check if document is an image"""
        return self.get_file_extension() in ['.png', '.jpg', '.jpeg']
    
    def can_preview(self):
        """Check if document can be previewed in browser"""
        return self.plik and self.get_file_extension() in ['.pdf', '.txt', '.png', '.jpg', '.jpeg']
    
    @property
    def download_url(self):
        """Get download URL for the document"""
        if self.plik:
            return f"/documents/{self.id}/download/"
        return None
    
    class Meta:
        db_table = 'dokument'
        ordering = ['-ostatnia_modyfikacja']
        permissions = (
            ('browse_document', 'Can browse document'),
            ('download_document', 'Can download document'),
            ('share_document', 'Can share document'),
            ('comment_document', 'Can comment on document'),
            ('manage_document', 'Can manage document permissions'),
        )


class DocumentVersion(models.Model):
    """Document version control"""
    dokument = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='wersje')
    numer_wersji = models.PositiveIntegerField()
    data_utworzenia = models.DateTimeField(auto_now_add=True)
    utworzony_przez = models.ForeignKey(User, on_delete=models.CASCADE)
    plik = models.FileField(upload_to='document_versions/', blank=True, null=True)
    komentarz = models.TextField(blank=True)
    rozmiar_pliku = models.PositiveIntegerField(default=0)
    hash_pliku = models.CharField(max_length=64, blank=True)
    
    def __str__(self):
        return f"{self.dokument.nazwa} v{self.numer_wersji}"
    
    def save(self, *args, **kwargs):
        """Auto-set version metadata"""
        if self.plik and not self.rozmiar_pliku:
            self.rozmiar_pliku = self.plik.size
            
            # Calculate hash
            import hashlib
            self.plik.seek(0)
            file_hash = hashlib.sha256()
            for chunk in iter(lambda: self.plik.read(4096), b""):
                file_hash.update(chunk)
            self.hash_pliku = file_hash.hexdigest()
            self.plik.seek(0)
        
        super().save(*args, **kwargs)
    
    class Meta:
        db_table = 'wersja_dokumentu'
        unique_together = ['dokument', 'numer_wersji']
        ordering = ['-numer_wersji']


# Rest of the models remain the same...
class DocumentTag(models.Model):
    """Through model for Document-Tag relationship"""
    dokument = models.ForeignKey(Document, on_delete=models.CASCADE)
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE)
    
    class Meta:
        db_table = 'dokument_tag'
        unique_together = ['dokument', 'tag']


class DocumentMetadata(models.Model):
    """Custom metadata for documents"""
    dokument = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='metadane')
    klucz = models.CharField(max_length=100)
    wartosc = models.TextField()
    
    def __str__(self):
        return f"{self.klucz}: {self.wartosc}"
    
    class Meta:
        db_table = 'metadane'
        unique_together = ['dokument', 'klucz']


class Comment(models.Model):
    """Comments for documents"""
    dokument = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='komentarze')
    uzytkownik = models.ForeignKey(User, on_delete=models.CASCADE)
    tresc = models.TextField()
    data_utworzenia = models.DateTimeField(auto_now_add=True)
    rodzic = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='odpowiedzi')
    
    def __str__(self):
        return f"Komentarz do {self.dokument.nazwa} - {self.uzytkownik.username}"
    
    class Meta:
        db_table = 'komentarz'
        ordering = ['-data_utworzenia']


class ActivityLog(models.Model):
    """Activity logging"""
    ACTION_CHOICES = [
        ('logowanie', 'Logowanie'),
        ('tworzenie', 'Tworzenie'),
        ('edycja', 'Edycja'),
        ('usuniecie', 'Usunięcie'),
        ('pobieranie', 'Pobieranie'),
        ('udostepnianie', 'Udostępnianie'),
        ('komentowanie', 'Komentowanie'),
        ('zmiana_uprawnien', 'Zmiana uprawnień'),
        ('zmiana_hasla', 'Zmiana hasła'),
    ]
    
    uzytkownik = models.ForeignKey(User, on_delete=models.CASCADE, related_name='logi_aktywnosci')
    typ_aktywnosci = models.CharField(max_length=50, choices=ACTION_CHOICES)
    dokument = models.ForeignKey(Document, on_delete=models.CASCADE, null=True, blank=True)
    folder = models.ForeignKey(Folder, on_delete=models.CASCADE, null=True, blank=True)
    szczegoly = models.TextField(blank=True)
    znacznik_czasu = models.DateTimeField(auto_now_add=True)
    adres_ip = models.GenericIPAddressField()
    
    def __str__(self):
        return f"{self.uzytkownik.username} - {self.typ_aktywnosci} - {self.znacznik_czasu}"
    
    class Meta:
        db_table = 'log_aktywnosci'
        ordering = ['-znacznik_czasu']


class DocumentShare(models.Model):
    """Track document sharing with specific permissions"""
    dokument = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='shares')
    udostepnione_przez = models.ForeignKey(User, on_delete=models.CASCADE, related_name='shared_documents')
    udostepnione_dla = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_documents')
    uprawnienie = models.CharField(max_length=50, choices=[
        ('browse_document', 'Tylko przeglądanie'),
        ('download_document', 'Przeglądanie i pobieranie'),
        ('comment_document', 'Przeglądanie i komentowanie'),
        ('manage_document', 'Pełne uprawnienia do edycji'),
    ])
    data_udostepnienia = models.DateTimeField(auto_now_add=True)
    data_wygasniecia = models.DateTimeField(null=True, blank=True)
    aktywne = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.dokument.nazwa} shared by {self.udostepnione_przez.username} to {self.udostepnione_dla.username}"
    
    class Meta:
        db_table = 'document_share'
        unique_together = ['dokument', 'udostepnione_dla']


class SystemSettings(models.Model):
    """Ustawienia systemowe"""
    key = models.CharField(max_length=100, unique=True, verbose_name='Klucz')
    value = models.TextField(verbose_name='Wartość')
    description = models.TextField(blank=True, verbose_name='Opis')
    category = models.CharField(max_length=50, default='general', verbose_name='Kategoria')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.key}: {self.value}"
    
    @classmethod
    def get_setting(cls, key, default=None):
        """Pobierz ustawienie lub zwróć wartość domyślną"""
        try:
            setting = cls.objects.get(key=key)
            return setting.value
        except cls.DoesNotExist:
            return default
    
    @classmethod
    def set_setting(cls, key, value, description='', category='general'):
        """Ustaw wartość ustawienia"""
        setting, created = cls.objects.get_or_create(
            key=key,
            defaults={
                'value': value,
                'description': description,
                'category': category
            }
        )
        if not created:
            setting.value = value
            setting.description = description
            setting.category = category
            setting.save()
        return setting
    
    class Meta:
        db_table = 'system_settings'
        verbose_name = 'Ustawienie systemowe'
        verbose_name_plural = 'Ustawienia systemowe'
        ordering = ['category', 'key']