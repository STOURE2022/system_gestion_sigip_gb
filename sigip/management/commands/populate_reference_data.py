"""
Management command to populate reference data (Pillars, Sectors, GovPriorities,
ExpenseNatures) from the PND 2026-2030 Excel reference files.

Usage:
    python manage.py populate_reference_data --settings=config.settings.development
"""
from django.core.management.base import BaseCommand
from sigip.models import Pillar, Sector, GovPriority, ExpenseNature


# ---------------------------------------------------------------------------
# Actual data extracted from RESUMO PND 2026_2030_04_JUNHO.xlsx
# ---------------------------------------------------------------------------

PILLARS = [
    {'code': 'P1', 'label': 'Consolidação da Paz, Governação e Construção do Estado de Direito Democrático', 'order': 1},
    {'code': 'P2', 'label': 'Diversificação e Transformação Estrutural da Economia', 'order': 2},
    {'code': 'P3', 'label': 'Desenvolvimento do Capital Humano e Melhoria de Condições de Vida', 'order': 3},
    {'code': 'P4', 'label': 'Preservação e Conservação da Biodiversidade, Combate às Alterações Climáticas e Valorização do Capital Natural', 'order': 4},
    {'code': 'P5', 'label': 'Redinamização da Política Externa, Reforço da Integração Regional e Valorização da Diáspora Guineense', 'order': 5},
    {'code': 'P6', 'label': 'Ordenamento do Território e Desenvolvimento Local', 'order': 6},
]

# Sectors from RESUMO_SECTOR_2026_2030 in PND_SECTOR file
# Parent sectors (4 main)
SECTORS_PARENT = [
    {'code': 'PROD', 'label': 'PRODUTIVO', 'parent_code': None},
    {'code': 'INFRA', 'label': 'INFRA/INFRAESTRUTURAS', 'parent_code': None},
    {'code': 'SOC', 'label': 'SOCIAIS', 'parent_code': None},
    {'code': 'GEST', 'label': 'GESTÃO ECONÓMICA', 'parent_code': None},
]

# Sub-sectors from RESUMO SECTOR_2026 sheet
SECTORS_SUB = [
    # PRODUTIVO sub-sectors
    {'code': 'PROD-AGR', 'label': 'Agricultura e Desenvolvimento Rural', 'parent_code': 'PROD'},
    {'code': 'PROD-PES', 'label': 'Pescas e Economia Marítima', 'parent_code': 'PROD'},
    {'code': 'PROD-TUR', 'label': 'Turismo e Artesanato', 'parent_code': 'PROD'},
    {'code': 'PROD-IND', 'label': 'Indústria', 'parent_code': 'PROD'},
    {'code': 'PROD-COM', 'label': 'Comércio', 'parent_code': 'PROD'},
    {'code': 'PROD-RN', 'label': 'Recursos Naturais', 'parent_code': 'PROD'},
    {'code': 'PROD-EMP', 'label': 'Promoção do Empreendorismo, Inovação e Desenvolvimento', 'parent_code': 'PROD'},
    # INFRA sub-sectors
    {'code': 'INFRA-OP', 'label': 'Obras Públicas, Habitação e Urbanismo', 'parent_code': 'INFRA'},
    {'code': 'INFRA-EN', 'label': 'Energia', 'parent_code': 'INFRA'},
    {'code': 'INFRA-TR', 'label': 'Transportes, Telecomunicações e Economia Digital', 'parent_code': 'INFRA'},
    # SOCIAIS sub-sectors
    {'code': 'SOC-EDU', 'label': 'Educação', 'parent_code': 'SOC'},
    {'code': 'SOC-SAU', 'label': 'Saúde', 'parent_code': 'SOC'},
    {'code': 'SOC-SOL', 'label': 'Solidariedade Social', 'parent_code': 'SOC'},
    {'code': 'SOC-CUL', 'label': 'Cultura', 'parent_code': 'SOC'},
    {'code': 'SOC-JUV', 'label': 'Juventude e Desportos', 'parent_code': 'SOC'},
    # GESTÃO ECONÓMICA sub-sectors
    {'code': 'GEST-ADM', 'label': 'Administração Pública', 'parent_code': 'GEST'},
    {'code': 'GEST-JUS', 'label': 'Justiça e Direitos Humanos', 'parent_code': 'GEST'},
    {'code': 'GEST-DEF', 'label': 'Defesa Nacional', 'parent_code': 'GEST'},
    {'code': 'GEST-SEG', 'label': 'Segurança e Ordem Pública', 'parent_code': 'GEST'},
    {'code': 'GEST-FIN', 'label': 'Finanças e Gestão Macroeconómica', 'parent_code': 'GEST'},
    {'code': 'GEST-AT', 'label': 'Administração Territorial e Poder Local', 'parent_code': 'GEST'},
    {'code': 'GEST-AMB', 'label': 'Protecção do Ambiente e Biodiversidade', 'parent_code': 'GEST'},
    {'code': 'GEST-EXT', 'label': 'Política Externa e Integração Regional', 'parent_code': 'GEST'},
    {'code': 'GEST-CS', 'label': 'Comunicação Social', 'parent_code': 'GEST'},
]

# GovPriorities from PRIORIDADE GOVERNO sheets (ministries/sectors)
GOV_PRIORITIES = [
    {'label': 'Serviços Públicos em Geral', 'order': 1},
    {'label': 'Defesa e Segurança', 'order': 2},
    {'label': 'Ordem Pública e Segurança', 'order': 3},
    {'label': 'Assuntos Económicos', 'order': 4},
    {'label': 'Protecção do Ambiente', 'order': 5},
    {'label': 'Capital Humano e Social', 'order': 6},
    {'label': 'Saúde', 'order': 7},
    {'label': 'Educação', 'order': 8},
    {'label': 'Infraestruturas Económicas', 'order': 9},
    {'label': 'Governação e Estado de Direito', 'order': 10},
]

# ExpenseNatures from Natureza_Despesa sheets
# 2 main categories with sub-items:
# FUNCIONAMENTO: Bens e Serviços, Combustível, Subsídio de Tecnicidade,
#                Assistência Técnica Estrangeira, Assistência Técnica Nacional
# INVESTIMENTO: Material de Transportes, Máquinas e Equipamentos,
#               Construção Civil, Formação (capital humano)
EXPENSE_NATURES = [
    {'code': 'FUNC', 'label': 'Despesas de Funcionamento'},
    {'code': 'FUNC-BS', 'label': 'Bens e Serviços'},
    {'code': 'FUNC-COMB', 'label': 'Combustível'},
    {'code': 'FUNC-SUB', 'label': 'Subsídio de Tecnicidade'},
    {'code': 'FUNC-ATE', 'label': 'Assistência Técnica Estrangeira'},
    {'code': 'FUNC-ATN', 'label': 'Assistência Técnica Nacional'},
    {'code': 'INV', 'label': 'Despesas de Investimento'},
    {'code': 'INV-MT', 'label': 'Material de Transportes'},
    {'code': 'INV-ME', 'label': 'Máquinas e Equipamentos'},
    {'code': 'INV-CC', 'label': 'Construção Civil'},
    {'code': 'INV-FOR', 'label': 'Formação (Capital Humano)'},
]


class Command(BaseCommand):
    help = 'Populate reference data (Pillars, Sectors, GovPriorities, ExpenseNatures) from PND 2026-2030'

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING('=== Populate Reference Data ==='))

        # ---- Pillars ----
        self.stdout.write('\n--- Pillars ---')
        for p in PILLARS:
            obj, created = Pillar.objects.get_or_create(
                code=p['code'],
                defaults={'label': p['label'], 'order': p['order']}
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'  CREATED  {obj.code}: {obj.label}'))
            else:
                self.stdout.write(f'  existed  {obj.code}: {obj.label}')
        self.stdout.write(f'  Total pillars: {Pillar.objects.count()}')

        # ---- Sectors (parents first) ----
        self.stdout.write('\n--- Sectors (parent) ---')
        parent_map = {}
        for s in SECTORS_PARENT:
            obj, created = Sector.objects.get_or_create(
                code=s['code'],
                defaults={'label': s['label'], 'parent': None}
            )
            parent_map[s['code']] = obj
            if created:
                self.stdout.write(self.style.SUCCESS(f'  CREATED  {obj.code}: {obj.label}'))
            else:
                self.stdout.write(f'  existed  {obj.code}: {obj.label}')

        self.stdout.write('\n--- Sectors (sub) ---')
        for s in SECTORS_SUB:
            parent = parent_map.get(s['parent_code'])
            obj, created = Sector.objects.get_or_create(
                code=s['code'],
                defaults={'label': s['label'], 'parent': parent}
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'  CREATED  {obj.code}: {obj.label} (parent={s["parent_code"]})'))
            else:
                self.stdout.write(f'  existed  {obj.code}: {obj.label}')
        self.stdout.write(f'  Total sectors: {Sector.objects.count()}')

        # ---- GovPriorities ----
        self.stdout.write('\n--- GovPriorities ---')
        for g in GOV_PRIORITIES:
            obj, created = GovPriority.objects.get_or_create(
                label=g['label'],
                defaults={'order': g['order']}
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'  CREATED  {obj.label}'))
            else:
                self.stdout.write(f'  existed  {obj.label}')
        self.stdout.write(f'  Total gov priorities: {GovPriority.objects.count()}')

        # ---- ExpenseNatures ----
        self.stdout.write('\n--- ExpenseNatures ---')
        for e in EXPENSE_NATURES:
            obj, created = ExpenseNature.objects.get_or_create(
                code=e['code'],
                defaults={'label': e['label']}
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'  CREATED  {obj.code}: {obj.label}'))
            else:
                self.stdout.write(f'  existed  {obj.code}: {obj.label}')
        self.stdout.write(f'  Total expense natures: {ExpenseNature.objects.count()}')

        self.stdout.write(self.style.SUCCESS('\n=== Done! ==='))
