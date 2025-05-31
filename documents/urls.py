from django.urls import path
from . import views

app_name = 'documents'

urlpatterns = [
    # Home/Dashboard
    path('', views.home, name='home'),
    path('folder/<int:folder_id>/', views.home, name='folder_view'),
    
    # Documents (admin only)
    path('admin/documents/', views.document_list, name='document_list'),
    path('documents/upload/', views.document_upload, name='document_upload'),
    path('documents/upload/<int:folder_id>/', views.document_upload, name='document_upload_to_folder'),
    path('documents/<int:pk>/', views.document_detail, name='document_detail'),
    path('documents/<int:pk>/edit/', views.document_edit, name='document_edit'),
    path('documents/<int:pk>/delete/', views.document_delete, name='document_delete'),
    path('documents/<int:pk>/download/', views.document_download, name='document_download'),
    path('documents/<int:pk>/preview/', views.document_preview, name='document_preview'),
    path('documents/<int:pk>/version/upload/', views.document_version_upload, name='document_version_upload'),
    
    # Folders (admin only)
    path('admin/folders/', views.folder_list, name='folder_list'),
    path('folders/create/', views.folder_create, name='folder_create'),
    path('folders/create/<int:parent_id>/', views.folder_create, name='folder_create_in_parent'),
    path('folders/<int:pk>/edit/', views.folder_edit, name='folder_edit'),
    path('folders/<int:pk>/delete/', views.folder_delete, name='folder_delete'),
    
    # Search and API
    path('search/', views.search_documents, name='search_documents'),
]