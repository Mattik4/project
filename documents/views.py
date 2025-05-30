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
    DocumentVersionUploadForm
)
from users.models import UserProfile
from users.permissions import (
    user_can_view_document, user_can_edit_document, 
    user_can_delete_document, user_can_view_folder
)
import os
import mimetypes
from datetime import datetime


def home(request):
    """Home page with recent documents"""
    if request.user.is_authenticated:
        # Get documents user can view
        if request.user.is_superuser or request.user.profile.is_admin:
            recent_documents = Document.objects.filter(
                usunieto=False
            ).select_related('wlasciciel', 'folder').order_by('-ostatnia_modyfikacja')[:10]
            
            total_documents = Document.objects.filter(usunieto=False).count()
            total_folders = Folder.objects.count()
        else:
            # For regular users, show only documents they can view
            user_documents = Document.objects.filter(
                wlasciciel=request.user, usunieto=False
            ).select_related('wlasciciel', 'folder').order_by('-ostatnia_modyfikacja')[:10]
            
            recent_documents = user_documents
            total_documents = Document.objects.filter(wlasciciel=request.user, usunieto=False).count()
            total_folders = Folder.objects.filter(wlasciciel=request.user).count()
    else:
        recent_documents = []
        total_documents = 0
        total_folders = 0
    
    context = {
        'recent_documents': recent_documents,
        'total_documents': total_documents,
        'total_folders': total_folders,
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
def document_upload(request):
    """Upload new document"""
    if request.method == 'POST':
        form = DocumentUploadForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            try:
                document = form.save(commit=False)
                document.wlasciciel = request.user
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
                    szczegoly=f"Utworzono dokument {document.nazwa}",
                    adres_ip=get_client_ip(request)
                )
                
                messages.success(request, f'Dokument "{document.nazwa}" został dodany pomyślnie.')
                return redirect('documents:document_detail', pk=document.pk)
                
            except Exception as e:
                messages.error(request, f'Błąd podczas dodawania dokumentu: {str(e)}')
    else:
        form = DocumentUploadForm(user=request.user)
    
    context = {'form': form}
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
        return redirect('documents:document_list')
    
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


# Rest of the views remain the same as before...
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
def folder_create(request):
    """Create new folder"""
    if request.method == 'POST':
        form = FolderCreateForm(request.POST, user=request.user)
        if form.is_valid():
            folder = form.save(commit=False)
            folder.wlasciciel = request.user
            folder.save()
            
            # Assign default permissions
            assign_perm('browse_folder', request.user, folder)
            assign_perm('change_folder', request.user, folder)
            assign_perm('delete_folder', request.user, folder)
            assign_perm('manage_folder', request.user, folder)
            
            messages.success(request, f'Folder "{folder.nazwa}" został utworzony.')
            return redirect('documents:folder_list')
    else:
        form = FolderCreateForm(user=request.user)
    
    context = {'form': form}
    return render(request, 'documents/folder_create.html', context)


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