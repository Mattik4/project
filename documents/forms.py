from django import forms
from django.core.validators import FileExtensionValidator
from django.core.exceptions import ValidationError
from .models import Document, Folder, Tag, Comment
import os


class DocumentUploadForm(forms.ModelForm):
    """Enhanced form for document upload with file handling"""
    
    plik = forms.FileField(
        label='Plik',
        validators=[FileExtensionValidator(
            allowed_extensions=['pdf', 'docx', 'doc', 'xlsx', 'xls', 'txt', 'png', 'jpg', 'jpeg']
        )],
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.pdf,.docx,.doc,.xlsx,.xls,.txt,.png,.jpg,.jpeg',
            'id': 'file-input'
        }),
        help_text="Obsługiwane formaty: PDF, DOCX, DOC, XLSX, XLS, TXT, PNG, JPG, JPEG. Maksymalny rozmiar: 50MB."
    )
    
    nazwa = forms.CharField(
        label='Nazwa dokumentu',
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Zostanie automatycznie ustawiona na podstawie nazwy pliku'
        }),
        help_text="Opcjonalnie - jeśli puste, zostanie użyta nazwa pliku"
    )
    
    opis = forms.CharField(
        label='Opis',
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Opcjonalny opis dokumentu'
        })
    )
    
    class Meta:
        model = Document
        fields = ['plik', 'nazwa', 'opis', 'folder', 'tagi', 'status']
        widgets = {
            'folder': forms.Select(attrs={'class': 'form-control'}),
            'tagi': forms.CheckboxSelectMultiple(),
            'status': forms.Select(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if user:
            # Show only folders owned by user or with permissions
            if user.is_superuser or (hasattr(user, 'profile') and user.profile.is_admin):
                self.fields['folder'].queryset = Folder.objects.all()
            else:
                self.fields['folder'].queryset = Folder.objects.filter(wlasciciel=user)
            
            # Set default folder if user has any
            if self.fields['folder'].queryset.exists() and not self.initial.get('folder'):
                self.fields['folder'].initial = self.fields['folder'].queryset.first()
    
    def clean_plik(self):
        """Validate uploaded file"""
        plik = self.cleaned_data.get('plik')
        
        if not plik:
            raise ValidationError("Musisz wybrać plik do wgrania.")
        
        # Check file size (50MB limit)
        max_size = 50 * 1024 * 1024  # 50MB
        if plik.size > max_size:
            raise ValidationError(f"Plik jest za duży! Maksymalny rozmiar to 50MB. Twój plik ma {plik.size / 1024 / 1024:.1f}MB.")
        
        # Check file extension
        allowed_extensions = ['pdf', 'docx', 'doc', 'xlsx', 'xls', 'txt', 'png', 'jpg', 'jpeg']
        ext = os.path.splitext(plik.name)[1].lower().lstrip('.')
        
        if ext not in allowed_extensions:
            raise ValidationError(f"Nieobsługiwany format pliku. Dozwolone formaty: {', '.join(allowed_extensions)}")
        
        # Basic security check - don't allow executable files
        dangerous_extensions = ['exe', 'bat', 'cmd', 'com', 'scr', 'vbs', 'js']
        if ext in dangerous_extensions:
            raise ValidationError("Ze względów bezpieczeństwa, ten typ pliku nie jest dozwolony.")
        
        return plik
    
    def clean_nazwa(self):
        """Clean document name"""
        nazwa = self.cleaned_data.get('nazwa', '').strip()
        
        # If no name provided, we'll use filename in save()
        if not nazwa:
            return nazwa
        
        # Validate name
        if len(nazwa) > 255:
            raise ValidationError("Nazwa dokumentu nie może być dłuższa niż 255 znaków.")
        
        # Remove dangerous characters
        dangerous_chars = ['<', '>', ':', '"', '|', '?', '*', '\\', '/']
        for char in dangerous_chars:
            if char in nazwa:
                raise ValidationError(f"Nazwa nie może zawierać znaku: {char}")
        
        return nazwa
    
    def clean(self):
        """Additional validation"""
        cleaned_data = super().clean()
        plik = cleaned_data.get('plik')
        nazwa = cleaned_data.get('nazwa')
        
        # If no name provided, set it from filename
        if plik and not nazwa:
            cleaned_data['nazwa'] = os.path.basename(plik.name)
        
        return cleaned_data


class DocumentUpdateForm(forms.ModelForm):
    """Form for updating document metadata (not the file itself)"""
    
    class Meta:
        model = Document
        fields = ['nazwa', 'opis', 'folder', 'tagi', 'status']
        widgets = {
            'nazwa': forms.TextInput(attrs={'class': 'form-control'}),
            'opis': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'folder': forms.Select(attrs={'class': 'form-control'}),
            'tagi': forms.CheckboxSelectMultiple(),
            'status': forms.Select(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if user:
            if user.is_superuser or (hasattr(user, 'profile') and user.profile.is_admin):
                self.fields['folder'].queryset = Folder.objects.all()
            else:
                self.fields['folder'].queryset = Folder.objects.filter(wlasciciel=user)


class DocumentVersionUploadForm(forms.Form):
    """Form for uploading new version of existing document"""
    
    plik = forms.FileField(
        label='Nowa wersja pliku',
        validators=[FileExtensionValidator(
            allowed_extensions=['pdf', 'docx', 'doc', 'xlsx', 'xls', 'txt', 'png', 'jpg', 'jpeg']
        )],
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.pdf,.docx,.doc,.xlsx,.xls,.txt,.png,.jpg,.jpeg'
        })
    )
    
    komentarz = forms.CharField(
        label='Komentarz do wersji',
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Opisz zmiany w tej wersji...'
        })
    )
    
    def clean_plik(self):
        """Validate uploaded file"""
        plik = self.cleaned_data.get('plik')
        
        if not plik:
            raise ValidationError("Musisz wybrać plik.")
        
        # Check file size
        max_size = 50 * 1024 * 1024  # 50MB
        if plik.size > max_size:
            raise ValidationError("Plik jest za duży! Maksymalny rozmiar to 50MB.")
        
        return plik


class FolderCreateForm(forms.ModelForm):
    class Meta:
        model = Folder
        fields = ['nazwa', 'opis', 'rodzic']
        widgets = {
            'nazwa': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nazwa folderu'}),
            'opis': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Opis folderu (opcjonalny)'}),
            'rodzic': forms.Select(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if user:
            if user.is_superuser or (hasattr(user, 'profile') and user.profile.is_admin):
                self.fields['rodzic'].queryset = Folder.objects.all()
            else:
                self.fields['rodzic'].queryset = Folder.objects.filter(wlasciciel=user)
            self.fields['rodzic'].empty_label = "Folder główny"


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ['tresc']
        widgets = {
            'tresc': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Dodaj komentarz...'
            })
        }


class TagCreateForm(forms.ModelForm):
    class Meta:
        model = Tag
        fields = ['nazwa', 'kolor']
        widgets = {
            'nazwa': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nazwa tagu'}),
            'kolor': forms.TextInput(attrs={'class': 'form-control', 'type': 'color'}),
        }


class DocumentSearchForm(forms.Form):
    search = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Szukaj dokumentów...',
            'autocomplete': 'off'
        })
    )
    folder = forms.ModelChoiceField(
        queryset=Folder.objects.all(),
        required=False,
        empty_label="Wszystkie foldery",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    tag = forms.ModelChoiceField(
        queryset=Tag.objects.all(),
        required=False,
        empty_label="Wszystkie tagi",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    file_type = forms.ChoiceField(
        choices=[
            ('', 'Wszystkie typy'),
            ('pdf', 'PDF'),
            ('word', 'Word (DOC/DOCX)'),
            ('excel', 'Excel (XLS/XLSX)'),
            ('text', 'Tekst (TXT)'),
            ('image', 'Obrazy (PNG/JPG)'),
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )


class DocumentShareForm(forms.Form):
    """Form for sharing documents with other users"""
    user_email = forms.EmailField(
        label='Email użytkownika',
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'jan.kowalski@firma.pl'
        })
    )
    
    permission_level = forms.ChoiceField(
        label='Poziom uprawnień',
        choices=[
            ('browse_document', 'Tylko przeglądanie'),
            ('download_document', 'Przeglądanie i pobieranie'),
            ('comment_document', 'Przeglądanie i komentowanie'),
            ('change_document', 'Pełne uprawnienia do edycji'),
        ],
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    expiry_date = forms.DateTimeField(
        label='Data wygaśnięcia (opcjonalnie)',
        required=False,
        widget=forms.DateTimeInput(attrs={
            'class': 'form-control',
            'type': 'datetime-local'
        })
    )


class BulkActionForm(forms.Form):
    """Form for bulk actions on documents"""
    action = forms.ChoiceField(
        choices=[
            ('publish', 'Opublikuj'),
            ('archive', 'Zarchiwizuj'),
            ('delete', 'Usuń'),
            ('move', 'Przenieś do folderu'),
        ],
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    target_folder = forms.ModelChoiceField(
        queryset=Folder.objects.all(),
        required=False,
        empty_label="Wybierz folder",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if user:
            if user.is_superuser or (hasattr(user, 'profile') and user.profile.is_admin):
                self.fields['target_folder'].queryset = Folder.objects.all()
            else:
                self.fields['target_folder'].queryset = Folder.objects.filter(wlasciciel=user)