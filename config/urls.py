from django.contrib.auth import views as auth_views
from django.urls import include, path
from garden import views

urlpatterns = [
    path("health/", views.health, name="health"),
    path("sw.js", views.service_worker, name="service-worker"),
    path("accounts/login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path(
        "accounts/set-password/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="registration/owner_password_setup.html",
            success_url="/accounts/login/",
        ),
        name="owner-password-setup",
    ),
    path("gardens/select/", views.select_garden, name="select-garden"),
    path("api/v1/", include("garden.api_v1_urls")),
    path("api/", include("garden.urls")),
    path("", views.index, name="index"),
]
