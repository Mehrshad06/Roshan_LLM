from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from django.views.generic import TemplateView
from rest_framework.routers import SimpleRouter
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from library.views import ConversationViewSet, DocumentViewSet, dashboard
from library.accounts import signup

router = SimpleRouter()
router.register("documents", DocumentViewSet, basename="document")
router.register("conversations", ConversationViewSet, basename="conversation")

urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("accounts/signup/", signup, name="signup"),
    path("accounts/login/", auth_views.LoginView.as_view(redirect_authenticated_user=True), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="api-docs"),
    path("api/guide/", TemplateView.as_view(template_name="api_docs.html"), name="api-guide"),
    path("api/", include(router.urls)),
]
