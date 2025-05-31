"""
Guardian permissions helpers for Document Manager
"""
from guardian.shortcuts import assign_perm, remove_perm, get_perms
from guardian.core import ObjectPermissionChecker
from django.contrib.auth.models import User
from .models import UserProfile, Role


def user_can_view_document(user, document):
    """Check if user can view specific document"""
    if not user.is_authenticated:
        return False
    
    # Admin can view everything
    if user.is_superuser or user.profile.is_admin:
        return True
    
    # Owner can view own documents
    if document.wlasciciel == user:
        return True
    
    # Check Guardian permissions (using new permission name)
    return user.has_perm('browse_document', document)


def user_can_edit_document(user, document):
    """Check if user can edit specific document"""
    if not user.is_authenticated:
        return False
    
    # Admin can edit everything
    if user.is_superuser or user.profile.is_admin:
        return True
    
    # Owner can edit own documents
    if document.wlasciciel == user:
        return True
    
    # Editors with permission can edit
    if user.profile.is_editor and user.has_perm('change_document', document):
        return True
    
    return False


def user_can_delete_document(user, document):
    """Check if user can delete specific document"""
    if not user.is_authenticated:
        return False
    
    # Only admin and owner can delete
    if user.is_superuser or user.profile.is_admin:
        return True
    
    if document.wlasciciel == user:
        return True
    
    return False


def user_can_share_document(user, document):
    """Check if user can share specific document"""
    if not user.is_authenticated:
        return False
    
    # Admin can share everything
    if user.is_superuser or user.profile.is_admin:
        return True
    
    # Owner can share own documents
    if document.wlasciciel == user:
        return True
    
    # Check if user has share permission
    return user.has_perm('share_document', document)


def share_document_with_user(document, from_user, to_user, permission_level='browse_document'):
    """Share document with another user"""
    # Remove existing permissions first
    remove_document_permissions(document, to_user)
    
    # Assign new permission
    assign_perm(permission_level, to_user, document)
    
    # Log the sharing activity
    from documents.models import ActivityLog
    ActivityLog.objects.create(
        uzytkownik=from_user,
        typ_aktywnosci='udostepnianie',
        dokument=document,
        szczegoly=f"Udostępniono dla {to_user.get_full_name()} z uprawnieniem {permission_level}",
        adres_ip='127.0.0.1'  # You should get real IP in views
    )


def remove_document_permissions(document, user):
    """Remove all document permissions from user"""
    permissions = ['browse_document', 'change_document', 'delete_document', 'share_document', 'download_document', 'comment_document', 'manage_document']
    for perm in permissions:
        remove_perm(perm, user, document)


def get_user_document_permissions(user, document):
    """Get all permissions user has for specific document"""
    return get_perms(user, document)


def user_can_view_folder(user, folder):
    """Check if user can view specific folder"""
    if not user.is_authenticated:
        return False
    
    # Admin can view everything
    if user.is_superuser or user.profile.is_admin:
        return True
    
    # Owner can view own folders
    if folder.wlasciciel == user:
        return True
    
    # Check Guardian permissions (using new permission name)
    return user.has_perm('browse_folder', folder)


def user_can_manage_folder(user, folder):
    """Check if user can manage specific folder"""
    if not user.is_authenticated:
        return False
    
    # Admin can manage everything
    if user.is_superuser or user.profile.is_admin:
        return True
    
    # Owner can manage own folders
    if folder.wlasciciel == user:
        return True
    
    # Check Guardian permissions
    return user.has_perm('manage_folder', folder)


def setup_default_permissions_for_user(user):
    """Setup default permissions when user is created"""
    # This can be called from signals or views
    # For now, we don't set any default object permissions
    # Permissions will be assigned when documents/folders are shared
    pass


def get_documents_user_can_view(user):
    """Get all documents user can view (using Guardian)"""
    from documents.models import Document
    
    if user.is_superuser or user.profile.is_admin:
        return Document.objects.filter(usunieto=False)
    
    # Get documents where user is owner OR has view permission
    user_documents = Document.objects.filter(wlasciciel=user, usunieto=False)
    
    # This is a simplified version - for performance, you might want to use
    # Guardian's get_objects_for_user() function
    return user_documents


def get_folders_user_can_view(user):
    """Get all folders user can view"""
    from documents.models import Folder
    
    if user.is_superuser or user.profile.is_admin:
        return Folder.objects.all()
    
    # Get folders where user is owner OR has view permission
    return Folder.objects.filter(wlasciciel=user)


class DocumentPermissionMixin:
    """Mixin for views that need document permission checking"""
    
    def dispatch(self, request, *args, **kwargs):
        # Get document from URL
        document = self.get_object()
        
        # Check permission based on view type
        if hasattr(self, 'required_permission'):
            if not getattr(self, f'user_can_{self.required_permission}')(request.user, document):
                from django.core.exceptions import PermissionDenied
                raise PermissionDenied("Brak uprawnień do tego dokumentu.")
        
        return super().dispatch(request, *args, **kwargs)
    
    def user_can_view(self, user, document):
        return user_can_view_document(user, document)
    
    def user_can_edit(self, user, document):
        return user_can_edit_document(user, document)
    
    def user_can_delete(self, user, document):
        return user_can_delete_document(user, document)


# Decorator for function-based views
def require_document_permission(permission):
    """Decorator to check document permissions in function-based views"""
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            # This is a simplified version - you'd need to get document_id from kwargs
            # and implement proper permission checking
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator

def user_can_manage_folder(user, folder):
    """Check if user can manage specific folder"""
    if not user.is_authenticated:
        return False
    
    # Admin can manage everything
    if user.is_superuser or (hasattr(user, 'profile') and user.profile.is_admin):
        return True
    
    # Owner can manage own folders
    if folder.wlasciciel == user:
        return True
    
    # Check Guardian permissions
    return user.has_perm('manage_folder', folder)