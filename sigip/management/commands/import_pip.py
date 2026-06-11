"""
Management command: import_pip
Importa os dados reais do PIP 2026-2030 para a base de dados SIGIP-GB.

Fontes:
  - scripts/pip_data.json  (extraído do protótipo HTML)

Uso:
  python manage.py import_pip
  python manage.py import_pip --clear     # apaga dados existentes antes de importar
  python manage.py import_pip --file /caminho/para/dados.json
"""

import json
import os
import re
from pathlib import Path
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from sigip.models import (
    Pillar, Sector, GovPriority, Ministry, Financier, FinancierType,
    Project, ProjectStatus, AnnualProgramming, ProjectFinancier, FinancierRole,
    PIPVersion, PIPVersionStatus,
)
from core.models import Tenant, Region, FiscalYear, Currency


# ---------------------------------------------------------------------------
# Normalisation maps
# ---------------------------------------------------------------------------

MINISTRY_NORMALISATION = {
    # Typos / variantes → nom canonique
    'ASSENBLEIA NACIONALPPUILAR':               'ASSEMBLEIA NACIONAL POPULAR',
    'ASSEMBLEIA NACIONAL POPULAR':              'ASSEMBLEIA NACIONAL POPULAR',
    'MINISTERIO DA  COMUNICAÇÃO SOCIAL':        'MINISTÉRIO DA COMUNICAÇÃO SOCIAL',
    'MINISTERIO DA ECONOMIA, PLANO E INTEGRAÇÃO REGIONAL REGIONAL':
        'MINISTÉRIO DA ECONOMIA, PLANO E INTEGRAÇÃO REGIONAL',
    'MINISTERIO DO  AMBIENTE, BIODIVERSIDADE E AÇÃO CLIMATICA':
        'MINISTÉRIO DO AMBIENTE, BIODIVERSIDADE E ACÇÃO CLIMÁTICA',
    'MINISTERIO DO TURISMO E ARTESANATO':       'MINISTÉRIO DO TURISMO E ARTESANATO',
    'MINISTERIO DOS  COMBATENTES DA LIBERDADE DA PATRIA':
        'MINISTÉRIO DOS COMBATENTES DA LIBERDADE DA PÁTRIA',
    'MINISTÉRIO  DA CULTURA , JUVENTUDE   E DESPORTOS':
        'MINISTÉRIO DA CULTURA, JUVENTUDE E DESPORTOS',
    'MINISTÉRIO DA  MULHER, FAMILIA E SOLIDARIEDADE SOCIAL':
        'MINISTÉRIO DA MULHER, FAMÍLIA E SOLIDARIEDADE SOCIAL',
    'COMÉRCIO':  'MINISTÉRIO DO COMÉRCIO E INDÚSTRIA',
    'INDÚSTRIA':  'MINISTÉRIO DO COMÉRCIO E INDÚSTRIA',
    'MINISTÉRIO DAS ÁGUAS E SANEAMENTO':        'MINISTÉRIO DAS ÁGUAS E SANEAMENTO',
}

MINISTRY_SHORT_NAMES = {
    'ASSEMBLEIA NACIONAL POPULAR':                                'ANP',
    'MINISTÉRIO DA PRESIDENCIA DO CONSELHO DE MINISTROS':         'Presidência CM',
    'MINISTÉRIO DA COMUNICAÇÃO SOCIAL':                           'Comunicação',
    'MINISTÉRIO DA ECONOMIA, PLANO E INTEGRAÇÃO REGIONAL':        'Economia/Plano',
    'MINISTÉRIO DO AMBIENTE, BIODIVERSIDADE E ACÇÃO CLIMÁTICA':   'Ambiente',
    'MINISTÉRIO DO TURISMO E ARTESANATO':                         'Turismo',
    'MINISTÉRIO DOS COMBATENTES DA LIBERDADE DA PÁTRIA':          'Combatentes',
    'MINISTÉRIO DA CULTURA, JUVENTUDE E DESPORTOS':               'Cultura/Juventude',
    'MINISTÉRIO DA MULHER, FAMÍLIA E SOLIDARIEDADE SOCIAL':       'Solidariedade',
    'MINISTÉRIO DA ADMINISTRAÇÃO PÚBLICA, TRABALHO, EMPREGO, FORMAÇÃO PROFISSIONAL E SEGURANÇA SOCIAL': 'Adm. Pública',
    'MINISTÉRIO DA ADMINISTRAÇÃO TERRITORIAL E DO PODER LOCAL':   'Adm. Territorial',
    'MINISTÉRIO DA AGRICULTURA, FLORESTA E DESENVOLVIMENTO RURAL':'Agricultura',
    'MINISTÉRIO DA DEFESA NACIONAL':                              'Defesa',
    'MINISTÉRIO DA EDUCAÇÃO NACIONAL, ENSINO SUPERIOR E INVESTIGAÇÃO CIENTIFICA': 'Educação',
    'MINISTÉRIO DA ENERGIA':                                      'Energia',
    'MINISTÉRIO DA JUSTIÇA E DIREITOS HUMANOS':                   'Justiça',
    'MINISTÉRIO DA SAÚDE PUBLICA':                                'Saúde',
    'MINISTÉRIO DAS FINANÇAS':                                    'Finanças',
    'MINISTÉRIO DAS OBRAS PÚBLICAS, HABITAÇÃO E URBANISMO':       'Obras Públicas',
    'MINISTÉRIO DAS PESCAS E ECONOMIA MARITIMA':                  'Pescas',
    'MINISTÉRIO DO INTERIOR E DA ORDEM PUBLICA':                  'Interior',
    'MINISTÉRIO DOS TRANSPORTES  TELECOMUNICAÇÃO E ECONOMIA DIGITAL': 'Transportes',
    'MINISTÉRIO DAS ÁGUAS E SANEAMENTO':                          'Águas/Saneamento',
    'MINISTÉRIO DO COMÉRCIO E INDÚSTRIA':                         'Comércio/Indústria',
}

FINANCIER_TYPE_MAP = {
    # fin_norm → (type, country)
    'Estado':          (FinancierType.ESTADO,       'Guiné-Bissau'),
    'BAD':             (FinancierType.MULTILATERAL,  'Côte d\'Ivoire'),
    'BM':              (FinancierType.MULTILATERAL,  'États-Unis'),
    'BID':             (FinancierType.MULTILATERAL,  'États-Unis'),
    'BOAD':            (FinancierType.MULTILATERAL,  'Togo'),
    'BADEA':           (FinancierType.MULTILATERAL,  'Arabie Saoudite'),
    'UEMOA':           (FinancierType.MULTILATERAL,  'Sénégal'),
    'CEDEAO':          (FinancierType.MULTILATERAL,  'Nigeria'),
    'FIDA':            (FinancierType.UN_AGENCY,     'Italie'),
    'FAO':             (FinancierType.UN_AGENCY,     'Italie'),
    'PNUD':            (FinancierType.UN_AGENCY,     'États-Unis'),
    'UNICEF':          (FinancierType.UN_AGENCY,     'États-Unis'),
    'PAM':             (FinancierType.UN_AGENCY,     'Italie'),
    'OMS':             (FinancierType.UN_AGENCY,     'Suisse'),
    'FNUAP':           (FinancierType.UN_AGENCY,     'États-Unis'),
    'UNFPA':           (FinancierType.UN_AGENCY,     'États-Unis'),
    'GEF':             (FinancierType.MULTILATERAL,  'États-Unis'),
    'GAVI':            (FinancierType.MULTILATERAL,  'Suisse'),
    'EU':              (FinancierType.MULTILATERAL,  'Belgique'),
    'U.E':             (FinancierType.MULTILATERAL,  'Belgique'),
    'CHINA':           (FinancierType.BILATERAL,     'Chine'),
    'BRASIL':          (FinancierType.BILATERAL,     'Brésil'),
    'JAPAO':           (FinancierType.BILATERAL,     'Japon'),
    'JAPÃO':           (FinancierType.BILATERAL,     'Japon'),
    'PORTUGAL':        (FinancierType.BILATERAL,     'Portugal'),
    'ESPANHA':         (FinancierType.BILATERAL,     'Espagne'),
    'FM':              (FinancierType.MULTILATERAL,  'États-Unis'),
}


# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

PILLARS = [
    ('P1', 'Boa Governação, Paz e Segurança', 1),
    ('P2', 'Desenvolvimento do Capital Humano', 2),
    ('P3', 'Desenvolvimento Económico Sustentável', 3),
    ('P4', 'Infraestruturas e Ordenamento do Território', 4),
    ('P5', 'Gestão Sustentável dos Recursos Naturais', 5),
    ('P6', 'Integração Regional e Cooperação Internacional', 6),
]

# Sector codes derived from first 2 digits of project code
SECTOR_MAP = {
    '11': 'Governação e Administração Pública',
    '12': 'Defesa e Segurança',
    '13': 'Justiça e Direitos Humanos',
    '21': 'Educação',
    '22': 'Saúde',
    '23': 'Água e Saneamento',
    '24': 'Habitação e Desenvolvimento Urbano',
    '25': 'Protecção Social e Género',
    '26': 'Cultura, Juventude e Desportos',
    '31': 'Agricultura e Desenvolvimento Rural',
    '32': 'Pecuária e Recursos Animais',
    '33': 'Pescas e Economia Marítima',
    '34': 'Comércio e Indústria',
    '35': 'Turismo e Artesanato',
    '36': 'Finanças e Economia',
    '41': 'Transportes e Comunicações',
    '42': 'Energia',
    '43': 'Telecomunicações e TIC',
    '44': 'Obras Públicas e Urbanismo',
    '51': 'Ambiente e Biodiversidade',
    '52': 'Florestas e Recursos Naturais',
    '53': 'Recursos Hídricos',
    '61': 'Saúde Pública (Internacional)',
    '62': 'Cooperação Internacional',
    '71': 'Investigação e Inovação',
    '81': 'Administração Financeira',
    '82': 'Segurança e Ordem Pública',
    '28': 'Segurança e Desmobilização',
    '99': 'Outros / Multisetorial',
}

REGIONS = [
    ('BF', 'Bafatá'),
    ('BB', 'Biombo'),
    ('BL', 'Bolama/Bijagós'),
    ('CA', 'Cacheu'),
    ('GA', 'Gabú'),
    ('OI', 'Oio'),
    ('QU', 'Quinara'),
    ('TO', 'Tombali'),
    ('BS', 'Bissau (SAB)'),
]


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = (
        'Importa os dados do PIP 2026-2030 para a base de dados SIGIP-GB. '
        'Idempotente: pode ser executado várias vezes sem criar duplicados.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Apaga todos os dados existentes antes de importar (CUIDADO!).',
        )
        parser.add_argument(
            '--file',
            type=str,
            default=None,
            help='Caminho para o ficheiro JSON de dados PIP (por defeito: scripts/pip_data.json).',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Analisa os dados mas não os guarda na base de dados.',
        )

    def handle(self, *args, **options):
        self.dry_run = options['dry_run']
        self.anomalies = []
        self.stats = {
            'pillars': 0, 'sectors': 0, 'ministries': 0, 'financiers': 0,
            'projects_created': 0, 'projects_updated': 0,
            'programming_created': 0, 'anomalies': 0,
        }

        if self.dry_run:
            self.stdout.write(self.style.WARNING('[DRY-RUN] Nada sera guardado.'))

        # Locate data file
        data_file = options['file']
        if not data_file:
            data_file = Path(__file__).resolve().parent.parent.parent.parent / 'scripts' / 'pip_data.json'
        data_file = Path(data_file)
        if not data_file.exists():
            raise CommandError(f'Ficheiro não encontrado: {data_file}')

        self.stdout.write(f'Lendo dados de: {data_file}')
        with open(data_file, encoding='utf-8') as f:
            pip_data = json.load(f)
        self.stdout.write(f'  -> {len(pip_data)} projectos lidos.')

        if options['clear'] and not self.dry_run:
            self._clear_data()

        with transaction.atomic():
            if self.dry_run:
                # We need a savepoint to rollback at the end
                from django.db import connection
                sid = connection.savepoint()

            self._create_regions()
            self._create_fiscal_years()
            self._create_currency()
            self._create_pillars()
            self._create_sectors(pip_data)
            ministries = self._create_ministries(pip_data)
            financiers = self._create_financiers(pip_data)
            self._create_dgp_tenant()
            self._import_projects(pip_data, ministries, financiers)
            self._create_pip_version()

            if self.dry_run:
                connection.savepoint_rollback(sid)

        self._print_report()

    # -----------------------------------------------------------------------
    # Clear
    # -----------------------------------------------------------------------

    def _clear_data(self):
        self.stdout.write(self.style.WARNING('Apagando dados existentes...'))
        AnnualProgramming.objects.all().delete()
        ProjectFinancier.objects.all().delete()
        Project.objects.all().delete()
        Ministry.objects.all().delete()
        Financier.objects.all().delete()
        Pillar.objects.all().delete()
        Sector.objects.all().delete()
        self.stdout.write('  -> Dados apagados.')

    # -----------------------------------------------------------------------
    # Regions, FiscalYears, Currency
    # -----------------------------------------------------------------------

    def _create_regions(self):
        for code, name in REGIONS:
            Region.objects.get_or_create(code=code, defaults={'name': name})

    def _create_fiscal_years(self):
        for year in range(2026, 2031):
            FiscalYear.objects.get_or_create(year=year, defaults={'is_active': year == 2026})

    def _create_currency(self):
        Currency.objects.get_or_create(
            code='XOF',
            defaults={'name': 'Franc CFA UEMOA', 'symbol': 'FCFA'}
        )

    # -----------------------------------------------------------------------
    # Pillars
    # -----------------------------------------------------------------------

    def _create_pillars(self):
        self.stdout.write('Criando pilares PND...')
        for code, label, order in PILLARS:
            _, created = Pillar.objects.get_or_create(
                code=code,
                defaults={'label': label, 'order': order}
            )
            if created:
                self.stats['pillars'] += 1
        self.stdout.write(f'  -> {self.stats["pillars"]} pilares criados.')

    # -----------------------------------------------------------------------
    # Sectors (inferred from project codes)
    # -----------------------------------------------------------------------

    def _create_sectors(self, pip_data):
        self.stdout.write('Criando sectores...')
        codes_seen = set()
        for project in pip_data:
            code = str(project.get('code', ''))
            if len(code) >= 2:
                sector_code = code[:2]
                codes_seen.add(sector_code)

        for sector_code in sorted(codes_seen):
            label = SECTOR_MAP.get(sector_code, f'Sector {sector_code}')
            _, created = Sector.objects.get_or_create(
                code=sector_code,
                defaults={'label': label}
            )
            if created:
                self.stats['sectors'] += 1

        self.stdout.write(f'  -> {self.stats["sectors"]} sectores criados.')

    # -----------------------------------------------------------------------
    # Ministries
    # -----------------------------------------------------------------------

    def _create_ministries(self, pip_data):
        self.stdout.write('Criando ministérios...')
        ministry_data = {}  # canonical_name → short_name

        for project in pip_data:
            raw_name = project.get('ministerio', '').strip()
            raw_abbr = project.get('min_abbr', '').strip()

            canonical = MINISTRY_NORMALISATION.get(raw_name, raw_name)
            if not canonical:
                continue

            # Clean up whitespace
            canonical = re.sub(r'\s+', ' ', canonical).strip()

            if canonical not in ministry_data:
                short = MINISTRY_SHORT_NAMES.get(canonical, raw_abbr or '')
                ministry_data[canonical] = short

        ministry_objects = {}
        for name, short in ministry_data.items():
            obj, created = Ministry.objects.get_or_create(
                name=name,
                defaults={'short_name': short}
            )
            ministry_objects[name] = obj
            if created:
                self.stats['ministries'] += 1

        self.stdout.write(f'  -> {self.stats["ministries"]} ministérios criados.')
        return ministry_objects

    # -----------------------------------------------------------------------
    # Financiers
    # -----------------------------------------------------------------------

    def _create_financiers(self, pip_data):
        self.stdout.write('Criando financiadores...')
        fin_data = {}  # fin_norm → original_name

        for project in pip_data:
            fin_norm = project.get('fin_norm', '').strip()
            fin_original = project.get('financiador', '').strip()
            if fin_norm and fin_norm not in fin_data:
                fin_data[fin_norm] = fin_original

        fin_objects = {}
        for fin_norm, fin_original in fin_data.items():
            ftype, country = FINANCIER_TYPE_MAP.get(fin_norm, (FinancierType.OTHER, ''))
            # Use fin_norm as the canonical name
            obj, created = Financier.objects.get_or_create(
                name=fin_norm,
                defaults={
                    'short_name': fin_norm[:50],
                    'type': ftype,
                    'country': country,
                }
            )
            fin_objects[fin_norm] = obj
            if created:
                self.stats['financiers'] += 1

        self.stdout.write(f'  -> {self.stats["financiers"]} financiadores criados.')
        return fin_objects

    # -----------------------------------------------------------------------
    # DGP Tenant
    # -----------------------------------------------------------------------

    def _create_dgp_tenant(self):
        Tenant.objects.get_or_create(
            short_name='DGP',
            defaults={
                'name': 'Direcção-Geral do Plano',
                'is_dgp': True,
            }
        )

    # -----------------------------------------------------------------------
    # Projects + AnnualProgramming
    # -----------------------------------------------------------------------

    def _import_projects(self, pip_data, ministries, financiers):
        self.stdout.write(f'Importando {len(pip_data)} projectos...')

        dgp_tenant = Tenant.objects.filter(is_dgp=True).first()

        for i, project in enumerate(pip_data, 1):
            code = str(project.get('code', '')).strip()
            if not code:
                self._add_anomaly(i, code, 'Código vazio - projecto ignorado')
                continue

            title = project.get('nome', '').strip()
            if not title:
                self._add_anomaly(i, code, 'Título vazio')

            # Resolve ministry
            raw_ministry = project.get('ministerio', '').strip()
            canonical_ministry = MINISTRY_NORMALISATION.get(raw_ministry, raw_ministry)
            canonical_ministry = re.sub(r'\s+', ' ', canonical_ministry).strip()
            ministry_obj = ministries.get(canonical_ministry)
            if not ministry_obj:
                # Fallback: try to find by partial match
                try:
                    ministry_obj = Ministry.objects.get(name=canonical_ministry)
                except Ministry.DoesNotExist:
                    self._add_anomaly(i, code, f'Ministério não encontrado: {repr(raw_ministry)}')
                    ministry_obj = Ministry.objects.first()

            # Resolve financier
            fin_norm = project.get('fin_norm', '').strip()
            financier_obj = financiers.get(fin_norm)
            if not financier_obj:
                self._add_anomaly(i, code, f'Financiador não encontrado: {repr(fin_norm)}')
                financier_obj = financiers.get('Estado') or Financier.objects.first()

            # Resolve sector
            sector_code = code[:2] if len(code) >= 2 else None
            sector_obj = Sector.objects.filter(code=sector_code).first() if sector_code else None

            total = Decimal(str(project.get('total', 0)))

            # Determine financing flags
            don_flag = project.get('don', 0)
            empr_flag = project.get('empr', 0)
            interno_flag = project.get('interno', 0)

            project_obj, created = Project.objects.get_or_create(
                code=code,
                defaults={
                    'title': title,
                    'ministry': ministry_obj,
                    'sector': sector_obj,
                    'principal_financier': financier_obj,
                    'total_cost': total,
                    'status': ProjectStatus.IDENTIFIED,
                    'is_national': True,
                    'tenant': dgp_tenant,
                }
            )

            if created:
                self.stats['projects_created'] += 1
            else:
                # Update if needed
                updated = False
                if project_obj.title != title:
                    project_obj.title = title
                    updated = True
                if project_obj.total_cost != total:
                    project_obj.total_cost = total
                    updated = True
                if updated:
                    project_obj.save()
                    self.stats['projects_updated'] += 1

            # Create/update AnnualProgramming (version 1)
            anos = project.get('anos', {})
            for year_str, year_total in anos.items():
                year = int(year_str)
                year_total_dec = Decimal(str(year_total))

                # Distribute total by funding type:
                # If we have total > 0, distribute proportionally to the flags
                # The flags don/empr/interno are 0 or 1 in source,
                # but total is the actual amount.
                # We use fin_norm to determine the funding type.
                if fin_norm == 'Estado':
                    donations = Decimal('0')
                    loans = Decimal('0')
                    state_contrib = year_total_dec
                elif don_flag and not empr_flag:
                    donations = year_total_dec
                    loans = Decimal('0')
                    state_contrib = Decimal('0')
                elif empr_flag and not don_flag:
                    donations = Decimal('0')
                    loans = year_total_dec
                    state_contrib = Decimal('0')
                elif don_flag and empr_flag:
                    # Split equally as we don't have per-year breakdown
                    donations = year_total_dec / 2
                    loans = year_total_dec - donations
                    state_contrib = Decimal('0')
                else:
                    # Default: treat as state if fin_norm == Estado, else donations
                    donations = year_total_dec
                    loans = Decimal('0')
                    state_contrib = Decimal('0')

                _, prog_created = AnnualProgramming.objects.get_or_create(
                    project=project_obj,
                    fiscal_year=year,
                    version=1,
                    defaults={
                        'donations': donations,
                        'loans': loans,
                        'state_contribution': state_contrib,
                    }
                )
                if prog_created:
                    self.stats['programming_created'] += 1

        self.stdout.write(
            f'  -> {self.stats["projects_created"]} projectos criados, '
            f'{self.stats["projects_updated"]} actualizados.'
        )
        self.stdout.write(
            f'  -> {self.stats["programming_created"]} linhas de programação criadas.'
        )

    # -----------------------------------------------------------------------
    # PIPVersion
    # -----------------------------------------------------------------------

    def _create_pip_version(self):
        from datetime import date
        PIPVersion.objects.get_or_create(
            revision_year=2026,
            defaults={
                'status': PIPVersionStatus.ADOPTED,
                'adoption_date': date(2026, 6, 5),
                'notes': 'Versão inicial PIP 2026-2030 - DGP/5 de junho de 2026',
            }
        )

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _add_anomaly(self, row, code, message):
        self.anomalies.append({'row': row, 'code': code, 'message': message})
        self.stats['anomalies'] += 1

    def _print_report(self):
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS('RELATÓRIO DE IMPORTAÇÃO - SIGIP-GB PIP 2026-2030'))
        self.stdout.write('=' * 60)
        self.stdout.write(f"  Pilares criados      : {self.stats['pillars']}")
        self.stdout.write(f"  Sectores criados     : {self.stats['sectors']}")
        self.stdout.write(f"  Ministérios criados  : {self.stats['ministries']}")
        self.stdout.write(f"  Financiadores criados: {self.stats['financiers']}")
        self.stdout.write(f"  Projectos criados    : {self.stats['projects_created']}")
        self.stdout.write(f"  Projectos actualizados: {self.stats['projects_updated']}")
        self.stdout.write(f"  Programações criadas : {self.stats['programming_created']}")
        self.stdout.write(f"  Anomalias detectadas : {self.stats['anomalies']}")

        if self.anomalies:
            self.stdout.write('\n' + self.style.WARNING('ANOMALIAS:'))
            for a in self.anomalies:
                self.stdout.write(
                    f"  Linha {a['row']:3d} | Código {a['code']!r:15s} | {a['message']}"
                )

        self.stdout.write('\n' + ('=' * 60))
        if self.dry_run:
            self.stdout.write(self.style.WARNING('DRY-RUN: nenhum dado foi guardado.'))
        else:
            self.stdout.write(self.style.SUCCESS('Importacao concluida com sucesso!'))
        self.stdout.write('=' * 60 + '\n')
