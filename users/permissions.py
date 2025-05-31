"""
Guardian permissions helpers for Document Manager
"""
from guardian.shortcuts import assign_perm, remove_perm, get_perms
# from guardian.core import ObjectPermissionChecker # Not directly used in these functions
from django.contrib.auth.models import User # Not directly needed if using request.user
# from .models import UserProfile, Role # UserProfile is accessed via user.profile

# It's good practice to import models from the app they belong to
# when using them in functions that might be called from various places.
# from documents.models import Document, Folder # Import these where needed or pass objects


# --- Document Permissions ---

def user_can_view_document(user, document):
    """Check if user can view specific document."""
    if not user.is_authenticated:
        return False

    # Public documents (if you add such a concept, e.g., document.is_public)
    # if document.is_public:
    #     return True

    if user.is_superuser or (hasattr(user, 'profile') and user.profile.is_admin):
        return True

    if document.wlasciciel == user:
        return True

    return user.has_perm('browse_document', document)


def user_can_create_document(user):
    """Check if user can create new documents."""
    if not user.is_authenticated:
        return False
    if user.is_superuser or (hasattr(user, 'profile') and (user.profile.is_admin or user.profile.is_editor)):
        return True
    return False


def user_can_edit_document(user, document):
    """Check if user can edit specific document metadata or upload new versions."""
    if not user.is_authenticated:
        return False

    if user.is_superuser or (hasattr(user, 'profile') and user.profile.is_admin):
        return True

    # Owner can always edit their own documents if they are an editor or admin
    if document.wlasciciel == user and (hasattr(user, 'profile') and (user.profile.is_admin or user.profile.is_editor)):
        return True
    
    # An editor can edit if they have explicit change_document permission
    if hasattr(user, 'profile') and user.profile.is_editor and user.has_perm('change_document', document):
        return True

    return False


def user_can_delete_document(user, document):
    """Check if user can delete specific document."""
    if not user.is_authenticated:
        return False

    if user.is_superuser or (hasattr(user, 'profile') and user.profile.is_admin):
        return True

    # Owner can delete their own documents if they are an editor or admin
    if document.wlasciciel == user and (hasattr(user, 'profile') and (user.profile.is_admin or user.profile.is_editor)):
        return True
        
    # An editor can delete if they have explicit delete_document permission (more restrictive)
    # Or, if 'change_document' implies delete for editors on shared items (policy decision)
    # For now, let's say only explicit delete_document perm or being admin/owner.
    # If you want editors with 'change_document' to also delete, add:
    # if hasattr(user, 'profile') and user.profile.is_editor and user.has_perm('delete_document', document):
    #     return True

    return False


def user_can_comment_on_document(user, document):
    """Check if user can comment on a document."""
    if not user.is_authenticated:
        return False

    # If document allows public comments (add a field to Document model if needed)
    # if document.allow_public_comments:
    #    return True

    # Admin, editor, or reader can comment if they can view the document
    if user_can_view_document(user, document) and \
       (user.is_superuser or (hasattr(user, 'profile') and (user.profile.is_admin or user.profile.is_editor or user.profile.is_reader))):
        # Optionally, add a specific 'comment_document' Guardian permission for more granular control
        # if user.has_perm('comment_document', document):
        #     return True
        return True
    return False


def user_can_share_document(user, document):
    """Check if user can share specific document."""
    if not user.is_authenticated:
        return False

    if user.is_superuser or (hasattr(user, 'profile') and user.profile.is_admin):
        return True

    if document.wlasciciel == user and (hasattr(user, 'profile') and (user.profile.is_admin or user.profile.is_editor)):
        return True
    
    # Check if user has explicit share permission (less common for editors unless they own it)
    # if hasattr(user, 'profile') and user.profile.is_editor and user.has_perm('share_document', document):
    #    return True

    return False


def share_document_with_user(document, from_user, to_user_obj, permission_level='browse_document'):
    """Share document with another user.
    to_user_obj is an instance of User.
    """
    # Define all possible document permissions
    all_doc_permissions = [
        'browse_document', 'change_document', 'delete_document', 
        'share_document', 'download_document', 'comment_document'
    ]
    
    # Remove existing document-specific permissions for this document from the target user
    for perm in all_doc_permissions:
        if to_user_obj.has_perm(perm, document):
            remove_perm(perm, to_user_obj, document)
    
    # Assign new permission
    assign_perm(permission_level, to_user_obj, document)
    
    # Log the sharing activity
    from documents.models import ActivityLog # Local import to avoid circularity
    ActivityLog.objects.create(
        uzytkownik=from_user,
        typ_aktywnosci='udostepnianie',
        dokument=document,
        szczegoly=f"Udostępniono '{document.nazwa}' dla {to_user_obj.get_full_name()} z uprawnieniem {permission_level}",
        # adres_ip='127.0.0.1'  # Get real IP in views
    )


def remove_all_permissions_for_document_from_user(document, user_obj):
    """Remove all document permissions for a specific document from a user."""
    all_doc_permissions = [
        'browse_document', 'change_document', 'delete_document', 
        'share_document', 'download_document', 'comment_document'
    ]
    for perm in all_doc_permissions:
        if user_obj.has_perm(perm, document):
            remove_perm(perm, user_obj, document)


def get_user_document_permissions(user, document):
    """Get all permissions user has for specific document."""
    return get_perms(user, document)


# --- Folder Permissions ---

def user_can_view_folder(user, folder):
    """Check if user can view specific folder."""
    if not user.is_authenticated:
        return False

    if user.is_superuser or (hasattr(user, 'profile') and user.profile.is_admin):
        return True

    if folder.wlasciciel == user: # Owner can always view
        return True

    return user.has_perm('browse_folder', folder)


def user_can_create_folder(user):
    """Check if user can create new folders."""
    if not user.is_authenticated:
        return False
    if user.is_superuser or (hasattr(user, 'profile') and (user.profile.is_admin or user.profile.is_editor)):
        return True
    return False


def user_can_edit_folder(user, folder): # Renamed from user_can_manage_folder for clarity
    """Check if user can edit specific folder's metadata."""
    if not user.is_authenticated:
        return False

    if user.is_superuser or (hasattr(user, 'profile') and user.profile.is_admin):
        return True

    if folder.wlasciciel == user and (hasattr(user, 'profile') and (user.profile.is_admin or user.profile.is_editor)):
        return True
        
    if hasattr(user, 'profile') and user.profile.is_editor and user.has_perm('change_folder', folder): # Specific perm for editing folder
        return True
        
    return False

def user_can_delete_folder(user, folder):
    """Check if user can delete specific folder."""
    if not user.is_authenticated:
        return False

    if user.is_superuser or (hasattr(user, 'profile') and user.profile.is_admin):
        return True

    if folder.wlasciciel == user and (hasattr(user, 'profile') and (user.profile.is_admin or user.profile.is_editor)):
        return True

    # if hasattr(user, 'profile') and user.profile.is_editor and user.has_perm('delete_folder', folder):
    #     return True
        
    return False