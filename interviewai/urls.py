# interviewai/urls.py
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('interviews.urls')),
    # NOTE: removed django.contrib.auth.urls — we handle login/logout ourselves
]