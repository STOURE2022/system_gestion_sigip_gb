"""
Core views for SIGIP-GB (authentication, users, reference data).
"""
from rest_framework import viewsets, generics, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.views import TokenObtainPairView
from django.contrib.auth import get_user_model
from .models import Tenant, Region, Currency, FiscalYear, AuditLog
from .serializers import (
    TenantSerializer, UserSerializer, UserCreateSerializer,
    RegionSerializer, CurrencySerializer, FiscalYearSerializer,
    AuditLogSerializer, CustomTokenObtainPairSerializer
)
from .permissions import IsDGPStaff, IsAdminOrDGP

User = get_user_model()


class CustomTokenObtainPairView(TokenObtainPairView):
    """Login endpoint que retorna JWT com claims adicionais."""
    serializer_class = CustomTokenObtainPairSerializer


class TenantViewSet(viewsets.ModelViewSet):
    queryset = Tenant.objects.all().order_by('name')
    serializer_class = TenantSerializer
    permission_classes = [IsAuthenticated, IsDGPStaff]
    search_fields = ['name', 'short_name']
    filterset_fields = ['is_dgp']


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.select_related('tenant').order_by('username')
    permission_classes = [IsAuthenticated, IsDGPStaff]
    search_fields = ['username', 'email', 'first_name', 'last_name']
    filterset_fields = ['role', 'tenant', 'is_active']

    def get_serializer_class(self):
        if self.action == 'create':
            return UserCreateSerializer
        return UserSerializer

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def me(self, request):
        """Retorna o perfil do utilizador autenticado."""
        serializer = UserSerializer(request.user)
        return Response(serializer.data)


class RegionViewSet(viewsets.ModelViewSet):
    queryset = Region.objects.all().order_by('name')
    serializer_class = RegionSerializer
    permission_classes = [IsAuthenticated]
    search_fields = ['name', 'code']


class FiscalYearViewSet(viewsets.ModelViewSet):
    queryset = FiscalYear.objects.all().order_by('year')
    serializer_class = FiscalYearSerializer
    permission_classes = [IsAuthenticated]


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AuditLog.objects.select_related('user').order_by('-timestamp')
    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticated, IsDGPStaff]
    filterset_fields = ['action', 'model_name', 'user']
    search_fields = ['model_name', 'object_id', 'user__username']
