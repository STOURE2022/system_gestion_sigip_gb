"""
SIGIP-GB ViewSets and Views.
"""
import logging
from decimal import Decimal
from django.db import transaction
from django.db.models import Sum, Count, F, Q, Value, DecimalField
from django.db.models.functions import Coalesce
from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import IsAuthenticated

from core.models import AuditLog, UserRole
from core.permissions import (
    IsAdminOrDGP, TenantFilterMixin, MinistryFilterMixin,
    CanWriteProject, CanSubmitProject, CanValidateProject,
)
from .models import (
    Pillar, Sector, GovPriority, Ministry, Financier, ExpenseNature,
    Project, AnnualProgramming, Disbursement, PPProject, PIPVersion,
    ProjectFinancier, WorkflowStatus,
)
from .serializers import (
    PillarSerializer, SectorSerializer, GovPrioritySerializer,
    MinistrySerializer, FinancierSerializer, ExpenseNatureSerializer,
    ProjectListSerializer, ProjectDetailSerializer,
    ProjectWriteSerializer,
    AnnualProgrammingSerializer, AnnualProgrammingWriteSerializer,
    AnnualProgrammingBulkSerializer,
    WorkflowTransitionSerializer,
    DisbursementSerializer,
    PPProjectSerializer, PIPVersionSerializer,
    DashboardStatsSerializer,
)
from .filters import (
    ProjectFilter, AnnualProgrammingFilter, DisbursementFilter,
    MinistryFilter, FinancierFilter
)
from .tasks import import_pip_data_task, send_workflow_notification_task

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Reference ViewSets
# ---------------------------------------------------------------------------

class PillarViewSet(viewsets.ModelViewSet):
    """Pilares do PND 2026-2030."""
    queryset = Pillar.objects.all().order_by('order', 'code')
    serializer_class = PillarSerializer
    permission_classes = [IsAuthenticated]
    search_fields = ['code', 'label']
    filterset_fields = ['code']

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            return [IsAdminOrDGP()]
        return [IsAuthenticated()]


class SectorViewSet(viewsets.ModelViewSet):
    """Sectores de actividade."""
    queryset = Sector.objects.select_related('parent').all().order_by('code')
    serializer_class = SectorSerializer
    permission_classes = [IsAuthenticated]
    search_fields = ['code', 'label']
    filterset_fields = ['parent']

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            return [IsAdminOrDGP()]
        return [IsAuthenticated()]


class GovPriorityViewSet(viewsets.ModelViewSet):
    queryset = GovPriority.objects.all().order_by('order', 'label')
    serializer_class = GovPrioritySerializer
    permission_classes = [IsAuthenticated]
    search_fields = ['label']


class MinistryViewSet(viewsets.ModelViewSet):
    """Ministérios e instituições."""
    queryset = Ministry.objects.select_related('pillar', 'gov_priority').all().order_by('name')
    serializer_class = MinistrySerializer
    permission_classes = [IsAuthenticated]
    filterset_class = MinistryFilter
    search_fields = ['name', 'short_name']

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            return [IsAdminOrDGP()]
        return [IsAuthenticated()]

    @action(detail=True, methods=['get'], url_path='projects')
    def projects(self, request, pk=None):
        """Retorna todos os projectos de um ministério."""
        ministry = self.get_object()
        qs = Project.objects.filter(
            ministry=ministry, is_deleted=False
        ).select_related('pillar', 'sector', 'principal_financier', 'region').order_by('code')
        serializer = ProjectListSerializer(qs, many=True, context={'request': request})
        return Response(serializer.data)


class FinancierViewSet(viewsets.ModelViewSet):
    """Financiadores e parceiros de desenvolvimento."""
    queryset = Financier.objects.all().order_by('name')
    serializer_class = FinancierSerializer
    permission_classes = [IsAuthenticated]
    filterset_class = FinancierFilter
    search_fields = ['name', 'short_name', 'country']

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            return [IsAdminOrDGP()]
        return [IsAuthenticated()]

    @action(detail=True, methods=['get'], url_path='projects')
    def projects(self, request, pk=None):
        """Retorna todos os projectos de um financiador."""
        financier = self.get_object()
        qs = Project.objects.filter(
            principal_financier=financier, is_deleted=False
        ).select_related('ministry', 'pillar', 'sector', 'region').order_by('code')
        serializer = ProjectListSerializer(qs, many=True, context={'request': request})
        return Response(serializer.data)


class ExpenseNatureViewSet(viewsets.ModelViewSet):
    queryset = ExpenseNature.objects.all().order_by('code')
    serializer_class = ExpenseNatureSerializer
    permission_classes = [IsAuthenticated]
    search_fields = ['code', 'label']


# ---------------------------------------------------------------------------
# Utilitaire d'audit
# ---------------------------------------------------------------------------

def _log_audit(request, action, project, changes=None):
    """Enregistre une entrée dans AuditLog."""
    ip = (
        request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
        or request.META.get('REMOTE_ADDR')
    )
    AuditLog.objects.create(
        user=request.user,
        action=action,
        model_name='Project',
        object_id=str(project.pk),
        changes=changes or {},
        ip_address=ip or None,
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
    )


# ---------------------------------------------------------------------------
# Project ViewSet
# ---------------------------------------------------------------------------

class ProjectViewSet(MinistryFilterMixin, viewsets.ModelViewSet):
    """
    ViewSet completo para projectos PIP.
    Suporta filtragem, pesquisa, ordenação e acções de workflow.

    Cloisonnement :
    - MINISTRY_AGENT voit uniquement les projets de son ministère.
    - DGP / ADMIN / READER voient tout.
    """
    filterset_class = ProjectFilter
    search_fields = ['code', 'title', 'description', 'ministry__name', 'principal_financier__name']
    ordering_fields = ['code', 'title', 'total_cost', 'created_at', 'ministry__name', 'workflow_status']
    ordering = ['code']

    def get_queryset(self):
        qs = Project.objects.filter(is_deleted=False).select_related(
            'ministry', 'sector', 'pillar', 'gov_priority',
            'principal_financier', 'region', 'tenant',
            'expense_nature', 'created_by', 'updated_by',
        )
        return self.get_ministry_queryset(qs)

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return ProjectWriteSerializer
        if self.action == 'retrieve':
            return ProjectDetailSerializer
        return ProjectListSerializer

    def get_permissions(self):
        if self.action in ('submit',):
            return [IsAuthenticated(), CanSubmitProject()]
        if self.action in ('validate_project', 'reject'):
            return [IsAuthenticated(), CanValidateProject()]
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            return [IsAuthenticated(), CanWriteProject()]
        return [IsAuthenticated()]

    def get_object(self):
        """Standard get_object + vérification objet pour CanWriteProject."""
        obj = super().get_object()
        # Vérification de permission au niveau objet pour les mutations
        if self.request.method not in ('GET', 'HEAD', 'OPTIONS'):
            for perm in self.get_permissions():
                if hasattr(perm, 'has_object_permission'):
                    if not perm.has_object_permission(self.request, self, obj):
                        self.permission_denied(
                            self.request,
                            message=getattr(perm, 'message', None),
                        )
        return obj

    def _check_no_ministry(self, request):
        """Retourne une Response 403 si MINISTRY_AGENT sans ministère."""
        if (request.user.role == UserRole.MINISTRY_AGENT and not request.user.ministry):
            return Response(
                {
                    'error': (
                        'A sua conta não está associada a nenhum ministério. '
                        'Contacte o administrador do sistema.'
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        return None

    def create(self, request, *args, **kwargs):
        check = self._check_no_ministry(request)
        if check:
            return check
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        user = self.request.user
        # Déterminer le tenant depuis le ministère si MINISTRY_AGENT
        ministry = serializer.validated_data.get('ministry') or (
            user.ministry if user.role == UserRole.MINISTRY_AGENT else None
        )
        tenant = getattr(ministry, 'tenant', None) if ministry else None

        project = serializer.save(
            created_by=user,
            updated_by=user,
            workflow_status=WorkflowStatus.RASCUNHO,
            tenant=tenant,
        )
        _log_audit(self.request, AuditLog.Action.CREATE, project, {
            'code': project.code,
            'title': project.title,
            'ministry': str(project.ministry),
        })

    def perform_update(self, serializer):
        project = serializer.save(updated_by=self.request.user)
        _log_audit(self.request, AuditLog.Action.UPDATE, project, {
            'updated_fields': list(serializer.validated_data.keys()),
        })

    def perform_destroy(self, instance):
        """Soft delete — vérifie que le projet n'est pas VALIDADO."""
        if instance.workflow_status == WorkflowStatus.VALIDADO:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied(
                'Não é possível eliminar um projecto validado. '
                'Solicite ao administrador que o devolva a Rascunho primeiro.'
            )
        instance.is_deleted = True
        instance.updated_by = self.request.user
        instance.save()
        _log_audit(self.request, AuditLog.Action.DELETE, instance, {
            'code': instance.code,
        })

    # ------------------------------------------------------------------
    # Acções de workflow
    # ------------------------------------------------------------------

    @action(detail=True, methods=['post'], url_path='submit',
            permission_classes=[IsAuthenticated])
    def submit(self, request, pk=None):
        """
        RASCUNHO → SUBMETIDO.
        Soumission d'un projet à la DGP par l'agent ministériel.
        """
        project = self.get_object()
        # Vérification de permission objet
        perm = CanSubmitProject()
        if not perm.has_object_permission(request, self, project):
            return Response({'error': perm.message}, status=status.HTTP_403_FORBIDDEN)

        if project.workflow_status != WorkflowStatus.RASCUNHO:
            return Response(
                {
                    'error': (
                        f'O projecto está em estado «{project.get_workflow_status_display()}» '
                        f'e não pode ser submetido novamente. '
                        f'Só projectos em Rascunho podem ser submetidos.'
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        project.workflow_status = WorkflowStatus.SUBMETIDO
        project.rejection_note = ''
        project.updated_by = request.user
        project.save(update_fields=['workflow_status', 'rejection_note', 'updated_by', 'updated_at'])

        _log_audit(request, AuditLog.Action.UPDATE, project, {
            'workflow_transition': 'RASCUNHO → SUBMETIDO',
        })

        send_workflow_notification_task.delay(project.pk, 'submit', request.user.pk)

        serializer = ProjectDetailSerializer(project, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='validate',
            permission_classes=[IsAuthenticated, CanValidateProject])
    def validate_project(self, request, pk=None):
        """
        SUBMETIDO → VALIDADO.
        Validation par la DGP.
        """
        project = self.get_object()

        if project.workflow_status != WorkflowStatus.SUBMETIDO:
            return Response(
                {
                    'error': (
                        f'Apenas projectos Submetidos podem ser validados. '
                        f'Estado actual: «{project.get_workflow_status_display()}».'
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        project.workflow_status = WorkflowStatus.VALIDADO
        project.rejection_note = ''
        project.updated_by = request.user
        project.save(update_fields=['workflow_status', 'rejection_note', 'updated_by', 'updated_at'])

        _log_audit(request, AuditLog.Action.UPDATE, project, {
            'workflow_transition': 'SUBMETIDO → VALIDADO',
        })

        send_workflow_notification_task.delay(project.pk, 'validate', request.user.pk)

        serializer = ProjectDetailSerializer(project, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='reject',
            permission_classes=[IsAuthenticated, CanValidateProject])
    def reject(self, request, pk=None):
        """
        SUBMETIDO → RASCUNHO.
        Rejet/retour en correction par la DGP.
        `rejection_note` est recommandé pour expliquer le motif.
        """
        project = self.get_object()

        if project.workflow_status != WorkflowStatus.SUBMETIDO:
            return Response(
                {
                    'error': (
                        f'Apenas projectos Submetidos podem ser devolvidos. '
                        f'Estado actual: «{project.get_workflow_status_display()}».'
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = WorkflowTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        project.workflow_status = WorkflowStatus.RASCUNHO
        project.rejection_note = serializer.validated_data.get('rejection_note', '')
        project.updated_by = request.user
        project.save(update_fields=['workflow_status', 'rejection_note', 'updated_by', 'updated_at'])

        _log_audit(request, AuditLog.Action.UPDATE, project, {
            'workflow_transition': 'SUBMETIDO → RASCUNHO',
            'rejection_note': project.rejection_note,
        })

        send_workflow_notification_task.delay(
            project.pk, 'reject', request.user.pk, project.rejection_note
        )

        serializer_out = ProjectDetailSerializer(project, context={'request': request})
        return Response(serializer_out.data)

    @action(detail=True, methods=['post'], url_path='unlock',
            permission_classes=[IsAuthenticated])
    def unlock(self, request, pk=None):
        """
        VALIDADO → RASCUNHO.
        Déverrouillage exceptionnel — ADMIN seulement.
        """
        if request.user.role != UserRole.ADMIN:
            return Response(
                {'error': 'Apenas o Administrador pode desbloquear um projecto validado.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        project = self.get_object()
        if project.workflow_status != WorkflowStatus.VALIDADO:
            return Response(
                {'error': 'Apenas projectos Validados podem ser desbloqueados.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer_in = WorkflowTransitionSerializer(data=request.data)
        serializer_in.is_valid(raise_exception=True)

        project.workflow_status = WorkflowStatus.RASCUNHO
        project.rejection_note = serializer_in.validated_data.get('rejection_note', '')
        project.updated_by = request.user
        project.save(update_fields=['workflow_status', 'rejection_note', 'updated_by', 'updated_at'])

        _log_audit(request, AuditLog.Action.UPDATE, project, {
            'workflow_transition': 'VALIDADO → RASCUNHO (desbloqueio)',
            'rejection_note': project.rejection_note,
        })

        send_workflow_notification_task.delay(
            project.pk, 'unlock', request.user.pk, project.rejection_note
        )

        serializer_out = ProjectDetailSerializer(project, context={'request': request})
        return Response(serializer_out.data)

    @action(detail=True, methods=['get'], url_path='pdf',
            permission_classes=[IsAuthenticated])
    def download_pdf(self, request, pk=None):
        """
        Gera e descarrega a ficha officielle PDF do projecto validé (A4).
        Apenas disponível para projectos com workflow_status = VALIDADO.
        """
        from django.http import HttpResponse

        project = self.get_object()

        if project.workflow_status != WorkflowStatus.VALIDADO:
            return Response(
                {'error': 'Apenas projectos validados podem ser exportados em PDF.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            from .pdf_generator import generate_project_pdf
            pdf_bytes = generate_project_pdf(project)
        except Exception as exc:
            logger.exception(f'PDF generation failed for project {project.code}: {exc}')
            return Response(
                {'error': f'Erro na geração do PDF: {exc}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = (
            f'attachment; filename="SIGIP-GB_{project.code}.pdf"'
        )
        return response

    # ------------------------------------------------------------------
    # Programmation annuelle (actions imbriquées)
    # ------------------------------------------------------------------

    @action(detail=True, methods=['get'], url_path='programming')
    def programming(self, request, pk=None):
        """Programação anual de um projecto."""
        project = self.get_object()
        qs = AnnualProgramming.objects.filter(project=project, version=1).order_by('fiscal_year')
        serializer = AnnualProgrammingSerializer(qs, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='programming/bulk',
            permission_classes=[IsAuthenticated, CanWriteProject])
    def programming_bulk(self, request, pk=None):
        """
        Upsert atomique de la programmation pluriannuelle (2026-2030).

        Corps attendu :
        {
          "programmings": [
            {"fiscal_year": 2026, "donations": 0, "loans": 500000, "state_contribution": 100000},
            ...
          ]
        }

        Règles :
        - Projet doit être en RASCUNHO (sauf ADMIN/DGP).
        - Agent ne peut modifier que son propre ministère.
        - Chaque montant ≥ 0.
        - Pas de doublon d'année.
        """
        project = self.get_object()

        # Vérif lock — VALIDADO est verrouillé pour tous sauf ADMIN
        user = request.user
        if project.workflow_status == WorkflowStatus.VALIDADO:
            if user.role != UserRole.ADMIN:
                return Response(
                    {
                        'error': (
                            'A programação de um projecto validado está bloqueada. '
                            'Apenas o Administrador pode desbloquear o projecto para edição.'
                        )
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
        elif user.role == UserRole.MINISTRY_AGENT:
            if project.workflow_status != WorkflowStatus.RASCUNHO:
                return Response(
                    {'error': 'A programação só pode ser editada enquanto o projecto está em Rascunho.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        bulk_ser = AnnualProgrammingBulkSerializer(data=request.data)
        bulk_ser.is_valid(raise_exception=True)

        with transaction.atomic():
            for row in bulk_ser.validated_data['programmings']:
                AnnualProgramming.objects.update_or_create(
                    project=project,
                    fiscal_year=row['fiscal_year'],
                    version=1,
                    defaults={
                        'donations': row.get('donations', Decimal('0')),
                        'loans': row.get('loans', Decimal('0')),
                        'state_contribution': row.get('state_contribution', Decimal('0')),
                    }
                )
            # Mise à jour du total_cost du projet
            agg = AnnualProgramming.objects.filter(project=project, version=1).aggregate(
                total=Sum(F('donations') + F('loans') + F('state_contribution'))
            )
            project.total_cost = agg['total'] or Decimal('0')
            project.updated_by = request.user
            project.save(update_fields=['total_cost', 'updated_by', 'updated_at'])

        _log_audit(request, AuditLog.Action.UPDATE, project, {
            'action': 'programming_bulk',
            'years': [r['fiscal_year'] for r in bulk_ser.validated_data['programmings']],
        })

        qs = AnnualProgramming.objects.filter(project=project, version=1).order_by('fiscal_year')
        serializer = AnnualProgrammingSerializer(qs, many=True, context={'request': request})
        return Response({'project_id': project.pk, 'programmings': serializer.data})

    @action(detail=True, methods=['get'], url_path='disbursements')
    def disbursements(self, request, pk=None):
        """Desembolsos de um projecto."""
        project = self.get_object()
        qs = Disbursement.objects.filter(project=project).select_related('financier').order_by('fiscal_year', 'period')
        serializer = DisbursementSerializer(qs, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='by-ministry')
    def by_ministry(self, request):
        """Agrupa projectos por ministério com totais."""
        qs = self.get_queryset()
        data = (
            qs.values('ministry__id', 'ministry__name', 'ministry__short_name')
            .annotate(
                project_count=Count('id'),
                total=Coalesce(
                    Sum(
                        F('annual_programmings__donations') +
                        F('annual_programmings__loans') +
                        F('annual_programmings__state_contribution')
                    ),
                    Value(Decimal('0'))
                )
            )
            .order_by('-total')
        )
        return Response(list(data))

    @action(detail=False, methods=['get'], url_path='by-pillar')
    def by_pillar(self, request):
        """Agrupa projectos por pilar com totais."""
        qs = self.get_queryset()
        data = (
            qs.values('pillar__id', 'pillar__code', 'pillar__label')
            .annotate(
                project_count=Count('id'),
                total=Coalesce(
                    Sum(
                        F('annual_programmings__donations') +
                        F('annual_programmings__loans') +
                        F('annual_programmings__state_contribution')
                    ),
                    Value(Decimal('0'))
                )
            )
            .order_by('pillar__order')
        )
        return Response(list(data))

    @action(detail=False, methods=['get'], url_path='my-ministry',
            permission_classes=[IsAuthenticated])
    def my_ministry(self, request):
        """
        Retourne le statut de rattachement au ministère de l'utilisateur connecté.
        Utile pour le frontend pour savoir si la saisie est possible.
        """
        user = request.user
        if user.role == UserRole.MINISTRY_AGENT:
            if not user.ministry:
                return Response({
                    'can_create': False,
                    'ministry': None,
                    'message': (
                        'A sua conta não está associada a nenhum ministério. '
                        'Contacte o administrador do sistema.'
                    ),
                })
            return Response({
                'can_create': True,
                'ministry': {
                    'id': user.ministry.id,
                    'name': user.ministry.name,
                    'short_name': user.ministry.short_name,
                },
                'message': None,
            })
        # DGP / ADMIN : peut créer pour n'importe quel ministère
        return Response({
            'can_create': True,
            'ministry': None,
            'message': None,
        })


# ---------------------------------------------------------------------------
# AnnualProgramming ViewSet
# ---------------------------------------------------------------------------

class AnnualProgrammingViewSet(viewsets.ModelViewSet):
    """
    Programação anual dos projectos PIP.
    MINISTRY_AGENT ne voit que la programmation des projets de son ministère.
    """
    filterset_class = AnnualProgrammingFilter
    ordering_fields = ['fiscal_year', 'project__code']
    ordering = ['project__code', 'fiscal_year']

    def get_queryset(self):
        qs = AnnualProgramming.objects.select_related(
            'project', 'project__ministry', 'project__pillar'
        ).filter(project__is_deleted=False)
        user = self.request.user
        if user.is_authenticated and user.role == UserRole.MINISTRY_AGENT:
            if not user.ministry:
                return qs.none()
            qs = qs.filter(project__ministry=user.ministry)
        return qs

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return AnnualProgrammingWriteSerializer
        return AnnualProgrammingSerializer

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            return [IsAuthenticated(), CanWriteProject()]
        return [IsAuthenticated()]

    @action(detail=False, methods=['get'], url_path='yearly-summary')
    def yearly_summary(self, request):
        """Sumário por ano fiscal."""
        qs = self.get_queryset().filter(version=1)
        data = (
            qs.values('fiscal_year')
            .annotate(
                total_donations=Coalesce(Sum('donations'), Value(Decimal('0'), output_field=DecimalField())),
                total_loans=Coalesce(Sum('loans'), Value(Decimal('0'), output_field=DecimalField())),
                total_state=Coalesce(Sum('state_contribution'), Value(Decimal('0'), output_field=DecimalField())),
            )
            .order_by('fiscal_year')
        )
        result = []
        for row in data:
            row['total'] = (
                (row['total_donations'] or 0) +
                (row['total_loans'] or 0) +
                (row['total_state'] or 0)
            )
            result.append(row)
        return Response(result)


# ---------------------------------------------------------------------------
# Disbursement ViewSet
# ---------------------------------------------------------------------------

class DisbursementViewSet(viewsets.ModelViewSet):
    """Desembolsos efectivos dos projectos com workflow de validação."""
    serializer_class = DisbursementSerializer
    filterset_class = DisbursementFilter
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    ordering_fields = ['fiscal_year', 'period', 'project__code', 'workflow_status']
    ordering = ['-submitted_at', 'project__code', 'fiscal_year', 'period']

    def get_queryset(self):
        qs = Disbursement.objects.select_related(
            'project', 'project__ministry', 'financier',
            'submitted_by', 'validated_by'
        ).filter(project__is_deleted=False)
        # Ministry agents see only their ministry's disbursements
        user = self.request.user
        if user.is_authenticated and user.role == UserRole.MINISTRY_AGENT:
            if user.ministry:
                qs = qs.filter(project__ministry=user.ministry)
            else:
                qs = qs.none()
        return qs

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            return [IsAuthenticated()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        user = self.request.user
        # Agents can only create for their ministry projects
        project = serializer.validated_data.get('project')
        if user.role == UserRole.MINISTRY_AGENT and user.ministry:
            if project.ministry_id != user.ministry_id:
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied('Não pode declarar despesas para outro ministério.')
        serializer.save(submitted_by=user)

    @action(detail=True, methods=['post'], url_path='submit')
    def submit(self, request, pk=None):
        """Agent submits disbursement to DGP for validation."""
        from django.utils import timezone
        disb = self.get_object()
        if disb.workflow_status != 'RASCUNHO':
            return Response({'detail': 'Apenas rascunhos podem ser submetidos.'},
                            status=status.HTTP_400_BAD_REQUEST)
        disb.workflow_status = 'SUBMETIDO'
        disb.submitted_by = request.user
        disb.submitted_at = timezone.now()
        disb.save()
        return Response(DisbursementSerializer(disb, context={'request': request}).data)

    @action(detail=True, methods=['post'], url_path='validate')
    def validate_disb(self, request, pk=None):
        """DGP validates a submitted disbursement."""
        from django.utils import timezone
        if not (request.user.is_dgp_staff or request.user.role == UserRole.ADMIN):
            return Response({'detail': 'Sem permissão.'}, status=status.HTTP_403_FORBIDDEN)
        disb = self.get_object()
        if disb.workflow_status != 'SUBMETIDO':
            return Response({'detail': 'Apenas desembolsos submetidos podem ser validados.'},
                            status=status.HTTP_400_BAD_REQUEST)
        disb.workflow_status = 'VALIDADO'
        disb.validated_by = request.user
        disb.validated_at = timezone.now()
        disb.save()
        return Response(DisbursementSerializer(disb, context={'request': request}).data)

    @action(detail=True, methods=['post'], url_path='reject')
    def reject(self, request, pk=None):
        """DGP rejects a submitted disbursement."""
        if not (request.user.is_dgp_staff or request.user.role == UserRole.ADMIN):
            return Response({'detail': 'Sem permissão.'}, status=status.HTTP_403_FORBIDDEN)
        disb = self.get_object()
        if disb.workflow_status != 'SUBMETIDO':
            return Response({'detail': 'Apenas desembolsos submetidos podem ser rejeitados.'},
                            status=status.HTTP_400_BAD_REQUEST)
        disb.workflow_status = 'REJEITADO'
        disb.rejection_note = request.data.get('rejection_note', '')
        disb.save()
        return Response(DisbursementSerializer(disb, context={'request': request}).data)


# ---------------------------------------------------------------------------
# PPProject ViewSet
# ---------------------------------------------------------------------------

class PPProjectViewSet(viewsets.ModelViewSet):
    queryset = PPProject.objects.select_related('project').all()
    serializer_class = PPProjectSerializer
    permission_classes = [IsAuthenticated]
    search_fields = ['private_partner', 'structure']

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            return [IsAdminOrDGP()]
        return [IsAuthenticated()]


# ---------------------------------------------------------------------------
# PIPVersion ViewSet
# ---------------------------------------------------------------------------

class PIPVersionViewSet(viewsets.ModelViewSet):
    queryset = PIPVersion.objects.all().order_by('-revision_year')
    serializer_class = PIPVersionSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['status', 'revision_year']

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            return [IsAdminOrDGP()]
        return [IsAuthenticated()]


# ---------------------------------------------------------------------------
# Dashboard View
# ---------------------------------------------------------------------------

class DashboardView(APIView):
    """
    Vue d'ensemble agrégée du PIP 2026-2030.
    Retourne les statistiques consolidées pour le tableau de bord.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        projects_qs = Project.objects.filter(is_deleted=False)
        programming_qs = AnnualProgramming.objects.filter(
            project__is_deleted=False, version=1
        )

        # Totaux généraux
        totals = programming_qs.aggregate(
            total_donations=Coalesce(Sum('donations'), Value(Decimal('0'))),
            total_loans=Coalesce(Sum('loans'), Value(Decimal('0'))),
            total_state=Coalesce(Sum('state_contribution'), Value(Decimal('0'))),
        )
        total_pip = (
            float(totals['total_donations'] or 0) +
            float(totals['total_loans'] or 0) +
            float(totals['total_state'] or 0)
        )

        # Par ministère
        by_ministry_raw = (
            programming_qs
            .values(
                ministry_id=F('project__ministry__id'),
                ministry_name=F('project__ministry__name'),
                ministry_short=F('project__ministry__short_name'),
            )
            .annotate(
                total=Coalesce(
                    Sum(F('donations') + F('loans') + F('state_contribution')),
                    Value(Decimal('0'))
                ),
                donations=Coalesce(Sum('donations'), Value(Decimal('0'))),
                loans=Coalesce(Sum('loans'), Value(Decimal('0'))),
                state_contribution=Coalesce(Sum('state_contribution'), Value(Decimal('0'))),
            )
            .order_by('-total')
        )

        by_ministry_counts = dict(
            projects_qs.values('ministry_id').annotate(c=Count('id')).values_list('ministry_id', 'c')
        )

        by_ministry = []
        for row in by_ministry_raw:
            mid = row['ministry_id']
            t = float(row['total'] or 0)
            by_ministry.append({
                'id': mid,
                'name': row['ministry_name'],
                'short_name': row['ministry_short'] or '',
                'project_count': by_ministry_counts.get(mid, 0),
                'total': t,
                'donations': float(row['donations'] or 0),
                'loans': float(row['loans'] or 0),
                'state_contribution': float(row['state_contribution'] or 0),
                'percentage': round(t / total_pip * 100, 2) if total_pip > 0 else 0,
            })

        # Par pilar
        by_pillar_raw = (
            programming_qs
            .values(
                pillar_id=F('project__pillar__id'),
                pillar_code=F('project__pillar__code'),
                pillar_label=F('project__pillar__label'),
            )
            .annotate(
                total=Coalesce(
                    Sum(F('donations') + F('loans') + F('state_contribution')),
                    Value(Decimal('0'))
                )
            )
            .order_by('pillar_code')
        )

        by_pillar_counts = dict(
            projects_qs.exclude(pillar__isnull=True)
            .values('pillar_id').annotate(c=Count('id')).values_list('pillar_id', 'c')
        )

        by_pillar = []
        for row in by_pillar_raw:
            pid = row['pillar_id']
            t = float(row['total'] or 0)
            by_pillar.append({
                'id': pid,
                'code': row['pillar_code'] or '',
                'label': row['pillar_label'] or '',
                'project_count': by_pillar_counts.get(pid, 0),
                'total': t,
                'percentage': round(t / total_pip * 100, 2) if total_pip > 0 else 0,
            })

        # Par financeur
        by_financier_raw = (
            programming_qs
            .values(
                financier_id=F('project__principal_financier__id'),
                financier_name=F('project__principal_financier__name'),
                financier_short=F('project__principal_financier__short_name'),
                financier_type=F('project__principal_financier__type'),
            )
            .annotate(
                total=Coalesce(
                    Sum(F('donations') + F('loans') + F('state_contribution')),
                    Value(Decimal('0'))
                )
            )
            .order_by('-total')
        )

        by_financier_counts = dict(
            projects_qs.values('principal_financier_id').annotate(c=Count('id'))
            .values_list('principal_financier_id', 'c')
        )

        by_financier = []
        for row in by_financier_raw:
            fid = row['financier_id']
            t = float(row['total'] or 0)
            by_financier.append({
                'id': fid,
                'name': row['financier_name'],
                'short_name': row['financier_short'] or '',
                'type': row['financier_type'] or '',
                'project_count': by_financier_counts.get(fid, 0),
                'total': t,
                'percentage': round(t / total_pip * 100, 2) if total_pip > 0 else 0,
            })

        # Trajectoire annuelle
        by_year_raw = (
            programming_qs
            .values('fiscal_year')
            .annotate(
                donations=Coalesce(Sum('donations'), Value(Decimal('0'))),
                loans=Coalesce(Sum('loans'), Value(Decimal('0'))),
                state_contribution=Coalesce(Sum('state_contribution'), Value(Decimal('0'))),
            )
            .order_by('fiscal_year')
        )

        by_year = []
        for row in by_year_raw:
            d = float(row['donations'] or 0)
            l = float(row['loans'] or 0)
            s = float(row['state_contribution'] or 0)
            by_year.append({
                'fiscal_year': row['fiscal_year'],
                'donations': d,
                'loans': l,
                'state_contribution': s,
                'total': d + l + s,
            })

        data = {
            'total_projects': projects_qs.count(),
            'total_pip_fcfa': total_pip,
            'total_donations_fcfa': float(totals['total_donations'] or 0),
            'total_loans_fcfa': float(totals['total_loans'] or 0),
            'total_state_fcfa': float(totals['total_state'] or 0),
            'total_ministries': Ministry.objects.count(),
            'total_financiers': Financier.objects.count(),
            'by_ministry': by_ministry,
            'by_pillar': by_pillar,
            'by_financier': by_financier,
            'by_year': by_year,
        }
        return Response(data)


# ---------------------------------------------------------------------------
# Execution Dashboard View
# ---------------------------------------------------------------------------

class ExecutionDashboardView(APIView):
    """
    Agrégation de l'exécution budgétaire par ministère.
    Retourne programmé vs décaissé avec taux d'exécution.
    Filtrable par ?year=2026 et ?period=Q1
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        year = request.query_params.get('year')
        period = request.query_params.get('period')
        user = request.user

        # Ministry filter for agents
        ministry_filter = Q()
        if user.role == UserRole.MINISTRY_AGENT and user.ministry:
            ministry_filter = Q(project__ministry=user.ministry)

        # Base querysets — only VALIDADO disbursements count
        prog_qs = AnnualProgramming.objects.filter(
            project__is_deleted=False, version=1
        ).filter(ministry_filter if not ministry_filter else Q(project__ministry=user.ministry) if user.role == UserRole.MINISTRY_AGENT and user.ministry else Q())
        disb_qs = Disbursement.objects.filter(
            project__is_deleted=False, workflow_status='VALIDADO'
        )
        if user.role == UserRole.MINISTRY_AGENT and user.ministry:
            prog_qs = prog_qs.filter(project__ministry=user.ministry)
            disb_qs = disb_qs.filter(project__ministry=user.ministry)

        if year:
            prog_qs = prog_qs.filter(fiscal_year=int(year))
            disb_qs = disb_qs.filter(fiscal_year=int(year))
        if period:
            disb_qs = disb_qs.filter(period=period)

        # Global totals
        global_prog = prog_qs.aggregate(
            total=Coalesce(
                Sum('donations') + Sum('loans') + Sum('state_contribution'),
                Value(Decimal('0'))
            )
        )['total']
        global_disb = disb_qs.aggregate(
            total=Coalesce(Sum('actual_amount'), Value(Decimal('0')))
        )['total']
        global_rate = round(float(global_disb) / float(global_prog) * 100, 2) if global_prog > 0 else 0

        # By ministry
        if user.role == UserRole.MINISTRY_AGENT and user.ministry:
            ministries = Ministry.objects.filter(id=user.ministry_id)
        else:
            ministries = Ministry.objects.all().order_by('name')

        by_ministry = []
        for m in ministries:
            m_prog = prog_qs.filter(project__ministry=m).aggregate(
                total=Coalesce(Sum('donations') + Sum('loans') + Sum('state_contribution'), Value(Decimal('0')))
            )['total']
            m_disb = disb_qs.filter(project__ministry=m).aggregate(
                total=Coalesce(Sum('actual_amount'), Value(Decimal('0')))
            )['total']
            prog = float(m_prog)
            disb = float(m_disb)
            rate = round(disb / prog * 100, 2) if prog > 0 else 0
            by_ministry.append({
                'id': m.id, 'name': m.name, 'short_name': m.short_name,
                'programmed': prog, 'disbursed': disb, 'execution_rate': rate,
            })
        by_ministry.sort(key=lambda x: x['programmed'], reverse=True)

        # By year
        by_year = []
        base_disb = Disbursement.objects.filter(project__is_deleted=False, workflow_status='VALIDADO')
        if user.role == UserRole.MINISTRY_AGENT and user.ministry:
            base_disb = base_disb.filter(project__ministry=user.ministry)
        for yr in [2026, 2027, 2028, 2029, 2030]:
            yr_prog_qs = prog_qs.filter(fiscal_year=yr) if not year else prog_qs
            if year and int(year) != yr:
                by_year.append({'year': yr, 'programmed': 0, 'disbursed': 0, 'rate': 0})
                continue
            yr_prog = yr_prog_qs.filter(fiscal_year=yr).aggregate(
                total=Coalesce(Sum('donations') + Sum('loans') + Sum('state_contribution'), Value(Decimal('0')))
            )['total']
            yr_disb_qs = base_disb.filter(fiscal_year=yr)
            if period:
                yr_disb_qs = yr_disb_qs.filter(period=period)
            yr_disb = yr_disb_qs.aggregate(total=Coalesce(Sum('actual_amount'), Value(Decimal('0'))))['total']
            by_year.append({
                'year': yr, 'programmed': float(yr_prog), 'disbursed': float(yr_disb),
                'rate': round(float(yr_disb) / float(yr_prog) * 100, 2) if yr_prog > 0 else 0,
            })

        # Pending count for DGP
        pending_count = 0
        if user.is_dgp_staff or user.role == UserRole.ADMIN:
            pending_count = Disbursement.objects.filter(
                project__is_deleted=False, workflow_status='SUBMETIDO'
            ).count()

        proj_qs = Project.objects.filter(is_deleted=False)
        if user.role == UserRole.MINISTRY_AGENT and user.ministry:
            proj_qs = proj_qs.filter(ministry=user.ministry)

        return Response({
            'global_programmed': float(global_prog),
            'global_disbursed': float(global_disb),
            'global_rate': global_rate,
            'project_count': proj_qs.count(),
            'pending_count': pending_count,
            'by_ministry': by_ministry,
            'by_year': by_year,
        })


# ---------------------------------------------------------------------------
# Import View
# ---------------------------------------------------------------------------

class ImportView(APIView):
    """
    Endpoint pour importer des données PIP depuis Excel ou JSON.
    Déclenche une tâche Celery asynchrone.
    """
    permission_classes = [IsAuthenticated, IsAdminOrDGP]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request, *args, **kwargs):
        file = request.FILES.get('file')
        json_data = request.data.get('data')

        if not file and not json_data:
            return Response(
                {'error': 'Forneça um ficheiro (file) ou dados JSON (data).'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Queue async task
        task = import_pip_data_task.delay(
            user_id=request.user.id,
            json_data=json_data if json_data else None,
        )

        return Response({
            'task_id': task.id,
            'status': 'queued',
            'message': 'Importação em curso. Consulte o task_id para acompanhar o progresso.'
        }, status=status.HTTP_202_ACCEPTED)

    def get(self, request, *args, **kwargs):
        """Status de uma tarefa de importação."""
        task_id = request.query_params.get('task_id')
        if not task_id:
            return Response({'error': 'Forneça task_id.'}, status=status.HTTP_400_BAD_REQUEST)

        from celery.result import AsyncResult
        result = AsyncResult(task_id)
        return Response({
            'task_id': task_id,
            'status': result.status,
            'result': result.result if result.ready() else None,
        })
