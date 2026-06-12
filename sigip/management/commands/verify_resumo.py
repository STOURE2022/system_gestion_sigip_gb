"""
Management command: verify_resumo
Verifica os totais agregados da base de dados contra os valores de referência
do PIP 2026-2030 oficial.

Uso:
  python manage.py verify_resumo
  python manage.py verify_resumo --validated     # apenas projectos validados
  python manage.py verify_resumo --tolerance 5   # tolerância em milliers FCFA
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Sum, Value, DecimalField
from django.db.models.functions import Coalesce

from sigip.models import AnnualProgramming


# ---------------------------------------------------------------------------
# Reference values (milliers FCFA) from official Excel
# PIP_2026_2030_DPDEP_V2 DGP_5_JUNHO_2026 PIP FINAL.xlsx
# ---------------------------------------------------------------------------

REFERENCE = {
    2026: {
        'donations':          Decimal('45200000.00'),
        'loans':              Decimal('22000000.00'),
        'state_contribution': Decimal('16000000.00'),
        'total':              Decimal('83200000.00'),
    },
    2027: {
        'donations':          Decimal('46909152.48'),
        'loans':              Decimal('29152343.76'),
        'state_contribution': Decimal('25990000.00'),
        'total':              Decimal('102051496.24'),
    },
    2028: {
        'donations':          Decimal('49890441.40'),
        'loans':              Decimal('33992700.10'),
        'state_contribution': Decimal('31178900.00'),
        'total':              Decimal('115062041.50'),
    },
    2029: {
        'donations':          Decimal('60996441.40'),
        'loans':              Decimal('57106250.00'),
        'state_contribution': Decimal('38625000.00'),
        'total':              Decimal('156727691.40'),
    },
    2030: {
        'donations':          Decimal('62643391.40'),
        'loans':              Decimal('62164300.00'),
        'state_contribution': Decimal('49350000.00'),
        'total':              Decimal('174157691.40'),
    },
    'grand_total': Decimal('631198920.55'),
}

ZERO = Decimal('0')


class Command(BaseCommand):
    help = (
        'Verifica os totais da base de dados contra os valores de referência '
        'do PIP 2026-2030 oficial (631 Mds FCFA).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--validated', action='store_true',
            help='Verifica apenas projectos com workflow_status=VALIDADO.',
        )
        parser.add_argument(
            '--tolerance', type=float, default=1.0,
            help='Tolerância máxima em milliers FCFA (padrão: 1.0).',
        )

    def handle(self, *args, **options):
        validated_only = options['validated']
        tolerance = Decimal(str(options['tolerance']))

        self.stdout.write('\n' + '=' * 70)
        self.stdout.write(self.style.MIGRATE_HEADING(
            'VERIFY RESUMO – SIGIP-GB PIP 2026-2030'
        ))
        if validated_only:
            self.stdout.write('  Filtro: apenas projectos VALIDADOS')
        self.stdout.write(f'  Tolerância: +-{tolerance} milliers FCFA')
        self.stdout.write('=' * 70)

        qs = AnnualProgramming.objects.filter(
            project__is_deleted=False,
            version=1,
        )
        if validated_only:
            qs = qs.filter(project__workflow_status='VALIDADO')

        # Aggregate per year
        failures = []
        db_grand = ZERO

        for yr in range(2026, 2031):
            yr_qs = qs.filter(fiscal_year=yr)
            agg = yr_qs.aggregate(
                s_don=Coalesce(Sum('donations'),          Value(ZERO, output_field=DecimalField())),
                s_emp=Coalesce(Sum('loans'),              Value(ZERO, output_field=DecimalField())),
                s_state=Coalesce(Sum('state_contribution'), Value(ZERO, output_field=DecimalField())),
            )
            db_don   = agg['s_don']
            db_emp   = agg['s_emp']
            db_state = agg['s_state']
            db_total = db_don + db_emp + db_state
            db_grand += db_total

            ref = REFERENCE[yr]

            self.stdout.write(f'\n  -- {yr} --')
            for field, db_val, ref_val in [
                ('donativos',     db_don,   ref['donations']),
                ('empréstimos',   db_emp,   ref['loans']),
                ('estado',        db_state, ref['state_contribution']),
                ('TOTAL',         db_total, ref['total']),
            ]:
                diff = abs(db_val - ref_val)
                status = 'OK   ' if diff <= tolerance else 'FAIL '
                style = self.style.SUCCESS if diff <= tolerance else self.style.ERROR
                self.stdout.write(style(
                    f'    [{status}] {field:14s}: DB={db_val:>18.2f}  '
                    f'REF={ref_val:>18.2f}  diff={diff:.4f}'
                ))
                if diff > tolerance:
                    failures.append(f'{yr}/{field}: diff={diff:.4f}')

        # Grand total
        ref_grand = REFERENCE['grand_total']
        diff_grand = abs(db_grand - ref_grand)
        status = 'OK   ' if diff_grand <= tolerance else 'FAIL '
        style = self.style.SUCCESS if diff_grand <= tolerance else self.style.ERROR
        self.stdout.write(f'\n  -- TOTAL GERAL PND 2026-2030 --')
        self.stdout.write(style(
            f'    [{status}] TOTAL GERAL   : DB={db_grand:>18.2f}  '
            f'REF={ref_grand:>18.2f}  diff={diff_grand:.4f}'
        ))
        if diff_grand > tolerance:
            failures.append(f'TOTAL/geral: diff={diff_grand:.4f}')

        # Project count
        n_projects = (
            qs.values('project_id').distinct().count()
        )
        self.stdout.write(f'\n  Projectos com programação: {n_projects} (referência: 292)')

        # Summary
        self.stdout.write('\n' + '=' * 70)
        if failures:
            self.stdout.write(self.style.ERROR(
                f'  RESULTADO: FALHOU ({len(failures)} verificações falhadas)'
            ))
            for f in failures:
                self.stdout.write(self.style.ERROR(f'    • {f}'))
        else:
            self.stdout.write(self.style.SUCCESS(
                '  RESULTADO: PASSOU – todos os totais correspondem à referência.'
            ))
        self.stdout.write('=' * 70 + '\n')
