from django.urls import path
from . import views

app_name = 'documents'

urlpatterns = [
    # Home
    path('', views.home, name='home'),
    
    # Documents
    path('documents/', views.document_list, name='document_list'),
    path('documents/upload/', views.document_upload, name='document_upload'),
    path('documents/<int:pk>/', views.document_detail, name='document_detail'),
    path('documents/<int:pk>/edit/', views.document_edit, name='document_edit'),
    path('documents/<int:pk>/delete/', views.document_delete, name='document_delete'),
    path('documents/<int:pk>/download/', views.document_download, name='document_download'),
    path('documents/<int:pk>/preview/', views.document_preview, name='document_preview'),
    path('documents/<int:pk>/version/upload/', views.document_version_upload, name='document_version_upload'),
    
    # Folders
    path('folders/', views.folder_list, name='folder_list'),
    path('folders/create/', views.folder_create, name='folder_create'),
    
    # Search and API
    path('search/', views.search_documents, name='search_documents'),
    path('api/contact-email/', views.contact_email_api, name='contact_email_api'),
    path('api/stats/', views.document_stats, name='document_stats'),
]