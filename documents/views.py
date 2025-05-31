from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse, Http404, FileResponse
from django.core.paginator import Paginator
from django.db.models import Q
from django.core.exceptions import PermissionDenied
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views import View
from django.conf import settings
from guardian.decorators import permission_required_or_403
from guardian.shortcuts import get_objects_for_user, assign_perm
from .models import Document, Folder, Tag, SystemSettings, DocumentVersion, ActivityLog
from .forms import (
    DocumentUploadForm, FolderCreateForm, DocumentUpdateForm, 
    DocumentVersionUploadForm, FolderUpdateForm, FolderDeleteForm
)
from users.models import UserProfile
from users.permissions import (
    user_can_view_document, user_can_edit_document, 
    user_can_delete_document, user_can_view_folder, user_can_manage_folder
)
import os
import mimetypes
from datetime import datetime


def home(request, folder_id=None):
    """New dashboard with file explorer style"""
    current_folder = None
    breadcrumbs = []
    
    # Get current folder if specified
    if folder_id:
        current_folder = get_object_or_404(Folder, pk=folder_id)
        # Check permissions
        if not user_can_view_folder(request.user, current_folder):
            messages.error(request, "Nie masz uprawnień do tego folderu.")
            return redirect('documents:home')
        
        # Build breadcrumbs
        temp_folder = current_folder
        while temp_folder:
            breadcrumbs.insert(0, temp_folder)
            temp_folder = temp_folder.rodzic
    
    if request.user.is_authenticated:
        # Get folders in current location
        if current_folder:
            if request.user.is_superuser or request.user.profile.is_admin:
                folders = Folder.objects.filter(rodzic=current_folder).order_by('nazwa')
                documents = Document.objects.filter(
                    folder=current_folder, usunieto=False
                ).select_related('wlasciciel').order_by('nazwa')
            else:
                folders = Folder.objects.filter(
                    rodzic=current_folder, wlasciciel=request.user
                ).order_by('nazwa')
                documents = Document.objects.filter(
                    folder=current_folder, wlasciciel=request.user, usunieto=False
                ).select_related('wlasciciel').order_by('nazwa')
        else:
            # Root level - show only items in root folders or without folder
            if request.user.is_superuser or request.user.profile.is_admin:
                folders = Folder.objects.filter(rodzic=None).order_by('nazwa')
                # Show documents that are in root folders or have no folder assigned
                documents = Document.objects.filter(
                    Q(folder__rodzic=None) | Q(folder=None), 
                    usunieto=False
                ).select_related('wlasciciel', 'folder').order_by('nazwa')
            else:
                folders = Folder.objects.filter(
                    rodzic=None, wlasciciel=request.user
                ).order_by('nazwa')
                documents = Document.objects.filter(
                    Q(folder__rodzic=None, wlasciciel=request.user) | Q(folder=None, wlasciciel=request.user),
                    usunieto=False
                ).select_related('wlasciciel', 'folder').order_by('nazwa')
        
        # Add folder stats for each folder
        for folder in folders:
            folder.doc_count = folder.documents.filter(usunieto=False).count()
            folder.subfolder_count = folder.podkatalogi.count()
        
        # Quick stats
        if request.user.is_superuser or request.user.profile.is_admin:
            total_documents = Document.objects.filter(usunieto=False).count()
            total_folders = Folder.objects.count()
            total_size = sum(doc.rozmiar_pliku or 0 for doc in Document.objects.filter(usunieto=False))
        else:
            user_documents = Document.objects.filter(wlasciciel=request.user, usunieto=False)
            total_documents = user_documents.count()
            total_folders = Folder.objects.filter(wlasciciel=request.user).count()
            total_size = sum(doc.rozmiar_pliku or 0 for doc in user_documents)
        
    else:
        folders = []
        documents = []
        total_documents = 0
        total_folders = 0
        total_size = 0
    
    # Convert size to human readable
    def human_readable_size(size_bytes):
        if size_bytes == 0:
            return "0 B"
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"
    
    context = {
        'current_folder': current_folder,
        'breadcrumbs': breadcrumbs,
        'folders': folders,
        'documents': documents,
        'total_documents': total_documents,
        'total_folders': total_folders,
        'total_size': human_readable_size(total_size),
        'is_root': current_folder is None,
    }
    return render(request, 'documents/home.html', context)


@login_required
def document_list(request):
    """List all documents with search and filtering"""
    # Get documents user can view
    if request.user.is_superuser or request.user.profile.is_admin:
        documents = Document.objects.filter(usunieto=False).select_related('wlasciciel', 'folder')
    else:
        documents = Document.objects.filter(
            wlasciciel=request.user, usunieto=False
        ).select_related('wlasciciel', 'folder')
    
    # Search functionality
    search_query = request.GET.get('search', '')
    if search_query:
        documents = documents.filter(
            Q(nazwa__icontains=search_query) |
            Q(opis__icontains=search_query) |
            Q(tagi__nazwa__icontains=search_query)
        ).distinct()
    
    # Filter by folder
    folder_id = request.GET.get('folder')
    if folder_id:
        documents = documents.filter(folder_id=folder_id)
    
    # Filter by tag
    tag_id = request.GET.get('tag')
    if tag_id:
        documents = documents.filter(tagi__id=tag_id)
    
    # Filter by file type
    file_type = request.GET.get('file_type')
    if file_type:
        if file_type == 'pdf':
            documents = documents.filter(typ_pliku__contains='pdf')
        elif file_type == 'word':
            documents = documents.filter(Q(typ_pliku__contains='word') | Q(nazwa__endswith='.docx') | Q(nazwa__endswith='.doc'))
        elif file_type == 'excel':
            documents = documents.filter(Q(typ_pliku__contains='excel') | Q(nazwa__endswith='.xlsx') | Q(nazwa__endswith='.xls'))
        elif file_type == 'text':
            documents = documents.filter(Q(typ_pliku__contains='text') | Q(nazwa__endswith='.txt'))
        elif file_type == 'image':
            documents = documents.filter(Q(typ_pliku__contains='image') | Q(nazwa__endswith='.png') | Q(nazwa__endswith='.jpg') | Q(nazwa__endswith='.jpeg'))
    
    # Pagination
    paginator = Paginator(documents, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get folders and tags user can see
    if request.user.is_superuser or request.user.profile.is_admin:
        folders = Folder.objects.all()
    else:
        folders = Folder.objects.filter(wlasciciel=request.user)
    
    tags = Tag.objects.all()
    
    context = {
        'page_obj': page_obj,
        'search_query': search_query,
        'folders': folders,
        'tags': tags,
        'selected_folder': folder_id,
        'selected_tag': tag_id,
        'selected_file_type': file_type,
    }
    return render(request, 'documents/document_list.html', context)


@login_required
def document_detail(request, pk):
    """Document detail view with permission checking"""
    document = get_object_or_404(Document, pk=pk, usunieto=False)
    
    # Check if user can view this document
    if not user_can_view_document(request.user, document):
        raise PermissionDenied("Nie masz uprawnień do tego dokumentu.")
    
    versions = document.wersje.all()
    comments = document.komentarze.filter(rodzic=None)  # Top-level comments only
    metadata = document.metadane.all()
    
    # Check what actions user can perform
    can_edit = user_can_edit_document(request.user, document)
    can_delete = user_can_delete_document(request.user, document)
    can_download = user_can_view_document(request.user, document)  # If can view, can download
    
    # Log view activity
    ActivityLog.objects.create(
        uzytkownik=request.user,
        typ_aktywnosci='pobieranie',  # Using existing choice
        dokument=document,
        szczegoly=f"Wyświetlenie dokumentu {document.nazwa}",
        adres_ip=get_client_ip(request)
    )
    
    context = {
        'document': document,
        'versions': versions,
        'comments': comments,
        'metadata': metadata,
        'can_edit': can_edit,
        'can_delete': can_delete,
        'can_download': can_download,
    }
    return render(request, 'documents/document_detail.html', context)


@login_required
def document_upload(request, folder_id=None):
    """Upload new document with optional folder parameter"""
    target_folder = None
    
    # Get target folder if specified
    if folder_id:
        target_folder = get_object_or_404(Folder, pk=folder_id)
        # Check permissions
        if not user_can_view_folder(request.user, target_folder):
            raise PermissionDenied("Nie masz uprawnień do tego folderu.")
    
    if request.method == 'POST':
        form = DocumentUploadForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            try:
                document = form.save(commit=False)
                document.wlasciciel = request.user
                
                # Set folder if specified
                if target_folder:
                    document.folder = target_folder
                
                document.save()
                
                # Save many-to-many relationships (tags)
                form.save_m2m()
                
                # Assign default permissions to owner
                assign_perm('browse_document', request.user, document)
                assign_perm('change_document', request.user, document)
                assign_perm('delete_document', request.user, document)
                assign_perm('share_document', request.user, document)
                assign_perm('download_document', request.user, document)
                
                # Log creation activity
                ActivityLog.objects.create(
                    uzytkownik=request.user,
                    typ_aktywnosci='tworzenie',
                    dokument=document,
                    szczegoly=f"Utworzono dokument {document.nazwa}" + 
                             (f" w folderze {target_folder.nazwa}" if target_folder else ""),
                    adres_ip=get_client_ip(request)
                )
                
                messages.success(request, f'Dokument "{document.nazwa}" został dodany pomyślnie.')
                
                # Redirect back to folder or home
                if target_folder:
                    return redirect('documents:folder_view', folder_id=target_folder.id)
                else:
                    return redirect('documents:home')
                
            except Exception as e:
                messages.error(request, f'Błąd podczas dodawania dokumentu: {str(e)}')
    else:
        form = DocumentUploadForm(user=request.user)
        
        # Pre-select target folder if specified
        if target_folder:
            form.fields['folder'].initial = target_folder
    
    context = {
        'form': form,
        'target_folder': target_folder,
    }
    return render(request, 'documents/document_upload.html', context)


@login_required
def document_download(request, pk):
    """Download document file"""
    document = get_object_or_404(Document, pk=pk, usunieto=False)
    
    # Check permissions
    if not user_can_view_document(request.user, document):
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
            filename=document.nazwa
        )
        return response
        
    except FileNotFoundError:
        raise Http404("Plik nie został znaleziony na serwerze.")


@login_required
def document_preview(request, pk):
    """Preview document in browser (for supported file types)"""
    document = get_object_or_404(Document, pk=pk, usunieto=False)
    
    # Check permissions
    if not user_can_view_document(request.user, document):
        raise PermissionDenied("Nie masz uprawnień do tego dokumentu.")
    
    if not document.plik:
        raise Http404("Plik nie został znaleziony.")
    
    if not document.can_preview():
        messages.warning(request, "Ten typ pliku nie może być wyświetlony w przeglądarce.")
        return redirect('documents:document_detail', pk=pk)
    
    try:
        # Determine content type
        content_type = mimetypes.guess_type(document.plik.name)[0]
        if not content_type:
            content_type = document.typ_pliku
        
        # Serve file for preview
        response = FileResponse(
            document.plik.open('rb'),
            content_type=content_type
        )
        response['Content-Disposition'] = f'inline; filename="{document.nazwa}"'
        return response
        
    except FileNotFoundError:
        raise Http404("Plik nie został znaleziony na serwerze.")


@login_required
def document_edit(request, pk):
    """Edit document metadata"""
    document = get_object_or_404(Document, pk=pk, usunieto=False)
    
    # Check permissions
    if not user_can_edit_document(request.user, document):
        raise PermissionDenied("Nie masz uprawnień do edycji tego dokumentu.")
    
    if request.method == 'POST':
        form = DocumentUpdateForm(request.POST, instance=document, user=request.user)
        if form.is_valid():
            form.save()
            
            # Log edit activity
            ActivityLog.objects.create(
                uzytkownik=request.user,
                typ_aktywnosci='edycja',
                dokument=document,
                szczegoly=f"Edytowano metadane dokumentu {document.nazwa}",
                adres_ip=get_client_ip(request)
            )
            
            messages.success(request, f'Dokument "{document.nazwa}" został zaktualizowany.')
            return redirect('documents:document_detail', pk=pk)
    else:
        form = DocumentUpdateForm(instance=document, user=request.user)
    
    context = {
        'form': form,
        'document': document,
    }
    return render(request, 'documents/document_edit.html', context)


@login_required
def document_delete(request, pk):
    """Delete document"""
    document = get_object_or_404(Document, pk=pk, usunieto=False)
    
    # Check permissions
    if not user_can_delete_document(request.user, document):
        raise PermissionDenied("Nie masz uprawnień do usunięcia tego dokumentu.")
    
    if request.method == 'POST':
        document_name = document.nazwa
        folder_id = document.folder.id if document.folder else None
        
        # Log deletion activity before deleting
        ActivityLog.objects.create(
            uzytkownik=request.user,
            typ_aktywnosci='usuniecie',
            szczegoly=f"Usunięto dokument {document_name}",
            adres_ip=get_client_ip(request)
        )
        
        # Mark as deleted (soft delete)
        document.usunieto = True
        document.save()
        
        messages.success(request, f'Dokument "{document_name}" został usunięty.')
        
        # Redirect back to folder or home
        if folder_id:
            return redirect('documents:folder_view', folder_id=folder_id)
        else:
            return redirect('documents:home')
    
    context = {'document': document}
    return render(request, 'documents/document_delete.html', context)


@login_required
def document_version_upload(request, pk):
    """Upload new version of existing document"""
    document = get_object_or_404(Document, pk=pk, usunieto=False)
    
    # Check permissions
    if not user_can_edit_document(request.user, document):
        raise PermissionDenied("Nie masz uprawnień do edycji tego dokumentu.")
    
    if request.method == 'POST':
        form = DocumentVersionUploadForm(request.POST, request.FILES)
        if form.is_valid():
            # Create new version
            latest_version = document.wersje.first()
            new_version_number = (latest_version.numer_wersji + 1) if latest_version else 1
            
            version = DocumentVersion.objects.create(
                dokument=document,
                numer_wersji=new_version_number,
                utworzony_przez=request.user,
                plik=form.cleaned_data['plik'],
                komentarz=form.cleaned_data['komentarz']
            )
            
            # Update main document file
            document.plik = version.plik
            document.rozmiar_pliku = version.rozmiar_pliku
            document.save()
            
            # Log version creation
            ActivityLog.objects.create(
                uzytkownik=request.user,
                typ_aktywnosci='edycja',
                dokument=document,
                szczegoly=f"Utworzono wersję {new_version_number} dokumentu {document.nazwa}",
                adres_ip=get_client_ip(request)
            )
            
            messages.success(request, f'Utworzono nową wersję ({new_version_number}) dokumentu.')
            return redirect('documents:document_detail', pk=pk)
    else:
        form = DocumentVersionUploadForm()
    
    context = {
        'form': form,
        'document': document,
    }
    return render(request, 'documents/document_version_upload.html', context)


@login_required
def folder_list(request):
    """List all folders in tree structure"""
    if request.user.is_superuser or request.user.profile.is_admin:
        root_folders = Folder.objects.filter(rodzic=None).prefetch_related('podkatalogi')
    else:
        root_folders = Folder.objects.filter(
            rodzic=None, wlasciciel=request.user
        ).prefetch_related('podkatalogi')
    
    context = {'root_folders': root_folders}
    return render(request, 'documents/folder_list.html', context)


@login_required
def folder_create(request, parent_id=None):
    """Create new folder with optional parent parameter"""
    parent_folder = None
    
    # Get parent folder if specified
    if parent_id:
        parent_folder = get_object_or_404(Folder, pk=parent_id)
        # Check permissions
        if not user_can_view_folder(request.user, parent_folder):
            raise PermissionDenied("Nie masz uprawnień do tego folderu.")
    
    if request.method == 'POST':
        form = FolderCreateForm(request.POST, user=request.user)
        if form.is_valid():
            folder = form.save(commit=False)
            folder.wlasciciel = request.user
            
            # Set parent if specified
            if parent_folder:
                folder.rodzic = parent_folder
            
            folder.save()
            
            # Assign default permissions
            assign_perm('browse_folder', request.user, folder)
            assign_perm('change_folder', request.user, folder)
            assign_perm('delete_folder', request.user, folder)
            assign_perm('manage_folder', request.user, folder)
            
            # Log creation activity
            ActivityLog.objects.create(
                uzytkownik=request.user,
                typ_aktywnosci='tworzenie',
                folder=folder,
                szczegoly=f"Utworzono folder {folder.nazwa}" + 
                         (f" w folderze {parent_folder.nazwa}" if parent_folder else ""),
                adres_ip=get_client_ip(request)
            )
            
            messages.success(request, f'Folder "{folder.nazwa}" został utworzony.')
            
            # Redirect back to parent folder or home
            if parent_folder:
                return redirect('documents:folder_view', folder_id=parent_folder.id)
            else:
                return redirect('documents:home')
    else:
        form = FolderCreateForm(user=request.user)
        
        # Pre-select parent folder if specified
        if parent_folder:
            form.fields['rodzic'].initial = parent_folder
    
    context = {
        'form': form,
        'parent_folder': parent_folder,
    }
    return render(request, 'documents/folder_create.html', context)


@login_required
def folder_edit(request, pk):
    """Edit folder metadata"""
    folder = get_object_or_404(Folder, pk=pk)
    
    # Check permissions
    if not user_can_manage_folder(request.user, folder):
        raise PermissionDenied("Nie masz uprawnień do edycji tego folderu.")
    
    if request.method == 'POST':
        form = FolderUpdateForm(request.POST, instance=folder, user=request.user)
        if form.is_valid():
            form.save()
            
            # Log edit activity
            ActivityLog.objects.create(
                uzytkownik=request.user,
                typ_aktywnosci='edycja',
                folder=folder,
                szczegoly=f"Edytowano folder {folder.nazwa}",
                adres_ip=get_client_ip(request)
            )
            
            messages.success(request, f'Folder "{folder.nazwa}" został zaktualizowany.')
            
            # Redirect back to parent folder or home
            if folder.rodzic:
                return redirect('documents:folder_view', folder_id=folder.rodzic.id)
            else:
                return redirect('documents:home')
    else:
        form = FolderUpdateForm(instance=folder, user=request.user)
    
    context = {
        'form': form,
        'folder': folder,
    }
    return render(request, 'documents/folder_edit.html', context)


@login_required
def folder_delete(request, pk):
    """Delete folder with options for handling contents"""
    folder = get_object_or_404(Folder, pk=pk)
    
    # Check permissions
    if not user_can_manage_folder(request.user, folder):
        raise PermissionDenied("Nie masz uprawnień do usunięcia tego folderu.")
    
    # Get folder contents for display
    documents_count = folder.documents.filter(usunieto=False).count()
    subfolders_count = folder.podkatalogi.count()
    
    if request.method == 'POST':
        form = FolderDeleteForm(request.POST, user=request.user, folder=folder)
        if form.is_valid():
            action = form.cleaned_data['action']
            target_folder = form.cleaned_data.get('target_folder')
            
            folder_name = folder.nazwa
            
            try:
                # Handle folder contents based on selected action
                if action == 'move_to_parent':
                    # Move contents to parent folder
                    parent_folder = folder.rodzic
                    
                    # Move documents
                    moved_docs = folder.documents.filter(usunieto=False).update(folder=parent_folder)
                    
                    # Move subfolders
                    moved_folders = folder.podkatalogi.update(rodzic=parent_folder)
                    
                    details = f"Usunięto folder {folder_name}. Przeniesiono {moved_docs} dokumentów i {moved_folders} podfolderów do folderu nadrzędnego."
                
                elif action == 'move_to_folder':
                    # Move contents to specified folder
                    
                    # Move documents
                    moved_docs = folder.documents.filter(usunieto=False).update(folder=target_folder)
                    
                    # Move subfolders
                    moved_folders = folder.podkatalogi.update(rodzic=target_folder)
                    
                    details = f"Usunięto folder {folder_name}. Przeniesiono {moved_docs} dokumentów i {moved_folders} podfolderów do folderu {target_folder.nazwa}."
                
                elif action == 'delete_all':
                    # Delete all contents (cascade delete will handle this)
                    # First, mark documents as deleted (soft delete)
                    deleted_docs = folder.documents.filter(usunieto=False).count()
                    folder.documents.filter(usunieto=False).update(usunieto=True)
                    
                    # Subfolders will be deleted by cascade
                    details = f"Usunięto folder {folder_name} wraz z {deleted_docs} dokumentami i {subfolders_count} podfolderami."
                
                # Log deletion activity before deleting the folder
                ActivityLog.objects.create(
                    uzytkownik=request.user,
                    typ_aktywnosci='usuniecie',
                    szczegoly=details,
                    adres_ip=get_client_ip(request)
                )
                
                # Delete the folder
                folder_parent_id = folder.rodzic.id if folder.rodzic else None
                folder.delete()
                
                messages.success(request, f'Folder "{folder_name}" został usunięty.')
                
                # Redirect back to parent folder or home
                if folder_parent_id:
                    return redirect('documents:folder_view', folder_id=folder_parent_id)
                else:
                    return redirect('documents:home')
                
            except Exception as e:
                messages.error(request, f'Błąd podczas usuwania folderu: {str(e)}')
    else:
        form = FolderDeleteForm(user=request.user, folder=folder)
    
    context = {
        'folder': folder,
        'form': form,
        'documents_count': documents_count,
        'subfolders_count': subfolders_count,
    }
    return render(request, 'documents/folder_delete.html', context)


@login_required
def search_documents(request):
    """AJAX search for documents"""
    query = request.GET.get('q', '')
    if len(query) < 3:
        return JsonResponse({'results': []})
    
    # Search in documents user can view
    if request.user.is_superuser or request.user.profile.is_admin:
        documents = Document.objects.filter(
            Q(nazwa__icontains=query) | Q(opis__icontains=query) | Q(tagi__nazwa__icontains=query),
            usunieto=False
        ).distinct()[:10]
    else:
        documents = Document.objects.filter(
            Q(nazwa__icontains=query) | Q(opis__icontains=query) | Q(tagi__nazwa__icontains=query),
            wlasciciel=request.user,
            usunieto=False
        ).distinct()[:10]
    
    results = []
    for doc in documents:
        results.append({
            'id': doc.id,
            'nazwa': doc.nazwa,
            'typ_pliku': doc.typ_pliku,
            'rozmiar': doc.get_file_size_display(),
            'url': f'/documents/{doc.id}/',
            'download_url': f'/documents/{doc.id}/download/',
            'icon': doc.get_file_icon(),
        })
    
    return JsonResponse({'results': results})


def get_client_ip(request):
    """Get client IP address"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def contact_email_api(request):
    """API endpoint to get contact email from settings"""
    contact_email = SystemSettings.get_setting('CONTACT_EMAIL', 'admin@docmanager.com')
    return JsonResponse({'email': contact_email})


@login_required
def document_stats(request):
    """Document statistics API"""
    if request.user.is_superuser or request.user.profile.is_admin:
        total_docs = Document.objects.filter(usunieto=False).count()
        total_size = sum(doc.rozmiar_pliku for doc in Document.objects.filter(usunieto=False))
    else:
        user_docs = Document.objects.filter(wlasciciel=request.user, usunieto=False)
        total_docs = user_docs.count()
        total_size = sum(doc.rozmiar_pliku for doc in user_docs)
    
    return JsonResponse({
        'total_documents': total_docs,
        'total_size': total_size,
        'total_size_mb': round(total_size / (1024 * 1024), 2),
    })