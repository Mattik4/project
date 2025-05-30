from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect

urlpatterns = [
    # Admin
    path('admin/', admin.site.urls),
    
    # Applications
    path('', include('documents.urls')),
    path('users/', include('users.urls')),
    
    # Built-in auth views (fallback)
    path('accounts/', include('django.contrib.auth.urls')),
    
    # Redirect common auth URLs to our custom views
    path('login/', lambda request: redirect('users:login')),
    path('logout/', lambda request: redirect('users:logout')),
    path('register/', lambda request: redirect('users:register')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)