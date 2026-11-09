from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "Apuramentu · Administrasaun"
admin.site.site_title = "Apuramentu"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("eleisaun.urls")),
]
