"""
Django admin configuration for core models.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group, Permission
from django.utils.translation import gettext_lazy as _
from .models import Tenant, User, AuditLog, Region, Currency, FiscalYear


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ['name', 'short_name', 'is_dgp', 'created_at']
    list_filter = ['is_dgp']
    search_fields = ['name', 'short_name']


# Re-register Group with search_fields so it can be used via autocomplete
admin.site.unregister(Group)

@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    search_fields = ['name']
    ordering = ['name']


# Register Permission with search_fields for autocomplete on user_permissions
@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    search_fields = ['name', 'codename', 'content_type__app_label']
    list_display = ['name', 'codename', 'content_type']
    list_filter = ['content_type__app_label']
    ordering = ['content_type__app_label', 'codename']


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        (_('SIGIP-GB'), {
            'fields': ('tenant', 'role', 'ministry', 'mfa_enabled', 'phone')
        }),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        (_('SIGIP-GB'), {
            'fields': ('tenant', 'role', 'ministry')
        }),
    )
    list_display = ['username', 'email', 'get_full_name', 'tenant', 'role', 'ministry', 'is_active']
    list_filter = ['role', 'tenant', 'ministry', 'is_active', 'is_staff']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    # Both groups and user_permissions via Select2 autocomplete — no more dual-panel widgets.
    filter_horizontal = ()
    autocomplete_fields = ['tenant', 'ministry', 'groups', 'user_permissions']

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        # RelatedFieldWidgetWrapper is applied inside super() — override AFTER.
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if formfield and db_field.name in ('groups', 'user_permissions'):
            w = formfield.widget
            if hasattr(w, 'can_add_related'):
                w.can_add_related = False
                w.can_change_related = False
                w.can_delete_related = False
                w.can_view_related = False
        return formfield


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ['timestamp', 'user', 'action', 'model_name', 'object_id', 'ip_address']
    list_filter = ['action', 'model_name']
    search_fields = ['user__username', 'model_name', 'object_id']
    readonly_fields = ['user', 'action', 'model_name', 'object_id', 'changes', 'timestamp', 'ip_address']
    date_hierarchy = 'timestamp'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ['name', 'code']
    search_fields = ['name', 'code']


@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'symbol']


@admin.register(FiscalYear)
class FiscalYearAdmin(admin.ModelAdmin):
    list_display = ['year', 'label', 'is_active']
    list_editable = ['is_active']
