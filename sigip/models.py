"""
SIGIP models – Programa de Investimento Público (PIP) 2026-2030
República da Guiné-Bissau

NOTA SOBRE UNIDADES MONETÁRIAS:
Todos os montantes são armazenados em FCFA (Franco CFA).
Exemplo: 275 000 000 FCFA = 275_000_000
"""
from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from core.models import Tenant, Region


# ---------------------------------------------------------------------------
# Pillar  (Pilar PND 2026-2030)
# ---------------------------------------------------------------------------
class Pillar(models.Model):
    """
    Pilar do Plano Nacional de Desenvolvimento (PND) 2026-2030.
    Existem 6 pilares oficiais.
    """
    code = models.CharField(_('Código'), max_length=10, unique=True)
    label = models.CharField(_('Denominação'), max_length=255)
    description = models.TextField(_('Descrição'), blank=True)
    order = models.PositiveSmallIntegerField(_('Ordem'), default=0)

    class Meta:
        verbose_name = _('Pilar PND')
        verbose_name_plural = _('Pilares PND')
        ordering = ['order', 'code']

    def __str__(self):
        return f'{self.code} – {self.label}'


# ---------------------------------------------------------------------------
# Sector (Sector e sub-sector)
# ---------------------------------------------------------------------------
class Sector(models.Model):
    """
    Sector de actividade. Pode ter sub-sectores (parent FK).
    O código do projecto: primeiros 2 dígitos = sector.
    """
    code = models.CharField(_('Código'), max_length=10, unique=True)
    label = models.CharField(_('Denominação'), max_length=255)
    parent = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name=_('Sector pai'), related_name='sub_sectors'
    )

    class Meta:
        verbose_name = _('Sector')
        verbose_name_plural = _('Sectores')
        ordering = ['code']

    def __str__(self):
        return f'{self.code} – {self.label}'


# ---------------------------------------------------------------------------
# GovPriority (Prioridade governamental)
# ---------------------------------------------------------------------------
class GovPriority(models.Model):
    """Prioridade governamental associada ao projecto."""
    label = models.CharField(_('Denominação'), max_length=255)
    order = models.PositiveSmallIntegerField(_('Ordem'), default=0)

    class Meta:
        verbose_name = _('Prioridade Governamental')
        verbose_name_plural = _('Prioridades Governamentais')
        ordering = ['order', 'label']

    def __str__(self):
        return self.label


# ---------------------------------------------------------------------------
# Ministry (Ministério / Instituição responsável)
# ---------------------------------------------------------------------------
class Ministry(models.Model):
    """
    Ministério ou instituição responsável pelo projecto.
    Associado a um pilar PND e opcionalmente a uma prioridade governamental.
    """
    name = models.CharField(_('Nome'), max_length=255, unique=True)
    short_name = models.CharField(_('Sigla'), max_length=30, blank=True)
    pillar = models.ForeignKey(
        Pillar, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name=_('Pilar'), related_name='ministries'
    )
    gov_priority = models.ForeignKey(
        GovPriority, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name=_('Prioridade Governamental'), related_name='ministries'
    )

    class Meta:
        verbose_name = _('Ministério')
        verbose_name_plural = _('Ministérios')
        ordering = ['name']

    def __str__(self):
        return self.short_name or self.name


# ---------------------------------------------------------------------------
# Financier (Financiador / Parceiro)
# ---------------------------------------------------------------------------
class FinancierType(models.TextChoices):
    ESTADO = 'ESTADO', _('Estado (Contribuição Nacional)')
    BILATERAL = 'BILATERAL', _('Bilateral')
    MULTILATERAL = 'MULTILATERAL', _('Multilateral')
    UN_AGENCY = 'UN_AGENCY', _('Agência ONU')
    PPP = 'PPP', _('Parceria Público-Privada')
    OTHER = 'OTHER', _('Outro')


class Financier(models.Model):
    """
    Financiador do projecto: Estado, banco de desenvolvimento, agência ONU, bilateral, etc.
    """
    name = models.CharField(_('Nome'), max_length=255, unique=True)
    short_name = models.CharField(_('Sigla'), max_length=50, blank=True)
    type = models.CharField(
        _('Tipo'), max_length=20,
        choices=FinancierType.choices, default=FinancierType.OTHER
    )
    country = models.CharField(_('País'), max_length=100, blank=True)
    website = models.URLField(_('Website'), blank=True)

    class Meta:
        verbose_name = _('Financiador')
        verbose_name_plural = _('Financiadores')
        ordering = ['name']

    def __str__(self):
        return self.short_name or self.name


# ---------------------------------------------------------------------------
# ExpenseNature (Natureza da Despesa)
# ---------------------------------------------------------------------------
class ExpenseNature(models.Model):
    """Natureza da despesa do projecto (ex.: Investimento, Funcionamento)."""
    code = models.CharField(_('Código'), max_length=20, unique=True)
    label = models.CharField(_('Denominação'), max_length=255)

    class Meta:
        verbose_name = _('Natureza da Despesa')
        verbose_name_plural = _('Naturezas da Despesa')
        ordering = ['code']

    def __str__(self):
        return f'{self.code} – {self.label}'


# ---------------------------------------------------------------------------
# Project (Projecto de Investimento)
# ---------------------------------------------------------------------------
class ProjectStatus(models.TextChoices):
    IDENTIFIED = 'IDENTIFIED', _('Identificado')
    IN_PROGRESS = 'IN_PROGRESS', _('Em Execução')
    COMPLETED = 'COMPLETED', _('Concluído')
    SUSPENDED = 'SUSPENDED', _('Suspenso')
    CANCELLED = 'CANCELLED', _('Cancelado')


class WorkflowStatus(models.TextChoices):
    """
    Estado do fluxo de validação da saisie (independente do estado de execução).
    RASCUNHO   → criado/editável pelo ministério
    SUBMETIDO  → enviado à DGP, só-leitura para o ministério
    VALIDADO   → aprovado pela DGP, bloqueado (apenas ADMIN pode desbloquear)
    """
    RASCUNHO  = 'RASCUNHO',  _('Rascunho')
    SUBMETIDO = 'SUBMETIDO', _('Submetido')
    VALIDADO  = 'VALIDADO',  _('Validado')


# Transições permitidas por papel
WORKFLOW_TRANSITIONS = {
    # (from_status, role) -> to_status
    ('RASCUNHO',  'MINISTRY_AGENT'): 'SUBMETIDO',
    ('RASCUNHO',  'DGP_ANALYST'):    'SUBMETIDO',
    ('RASCUNHO',  'ADMIN'):          'SUBMETIDO',
    ('SUBMETIDO', 'DGP_ANALYST'):    'VALIDADO',
    ('SUBMETIDO', 'VALIDATOR'):      'VALIDADO',
    ('SUBMETIDO', 'ADMIN'):          'VALIDADO',
    # Rejeição : SUBMETIDO → RASCUNHO
    ('SUBMETIDO', 'DGP_ANALYST'):    'RASCUNHO',
    ('SUBMETIDO', 'VALIDATOR'):      'RASCUNHO',
    ('SUBMETIDO', 'ADMIN'):          'RASCUNHO',
    # Déverrouillage exceptionnel : VALIDADO → RASCUNHO (ADMIN seulement)
    ('VALIDADO',  'ADMIN'):          'RASCUNHO',
}


class StateFunction(models.Model):
    """
    Função do Estado (COFOG – Classification of Functions of Government).
    Classificação orçamental conforme normas UEMOA/CEDEAO.
    """
    code = models.CharField(_('Código'), max_length=10, unique=True)
    label = models.CharField(_('Denominação'), max_length=255)
    order = models.PositiveSmallIntegerField(_('Ordem'), default=0)

    class Meta:
        verbose_name = _('Função do Estado')
        verbose_name_plural = _('Funções do Estado')
        ordering = ['order', 'code']

    def __str__(self):
        return f'{self.code} – {self.label}'


class Project(models.Model):
    """
    Projecto do Programa de Investimento Público (PIP) 2026-2030.

    MONTANTES EM FCFA.
    Código do projecto: 9 caracteres alfanuméricos únicos.
    """
    # Identificação
    code = models.CharField(
        _('Código'), max_length=20, unique=True, db_index=True,
        help_text=_('Código único do projecto (ex.: 111920101)')
    )
    title = models.CharField(_('Título'), max_length=500)
    description = models.TextField(_('Descrição'), blank=True)

    # Classificação
    ministry = models.ForeignKey(
        Ministry, on_delete=models.PROTECT,
        verbose_name=_('Ministério'), related_name='projects'
    )
    sector = models.ForeignKey(
        Sector, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name=_('Sector'), related_name='projects'
    )
    pillar = models.ForeignKey(
        Pillar, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name=_('Pilar PND'), related_name='projects'
    )
    gov_priority = models.ForeignKey(
        GovPriority, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name=_('Prioridade Governamental'), related_name='projects'
    )
    expense_nature = models.ForeignKey(
        ExpenseNature, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name=_('Natureza da Despesa'), related_name='projects'
    )
    state_function = models.ForeignKey(
        'StateFunction', on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name=_('Função do Estado'), related_name='projects'
    )

    # Financiamento
    principal_financier = models.ForeignKey(
        Financier, on_delete=models.PROTECT,
        verbose_name=_('Financiador Principal'), related_name='led_projects'
    )

    # Localização
    region = models.ForeignKey(
        Region, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name=_('Região'), related_name='projects'
    )
    is_national = models.BooleanField(_('Nacional'), default=True)

    # Estado de execução
    status = models.CharField(
        _('Estado'), max_length=20,
        choices=ProjectStatus.choices, default=ProjectStatus.IDENTIFIED
    )

    # Estado do fluxo de validação (saisie continue)
    workflow_status = models.CharField(
        _('Estado de Validação'), max_length=20,
        choices=WorkflowStatus.choices, default=WorkflowStatus.RASCUNHO,
        db_index=True,
        help_text=_('Rascunho → Submetido (pelo ministério) → Validado (pela DGP)')
    )
    rejection_note = models.TextField(
        _('Nota de Rejeição'), blank=True,
        help_text=_('Motivo de devolução preenchido pela DGP')
    )

    # Datas
    start_date = models.DateField(_('Data de Início'), null=True, blank=True)
    end_date = models.DateField(_('Data de Conclusão'), null=True, blank=True)

    # Montante total programado (soma das programações anuais) – em FCFA
    total_cost = models.DecimalField(
        _('Custo Total (FCFA)'), max_digits=20, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        help_text=_('Montante total em FCFA')
    )

    # Tenant (ministério proprietário do registo)
    tenant = models.ForeignKey(
        Tenant, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name=_('Instituição'), related_name='projects'
    )

    # Meta
    created_at = models.DateTimeField(_('Criado em'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Actualizado em'), auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='projects_created',
        verbose_name=_('Criado por')
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='projects_updated',
        verbose_name=_('Actualizado por')
    )
    is_deleted = models.BooleanField(_('Eliminado'), default=False, db_index=True)

    class Meta:
        verbose_name = _('Projecto')
        verbose_name_plural = _('Projectos')
        ordering = ['code']
        indexes = [
            models.Index(fields=['ministry', 'status']),
            models.Index(fields=['ministry', 'workflow_status']),
            models.Index(fields=['pillar', 'sector']),
            models.Index(fields=['is_deleted']),
        ]

    def __str__(self):
        return f'{self.code} – {self.title[:60]}'

    @property
    def total_programmed(self):
        """Calcula o total programado a partir das programações anuais."""
        result = self.annual_programmings.aggregate(
            total=models.Sum(
                models.F('donations') + models.F('loans') + models.F('state_contribution')
            )
        )
        return result['total'] or Decimal('0')


# ---------------------------------------------------------------------------
# ProjectFinancier (Financiadores do projecto)
# ---------------------------------------------------------------------------
class FinancierRole(models.TextChoices):
    PRINCIPAL = 'PRINCIPAL', _('Principal')
    COFINANCER = 'COFINANCER', _('Co-Financiador')


class ProjectFinancier(models.Model):
    """
    Relação entre projecto e financiador (permite múltiplos financiadores por projecto).
    """
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE,
        verbose_name=_('Projecto'), related_name='project_financiers'
    )
    financier = models.ForeignKey(
        Financier, on_delete=models.PROTECT,
        verbose_name=_('Financiador'), related_name='project_financiers'
    )
    role = models.CharField(
        _('Papel'), max_length=20,
        choices=FinancierRole.choices, default=FinancierRole.COFINANCER
    )

    class Meta:
        verbose_name = _('Financiador do Projecto')
        verbose_name_plural = _('Financiadores do Projecto')
        unique_together = [('project', 'financier')]

    def __str__(self):
        return f'{self.financier} – {self.project.code} [{self.role}]'


# ---------------------------------------------------------------------------
# AnnualProgramming (Programação Anual)
# ---------------------------------------------------------------------------
class AnnualProgramming(models.Model):
    """
    Programação anual do projecto por fonte de financiamento.
    Todos os montantes em FCFA.

    Fontes:
    - donations  : Donativos (recursos externos não reembolsáveis)
    - loans      : Empréstimos (recursos externos reembolsáveis)
    - state_contribution: Contribuição do Estado (recursos internos)
    """
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE,
        verbose_name=_('Projecto'), related_name='annual_programmings'
    )
    fiscal_year = models.IntegerField(
        _('Ano Fiscal'),
        help_text=_('Ano de programação (2026-2030)')
    )
    # Montantes em FCFA
    donations = models.DecimalField(
        _('Donativos (FCFA)'), max_digits=20, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))]
    )
    loans = models.DecimalField(
        _('Empréstimos (FCFA)'), max_digits=20, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))]
    )
    state_contribution = models.DecimalField(
        _('Financiamento interno do Estado (FCFA)'), max_digits=20, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))]
    )
    version = models.IntegerField(_('Versão'), default=1)

    class Meta:
        verbose_name = _('Programação Anual')
        verbose_name_plural = _('Programações Anuais')
        ordering = ['project', 'fiscal_year']
        unique_together = [('project', 'fiscal_year', 'version')]
        indexes = [
            models.Index(fields=['fiscal_year']),
            models.Index(fields=['project', 'fiscal_year']),
        ]

    def __str__(self):
        return f'{self.project.code} – {self.fiscal_year} (v{self.version})'

    @property
    def total(self):
        """Total = Donativos + Empréstimos + Contribuição do Estado."""
        return self.donations + self.loans + self.state_contribution

    @classmethod
    def get_yearly_totals(cls, fiscal_year=None):
        """Retorna totais agregados por ano (ou para um ano específico)."""
        from django.db.models import Sum
        qs = cls.objects.filter(version=1)
        if fiscal_year:
            qs = qs.filter(fiscal_year=fiscal_year)
        return qs.aggregate(
            total_donations=Sum('donations'),
            total_loans=Sum('loans'),
            total_state=Sum('state_contribution'),
        )


# ---------------------------------------------------------------------------
# Disbursement (Desembolso)
# ---------------------------------------------------------------------------
class DisbursementPeriod(models.TextChoices):
    Q1 = 'Q1', _('1º Trimestre')
    Q2 = 'Q2', _('2º Trimestre')
    Q3 = 'Q3', _('3º Trimestre')
    Q4 = 'Q4', _('4º Trimestre')
    ANNUAL = 'ANNUAL', _('Anual')


class Disbursement(models.Model):
    """
    Desembolso efectivo vs programado para um projecto.
    Permite seguir a execução financeira por trimestre.
    Montantes em FCFA.
    """
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE,
        verbose_name=_('Projecto'), related_name='disbursements'
    )
    financier = models.ForeignKey(
        Financier, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name=_('Financiador'), related_name='disbursements'
    )
    fiscal_year = models.IntegerField(_('Ano Fiscal'))
    period = models.CharField(
        _('Período'), max_length=10,
        choices=DisbursementPeriod.choices, default=DisbursementPeriod.ANNUAL
    )
    programmed_amount = models.DecimalField(
        _('Montante Programado (FCFA)'), max_digits=20, decimal_places=2,
        default=Decimal('0'), validators=[MinValueValidator(Decimal('0'))]
    )
    actual_amount = models.DecimalField(
        _('Montante Realizado (FCFA)'), max_digits=20, decimal_places=2,
        default=Decimal('0'), validators=[MinValueValidator(Decimal('0'))]
    )
    date = models.DateField(_('Data do Desembolso'), null=True, blank=True)
    notes = models.TextField(_('Notas'), blank=True)

    class Meta:
        verbose_name = _('Desembolso')
        verbose_name_plural = _('Desembolsos')
        ordering = ['project', 'fiscal_year', 'period']
        indexes = [
            models.Index(fields=['project', 'fiscal_year']),
        ]

    def __str__(self):
        return f'{self.project.code} – {self.fiscal_year}/{self.period}'

    @property
    def execution_rate(self):
        if self.programmed_amount > 0:
            return round(float(self.actual_amount) / float(self.programmed_amount) * 100, 2)
        return 0.0


# ---------------------------------------------------------------------------
# PPProject (Parceria Público-Privada)
# ---------------------------------------------------------------------------
class PPProject(models.Model):
    """
    Projecto de Parceria Público-Privada (PPP).
    Pode estar ligado a um projecto PIP ou ser independente.
    Montantes em FCFA.
    """
    project = models.OneToOneField(
        Project, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name=_('Projecto PIP associado'), related_name='ppp_info'
    )
    private_partner = models.CharField(_('Parceiro Privado'), max_length=255)
    structure = models.CharField(_('Estrutura/Modalidade'), max_length=255, blank=True)
    amount = models.DecimalField(
        _('Montante (FCFA)'), max_digits=20, decimal_places=2,
        default=Decimal('0'), validators=[MinValueValidator(Decimal('0'))]
    )
    signing_date = models.DateField(_('Data de Assinatura'), null=True, blank=True)
    duration_years = models.PositiveIntegerField(_('Duração (anos)'), null=True, blank=True)
    notes = models.TextField(_('Notas'), blank=True)

    class Meta:
        verbose_name = _('Projecto PPP')
        verbose_name_plural = _('Projectos PPP')

    def __str__(self):
        return f'PPP – {self.private_partner}'


# ---------------------------------------------------------------------------
# PIPVersion (Versão do PIP)
# ---------------------------------------------------------------------------
class PIPVersionStatus(models.TextChoices):
    DRAFT = 'DRAFT', _('Rascunho')
    REVIEW = 'REVIEW', _('Em Revisão')
    ADOPTED = 'ADOPTED', _('Adoptado')
    ARCHIVED = 'ARCHIVED', _('Arquivado')


class PIPVersion(models.Model):
    """
    Versão do Programa de Investimento Público.
    Permite gerir revisões anuais do PIP (PIP 2026, PIP 2027, etc.).
    """
    revision_year = models.IntegerField(_('Ano de Revisão'), unique=True)
    status = models.CharField(
        _('Estado'), max_length=20,
        choices=PIPVersionStatus.choices, default=PIPVersionStatus.DRAFT
    )
    adoption_date = models.DateField(_('Data de Adopção'), null=True, blank=True)
    notes = models.TextField(_('Notas'), blank=True)
    created_at = models.DateTimeField(_('Criado em'), auto_now_add=True)

    class Meta:
        verbose_name = _('Versão do PIP')
        verbose_name_plural = _('Versões do PIP')
        ordering = ['-revision_year']

    def __str__(self):
        return f'PIP {self.revision_year} [{self.get_status_display()}]'
