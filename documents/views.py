from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse, Http404, FileResponse
from django.core.paginator import Paginator
from django.db.models import Q, Prefetch
from django.core.exceptions import PermissionDenied
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views import View
from django.conf import settings
from guardian.decorators import permission_required_or_403 # Keep if used elsewhere
from guardian.shortcuts import get_objects_for_user, assign_perm, remove_perm

from .models import Document, Folder, Tag, SystemSettings, DocumentVersion, ActivityLog, Comment
from .forms import (
    DocumentUploadForm, FolderCreateForm, DocumentUpdateForm,
    DocumentVersionUploadForm, FolderUpdateForm, FolderDeleteForm, CommentForm
)
# Assuming UserProfile is in users.models
# from users.models import UserProfile

# Import your refined permission functions
from users.permissions import (
    user_can_view_document, user_can_edit_document, user_can_delete_document,
    user_can_create_document, user_can_comment_on_document, user_can_share_document,
    user_can_view_folder, user_can_edit_folder, user_can_delete_folder,
    user_can_create_folder
)
import os
import mimetypes
from datetime import datetime


def get_client_ip(request): # Moved to top for easier access
    """Get client IP address"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def home(request, folder_id=None):
    """New dashboard with file explorer style"""
    current_folder = None
    breadcrumbs = []

    if folder_id:
        current_folder = get_object_or_404(Folder.objects.prefetch_related('tagi'), pk=folder_id)
        if not user_can_view_folder(request.user, current_folder):
            messages.error(request, "Nie masz uprawnień do tego folderu.")
            return redirect('documents:home')
        temp_folder = current_folder
        while temp_folder:
            breadcrumbs.insert(0, temp_folder)
            temp_folder = temp_folder.rodzic
    
    folders_qs = Folder.objects.none()
    documents_qs = Document.objects.none()

    if request.user.is_authenticated:
        if current_folder:
            # Simplified for brevity; actual permission filtering for listed items can be complex
            # For now, assumes if user can view current_folder, they see its immediate contents
            # More granular would involve checking perms for each sub-folder/document
            folders_qs = Folder.objects.filter(rodzic=current_folder).prefetch_related('tagi', 'wlasciciel__profile').order_by('nazwa')
            documents_qs = Document.objects.filter(
                folder=current_folder, usunieto=False
            ).select_related('wlasciciel__profile', 'folder').prefetch_related('tagi').order_by('nazwa')
        else: # Root level
            # Show folders user owns or has browse_folder perm on at root
            # This part can be complex for optimal performance with Guardian.
            # get_objects_for_user is better for Guardian based listings.
            owned_root_folders = Folder.objects.filter(rodzic=None, wlasciciel=request.user)
            # Add folders shared via Guardian (simplified)
            # shared_root_folders = get_objects_for_user(request.user, 'documents.browse_folder', klass=Folder).filter(rodzic=None)
            # folders_qs = (owned_root_folders | shared_root_folders).distinct().prefetch_related('tagi', 'wlasciciel__profile').order_by('nazwa')
            
            # Simplified: show owned root folders for non-admins, all for admins
            if request.user.is_superuser or (hasattr(request.user, 'profile') and request.user.profile.is_admin):
                folders_qs = Folder.objects.filter(rodzic=None).prefetch_related('tagi', 'wlasciciel__profile').order_by('nazwa')
                documents_qs = Document.objects.filter(
                    Q(folder=None) | Q(folder__rodzic=None), usunieto=False # Docs in root or in root folders
                ).select_related('wlasciciel__profile', 'folder').prefetch_related('tagi').order_by('nazwa')
            else:
                folders_qs = Folder.objects.filter(rodzic=None, wlasciciel=request.user).prefetch_related('tagi', 'wlasciciel__profile').order_by('nazwa')
                documents_qs = Document.objects.filter(
                     Q(folder=None, wlasciciel=request.user) | Q(folder__rodzic=None, wlasciciel=request.user), usunieto=False
                ).select_related('wlasciciel__profile', 'folder').prefetch_related('tagi').order_by('nazwa')


        for folder_item in folders_qs:
            folder_item.doc_count = folder_item.documents.filter(usunieto=False).count()
            folder_item.subfolder_count = folder_item.podkatalogi.count()
            # For template: Check if current user can edit/delete this specific folder
            folder_item.current_user_can_edit = user_can_edit_folder(request.user, folder_item)
            folder_item.current_user_can_delete = user_can_delete_folder(request.user, folder_item)

        for doc_item in documents_qs:
            # For template: Check if current user can edit/delete this specific document
            doc_item.current_user_can_edit = user_can_edit_document(request.user, doc_item)
            doc_item.current_user_can_delete = user_can_delete_document(request.user, doc_item)

        # Quick stats (remains largely the same, based on ownership or superuser status)
        if request.user.is_superuser or (hasattr(request.user, 'profile') and request.user.profile.is_admin):
            total_documents = Document.objects.filter(usunieto=False).count()
            total_folders = Folder.objects.count()
            total_size = sum(doc.rozmiar_pliku or 0 for doc in Document.objects.filter(usunieto=False))
        else:
            user_documents_qs = Document.objects.filter(wlasciciel=request.user, usunieto=False)
            total_documents = user_documents_qs.count()
            total_folders = Folder.objects.filter(wlasciciel=request.user).count()
            total_size = sum(doc.rozmiar_pliku or 0 for doc in user_documents_qs)
    else: # Not authenticated
        total_documents = 0
        total_folders = 0
        total_size = 0

    def human_readable_size(size_bytes):
        if size_bytes == 0: return "0 B"
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0: return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} PB" # Should not happen

    context = {
        'current_folder': current_folder,
        'breadcrumbs': breadcrumbs,
        'folders': folders_qs,
        'documents': documents_qs,
        'total_documents': total_documents,
        'total_folders': total_folders,
        'total_size': human_readable_size(total_size),
        'is_root': current_folder is None,
        'user_can_create_documents': user_can_create_document(request.user) if request.user.is_authenticated else False,
        'user_can_create_folders': user_can_create_folder(request.user) if request.user.is_authenticated else False,
    }
    return render(request, 'documents/home.html', context)


@login_required
def document_list(request):
    # This view might be admin-focused or a general list.
    # For now, it shows documents based on ownership or superuser status.
    # For a true "all documents I can see" list, Guardian's get_objects_for_user is better.
    if not (request.user.is_superuser or (hasattr(request.user, 'profile') and request.user.profile.is_admin)):
        # If not admin, maybe show only their documents or redirect?
        # For now, let's assume it's an admin view as per original comment in urls.py
        messages.warning(request, "Ta lista dokumentów jest dostępna dla administratorów.")
        # return redirect('documents:home')
        # Or, filter to show only documents the user has *some* permission for (more complex)
        documents_qs = get_objects_for_user(request.user, 'documents.browse_document', klass=Document, use_groups=True, with_superuser=False)
        documents_qs = documents_qs.filter(usunieto=False).select_related('wlasciciel__profile', 'folder').prefetch_related('tagi')
    else:
        documents_qs = Document.objects.filter(usunieto=False).select_related('wlasciciel__profile', 'folder').prefetch_related('tagi')

    search_query = request.GET.get('search', '')
    if search_query:
        documents_qs = documents_qs.filter(
            Q(nazwa__icontains=search_query) | Q(opis__icontains=search_query) | Q(tagi__nazwa__icontains=search_query)
        ).distinct()
    
    folder_id_filter = request.GET.get('folder')
    if folder_id_filter:
        documents_qs = documents_qs.filter(folder_id=folder_id_filter)
    
    tag_id_filter = request.GET.get('tag')
    if tag_id_filter:
        documents_qs = documents_qs.filter(tagi__id=tag_id_filter)
    
    file_type_filter = request.GET.get('file_type')
    if file_type_filter:
        # ... (file type filtering logic remains the same)
        if file_type_filter == 'pdf': documents_qs = documents_qs.filter(typ_pliku__contains='pdf')
        elif file_type_filter == 'word': documents_qs = documents_qs.filter(Q(typ_pliku__contains='word') | Q(nazwa__endswith='.docx') | Q(nazwa__endswith='.doc'))
        elif file_type_filter == 'excel': documents_qs = documents_qs.filter(Q(typ_pliku__contains='excel') | Q(nazwa__endswith='.xlsx') | Q(nazwa__endswith='.xls'))
        elif file_type_filter == 'text': documents_qs = documents_qs.filter(Q(typ_pliku__contains='text') | Q(nazwa__endswith='.txt'))
        elif file_type_filter == 'image': documents_qs = documents_qs.filter(Q(typ_pliku__contains='image') | Q(nazwa__endswith='.png') | Q(nazwa__endswith='.jpg') | Q(nazwa__endswith='.jpeg'))


    paginator = Paginator(documents_qs, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    for doc_item in page_obj:
        doc_item.current_user_can_edit = user_can_edit_document(request.user, doc_item)
        doc_item.current_user_can_delete = user_can_delete_document(request.user, doc_item)

    # Folders and Tags for filtering dropdowns
    if request.user.is_superuser or (hasattr(request.user, 'profile') and request.user.profile.is_admin):
        folders_for_filter = Folder.objects.all().order_by('nazwa')
    else:
        folders_for_filter = Folder.objects.filter(wlasciciel=request.user).order_by('nazwa') # Or folders they can view
    
    tags_for_filter = Tag.objects.all().order_by('nazwa')
    
    context = {
        'page_obj': page_obj,
        'search_query': search_query,
        'folders': folders_for_filter,
        'tags': tags_for_filter,
        'selected_folder': folder_id_filter,
        'selected_tag': tag_id_filter,
        'selected_file_type': file_type_filter,
        'user_can_create_documents': user_can_create_document(request.user),
    }
    return render(request, 'documents/document_list.html', context)


@login_required
def document_detail(request, pk):
    document = get_object_or_404(
        Document.objects.prefetch_related(
            'tagi', 'wlasciciel__profile', 'folder',
            'wersje__utworzony_przez__profile',
            Prefetch('komentarze', queryset=Comment.objects.filter(rodzic=None, aktywny=True).select_related('uzytkownik__profile').order_by('data_utworzenia')),
            'metadane'
        ),
        pk=pk, usunieto=False
    )

    if not user_can_view_document(request.user, document):
        raise PermissionDenied("Nie masz uprawnień do tego dokumentu.")

    comment_form = CommentForm()
    if request.method == 'POST' and 'submit_comment' in request.POST:
        if not user_can_comment_on_document(request.user, document):
            messages.error(request, "Nie masz uprawnień do komentowania tego dokumentu.")
            return redirect('documents:document_detail', pk=document.pk)
        
        posted_comment_form = CommentForm(request.POST)
        if posted_comment_form.is_valid():
            new_comment = posted_comment_form.save(commit=False)
            new_comment.dokument = document
            new_comment.uzytkownik = request.user
            new_comment.save()
            messages.success(request, 'Komentarz został dodany pomyślnie.')
            ActivityLog.objects.create(
                uzytkownik=request.user, typ_aktywnosci='komentarz', dokument=document,
                szczegoly=f"Dodano komentarz do dokumentu {document.nazwa}", adres_ip=get_client_ip(request)
            )
            return redirect('documents:document_detail', pk=document.pk)
        else:
            comment_form = posted_comment_form
            messages.error(request, 'Wystąpił błąd podczas dodawania komentarza.')

    if request.method == 'GET':
        ActivityLog.objects.create(
            uzytkownik=request.user, typ_aktywnosci='pobieranie', dokument=document,
            szczegoly=f"Wyświetlenie dokumentu {document.nazwa}", adres_ip=get_client_ip(request)
        )

    context = {
    'document': document,
    'versions': document.wersje.all(),
    'comments': document.komentarze.all(),
    'metadata': document.metadane.all(),
    'can_edit': user_can_edit_document(request.user, document),
    'can_delete': user_can_delete_document(request.user, document),
    'can_download': user_can_view_document(request.user, document),  # dla pobierania
    'user_can_comment': user_can_comment_on_document(request.user, document),
    'can_share': user_can_share_document(request.user, document),
    'comment_form': comment_form,
}
    return render(request, 'documents/document_detail.html', context)


@login_required
def document_upload(request, folder_id=None):
    target_folder = None
    if folder_id:
        target_folder = get_object_or_404(Folder, pk=folder_id)
        # Permission to add to this specific folder (can be more granular)
        if not user_can_view_folder(request.user, target_folder): # At least view to upload into
            raise PermissionDenied("Nie masz uprawnień do tego folderu.")

    if not user_can_create_document(request.user):
        messages.error(request, "Nie masz uprawnień do dodawania dokumentów.")
        return redirect('documents:home' if not folder_id else ('documents:folder_view', folder_id))

    if request.method == 'POST':
        form = DocumentUploadForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            document = form.save(commit=False)
            document.wlasciciel = request.user
            if target_folder:
                document.folder = target_folder
            document.save()
            form.save_m2m()

            # Assign default owner permissions
            assign_perm('browse_document', request.user, document)
            assign_perm('change_document', request.user, document)
            assign_perm('delete_document', request.user, document)
            assign_perm('share_document', request.user, document)
            assign_perm('download_document', request.user, document)
            assign_perm('comment_document', request.user, document)

            ActivityLog.objects.create(
                uzytkownik=request.user, typ_aktywnosci='tworzenie', dokument=document,
                szczegoly=f"Utworzono dokument {document.nazwa}" + (f" w folderze {target_folder.nazwa}" if target_folder else ""),
                adres_ip=get_client_ip(request)
            )
            messages.success(request, f'Dokument "{document.nazwa}" został dodany.')
            return redirect('documents:folder_view', folder_id=document.folder.id) if document.folder else redirect('documents:home')
        else:
            messages.error(request, "Popraw błędy w formularzu.")
    else:
        form = DocumentUploadForm(user=request.user)
        if target_folder:
            form.fields['folder'].initial = target_folder
            form.fields['folder'].widget.attrs['disabled'] = True # If uploading to specific folder, don't allow change

    context = {'form': form, 'target_folder': target_folder}
    return render(request, 'documents/document_upload.html', context)


@login_required
def document_edit(request, pk):
    document = get_object_or_404(Document.objects.select_related('wlasciciel__profile'), pk=pk, usunieto=False)
    if not user_can_edit_document(request.user, document):
        raise PermissionDenied("Nie masz uprawnień do edycji tego dokumentu.")

    if request.method == 'POST':
        form = DocumentUpdateForm(request.POST, instance=document, user=request.user)
        if form.is_valid():
            form.save()
            ActivityLog.objects.create(
                uzytkownik=request.user, typ_aktywnosci='edycja', dokument=document,
                szczegoly=f"Edytowano metadane dokumentu {document.nazwa}", adres_ip=get_client_ip(request)
            )
            messages.success(request, f'Dokument "{document.nazwa}" został zaktualizowany.')
            return redirect('documents:document_detail', pk=pk)
    else:
        form = DocumentUpdateForm(instance=document, user=request.user)
    
    context = {'form': form, 'document': document}
    return render(request, 'documents/document_edit.html', context)


@login_required
def document_delete(request, pk):
    document = get_object_or_404(Document.objects.select_related('wlasciciel__profile', 'folder'), pk=pk, usunieto=False)
    if not user_can_delete_document(request.user, document):
        raise PermissionDenied("Nie masz uprawnień do usunięcia tego dokumentu.")

    if request.method == 'POST':
        # Final confirmation from form might be good here
        # if request.POST.get('final_confirm') == 'yes': # From document_delete.html
        document_name = document.nazwa
        folder_id = document.folder.id if document.folder else None
        ActivityLog.objects.create(
            uzytkownik=request.user, typ_aktywnosci='usuniecie',
            szczegoly=f"Usunięto dokument {document_name}", adres_ip=get_client_ip(request)
        )
        document.usunieto = True # Soft delete
        document.save()
        messages.success(request, f'Dokument "{document_name}" został usunięty.')
        return redirect('documents:folder_view', folder_id=folder_id) if folder_id else redirect('documents:home')
        # else:
        #     messages.warning(request, "Usunięcie nie zostało potwierdzone.")
        #     return redirect('documents:document_delete', pk=pk)


    context = {'document': document}
    return render(request, 'documents/document_delete.html', context)


@login_required
def document_version_upload(request, pk):
    document = get_object_or_404(Document.objects.select_related('wlasciciel__profile').prefetch_related('wersje'), pk=pk, usunieto=False)
    if not user_can_edit_document(request.user, document): # Editing document implies can upload version
        raise PermissionDenied("Nie masz uprawnień do dodawania nowej wersji tego dokumentu.")

    if request.method == 'POST':
        form = DocumentVersionUploadForm(request.POST, request.FILES)
        if form.is_valid():
            latest_version = document.wersje.order_by('-numer_wersji').first()
            new_version_number = (latest_version.numer_wersji + 1) if latest_version else 1
            
            version = DocumentVersion.objects.create(
                dokument=document, numer_wersji=new_version_number,
                utworzony_przez=request.user, plik=form.cleaned_data['plik'],
                komentarz=form.cleaned_data['komentarz']
            )
            document.plik = version.plik
            document.rozmiar_pliku = version.rozmiar_pliku
            document.save() # This also updates ostatnia_modyfikacja

            ActivityLog.objects.create(
                uzytkownik=request.user, typ_aktywnosci='edycja', dokument=document,
                szczegoly=f"Utworzono wersję {new_version_number} dokumentu {document.nazwa}", adres_ip=get_client_ip(request)
            )
            messages.success(request, f'Utworzono nową wersję ({new_version_number}) dokumentu.')
            return redirect('documents:document_detail', pk=pk)
    else:
        form = DocumentVersionUploadForm()
    
    context = {'form': form, 'document': document}
    return render(request, 'documents/document_version_upload.html', context)


@login_required
def folder_list(request):
    # Similar to document_list, this could be admin-focused or show folders user can view
    if not (request.user.is_superuser or (hasattr(request.user, 'profile') and request.user.profile.is_admin)):
        messages.warning(request, "Ta lista folderów jest dostępna dla administratorów.")
        # return redirect('documents:home')
        root_folders_qs = get_objects_for_user(request.user, 'documents.browse_folder', klass=Folder).filter(rodzic=None)
    else:
        root_folders_qs = Folder.objects.filter(rodzic=None)

    root_folders_qs = root_folders_qs.select_related('wlasciciel__profile').prefetch_related(
        'tagi', 
        Prefetch('podkatalogi', queryset=Folder.objects.select_related('wlasciciel__profile').prefetch_related('tagi'))
    )
    
    for folder_item in root_folders_qs:
        folder_item.current_user_can_edit = user_can_edit_folder(request.user, folder_item)
        folder_item.current_user_can_delete = user_can_delete_folder(request.user, folder_item)
        for sub_folder in folder_item.podkatalogi.all(): # Assuming prefetch worked
            sub_folder.current_user_can_edit = user_can_edit_folder(request.user, sub_folder)
            sub_folder.current_user_can_delete = user_can_delete_folder(request.user, sub_folder)


    # For statistics card
    user_folders_count = Folder.objects.filter(wlasciciel=request.user).count()


    context = {
        'root_folders': root_folders_qs,
        'user_can_create_folders': user_can_create_folder(request.user),
        'user_folders_count': user_folders_count, # For stats card
        }
    return render(request, 'documents/folder_list.html', context)


@login_required
def folder_create(request, parent_id=None):
    parent_folder = None
    if parent_id:
        parent_folder = get_object_or_404(Folder, pk=parent_id)
        if not user_can_view_folder(request.user, parent_folder): # Need to view parent to create subfolder
            raise PermissionDenied("Nie masz uprawnień do tego folderu nadrzędnego.")

    if not user_can_create_folder(request.user):
        messages.error(request, "Nie masz uprawnień do tworzenia folderów.")
        return redirect('documents:home' if not parent_id else ('documents:folder_view', parent_id))

    if request.method == 'POST':
        form = FolderCreateForm(request.POST, user=request.user) # Pass user to form for queryset filtering if needed
        if form.is_valid():
            new_folder = form.save(commit=False)
            new_folder.wlasciciel = request.user
            if parent_folder:
                new_folder.rodzic = parent_folder
            new_folder.save()
            form.save_m2m() # For tags

            # Assign default owner permissions
            assign_perm('browse_folder', request.user, new_folder)
            assign_perm('change_folder', request.user, new_folder)
            assign_perm('delete_folder', request.user, new_folder)
            # assign_perm('add_document_to_folder', request.user, new_folder)
            # assign_perm('add_subfolder_to_folder', request.user, new_folder)

            ActivityLog.objects.create(
                uzytkownik=request.user, typ_aktywnosci='tworzenie', folder=new_folder,
                szczegoly=f"Utworzono folder {new_folder.nazwa}" + (f" w folderze {parent_folder.nazwa}" if parent_folder else ""),
                adres_ip=get_client_ip(request)
            )
            messages.success(request, f'Folder "{new_folder.nazwa}" został utworzony.')
            return redirect('documents:folder_view', folder_id=new_folder.id)
    else:
        form = FolderCreateForm(user=request.user)
        if parent_folder:
            form.fields['rodzic'].initial = parent_folder
            form.fields['rodzic'].widget.attrs['disabled'] = True

    context = {'form': form, 'parent_folder': parent_folder}
    return render(request, 'documents/folder_create.html', context)


@login_required
def folder_edit(request, pk):
    folder = get_object_or_404(Folder.objects.select_related('wlasciciel__profile'), pk=pk)
    if not user_can_edit_folder(request.user, folder):
        raise PermissionDenied("Nie masz uprawnień do edycji tego folderu.")

    if request.method == 'POST':
        form = FolderUpdateForm(request.POST, instance=folder, user=request.user)
        if form.is_valid():
            updated_folder = form.save()
            ActivityLog.objects.create(
                uzytkownik=request.user, typ_aktywnosci='edycja', folder=updated_folder,
                szczegoly=f"Edytowano folder {updated_folder.nazwa}", adres_ip=get_client_ip(request)
            )
            messages.success(request, f'Folder "{updated_folder.nazwa}" został zaktualizowany.')
            return redirect('documents:folder_view', folder_id=updated_folder.id)
    else:
        form = FolderUpdateForm(instance=folder, user=request.user)
    
    context = {'form': form, 'folder': folder}
    return render(request, 'documents/folder_edit.html', context)


@login_required
def folder_delete(request, pk):
    folder = get_object_or_404(Folder.objects.select_related('wlasciciel__profile', 'rodzic').prefetch_related('documents', 'podkatalogi'), pk=pk)
    if not user_can_delete_folder(request.user, folder):
        raise PermissionDenied("Nie masz uprawnień do usunięcia tego folderu.")

    documents_count = folder.documents.filter(usunieto=False).count()
    subfolders_count = folder.podkatalogi.count() # Assumes podkatalogi is the related_name

    if request.method == 'POST':
        form = FolderDeleteForm(request.POST, user=request.user, folder=folder)
        if form.is_valid():
            action = form.cleaned_data['action']
            target_folder_form = form.cleaned_data.get('target_folder')
            folder_name = folder.nazwa
            details = f"Próba usunięcia folderu {folder_name} z akcją: {action}."

            try:
                if action == 'move_to_parent':
                    parent = folder.rodzic
                    moved_docs = folder.documents.filter(usunieto=False).update(folder=parent)
                    moved_folders = folder.podkatalogi.update(rodzic=parent)
                    details = f"Usunięto folder {folder_name}. Przeniesiono {moved_docs} dok. i {moved_folders} podf. do nadrzędnego."
                elif action == 'move_to_folder':
                    moved_docs = folder.documents.filter(usunieto=False).update(folder=target_folder_form)
                    moved_folders = folder.podkatalogi.update(rodzic=target_folder_form)
                    details = f"Usunięto folder {folder_name}. Przeniesiono {moved_docs} dok. i {moved_folders} podf. do {target_folder_form.nazwa}."
                elif action == 'delete_all':
                    # Documents marked as usunieto=True
                    deleted_docs_count = folder.documents.filter(usunieto=False).update(usunieto=True)
                    # Subfolders will be deleted by cascade if Folder.rodzic on_delete=models.CASCADE
                    # If not, you'd need to recursively delete subfolders here or ensure models.CASCADE.
                    details = f"Usunięto folder {folder_name} wraz z {deleted_docs_count} dok. i {subfolders_count} podfolderami."

                ActivityLog.objects.create(
                    uzytkownik=request.user, typ_aktywnosci='usuniecie',
                    szczegoly=details, adres_ip=get_client_ip(request)
                )
                
                folder_parent_id_for_redirect = folder.rodzic.id if folder.rodzic else None
                folder.delete() # This will trigger cascade for subfolders if on_delete=CASCADE
                
                messages.success(request, f'Folder "{folder_name}" został pomyślnie usunięty.')
                return redirect('documents:folder_view', folder_id=folder_parent_id_for_redirect) if folder_parent_id_for_redirect else redirect('documents:home')

            except Exception as e:
                messages.error(request, f'Błąd podczas usuwania folderu: {str(e)}')
                # Log the exception e for debugging
    else:
        form = FolderDeleteForm(user=request.user, folder=folder)

    context = {
        'folder': folder, 'form': form,
        'documents_count': documents_count, 'subfolders_count': subfolders_count
    }
    return render(request, 'documents/folder_delete.html', context)


# AJAX Search and other APIs remain largely the same,
# but ensure their internal queries respect permissions if they list/access sensitive data.
# For search_documents, the existing owner/superuser check is a basic filter.
# A full permission-aware search would use get_objects_for_user.

@login_required
def search_documents(request):
    query = request.GET.get('q', '')
    results_data = []
    if len(query) >= 2: # Minimum query length
        # Get documents user is allowed to browse
        allowed_documents = get_objects_for_user(
            request.user,
            'documents.browse_document',
            klass=Document
        ).filter(usunieto=False)

        # Further filter by the search query
        searched_documents = allowed_documents.filter(
            Q(nazwa__icontains=query) |
            Q(opis__icontains=query) |
            Q(tagi__nazwa__icontains=query)
        ).distinct()[:10] # Limit results

        for doc in searched_documents:
            results_data.append({
                'id': doc.id,
                'nazwa': doc.nazwa,
                'typ_pliku': doc.typ_pliku,
                'rozmiar': doc.get_file_size_display(),
                'url': reverse('documents:document_detail', args=[doc.id]),
                'download_url': reverse('documents:document_download', args=[doc.id]),
                'icon': doc.get_file_icon(),
                'folder_path': doc.folder.get_full_path() if doc.folder else "Główny",
            })
    return JsonResponse({'results': results_data})

# contact_email_api and document_stats can remain as they are,
# as document_stats already filters by owner or shows all for admin.

@login_required
def document_download(request, pk):
    """Download document file"""
    document = get_object_or_404(Document, pk=pk, usunieto=False)

    # Check permissions (using your existing permission function)
    if not user_can_view_document(request.user, document): # Or a more specific download permission
        raise PermissionDenied("Nie masz uprawnień do pobrania tego dokumentu.")

    if not document.plik:
        raise Http404("Plik nie został znaleziony.")

    try:
        # Log download activity
        ActivityLog.objects.create(
            uzytkownik=request.user,
            typ_aktywnosci='pobieranie',
            dokument=document,
            szczegoly=f"Pobranie dokumentu {document.nazwa}",
            adres_ip=get_client_ip(request)
        )

        # Serve file
        response = FileResponse(
            document.plik.open('rb'),
            as_attachment=True,
            filename=document.nazwa # Use the document's name for the downloaded file
        )
        return response

    except FileNotFoundError:
        # This might happen if the file reference in the DB is stale
        # or the file was deleted from the filesystem without updating the DB.
        messages.error(request, "Plik dokumentu nie został znaleziony na serwerze.")
        # Redirect to document detail or a relevant error page
        return redirect('documents:document_detail', pk=document.pk)
    except Exception as e:
        # Log other potential errors during file serving
        messages.error(request, f"Wystąpił nieoczekiwany błąd podczas próby pobrania pliku: {e}")
        return redirect('documents:document_detail', pk=document.pk)

@login_required
def document_preview(request, pk):
    """Preview document in browser (for supported file types)"""
    document = get_object_or_404(Document, pk=pk, usunieto=False)

    # Check permissions
    if not user_can_view_document(request.user, document):
        raise PermissionDenied("Nie masz uprawnień do tego dokumentu.")

    if not document.plik:
        raise Http404("Plik nie został znaleziony.")

    # Assuming your Document model has a method like can_preview()
    if not document.can_preview():
        messages.warning(request, "Ten typ pliku nie może być wyświetlony w przeglądarce.")
        return redirect('documents:document_detail', pk=pk)

    try:
        # Determine content type
        content_type, encoding = mimetypes.guess_type(document.plik.name)
        if not content_type:
            # Fallback if mimetypes can't guess, you might have stored it on the model
            content_type = document.typ_pliku # Assuming typ_pliku is a basic MIME type
            if not content_type: # Further fallback
                 content_type = 'application/octet-stream'


        # Serve file for preview
        response = FileResponse(
            document.plik.open('rb'),
            content_type=content_type
        )
        # 'inline' suggests to the browser to display it if possible, rather than download
        response['Content-Disposition'] = f'inline; filename="{document.nazwa}"'
        return response

    except FileNotFoundError:
        messages.error(request, "Plik dokumentu nie został znaleziony na serwerze.")
        return redirect('documents:document_detail', pk=document.pk)
    except Exception as e:
        messages.error(request, f"Wystąpił błąd podczas próby podglądu pliku: {e}")
        return redirect('documents:document_detail', pk=document.pk)

@login_required
def document_version_download(request, document_pk, version_pk):
    """Download specific version of document file"""
    document = get_object_or_404(Document, pk=document_pk, usunieto=False)
    version = get_object_or_404(DocumentVersion, pk=version_pk, dokument=document)

    # Check permissions (user must be able to view the document)
    if not user_can_view_document(request.user, document):
        raise PermissionDenied("Nie masz uprawnień do pobrania tego dokumentu.")

    if not version.plik:
        raise Http404("Plik wersji nie został znaleziony.")

    try:
        # Log download activity
        ActivityLog.objects.create(
            uzytkownik=request.user,
            typ_aktywnosci='pobieranie',
            dokument=document,
            szczegoly=f"Pobranie wersji {version.numer_wersji} dokumentu {document.nazwa}",
            adres_ip=get_client_ip(request)
        )

        # Serve file with version info in filename
        base_name = os.path.splitext(document.nazwa)[0]
        ext = os.path.splitext(document.nazwa)[1]
        version_filename = f"{base_name}_v{version.numer_wersji}{ext}"

        response = FileResponse(
            version.plik.open('rb'),
            as_attachment=True,
            filename=version_filename
        )
        return response

    except FileNotFoundError:
        messages.error(request, "Plik wersji nie został znaleziony na serwerze.")
        return redirect('documents:document_detail', pk=document.pk)
    except Exception as e:
        messages.error(request, f"Wystąpił błąd podczas próby pobrania pliku: {e}")
        return redirect('documents:document_detail', pk=document.pk)