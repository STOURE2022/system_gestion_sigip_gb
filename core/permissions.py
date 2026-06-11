"""
Custom DRF permissions for SIGIP-GB.
"""
from rest_framework.permissions import BasePermission, SAFE_METHODS
from .models import UserRole


class IsDGPStaff(BasePermission):
    """Permite acesso apenas a utilizadores da DGP (ADMIN ou DGP_ANALYST)."""
    message = 'Acesso restrito ao pessoal da DGP.'

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.is_dgp_staff
        )


class IsAdminOrDGP(BasePermission):
    """Acesso total para ADMIN/DGP; leitura para todos autenticados."""
    message = 'Sem permissão para esta operação.'

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.is_dgp_staff or request.user.role == UserRole.ADMIN


class IsMinistryAgentOrAbove(BasePermission):
    """Agentes ministeriais podem editar os seus próprios dados; DGP pode editar tudo."""
    message = 'Acesso restrito a agentes ministeriais ou superiores.'

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.role in (
            UserRole.ADMIN,
            UserRole.DGP_ANALYST,
            UserRole.MINISTRY_AGENT,
            UserRole.VALIDATOR,
        )


class IsValidatorOrAbove(BasePermission):
    """Validadores e superiores podem aprovar/rejeitar registos."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.role in (
            UserRole.ADMIN,
            UserRole.DGP_ANALYST,
            UserRole.VALIDATOR,
        )


class ReadOnly(BasePermission):
    """Apenas leitura."""
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.method in SAFE_METHODS
        )


# ---------------------------------------------------------------------------
# CanWriteProject  —  permission centrale pour la saisie continue
# ---------------------------------------------------------------------------

class CanWriteProject(BasePermission):
    """
    Règles d'écriture sur les projets :

    ADMIN / DGP_ANALYST :
        - Peut créer, modifier, supprimer n'importe quel projet.
        - Peut modifier un projet VALIDADO.

    VALIDATOR :
        - Lecture seule sur tous les projets.
        - Peut changer workflow_status (via actions dédiées).

    MINISTRY_AGENT :
        - Peut créer des projets pour SON ministère uniquement.
        - Peut modifier seulement les projets RASCUNHO de son ministère.
        - Ne peut pas modifier un projet SUBMETIDO ou VALIDADO.
        - Doit être rattaché à un ministère (sinon 403 explicite).

    READER / DONOR :
        - Lecture seule.
    """
    message = 'Sem permissão para esta operação.'

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        # Lecture : tout le monde
        if request.method in SAFE_METHODS:
            return True
        # Écriture : ADMIN, DGP, MINISTRY_AGENT seulement
        return request.user.role in (
            UserRole.ADMIN,
            UserRole.DGP_ANALYST,
            UserRole.MINISTRY_AGENT,
        )

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        # Lecture toujours permise
        if request.method in SAFE_METHODS:
            return True

        user = request.user

        # ADMIN : accès total
        if user.role == UserRole.ADMIN:
            return True

        # DGP_ANALYST : peut tout modifier sauf VALIDADO
        if user.role == UserRole.DGP_ANALYST:
            from sigip.models import WorkflowStatus
            if obj.workflow_status == WorkflowStatus.VALIDADO:
                self.message = (
                    'Este projecto está validado. Apenas um Administrador pode '
                    'desbloqueá-lo.'
                )
                return False
            return True

        # MINISTRY_AGENT : seulement son ministère, seulement RASCUNHO
        if user.role == UserRole.MINISTRY_AGENT:
            if not user.ministry:
                self.message = (
                    'A sua conta não está associada a nenhum ministério. '
                    'Contacte o administrador do sistema.'
                )
                return False
            if obj.ministry_id != user.ministry_id:
                self.message = 'Não tem permissão para modificar projectos de outro ministério.'
                return False
            from sigip.models import WorkflowStatus
            if obj.workflow_status != WorkflowStatus.RASCUNHO:
                self.message = (
                    'Este projecto foi submetido à DGP e não pode ser editado. '
                    'Aguarde a validação ou a devolução.'
                )
                return False
            return True

        return False


class CanSubmitProject(BasePermission):
    """
    Controle d'accès pour l'action 'submit' (RASCUNHO → SUBMETIDO).
    Seuls l'agent du ministère propriétaire, DGP_ANALYST et ADMIN.
    """
    message = 'Sem permissão para submeter este projecto.'

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.role == UserRole.ADMIN:
            return True
        if user.role == UserRole.DGP_ANALYST:
            return True
        if user.role == UserRole.MINISTRY_AGENT:
            if not user.ministry:
                self.message = (
                    'A sua conta não está associada a nenhum ministério.'
                )
                return False
            return obj.ministry_id == user.ministry_id
        return False


class CanValidateProject(BasePermission):
    """
    Controle d'accès pour 'validate' et 'reject' (DGP/VALIDATOR/ADMIN).
    """
    message = 'Sem permissão para validar ou devolver projectos.'

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.role in (
            UserRole.ADMIN,
            UserRole.DGP_ANALYST,
            UserRole.VALIDATOR,
        )


# ---------------------------------------------------------------------------
# TenantFilterMixin  (inchangé — garde la compatibilité)
# ---------------------------------------------------------------------------

class TenantFilterMixin:
    """
    Mixin pour ViewSets qui filtre automatiquement les querysets
    par tenant de l'utilisateur authentifié.
    Utilisateurs DGP voient toutes les données.
    """
    def get_tenant_queryset(self, queryset):
        user = self.request.user
        if user.is_authenticated and not user.is_dgp_staff:
            if hasattr(queryset.model, 'tenant'):
                queryset = queryset.filter(tenant=user.tenant)
        return queryset


# ---------------------------------------------------------------------------
# MinistryFilterMixin  (nouveau — filtre par ministère pour MINISTRY_AGENT)
# ---------------------------------------------------------------------------

class MinistryFilterMixin:
    """
    Mixin pour ProjectViewSet : filtre le queryset par ministère de l'agent.
    - ADMIN / DGP_ANALYST / VALIDATOR / READER / DONOR : voient tout.
    - MINISTRY_AGENT avec ministry : voient uniquement leur ministère.
    - MINISTRY_AGENT sans ministry : queryset vide (pas d'erreur 500).
    """
    def get_ministry_queryset(self, queryset):
        user = self.request.user
        if not user.is_authenticated:
            return queryset.none()
        if user.role == UserRole.MINISTRY_AGENT:
            if not user.ministry:
                return queryset.none()
            return queryset.filter(ministry=user.ministry)
        return queryset
