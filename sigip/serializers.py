"""
DRF Serializers for SIGIP-GB.
"""
from decimal import Decimal
from django.db.models import Sum, Count, Q
from rest_framework import serializers
from .models import (
    Pillar, Sector, GovPriority, Ministry, Financier, ExpenseNature,
    Project, ProjectFinancier, AnnualProgramming, Disbursement,
    PPProject, PIPVersion, WorkflowStatus
)


# ---------------------------------------------------------------------------
# Reference data serializers
# ---------------------------------------------------------------------------

class PillarSerializer(serializers.ModelSerializer):
    project_count = serializers.SerializerMethodField()

    class Meta:
        model = Pillar
        fields = ['id', 'code', 'label', 'description', 'order', 'project_count']

    def get_project_count(self, obj):
        return obj.projects.filter(is_deleted=False).count()


class SectorSerializer(serializers.ModelSerializer):
    parent_label = serializers.CharField(source='parent.label', read_only=True)
    sub_sectors = serializers.SerializerMethodField()

    class Meta:
        model = Sector
        fields = ['id', 'code', 'label', 'parent', 'parent_label', 'sub_sectors']

    def get_sub_sectors(self, obj):
        if obj.sub_sectors.exists():
            return SectorSerializer(obj.sub_sectors.all(), many=True).data
        return []


class GovPrioritySerializer(serializers.ModelSerializer):
    class Meta:
        model = GovPriority
        fields = ['id', 'label', 'order']


class MinistrySerializer(serializers.ModelSerializer):
    pillar_label = serializers.CharField(source='pillar.label', read_only=True)
    pillar_code = serializers.CharField(source='pillar.code', read_only=True)
    project_count = serializers.SerializerMethodField()
    total_programmed = serializers.SerializerMethodField()

    class Meta:
        model = Ministry
        fields = [
            'id', 'name', 'short_name',
            'pillar', 'pillar_code', 'pillar_label',
            'gov_priority', 'project_count', 'total_programmed'
        ]

    def get_project_count(self, obj):
        return obj.projects.filter(is_deleted=False).count()

    def get_total_programmed(self, obj):
        result = AnnualProgramming.objects.filter(
            project__ministry=obj,
            project__is_deleted=False,
            version=1
        ).aggregate(
            total=Sum('donations') + Sum('loans') + Sum('state_contribution')
        )
        val = result.get('total') or Decimal('0')
        return float(val)


class FinancierSerializer(serializers.ModelSerializer):
    project_count = serializers.SerializerMethodField()
    total_programmed = serializers.SerializerMethodField()

    class Meta:
        model = Financier
        fields = [
            'id', 'name', 'short_name', 'type', 'country', 'website',
            'project_count', 'total_programmed'
        ]

    def get_project_count(self, obj):
        return obj.led_projects.filter(is_deleted=False).count()

    def get_total_programmed(self, obj):
        result = AnnualProgramming.objects.filter(
            project__principal_financier=obj,
            project__is_deleted=False,
            version=1
        ).aggregate(
            total=Sum('donations') + Sum('loans') + Sum('state_contribution')
        )
        val = result.get('total') or Decimal('0')
        return float(val)


class ExpenseNatureSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseNature
        fields = ['id', 'code', 'label']


# ---------------------------------------------------------------------------
# Annual Programming
# ---------------------------------------------------------------------------
class AnnualProgrammingSerializer(serializers.ModelSerializer):
    total = serializers.SerializerMethodField()
    project_code = serializers.CharField(source='project.code', read_only=True)
    project_title = serializers.CharField(source='project.title', read_only=True)
    financement_externe = serializers.SerializerMethodField()
    financement_interno = serializers.SerializerMethodField()

    class Meta:
        model = AnnualProgramming
        fields = [
            'id', 'project', 'project_code', 'project_title',
            'fiscal_year', 'donations', 'loans', 'state_contribution',
            'total', 'financement_externe', 'financement_interno', 'version'
        ]

    def get_total(self, obj):
        return float(obj.donations + obj.loans + obj.state_contribution)

    def get_financement_externe(self, obj):
        return float((obj.donations or 0) + (obj.loans or 0))

    def get_financement_interno(self, obj):
        return float(obj.state_contribution or 0)


# ---------------------------------------------------------------------------
# Disbursement
# ---------------------------------------------------------------------------
class DisbursementSerializer(serializers.ModelSerializer):
    execution_rate = serializers.SerializerMethodField()
    project_code = serializers.CharField(source='project.code', read_only=True)
    financier_name = serializers.CharField(source='financier.name', read_only=True)
    period_display = serializers.CharField(source='get_period_display', read_only=True)

    class Meta:
        model = Disbursement
        fields = [
            'id', 'project', 'project_code', 'financier', 'financier_name',
            'fiscal_year', 'period', 'period_display',
            'programmed_amount', 'actual_amount', 'execution_rate',
            'date', 'notes'
        ]

    def get_execution_rate(self, obj):
        return obj.execution_rate


# ---------------------------------------------------------------------------
# ProjectFinancier
# ---------------------------------------------------------------------------
class ProjectFinancierSerializer(serializers.ModelSerializer):
    financier_name = serializers.CharField(source='financier.name', read_only=True)
    financier_short = serializers.CharField(source='financier.short_name', read_only=True)
    financier_type = serializers.CharField(source='financier.type', read_only=True)
    role_display = serializers.CharField(source='get_role_display', read_only=True)

    class Meta:
        model = ProjectFinancier
        fields = [
            'id', 'financier', 'financier_name', 'financier_short',
            'financier_type', 'role', 'role_display'
        ]


# ---------------------------------------------------------------------------
# Project (List – lightweight)
# ---------------------------------------------------------------------------
class ProjectListSerializer(serializers.ModelSerializer):
    """Serializer allégé pour les listes (pas de données imbriquées volumineuses)."""
    ministry_name = serializers.CharField(source='ministry.name', read_only=True)
    ministry_short = serializers.CharField(source='ministry.short_name', read_only=True)
    pillar_code = serializers.CharField(source='pillar.code', read_only=True)
    pillar_label = serializers.CharField(source='pillar.label', read_only=True)
    sector_label = serializers.CharField(source='sector.label', read_only=True)
    financier_name = serializers.CharField(source='principal_financier.name', read_only=True)
    financier_short = serializers.CharField(source='principal_financier.short_name', read_only=True)
    financier_type = serializers.CharField(source='principal_financier.type', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    workflow_status_display = serializers.CharField(source='get_workflow_status_display', read_only=True)
    region_name = serializers.CharField(source='region.name', read_only=True)
    total_programmed = serializers.SerializerMethodField()
    total_programmed_externe = serializers.SerializerMethodField()
    total_programmed_interno = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = [
            'id', 'code', 'title', 'status', 'status_display',
            'workflow_status', 'workflow_status_display',
            'ministry', 'ministry_name', 'ministry_short',
            'pillar', 'pillar_code', 'pillar_label',
            'sector', 'sector_label',
            'principal_financier', 'financier_name', 'financier_short', 'financier_type',
            'region', 'region_name', 'is_national',
            'total_cost', 'total_programmed',
            'total_programmed_externe', 'total_programmed_interno',
            'start_date', 'end_date',
        ]

    def get_total_programmed(self, obj):
        # Use prefetched data if available
        if hasattr(obj, '_total_programmed'):
            return float(obj._total_programmed or 0)
        result = obj.annual_programmings.filter(version=1).aggregate(
            total=Sum('donations') + Sum('loans') + Sum('state_contribution')
        )
        return float(result.get('total') or 0)

    def get_total_programmed_externe(self, obj):
        from django.db.models.functions import Coalesce
        from django.db.models import Value, DecimalField
        result = obj.annual_programmings.filter(version=1).aggregate(
            donations=Coalesce(Sum('donations'), Value(0, output_field=DecimalField())),
            loans=Coalesce(Sum('loans'), Value(0, output_field=DecimalField())),
        )
        return float((result.get('donations') or 0) + (result.get('loans') or 0))

    def get_total_programmed_interno(self, obj):
        from django.db.models.functions import Coalesce
        from django.db.models import Value, DecimalField
        result = obj.annual_programmings.filter(version=1).aggregate(
            state=Coalesce(Sum('state_contribution'), Value(0, output_field=DecimalField())),
        )
        return float(result.get('state') or 0)


# ---------------------------------------------------------------------------
# Project (Detail – full)
# ---------------------------------------------------------------------------
class ProjectDetailSerializer(serializers.ModelSerializer):
    """Serializer complet avec données imbriquées."""
    ministry_name = serializers.CharField(source='ministry.name', read_only=True)
    ministry_short = serializers.CharField(source='ministry.short_name', read_only=True)
    pillar_code = serializers.CharField(source='pillar.code', read_only=True)
    pillar_label = serializers.CharField(source='pillar.label', read_only=True)
    sector_label = serializers.CharField(source='sector.label', read_only=True)
    financier_name = serializers.CharField(source='principal_financier.name', read_only=True)
    financier_short = serializers.CharField(source='principal_financier.short_name', read_only=True)
    financier_type = serializers.CharField(source='principal_financier.type', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    workflow_status_display = serializers.CharField(source='get_workflow_status_display', read_only=True)
    region_name = serializers.CharField(source='region.name', read_only=True)

    annual_programmings = AnnualProgrammingSerializer(many=True, read_only=True)
    project_financiers = ProjectFinancierSerializer(many=True, read_only=True)
    disbursements = DisbursementSerializer(many=True, read_only=True)
    total_programmed = serializers.SerializerMethodField()
    total_programmed_externe = serializers.SerializerMethodField()
    total_programmed_interno = serializers.SerializerMethodField()
    programming_by_year = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = [
            'id', 'code', 'title', 'description', 'status', 'status_display',
            'workflow_status', 'workflow_status_display', 'rejection_note',
            'ministry', 'ministry_name', 'ministry_short',
            'pillar', 'pillar_code', 'pillar_label',
            'sector', 'sector_label',
            'gov_priority', 'expense_nature',
            'principal_financier', 'financier_name', 'financier_short', 'financier_type',
            'region', 'region_name', 'is_national',
            'total_cost', 'total_programmed',
            'total_programmed_externe', 'total_programmed_interno',
            'start_date', 'end_date',
            'tenant', 'created_at', 'updated_at',
            'annual_programmings', 'project_financiers', 'disbursements',
            'programming_by_year',
        ]
        read_only_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']

    def get_total_programmed(self, obj):
        result = obj.annual_programmings.filter(version=1).aggregate(
            total=Sum('donations') + Sum('loans') + Sum('state_contribution')
        )
        return float(result.get('total') or 0)

    def get_total_programmed_externe(self, obj):
        from django.db.models.functions import Coalesce
        from django.db.models import Value, DecimalField
        result = obj.annual_programmings.filter(version=1).aggregate(
            donations=Coalesce(Sum('donations'), Value(0, output_field=DecimalField())),
            loans=Coalesce(Sum('loans'), Value(0, output_field=DecimalField())),
        )
        return float((result.get('donations') or 0) + (result.get('loans') or 0))

    def get_total_programmed_interno(self, obj):
        from django.db.models.functions import Coalesce
        from django.db.models import Value, DecimalField
        result = obj.annual_programmings.filter(version=1).aggregate(
            state=Coalesce(Sum('state_contribution'), Value(0, output_field=DecimalField())),
        )
        return float(result.get('state') or 0)

    def get_programming_by_year(self, obj):
        """Retorna um dict {2026: {donations, loans, state, total}, ...}"""
        programmings = obj.annual_programmings.filter(version=1).order_by('fiscal_year')
        result = {}
        for p in programmings:
            result[p.fiscal_year] = {
                'donations': float(p.donations),
                'loans': float(p.loans),
                'state_contribution': float(p.state_contribution),
                'total': float(p.donations + p.loans + p.state_contribution),
            }
        return result


# ---------------------------------------------------------------------------
# Dashboard Stats
# ---------------------------------------------------------------------------
class YearlyTrajectorySerializer(serializers.Serializer):
    fiscal_year = serializers.IntegerField()
    total = serializers.FloatField()
    donations = serializers.FloatField()
    loans = serializers.FloatField()
    state_contribution = serializers.FloatField()


class MinistryStatsSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    short_name = serializers.CharField()
    project_count = serializers.IntegerField()
    total = serializers.FloatField()
    percentage = serializers.FloatField()


class PillarStatsSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    code = serializers.CharField()
    label = serializers.CharField()
    project_count = serializers.IntegerField()
    total = serializers.FloatField()
    percentage = serializers.FloatField()


class FinancierStatsSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    short_name = serializers.CharField()
    type = serializers.CharField()
    project_count = serializers.IntegerField()
    total = serializers.FloatField()
    percentage = serializers.FloatField()


class DashboardStatsSerializer(serializers.Serializer):
    # Totaux généraux
    total_projects = serializers.IntegerField()
    total_pip_fcfa = serializers.FloatField(help_text='Montant total PIP en FCFA')
    total_donations_fcfa = serializers.FloatField()
    total_loans_fcfa = serializers.FloatField()
    total_state_fcfa = serializers.FloatField()

    # Statistiques par entité
    by_ministry = MinistryStatsSerializer(many=True)
    by_pillar = PillarStatsSerializer(many=True)
    by_financier = FinancierStatsSerializer(many=True)
    by_year = YearlyTrajectorySerializer(many=True)

    # Comptages
    total_ministries = serializers.IntegerField()
    total_financiers = serializers.IntegerField()


# ---------------------------------------------------------------------------
# ProjectWriteSerializer  —  saisie continue par les ministères
# ---------------------------------------------------------------------------

class ProjectWriteSerializer(serializers.ModelSerializer):
    """
    Serializer de création/modification d'un projet par un ministère.

    Règles :
    - `ministry` est injecté automatiquement depuis request.user.ministry
      (les MINISTRY_AGENT ne peuvent pas choisir un autre ministère).
    - `workflow_status` est géré via les actions dédiées (submit/validate/reject),
      pas ici.
    - `code` doit être unique.
    - `total_cost` ≥ 0.
    """
    class Meta:
        model = Project
        fields = [
            'id', 'code', 'title', 'description',
            'ministry',
            'sector', 'pillar', 'gov_priority', 'expense_nature',
            'principal_financier',
            'region', 'is_national',
            'status',
            'total_cost',
            'start_date', 'end_date',
        ]
        read_only_fields = ['id']

    def validate_code(self, value):
        # Unicité, en excluant l'instance courante lors d'une mise à jour
        qs = Project.objects.filter(code=value, is_deleted=False)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                f"Já existe um projecto com o código «{value}»."
            )
        return value

    def validate_total_cost(self, value):
        if value < Decimal('0'):
            raise serializers.ValidationError("O custo total não pode ser negativo.")
        return value

    def validate(self, attrs):
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            from core.models import UserRole
            user = request.user
            # MINISTRY_AGENT : forcer le ministry depuis le profil
            if user.role == UserRole.MINISTRY_AGENT:
                if not user.ministry:
                    raise serializers.ValidationError(
                        "A sua conta não está associada a nenhum ministério. "
                        "Contacte o administrador."
                    )
                attrs['ministry'] = user.ministry
            # Vérification dates
            start = attrs.get('start_date')
            end = attrs.get('end_date')
            if start and end and end < start:
                raise serializers.ValidationError(
                    "A data de conclusão não pode ser anterior à data de início."
                )
        return attrs


# ---------------------------------------------------------------------------
# AnnualProgrammingWriteSerializer  —  saisie d'une année
# ---------------------------------------------------------------------------

class AnnualProgrammingWriteSerializer(serializers.ModelSerializer):
    """
    Saisie/mise à jour d'une ligne de programmation annuelle.
    Valide que tous les montants sont ≥ 0.
    """
    total = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = AnnualProgramming
        fields = [
            'id', 'project', 'fiscal_year',
            'donations', 'loans', 'state_contribution',
            'total', 'version',
        ]

    def get_total(self, obj):
        return float(obj.donations + obj.loans + obj.state_contribution)

    def validate_fiscal_year(self, value):
        if value not in range(2026, 2031):
            raise serializers.ValidationError(
                "O ano fiscal deve estar entre 2026 e 2030."
            )
        return value

    def validate_donations(self, value):
        if value < Decimal('0'):
            raise serializers.ValidationError("Os donativos não podem ser negativos.")
        return value

    def validate_loans(self, value):
        if value < Decimal('0'):
            raise serializers.ValidationError("Os empréstimos não podem ser negativos.")
        return value

    def validate_state_contribution(self, value):
        if value < Decimal('0'):
            raise serializers.ValidationError(
                "A contribuição do Estado não pode ser negativa."
            )
        return value

    def validate(self, attrs):
        # Contrôle de cohérence : total doit être cohérent
        d = attrs.get('donations', Decimal('0'))
        l = attrs.get('loans', Decimal('0'))
        s = attrs.get('state_contribution', Decimal('0'))
        if d + l + s < Decimal('0'):
            raise serializers.ValidationError(
                "O total de financiamento não pode ser negativo."
            )
        return attrs


# ---------------------------------------------------------------------------
# AnnualProgrammingBulkSerializer  —  saisie en bloc des 5 années
# ---------------------------------------------------------------------------

class AnnualProgrammingYearSerializer(serializers.Serializer):
    """Une ligne du tableau pluriannuel."""
    fiscal_year = serializers.IntegerField()
    donations = serializers.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    loans = serializers.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    state_contribution = serializers.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))

    def validate_fiscal_year(self, value):
        if value not in range(2026, 2031):
            raise serializers.ValidationError(
                f"Ano {value} não pertence ao PIP 2026-2030."
            )
        return value

    def validate_donations(self, value):
        if value < Decimal('0'):
            raise serializers.ValidationError("Os donativos não podem ser negativos.")
        return value

    def validate_loans(self, value):
        if value < Decimal('0'):
            raise serializers.ValidationError("Os empréstimos não podem ser negativos.")
        return value

    def validate_state_contribution(self, value):
        if value < Decimal('0'):
            raise serializers.ValidationError(
                "A contribuição do Estado não pode ser negativa."
            )
        return value


class AnnualProgrammingBulkSerializer(serializers.Serializer):
    """
    Reçoit une liste de lignes {fiscal_year, donations, loans, state_contribution}
    et fait un upsert atomique pour le projet donné.

    Validations :
    - Pas de doublon d'année dans la liste soumise.
    - Chaque montant ≥ 0.
    - Le projet doit être en état RASCUNHO (sauf ADMIN/DGP).
    """
    programmings = AnnualProgrammingYearSerializer(many=True)

    def validate_programmings(self, value):
        years = [p['fiscal_year'] for p in value]
        if len(years) != len(set(years)):
            raise serializers.ValidationError(
                "Existem anos duplicados na programação submetida."
            )
        return value


# ---------------------------------------------------------------------------
# WorkflowTransitionSerializer  —  soumission / validation / rejet
# ---------------------------------------------------------------------------

class WorkflowTransitionSerializer(serializers.Serializer):
    """
    Payload pour les actions de transition de workflow.
    `rejection_note` est requis uniquement lors d'un rejet.
    """
    rejection_note = serializers.CharField(
        required=False, allow_blank=True, default='',
        help_text="Motivo de devolução (obrigatório para a acção 'reject')"
    )


# ---------------------------------------------------------------------------
# PPProject
# ---------------------------------------------------------------------------
class PPProjectSerializer(serializers.ModelSerializer):
    project_code = serializers.CharField(source='project.code', read_only=True)

    class Meta:
        model = PPProject
        fields = [
            'id', 'project', 'project_code',
            'private_partner', 'structure', 'amount',
            'signing_date', 'duration_years', 'notes'
        ]


# ---------------------------------------------------------------------------
# PIPVersion
# ---------------------------------------------------------------------------
class PIPVersionSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = PIPVersion
        fields = ['id', 'revision_year', 'status', 'status_display', 'adoption_date', 'notes', 'created_at']
