"""
Helpers de création de données pour les tests SIGIP-GB.
Pas de dépendance factory_boy : utilisation directe de l'ORM.
"""
from decimal import Decimal
from core.models import Tenant, User, UserRole
from sigip.models import (
    Pillar, Sector, Ministry, Financier, FinancierType,
    Project, ProjectStatus, WorkflowStatus, AnnualProgramming,
)


def make_tenant(name='DGP', is_dgp=True):
    return Tenant.objects.get_or_create(
        name=name,
        defaults={'short_name': name[:10], 'is_dgp': is_dgp}
    )[0]


def make_pillar(code='P1', label='Pilar 1', order=1):
    return Pillar.objects.get_or_create(
        code=code,
        defaults={'label': label, 'order': order}
    )[0]


def make_sector(code='11', label='Governação'):
    return Sector.objects.get_or_create(
        code=code,
        defaults={'label': label}
    )[0]


def make_financier(name='Estado', short_name='GOV', ftype=FinancierType.ESTADO):
    return Financier.objects.get_or_create(
        name=name,
        defaults={'short_name': short_name, 'type': ftype}
    )[0]


def make_ministry(name='MINFIN', short_name='MINFIN', pillar=None):
    pillar = pillar or make_pillar()
    return Ministry.objects.get_or_create(
        name=name,
        defaults={'short_name': short_name, 'pillar': pillar}
    )[0]


def make_user(username, role, ministry=None, tenant=None, password='test1234!'):
    user = User.objects.create_user(
        username=username,
        password=password,
        role=role,
        ministry=ministry,
        tenant=tenant,
    )
    return user


def make_project(code, title, ministry, financier=None, workflow=WorkflowStatus.RASCUNHO,
                 sector=None, pillar=None):
    financier = financier or make_financier()
    pillar = pillar or make_pillar()
    sector = sector or make_sector()
    return Project.objects.create(
        code=code,
        title=title,
        ministry=ministry,
        sector=sector,
        pillar=pillar,
        principal_financier=financier,
        status=ProjectStatus.IDENTIFIED,
        workflow_status=workflow,
        total_cost=Decimal('0'),
    )


def make_programming(project, fiscal_year=2026, donations=0, loans=0, state=0):
    return AnnualProgramming.objects.create(
        project=project,
        fiscal_year=fiscal_year,
        donations=Decimal(str(donations)),
        loans=Decimal(str(loans)),
        state_contribution=Decimal(str(state)),
        version=1,
    )
