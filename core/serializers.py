"""
Core serializers for SIGIP-GB.
"""
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import get_user_model
from .models import Tenant, Region, Currency, FiscalYear, AuditLog

User = get_user_model()


class TenantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = ['id', 'name', 'short_name', 'is_dgp', 'created_at']
        read_only_fields = ['created_at']


class UserSerializer(serializers.ModelSerializer):
    tenant_name = serializers.CharField(source='tenant.name', read_only=True)
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    ministry_name = serializers.CharField(source='ministry.name', read_only=True)
    ministry_short = serializers.CharField(source='ministry.short_name', read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'tenant', 'tenant_name', 'role', 'role_display',
            'ministry', 'ministry_name', 'ministry_short',
            'mfa_enabled', 'phone', 'is_active', 'created_at'
        ]
        read_only_fields = ['created_at']


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = [
            'username', 'email', 'first_name', 'last_name',
            'tenant', 'role', 'phone', 'password', 'password_confirm'
        ]

    def validate(self, data):
        if data['password'] != data.pop('password_confirm'):
            raise serializers.ValidationError({'password_confirm': 'As palavras-passe não coincidem.'})
        return data

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class RegionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Region
        fields = ['id', 'name', 'code']


class CurrencySerializer(serializers.ModelSerializer):
    class Meta:
        model = Currency
        fields = ['id', 'code', 'name', 'symbol']


class FiscalYearSerializer(serializers.ModelSerializer):
    class Meta:
        model = FiscalYear
        fields = ['id', 'year', 'label', 'is_active']


class AuditLogSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    action_display = serializers.CharField(source='get_action_display', read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            'id', 'user', 'username', 'action', 'action_display',
            'model_name', 'object_id', 'changes',
            'timestamp', 'ip_address'
        ]
        read_only_fields = fields


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """JWT token com claims adicionais (role, tenant)."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['username'] = user.username
        token['role'] = user.role
        token['tenant_id'] = user.tenant_id
        token['tenant_name'] = user.tenant.name if user.tenant else None
        token['is_dgp'] = user.tenant.is_dgp if user.tenant else False
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        user = self.user
        data['user'] = {
            'id': user.id,
            'username': user.username,
            'full_name': user.get_full_name(),
            'role': user.role,
            'tenant_id': user.tenant_id,
            'tenant_name': user.tenant.name if user.tenant else None,
        }
        return data
