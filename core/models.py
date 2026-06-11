"""
Core models for SIGIP-GB.
Modelos base: Tenant, User, AuditLog, Region, Currency, FiscalYear.
"""
import json
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _


# ---------------------------------------------------------------------------
# Tenant  (Ministério ou DGP)
# ---------------------------------------------------------------------------
class Tenant(models.Model):
    """
    Representa uma instituição/ministério no sistema.
    Cada utilizador pertence a um tenant que controla o acesso aos dados.
    """
    name = models.CharField(_('Nome'), max_length=255, unique=True)
    short_name = models.CharField(_('Sigla'), max_length=20, blank=True)
    is_dgp = models.BooleanField(
        _('É DGP?'), default=False,
        help_text=_('Marque se este tenant é a Direcção Geral do Planeamento (acesso total).')
    )
    created_at = models.DateTimeField(_('Criado em'), auto_now_add=True)

    class Meta:
        verbose_name = _('Instituição')
        verbose_name_plural = _('Instituições')
        ordering = ['name']

    def __str__(self):
        return self.short_name or self.name


# ---------------------------------------------------------------------------
# Custom User
# ---------------------------------------------------------------------------
class UserRole(models.TextChoices):
    ADMIN = 'ADMIN', _('Administrador')
    DGP_ANALYST = 'DGP_ANALYST', _('Analista DGP')
    MINISTRY_AGENT = 'MINISTRY_AGENT', _('Agente Ministerial')
    VALIDATOR = 'VALIDATOR', _('Validador')
    READER = 'READER', _('Leitor')
    DONOR = 'DONOR', _('Parceiro/Doador')


class User(AbstractUser):
    """
    Utilizador personalizado do SIGIP-GB com tenant e papel (role).
    """
    tenant = models.ForeignKey(
        Tenant, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name=_('Instituição'), related_name='users'
    )
    role = models.CharField(
        _('Papel'), max_length=20,
        choices=UserRole.choices, default=UserRole.READER
    )
    # Lien direct vers le ministère pour les agents ministériels.
    # Utiliser un import paresseux (string) pour éviter les imports circulaires.
    ministry = models.ForeignKey(
        'sigip.Ministry', on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name=_('Ministério'), related_name='agents',
        help_text=_('Ministério do agente (obrigatório para o papel Agente Ministerial)')
    )
    mfa_enabled = models.BooleanField(_('MFA activo'), default=False)
    phone = models.CharField(_('Telefone'), max_length=30, blank=True)
    created_at = models.DateTimeField(_('Criado em'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Actualizado em'), auto_now=True)

    class Meta:
        verbose_name = _('Utilizador')
        verbose_name_plural = _('Utilizadores')

    def __str__(self):
        return f'{self.get_full_name() or self.username} [{self.get_role_display()}]'

    @property
    def is_dgp_staff(self):
        return self.role in (UserRole.ADMIN, UserRole.DGP_ANALYST) or (
            self.tenant and self.tenant.is_dgp
        )


# ---------------------------------------------------------------------------
# Audit Log
# ---------------------------------------------------------------------------
class AuditLog(models.Model):
    """
    Registo de auditoria de todas as operações críticas do sistema.
    """
    class Action(models.TextChoices):
        CREATE = 'CREATE', _('Criar')
        UPDATE = 'UPDATE', _('Actualizar')
        DELETE = 'DELETE', _('Eliminar')
        LOGIN = 'LOGIN', _('Autenticação')
        LOGOUT = 'LOGOUT', _('Logout')
        EXPORT = 'EXPORT', _('Exportar')
        IMPORT = 'IMPORT', _('Importar')

    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name=_('Utilizador'), related_name='audit_logs'
    )
    action = models.CharField(_('Acção'), max_length=20, choices=Action.choices)
    model_name = models.CharField(_('Modelo'), max_length=100, blank=True)
    object_id = models.CharField(_('ID do objecto'), max_length=50, blank=True)
    changes = models.JSONField(_('Alterações'), default=dict, blank=True)
    timestamp = models.DateTimeField(_('Data/hora'), auto_now_add=True, db_index=True)
    ip_address = models.GenericIPAddressField(_('Endereço IP'), null=True, blank=True)
    user_agent = models.CharField(_('User-Agent'), max_length=500, blank=True)

    class Meta:
        verbose_name = _('Registo de Auditoria')
        verbose_name_plural = _('Registos de Auditoria')
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['model_name', 'object_id']),
            models.Index(fields=['user', 'timestamp']),
        ]

    def __str__(self):
        return f'{self.action} – {self.model_name}/{self.object_id} por {self.user} em {self.timestamp}'


# ---------------------------------------------------------------------------
# Region (Região administrativa)
# ---------------------------------------------------------------------------
class Region(models.Model):
    """
    Região administrativa da Guiné-Bissau.
    (Bafatá, Biombo, Bolama/Bijagós, Cacheu, Gabú, Oio, Quinara, Tombali, SAB)
    """
    name = models.CharField(_('Nome'), max_length=100, unique=True)
    code = models.CharField(_('Código'), max_length=10, unique=True)

    class Meta:
        verbose_name = _('Região')
        verbose_name_plural = _('Regiões')
        ordering = ['name']

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# Currency
# ---------------------------------------------------------------------------
class Currency(models.Model):
    """Moeda utilizada no sistema (por defeito XOF/FCFA)."""
    code = models.CharField(_('Código'), max_length=5, unique=True, default='XOF')
    name = models.CharField(_('Nome'), max_length=100)
    symbol = models.CharField(_('Símbolo'), max_length=10, default='FCFA')

    class Meta:
        verbose_name = _('Moeda')
        verbose_name_plural = _('Moedas')

    def __str__(self):
        return f'{self.code} – {self.symbol}'


# ---------------------------------------------------------------------------
# FiscalYear (Ano fiscal)
# ---------------------------------------------------------------------------
class FiscalYear(models.Model):
    """Ano fiscal do PIP 2026-2030."""
    year = models.IntegerField(_('Ano'), unique=True)
    is_active = models.BooleanField(_('Activo'), default=False)
    label = models.CharField(_('Etiqueta'), max_length=20, blank=True)

    class Meta:
        verbose_name = _('Ano Fiscal')
        verbose_name_plural = _('Anos Fiscais')
        ordering = ['year']

    def __str__(self):
        return str(self.year)

    def save(self, *args, **kwargs):
        if not self.label:
            self.label = str(self.year)
        super().save(*args, **kwargs)
