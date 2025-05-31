from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin # Alias to avoid confusion
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm as BaseUserCreationForm # Alias
from django.utils.html import format_html
from django.core.exceptions import ValidationError
from django.conf import settings # Import settings
from django.contrib import messages # For success messages

from .models import Role, UserProfile, UserSession


class CustomUserCreationForm(BaseUserCreationForm):
    """Custom user creation form with role selection and required fields"""
    
    first_name = forms.CharField(
        max_length=150, # Increased from 30 to match User model's first_name
        required=True,
        label='Imię',
        widget=forms.TextInput(attrs={'class': 'vTextField'})
    )
    last_name = forms.CharField(
        max_length=150, # Increased from 30 to match User model's last_name
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
        required=True, # Make it required for new users
        label='Rola',
        empty_label=None, # No empty choice
        widget=forms.Select(attrs={'class': 'vTextField'})
    )

    class Meta(BaseUserCreationForm.Meta): # Inherit Meta from base
        model = User
        # Fields inherited from BaseUserCreationForm: username, password1, password2
        # We add our custom fields
        fields = ("username", "first_name", "last_name", "email", "rola") # password fields are handled by base

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set default role to 'czytelnik' if it exists
        try:
            default_role = Role.objects.get(nazwa=Role.READER) # Use constant
            self.fields['rola'].initial = default_role
        except Role.DoesNotExist:
            # If default role doesn't exist, admin needs to create it or choose one manually
            # Or, you could create it here if that's desired behavior
            pass
        
        # Reorder fields for better display in admin add form
        # Note: password fields are handled by BaseUserCreationForm's fieldsets
        # This ordering affects the form if not using fieldsets in add_form_template
        # For CustomUserAdmin.add_fieldsets, the order there takes precedence.
        current_fields = list(self.fields.keys())
        preferred_order = ['username', 'first_name', 'last_name', 'email', 'rola']
        # Add any other fields that might be in BaseUserCreationForm.Meta.fields
        # For standard UserCreationForm, it's just 'username'. Password fields are separate.
        
        ordered_fields = {
            field: self.fields[field] for field in preferred_order if field in current_fields
        }
        # Add remaining fields not in preferred_order
        for field in current_fields:
            if field not in ordered_fields:
                ordered_fields[field] = self.fields[field]
        self.fields = ordered_fields


    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email and User.objects.filter(email=email).exists(): # Check if email is provided
            raise ValidationError('Użytkownik z tym adresem email już istnieje.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False) # Save User instance first, but don't hit DB
        user.email = self.cleaned_data["email"]
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        
        if commit:
            user.save() # Save User to DB
            
            # Now handle UserProfile creation with the selected role
            selected_role = self.cleaned_data.get("rola")
            if selected_role: # Ensure role was selected
                UserProfile.objects.create(
                    user=user,
                    rola=selected_role,
                    aktywny=True # Default to active profile
                )
            else:
                # Fallback if role somehow wasn't selected, though it's required
                # This part depends on how strictly you want to enforce role on creation
                # Or rely on the post_save signal as a further fallback.
                pass
        return user


class CustomUserChangeForm(forms.ModelForm):
    """Custom user change form with role editing for UserProfile."""
    
    rola = forms.ModelChoiceField(
        queryset=Role.objects.all(),
        required=False, # Role might not be set, or admin might want to remove it
        label='Rola',
        widget=forms.Select(attrs={'class': 'vTextField'})
    )
    
    # This 'aktywny' is for the UserProfile's active status
    profil_aktywny = forms.BooleanField( # Renamed to avoid clash with User.is_active
        required=False,
        label='Profil użytkownika aktywny', # More descriptive label
        widget=forms.CheckboxInput()
    )

    class Meta:
        model = User # This form is for the User model primarily
        fields = '__all__' # Or specify fields explicitly

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Load current role and status from associated UserProfile
        # self.instance is the User instance
        if self.instance and self.instance.pk: # Ensure instance is saved and has a PK
            try:
                profile = self.instance.profile # Access via related_name 'profile'
                self.fields['rola'].initial = profile.rola
                self.fields['profil_aktywny'].initial = profile.aktywny
            except UserProfile.DoesNotExist:
                # Profile doesn't exist, fields will show default/empty
                # This case should ideally be handled by signals or save_model
                pass

    def save(self, commit=True):
        user = super().save(commit=commit) # Save the User model instance

        if commit:
            # Get or create the profile to ensure it exists
            profile, created = UserProfile.objects.get_or_create(user=user)
            
            # Update profile with new role and status from the form
            if 'rola' in self.cleaned_data:
                profile.rola = self.cleaned_data.get('rola') # Use .get() for safety
            
            if 'profil_aktywny' in self.cleaned_data:
                profile.aktywny = self.cleaned_data['profil_aktywny']
            
            profile.save() # Save the UserProfile instance
        
        return user


class CustomUserAdmin(BaseUserAdmin): # Inherit from Django's BaseUserAdmin
    """Enhanced User Admin with role in forms and UserProfile integration."""
    
    add_form = CustomUserCreationForm
    form = CustomUserChangeForm # This form edits the User, and its save handles UserProfile
    
    list_display = (
        'username', 'email', 'first_name', 'last_name', 
        'get_user_profile_role', 'get_user_profile_active_status', 
        'is_staff', 'is_active', # User model's is_active
        'date_joined', 'last_login'
    )
    list_filter = (
        'is_staff', 'is_active', # User model's is_active
        'profile__rola', 'profile__aktywny', # Filter by UserProfile fields
        'date_joined'
    )
    search_fields = ('username', 'first_name', 'last_name', 'email')
    ordering = ('-date_joined',)
    
    # Fieldsets for ADDING users (uses CustomUserCreationForm implicitly)
    # These are used by the add_form_template if specified, or by default add view
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Dane personalne', {'fields': ('first_name', 'last_name', 'email')}),
        ('Rola w systemie', {'fields': ('rola',)}),
    )
    
    # Fieldsets for EDITING users (uses CustomUserChangeForm)
    # We need to define these to include our custom 'rola' and 'profil_aktywny' fields
    # from the CustomUserChangeForm.
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Informacje osobowe', {'fields': ('first_name', 'last_name', 'email')}),
        ('Profil i Rola', {'fields': ('rola', 'profil_aktywny')}), # Fields from CustomUserChangeForm
        ('Uprawnienia', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        ('Ważne daty', {'fields': ('last_login', 'date_joined')}),
    )
    
    actions = ['make_admin_role', 'make_editor_role', 'make_reader_role', 
               'activate_user_profiles', 'deactivate_user_profiles'] # Renamed actions for clarity
    
    @admin.display(description='Rola (Profil)', ordering='profile__rola__nazwa')
    def get_user_profile_role(self, obj):
        """Get user role from UserProfile."""
        try:
            if obj.profile and obj.profile.rola:
                role_name = obj.profile.rola.get_nazwa_display()
                role_value = obj.profile.rola.nazwa
                if role_value == Role.ADMIN:
                    return format_html('<span style="color: #dc3545; font-weight: bold;">{}</span>', role_name)
                elif role_value == Role.EDITOR:
                    return format_html('<span style="color: #fd7e14; font-weight: bold;">{}</span>', role_name)
                elif role_value == Role.READER: # Assuming Role.READER exists
                    return format_html('<span style="color: #0dcaf0;">{}</span>', role_name)
                return role_name # Fallback for other roles
        except UserProfile.DoesNotExist:
            pass
        return format_html('<span style="color: #6c757d;">Brak profilu/roli</span>')

    @admin.display(description='Status Profilu', ordering='profile__aktywny', boolean=True)
    def get_user_profile_active_status(self, obj):
        """Get user active status from UserProfile."""
        try:
            if obj.profile:
                return obj.profile.aktywny # Returns True/False, admin renders as icon
        except UserProfile.DoesNotExist:
            pass
        return None # Let admin render default for None boolean

    def get_queryset(self, request):
        """Optimize queries by prefetching related UserProfile and Role."""
        return super().get_queryset(request).select_related('profile__rola')
    
    # save_model is generally handled by the form's save method.
    # The BaseUserAdmin.save_model calls form.save().
    # The fallback UserProfile creation logic in the signal is usually sufficient.
    # If you need more specific logic here, you can override it.
    # For now, relying on signals and form save methods.

    def _update_profile_role(self, request, queryset, role_const, role_description_default):
        role_obj, created = Role.objects.get_or_create(
            nazwa=role_const,
            defaults={'opis': role_description_default}
        )
        updated_count = 0
        for user in queryset:
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.rola = role_obj
            profile.save()
            updated_count += 1
        self.message_user(request, f'{updated_count} użytkowników otrzymało rolę {role_obj.get_nazwa_display()}.')

    @admin.action(description="Zmień rolę na Administrator")
    def make_admin_role(self, request, queryset):
        self._update_profile_role(request, queryset, Role.ADMIN, 'Pełne uprawnienia administracyjne')
    
    @admin.action(description="Zmień rolę na Edytor")
    def make_editor_role(self, request, queryset):
        self._update_profile_role(request, queryset, Role.EDITOR, 'Uprawnienia edytora')

    @admin.action(description="Zmień rolę na Czytelnik")
    def make_reader_role(self, request, queryset):
        self._update_profile_role(request, queryset, Role.READER, 'Podstawowe uprawnienia czytelnika')

    def _update_profile_status(self, request, queryset, is_active):
        updated_count = 0
        action_text = "aktywowanych" if is_active else "dezaktywowanych"
        for user in queryset:
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.aktywny = is_active
            profile.save()
            updated_count += 1
        self.message_user(request, f'{updated_count} profili użytkowników zostało {action_text}.')

    @admin.action(description="Aktywuj profile użytkowników")
    def activate_user_profiles(self, request, queryset):
        self._update_profile_status(request, queryset, True)
    
    @admin.action(description="Dezaktywuj profile użytkowników")
    def deactivate_user_profiles(self, request, queryset):
        self._update_profile_status(request, queryset, False)


# Re-register User model with our custom admin
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    """Role administration."""
    list_display = ['get_nazwa_display', 'opis', 'get_users_count'] # Use get_nazwa_display for choices
    search_fields = ['nazwa', 'opis']
    readonly_fields = ('get_users_count',) # Make it a method call
    
    fieldsets = (
        ('Informacje o roli', {'fields': ('nazwa', 'opis')}),
        ('Statystyki', {'fields': ('get_users_count',), 'classes': ('collapse',)})
    )
    
    @admin.display(description='Liczba użytkowników')
    def get_users_count(self, obj):
        """Count users with this role."""
        # Access UserProfile via the related_name from UserProfile.rola
        # Assuming UserProfile.rola has related_name='user_profiles' or default 'userprofile_set'
        count = UserProfile.objects.filter(rola=obj, aktywny=True).count()
        total = UserProfile.objects.filter(rola=obj).count()
        return f"{count} aktywnych / {total} wszystkich"
    
    # No need for get_queryset here unless complex prefetching is required beyond default M2M.


@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
    """User session administration."""
    list_display = [
        'get_user_display', 'login_time', 'get_session_duration', 
        'ip_address', 'is_active'
    ]
    list_filter = ['is_active', 'login_time']
    search_fields = ['user__username', 'user__first_name', 'user__last_name', 'user__email', 'ip_address']
    readonly_fields = ['user', 'session_key', 'login_time', 'logout_time', 'user_agent', 'ip_address']
    date_hierarchy = 'login_time'
    ordering = ['-login_time']
    
    fieldsets = (
        ('Sesja', {'fields': ('user', 'is_active', 'session_key')}),
        ('Czas', {'fields': ('login_time', 'logout_time')}),
        ('Informacje techniczne', {'fields': ('ip_address', 'user_agent'), 'classes': ('collapse',)})
    )
    
    @admin.display(description='Użytkownik', ordering='user__username')
    def get_user_display(self, obj):
        return obj.user.get_full_name() or obj.user.email
    
    @admin.display(description='Czas trwania')
    def get_session_duration(self, obj):
        if obj.logout_time:
            duration = obj.logout_time - obj.login_time
            # Simplified duration display
            total_seconds = int(duration.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            if hours > 0:
                return f"{hours}g {minutes}m"
            elif minutes > 0:
                return f"{minutes}m {seconds}s"
            return f"{seconds}s"
        elif obj.is_active:
            return format_html('<span style="color: green;">Aktywna</span>')
        return "Zakończona (brak danych)"
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')
    
    def has_add_permission(self, request):
        return False # Sessions are created programmatically

    def has_change_permission(self, request, obj=None):
        return False # Sessions should generally not be changed manually

    def has_delete_permission(self, request, obj=None):
        return True # Allow deleting old sessions if needed


# Customize admin site appearance
admin.site.site_header = "Document Manager - Panel Administracyjny"
admin.site.site_title = "Document Manager Admin"
admin.site.index_title = "Zarządzanie systemem"