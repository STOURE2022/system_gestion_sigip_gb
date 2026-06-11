"""
Core URL patterns for SIGIP-GB (auth + reference data).
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView
from .views import (
    CustomTokenObtainPairView, TenantViewSet, UserViewSet,
    RegionViewSet, FiscalYearViewSet, AuditLogViewSet
)

router = DefaultRouter()
router.register('tenants', TenantViewSet, basename='tenant')
router.register('users', UserViewSet, basename='user')
router.register('regions', RegionViewSet, basename='region')
router.register('fiscal-years', FiscalYearViewSet, basename='fiscal-year')
router.register('audit-logs', AuditLogViewSet, basename='audit-log')

urlpatterns = [
    path('', include(router.urls)),
    path('token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('token/verify/', TokenVerifyView.as_view(), name='token_verify'),
]
