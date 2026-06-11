"""
Django admin configuration for SIGIP models.
"""
from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.db.models import Sum
from .models import (
    Pillar, Sector, GovPriority, Ministry, Financier, ExpenseNature,
    Project, ProjectFinancier, AnnualProgramming, Disbursement,
    PPProject, PIPVersion
)


@admin.register(Pillar)
class PillarAdmin(admin.ModelAdmin):
    list_display = ['code', 'label', 'order']
    list_editable = ['order']
    search_fields = ['code', 'label']
    ordering = ['order', 'code']


@admin.register(Sector)
class SectorAdmin(admin.ModelAdmin):
    list_display = ['code', 'label', 'parent']
    list_filter = ['parent']
    search_fields = ['code', 'label']
    raw_id_fields = ['parent']
    ordering = ['code']


@admin.register(GovPriority)
class GovPriorityAdmin(admin.ModelAdmin):
    list_display = ['label', 'order']
    list_editable = ['order']
    search_fields = ['label']


@admin.register(Ministry)
class MinistryAdmin(admin.ModelAdmin):
    list_display = ['name', 'short_name', 'pillar', 'project_count']
    list_filter = ['pillar']
    search_fields = ['name', 'short_name']
    autocomplete_fields = ['pillar']

    def project_count(self, obj):
        return obj.projects.filter(is_deleted=False).count()
    project_count.short_description = _('Projectos')


@admin.register(Financier)
class FinancierAdmin(admin.ModelAdmin):
    list_display = ['name', 'short_name', 'type', 'country', 'project_count']
    list_filter = ['type', 'country']
    search_fields = ['name', 'short_name', 'country']

    def project_count(self, obj):
        return obj.led_projects.filter(is_deleted=False).count()
    project_count.short_description = _('Projectos liderados')


@admin.register(ExpenseNature)
class ExpenseNatureAdmin(admin.ModelAdmin):
    list_display = ['code', 'label']
    search_fields = ['code', 'label']


class AnnualProgrammingInline(admin.TabularInline):
    model = AnnualProgramming
    extra = 0
    fields = ['fiscal_year', 'donations', 'loans', 'state_contribution', 'version']
    readonly_fields = []


class ProjectFinancierInline(admin.TabularInline):
    model = ProjectFinancier
    extra = 0
    autocomplete_fields = ['financier']


def mark_as_submitted(modeladmin, request, queryset):
    queryset.update(workflow_status='submitted')
mark_as_submitted.short_description = _('Marcar seleccionados como submetidos')


def mark_as_validated(modeladmin, request, queryset):
    queryset.update(workflow_status='validated')
mark_as_validated.short_description = _('Marcar seleccionados como validados')


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = [
        'code', 'title_short', 'ministry', 'pillar', 'status',
        'workflow_badge', 'principal_financier', 'total_programmed_display', 'is_deleted'
    ]
    list_filter = [
        'status', 'workflow_status', 'pillar', 'ministry', 'principal_financier__type',
        'is_national', 'is_deleted'
    ]
    actions = [mark_as_submitted, mark_as_validated]
    search_fields = ['code', 'title', 'description', 'ministry__name', 'principal_financier__name']
    autocomplete_fields = ['ministry', 'sector', 'pillar', 'principal_financier', 'region', 'tenant']
    readonly_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
    list_select_related = ['ministry', 'pillar', 'principal_financier']
    ordering = ['code']
    date_hierarchy = 'created_at'
    inlines = [AnnualProgrammingInline, ProjectFinancierInline]

    fieldsets = (
        (_('Identificação'), {
            'fields': ('code', 'title', 'description', 'status', 'workflow_status', 'rejection_note')
        }),
        (_('Classificação'), {
            'fields': ('ministry', 'sector', 'pillar', 'gov_priority', 'expense_nature')
        }),
        (_('Financiamento'), {
            'fields': ('principal_financier', 'total_cost')
        }),
        (_('Localização'), {
            'fields': ('region', 'is_national')
        }),
        (_('Datas'), {
            'fields': ('start_date', 'end_date')
        }),
        (_('Sistema'), {
            'fields': ('tenant', 'is_deleted', 'created_at', 'updated_at', 'created_by', 'updated_by'),
            'classes': ('collapse',)
        }),
    )

    def title_short(self, obj):
        return obj.title[:60] + ('...' if len(obj.title) > 60 else '')
    title_short.short_description = _('Título')

    _WORKFLOW_COLOURS = {
        'draft':     ('#6c757d', 'Rascunho'),
        'submitted': ('#0d6efd', 'Submetido'),
        'validated': ('#198754', 'Validado'),
        'rejected':  ('#dc3545', 'Rejeitado'),
        'archived':  ('#343a40', 'Arquivado'),
    }

    def workflow_badge(self, obj):
        status = obj.workflow_status or 'draft'
        colour, label = self._WORKFLOW_COLOURS.get(status, ('#6c757d', status))
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:4px;font-size:0.85em;white-space:nowrap;">{}</span>',
            colour, label
        )
    workflow_badge.short_description = _('Workflow')
    workflow_badge.allow_tags = True

    def total_programmed_display(self, obj):
        result = obj.annual_programmings.filter(version=1).aggregate(
            total=Sum('donations') + Sum('loans') + Sum('state_contribution')
        )
        val = result.get('total') or 0
        return f'{float(val):,.0f} FCFA'
    total_programmed_display.short_description = _('Total Programado')

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('annual_programmings')


@admin.register(AnnualProgramming)
class AnnualProgrammingAdmin(admin.ModelAdmin):
    list_display = ['project', 'fiscal_year', 'donations', 'loans', 'state_contribution', 'total_display', 'version']
    list_filter = ['fiscal_year', 'version']
    search_fields = ['project__code', 'project__title']
    autocomplete_fields = ['project']
    ordering = ['project__code', 'fiscal_year']

    def total_display(self, obj):
        return f'{float(obj.total):,.0f} FCFA'
    total_display.short_description = _('Total (FCFA)')


@admin.register(Disbursement)
class DisbursementAdmin(admin.ModelAdmin):
    list_display = ['project', 'financier', 'fiscal_year', 'period', 'programmed_amount', 'actual_amount', 'execution_rate_display']
    list_filter = ['fiscal_year', 'period']
    search_fields = ['project__code', 'project__title']
    autocomplete_fields = ['project', 'financier']
    ordering = ['project__code', 'fiscal_year', 'period']

    def execution_rate_display(self, obj):
        return f'{obj.execution_rate:.1f}%'
    execution_rate_display.short_description = _('Taxa de Execução')


@admin.register(PPProject)
class PPProjectAdmin(admin.ModelAdmin):
    list_display = ['private_partner', 'project', 'structure', 'amount', 'signing_date']
    search_fields = ['private_partner', 'structure']
    autocomplete_fields = ['project']


@admin.register(PIPVersion)
class PIPVersionAdmin(admin.ModelAdmin):
    list_display = ['revision_year', 'status', 'adoption_date', 'created_at']
    list_filter = ['status']
    ordering = ['-revision_year']
