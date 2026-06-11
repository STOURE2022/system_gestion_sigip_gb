"""
django-filter FilterSets for SIGIP-GB.
"""
import django_filters
from .models import Project, AnnualProgramming, Disbursement, Ministry, Financier


class ProjectFilter(django_filters.FilterSet):
    """Filtrage avancé des projets PIP."""
    ministry = django_filters.NumberFilter(field_name='ministry__id')
    ministry_name = django_filters.CharFilter(field_name='ministry__name', lookup_expr='icontains')
    sector = django_filters.NumberFilter(field_name='sector__id')
    pillar = django_filters.NumberFilter(field_name='pillar__id')
    pillar_code = django_filters.CharFilter(field_name='pillar__code')
    financier = django_filters.NumberFilter(field_name='principal_financier__id')
    financier_name = django_filters.CharFilter(field_name='principal_financier__name', lookup_expr='icontains')
    financier_type = django_filters.CharFilter(field_name='principal_financier__type')
    status = django_filters.CharFilter(field_name='status')
    region = django_filters.NumberFilter(field_name='region__id')
    is_national = django_filters.BooleanFilter(field_name='is_national')

    # Filtrage par montant
    min_total = django_filters.NumberFilter(field_name='total_cost', lookup_expr='gte')
    max_total = django_filters.NumberFilter(field_name='total_cost', lookup_expr='lte')

    # Filtrage par année de programmation
    has_programming_year = django_filters.NumberFilter(
        method='filter_has_programming_year',
        label='Ano de programação'
    )

    class Meta:
        model = Project
        fields = ['ministry', 'sector', 'pillar', 'status', 'region', 'is_national']

    def filter_has_programming_year(self, queryset, name, value):
        return queryset.filter(annual_programmings__fiscal_year=value).distinct()


class AnnualProgrammingFilter(django_filters.FilterSet):
    project = django_filters.NumberFilter(field_name='project__id')
    project_code = django_filters.CharFilter(field_name='project__code', lookup_expr='icontains')
    ministry = django_filters.NumberFilter(field_name='project__ministry__id')
    pillar = django_filters.NumberFilter(field_name='project__pillar__id')
    fiscal_year = django_filters.NumberFilter(field_name='fiscal_year')
    fiscal_year_gte = django_filters.NumberFilter(field_name='fiscal_year', lookup_expr='gte')
    fiscal_year_lte = django_filters.NumberFilter(field_name='fiscal_year', lookup_expr='lte')
    version = django_filters.NumberFilter(field_name='version')

    class Meta:
        model = AnnualProgramming
        fields = ['project', 'fiscal_year', 'version']


class DisbursementFilter(django_filters.FilterSet):
    project = django_filters.NumberFilter(field_name='project__id')
    financier = django_filters.NumberFilter(field_name='financier__id')
    fiscal_year = django_filters.NumberFilter(field_name='fiscal_year')
    period = django_filters.CharFilter(field_name='period')

    class Meta:
        model = Disbursement
        fields = ['project', 'financier', 'fiscal_year', 'period']


class MinistryFilter(django_filters.FilterSet):
    pillar = django_filters.NumberFilter(field_name='pillar__id')
    pillar_code = django_filters.CharFilter(field_name='pillar__code')

    class Meta:
        model = Ministry
        fields = ['pillar']


class FinancierFilter(django_filters.FilterSet):
    type = django_filters.CharFilter(field_name='type')
    name = django_filters.CharFilter(field_name='name', lookup_expr='icontains')

    class Meta:
        model = Financier
        fields = ['type']
