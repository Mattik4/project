from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django.utils.html import format_html
from django.core.exceptions import ValidationError
from .models import Role, UserProfile, UserSession


class CustomUserCreationForm(UserCreationForm):
    """Custom user creation form with role selection and required fields"""
    
    first_name = forms.CharField(
        max_length=30, 
        required=True,
        label='Imię',
        widget=forms.TextInput(attrs={'class': 'vTextField'})
    )
    last_name = forms.CharField(
        max_length=30, 
        required=True,
        label='Nazwisko',
        widget=forms.TextInput(attrs={'class': 'vTextField'})
    )
    email = forms.EmailField(
        required=True,
        label='Email',
        widget=forms.EmailInput(attrs={'class': 'vTextField'})
    )
    rola = forms.ModelChoiceField(
        queryset=Role.objects.all(),
        required=True,
        label='Rola',
        empty_label=None,
        widget=forms.Select(attrs={'class': 'vTextField'})
    )

    class Meta:
        model = User
        fields = ("username", "first_name", "last_name", "email", "password1", "password2", "rola")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set default role to 'czytelnik'
        try:
            default_role = Role.objects.get(nazwa='czytelnik')
            self.fields['rola'].initial = default_role
        except Role.DoesNotExist:
            pass
        
        # Reorder fields
        field_order = ['username', 'first_name', 'last_name', 'email', 'rola', 'password1', 'password2']
        self.fields = {field: self.fields[field] for field in field_order}

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise ValidationError('Użytkownik z tym adresem email już istnieje.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        
        if commit:
            user.save()
            # Create profile with selected role
            selected_role = self.cleaned_data["rola"]
            UserProfile.objects.create(
                user=user,
                rola=selected_role,
                aktywny=True
            )
        return user


class CustomUserChangeForm(forms.ModelForm):
    """Custom user change form with role editing"""
    
    rola = forms.ModelChoiceField(
        queryset=Role.objects.all(),
        required=False,
        label='Rola',
        widget=forms.Select(attrs={'class': 'vTextField'})
    )
    
    aktywny = forms.BooleanField(
        required=False,
        label='Profil aktywny',
        widget=forms.CheckboxInput()
    )

    class Meta:
        model = User
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Load current role and status from profile
        if self.instance and hasattr(self.instance, 'profile'):
            self.fields['rola'].initial = self.instance.profile.rola
            self.fields['aktywny'].initial = self.instance.profile.aktywny

    def save(self, commit=True):
        user = super().save(commit=commit)
        
        if commit and hasattr(user, 'profile'):
            # Update profile with new role and status
            if 'rola' in self.cleaned_data and self.cleaned_data['rola']:
                user.profile.rola = self.cleaned_data['rola']
            if 'aktywny' in self.cleaned_data:
                user.profile.aktywny = self.cleaned_data['aktywny']
            user.profile.save()
        
        return user


class CustomUserAdmin(UserAdmin):
    """Enhanced User Admin with role in forms"""
    
    # Use custom forms
    add_form = CustomUserCreationForm
    form = CustomUserChangeForm
    
    # Enhanced display with role information
    list_display = (
        'username', 'email', 'first_name', 'last_name', 'get_role', 'get_active_status', 
        'date_joined', 'last_login', 'is_staff', 'is_active'
    )
    list_filter = ('is_staff', 'is_active', 'date_joined', 'profile__rola', 'profile__aktywny')
    search_fields = ('first_name', 'last_name', 'email', 'username')
    ordering = ('-date_joined',)
    
    # Custom fieldsets for adding users
    add_fieldsets = (
        ('Informacje o użytkowniku', {
            'classes': ('wide',),
            'fields': ('username', 'first_name', 'last_name', 'email'),
        }),
        ('Rola w systemie', {
            'classes': ('wide',),
            'fields': ('rola',),
        }),
        ('Hasło', {
            'classes': ('wide',),
            'fields': ('password1', 'password2'),
        }),
    )
    
    # Custom fieldsets for editing users
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Informacje osobowe', {'fields': ('first_name', 'last_name', 'email')}),
        ('Rola i status', {'fields': ('rola', 'aktywny')}),
        ('Uprawnienia', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
            'classes': ('collapse',)
        }),
        ('Ważne daty', {
            'fields': ('last_login', 'date_joined'),
            'classes': ('collapse',)
        }),
    )
    
    # Add actions to change roles from the user list
    actions = ['make_admin', 'make_editor', 'make_reader', 'activate_users', 'deactivate_users']
    
    def get_role(self, obj):
        """Get user role from profile"""
        if hasattr(obj, 'profile') and obj.profile.rola:
            role_name = obj.profile.rola.get_nazwa_display()
            if obj.profile.rola.nazwa == Role.ADMIN:
                return format_html('<span style="color: #dc3545; font-weight: bold;">{}</span>', role_name)
            elif obj.profile.rola.nazwa == Role.EDITOR:
                return format_html('<span style="color: #fd7e14; font-weight: bold;">{}</span>', role_name)
            else:
                return format_html('<span style="color: #0dcaf0;">{}</span>', role_name)
        return format_html('<span style="color: #6c757d;">Brak roli</span>')
    get_role.short_description = 'Rola'
    get_role.admin_order_field = 'profile__rola'
    
    def get_active_status(self, obj):
        """Get user active status from profile"""
        if hasattr(obj, 'profile'):
            if obj.profile.aktywny:
                return format_html('<span style="color: green;">●</span> Aktywny')
            else:
                return format_html('<span style="color: red;">●</span> Nieaktywny')
        return format_html('<span style="color: orange;">●</span> Brak profilu')
    get_active_status.short_description = 'Status profilu'
    get_active_status.admin_order_field = 'profile__aktywny'
    
    def get_queryset(self, request):
        """Optimize queries"""
        return super().get_queryset(request).select_related('profile', 'profile__rola')
    
    def save_model(self, request, obj, form, change):
        """Save user and handle profile creation/updates"""
        super().save_model(request, obj, form, change)
        
        # Ensure profile exists (for users created outside this form)
        if not hasattr(obj, 'profile'):
            from django.conf import settings
            default_role_name = getattr(settings, 'DEFAULT_USER_ROLE', 'czytelnik')
            try:
                default_role = Role.objects.get(nazwa=default_role_name)
            except Role.DoesNotExist:
                default_role = Role.objects.create(
                    nazwa=default_role_name,
                    opis='Podstawowa rola z prawami do odczytu'
                )
            
            UserProfile.objects.create(
                user=obj, 
                rola=default_role,
                aktywny=True
            )
        
        # Success message
        if not change:  # New user
            role_name = "nieznana"
            if hasattr(obj, 'profile') and obj.profile.rola:
                role_name = obj.profile.rola.get_nazwa_display()
            
            from django.contrib import messages
            messages.success(
                request, 
                f'Użytkownik "{obj.get_full_name()}" został utworzony z rolą "{role_name}".'
            )
    
    # Admin actions to change roles
    def make_admin(self, request, queryset):
        """Change selected users to Admin role"""
        admin_role, _ = Role.objects.get_or_create(
            nazwa='administrator',
            defaults={'opis': 'Pełne uprawnienia administracyjne'}
        )
        
        updated = 0
        for user in queryset:
            if hasattr(user, 'profile'):
                user.profile.rola = admin_role
                user.profile.save()
                updated += 1
        
        self.message_user(request, f'{updated} użytkowników otrzymało rolę Administrator.')
    make_admin.short_description = "Zmień rolę na Administrator"
    
    def make_editor(self, request, queryset):
        """Change selected users to Editor role"""
        editor_role, _ = Role.objects.get_or_create(
            nazwa='edytor',
            defaults={'opis': 'Uprawnienia edytora'}
        )
        
        updated = 0
        for user in queryset:
            if hasattr(user, 'profile'):
                user.profile.rola = editor_role
                user.profile.save()
                updated += 1
        
        self.message_user(request, f'{updated} użytkowników otrzymało rolę Edytor.')
    make_editor.short_description = "Zmień rolę na Edytor"
    
    def make_reader(self, request, queryset):
        """Change selected users to Reader role"""
        reader_role, _ = Role.objects.get_or_create(
            nazwa='czytelnik',
            defaults={'opis': 'Uprawnienia czytelnika'}
        )
        
        updated = 0
        for user in queryset:
            if hasattr(user, 'profile'):
                user.profile.rola = reader_role
                user.profile.save()
                updated += 1
        
        self.message_user(request, f'{updated} użytkowników otrzymało rolę Czytelnik.')
    make_reader.short_description = "Zmień rolę na Czytelnik"
    
    def activate_users(self, request, queryset):
        """Activate selected users' profiles"""
        updated = 0
        for user in queryset:
            if hasattr(user, 'profile'):
                user.profile.aktywny = True
                user.profile.save()
                updated += 1
        
        self.message_user(request, f'{updated} profili użytkowników zostało aktywowanych.')
    activate_users.short_description = "Aktywuj profile użytkowników"
    
    def deactivate_users(self, request, queryset):
        """Deactivate selected users' profiles"""
        updated = 0
        for user in queryset:
            if hasattr(user, 'profile'):
                user.profile.aktywny = False
                user.profile.save()
                updated += 1
        
        self.message_user(request, f'{updated} profili użytkowników zostało dezaktywowanych.')
    deactivate_users.short_description = "Dezaktywuj profile użytkowników"


# Re-register UserAdmin
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    """Role administration"""
    list_display = ['nazwa', 'get_nazwa_display', 'opis', 'users_count']
    search_fields = ['nazwa', 'opis']
    readonly_fields = ('users_count',)
    
    fieldsets = (
        ('Informacje o roli', {
            'fields': ('nazwa', 'opis')
        }),
        ('Statystyki', {
            'fields': ('users_count',),
            'classes': ('collapse',)
        })
    )
    
    def users_count(self, obj):
        """Count users with this role"""
        count = obj.userprofile_set.filter(aktywny=True).count()
        total = obj.userprofile_set.count()
        return f"{count} aktywnych / {total} wszystkich"
    users_count.short_description = 'Liczba użytkowników'
    
    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('userprofile_set')


@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
    """User session administration"""
    list_display = [
        'get_user_display', 'login_time', 'logout_time', 'ip_address', 
        'is_active', 'get_session_duration'
    ]
    list_filter = ['is_active', 'login_time']
    search_fields = ['user__first_name', 'user__last_name', 'user__email', 'ip_address']
    readonly_fields = ['session_key', 'login_time', 'logout_time', 'user_agent']
    date_hierarchy = 'login_time'
    ordering = ['-login_time']
    
    fieldsets = (
        ('Sesja', {
            'fields': ('user', 'is_active', 'session_key')
        }),
        ('Czas', {
            'fields': ('login_time', 'logout_time')
        }),
        ('Informacje techniczne', {
            'fields': ('ip_address', 'user_agent'),
            'classes': ('collapse',)
        })
    )
    
    def get_user_display(self, obj):
        """Display user name"""
        return obj.user.get_full_name() or obj.user.email
    get_user_display.short_description = 'Użytkownik'
    get_user_display.admin_order_field = 'user__first_name'
    
    def get_session_duration(self, obj):
        """Calculate session duration"""
        if obj.logout_time:
            duration = obj.logout_time - obj.login_time
            hours, remainder = divmod(duration.total_seconds(), 3600)
            minutes, _ = divmod(remainder, 60)
            return f"{int(hours)}h {int(minutes)}m"
        elif obj.is_active:
            return "Aktywna"
        return "Nieznana"
    get_session_duration.short_description = 'Czas trwania'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')
    
    def has_add_permission(self, request):
        """Disable manual session creation"""
        return False


# Customize admin site
admin.site.site_header = "Document Manager - Panel Administracyjny"
admin.site.site_title = "Document Manager Admin"
admin.site.index_title = "Zarządzanie systemem"
