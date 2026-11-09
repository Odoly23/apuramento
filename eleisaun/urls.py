from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", views.ThrottledLoginView.as_view(), name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("lang/<str:code>/", views.set_language, name="set_language"),
    path("painel/", views.dashboard, name="dashboard"),
    path("komparasaun/", views.compare, name="compare"),
    path("api/live/", views.api_live, name="api_live"),
    path("export/<str:level>.csv", views.export_csv, name="export_csv"),
    path("fiskal/", views.fiskal_home, name="fiskal_home"),
    path("fiskal/sentru/<int:centre_id>/", views.submit_report, name="submit_report"),
    path("relatoriu/<int:pk>/", views.report_detail, name="report_detail"),
    path("relatoriu/<int:pk>/review/", views.report_review, name="report_review"),
    path("verifikasaun/", views.verification, name="verification"),
    path("audit/", views.audit, name="audit"),
    path("prova/<int:pk>/", views.evidence_file, name="evidence_file"),
    path("api/chat/", views.chat_api, name="chat_api"),
]
