"""
URL configuration for Birnagar Municipality project.
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings

from core.views import (
    protected_media,
    error_400, error_403, error_404, error_500,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    # Media files — routed through protected_media gatekeeper (login required)
    path('media/<path:file_path>', protected_media, name='protected_media'),
    path('', include('core.urls')),
]

# Custom error handlers — active only when DEBUG=False.
# In development (DEBUG=True), Django shows its own debug error pages.
handler400 = error_400
handler403 = error_403
handler404 = error_404
handler500 = error_500
