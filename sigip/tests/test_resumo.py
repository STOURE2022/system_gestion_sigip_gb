"""
Tests for the Resumo (Síntese) aggregation endpoints.

Endpoints tested:
  GET /api/v1/resumo/pnd/
  GET /api/v1/resumo/sector/
  GET /api/v1/resumo/natureza_despesa/
  GET /api/v1/resumo/prioridade_governo/
"""
from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import UserRole
from sigip.models import (
    Pillar, Sector, GovPriority, ExpenseNature,
    AnnualProgramming,
)
from .factories import (
    make_ministry, make_user, make_project, make_financier,
    make_pillar, make_sector, make_programming,
)


def auth_header(user):
    refresh = RefreshToken.for_user(user)
    return {'HTTP_AUTHORIZATION': f'Bearer {refresh.access_token}'}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_expense_nature(code='INV', label='Investimento'):
    obj, _ = ExpenseNature.objects.get_or_create(code=code, defaults={'label': label})
    return obj


def make_gov_priority(label='Prior. Test', order=1):
    obj, _ = GovPriority.objects.get_or_create(label=label, defaults={'order': order})
    return obj


# ---------------------------------------------------------------------------
# Resumo PND tests
# ---------------------------------------------------------------------------

class ResumoPNDTests(APITestCase):

    def setUp(self):
        self.pillar1 = make_pillar('TP1', 'Test Pilar 1', order=10)
        self.pillar2 = make_pillar('TP2', 'Test Pilar 2', order=11)
        self.sector = make_sector('T11', 'Test Sector')
        self.financier = make_financier('TestFinancier', 'TF')
        self.ministry = make_ministry('Test Ministry PND', 'TMPND', self.pillar1)
        self.user = make_user('test_pnd_user', UserRole.DGP_ANALYST)

        # Project in pillar1 with programming
        self.proj1 = make_project('TPND001', 'Proj PND 1', self.ministry, self.financier,
                                  pillar=self.pillar1)
        make_programming(self.proj1, fiscal_year=2026, donations=1_000_000, loans=500_000, state=200_000)
        make_programming(self.proj1, fiscal_year=2027, donations=2_000_000, loans=0, state=300_000)

        # Project in pillar2
        self.proj2 = make_project('TPND002', 'Proj PND 2', self.ministry, self.financier,
                                  pillar=self.pillar2)
        make_programming(self.proj2, fiscal_year=2026, donations=500_000, loans=0, state=100_000)

    def test_unauthenticated_returns_401(self):
        url = reverse('resumo-pnd')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_returns_200(self):
        url = reverse('resumo-pnd')
        resp = self.client.get(url, **auth_header(self.user))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_response_has_rows_and_grand_total(self):
        url = reverse('resumo-pnd')
        resp = self.client.get(url, **auth_header(self.user))
        self.assertIn('rows', resp.data)
        self.assertIn('grand_total', resp.data)

    def test_rows_have_years_key(self):
        url = reverse('resumo-pnd')
        resp = self.client.get(url, **auth_header(self.user))
        for row in resp.data['rows']:
            self.assertIn('years', row)
            self.assertIn('total', row['years'])  # 'total' key is the all-years total

    def test_grand_total_equals_sum_of_rows(self):
        url = reverse('resumo-pnd')
        resp = self.client.get(url, **auth_header(self.user))
        grand_overall = float(resp.data['grand_total']['years']['total']['total'])
        rows_total = sum(float(row['years']['total']['total']) for row in resp.data['rows'])
        self.assertAlmostEqual(grand_overall, rows_total, places=2)

    def test_pct_sums_to_100(self):
        url = reverse('resumo-pnd')
        resp = self.client.get(url, **auth_header(self.user))
        grand_overall = float(resp.data['grand_total']['years']['total']['total'])
        if grand_overall > 0:
            total_pct = sum(float(row['years']['total']['pct']) for row in resp.data['rows'])
            self.assertAlmostEqual(total_pct, 100.0, delta=0.1)

    def test_year_filter(self):
        url = reverse('resumo-pnd')
        resp = self.client.get(url + '?year=2026', **auth_header(self.user))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Should only have 2026 in row years (plus 'total')
        for row in resp.data['rows']:
            year_keys = [k for k in row['years'].keys() if k != 'total']
            self.assertEqual(year_keys, [2026])

    def test_empty_case_returns_zeros_not_errors(self):
        # Create a user but no data for pillar 99
        url = reverse('resumo-pnd')
        resp = self.client.get(url, **auth_header(self.user))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsInstance(resp.data['rows'], list)

    def test_grand_total_has_total_key(self):
        url = reverse('resumo-pnd')
        resp = self.client.get(url, **auth_header(self.user))
        self.assertIn('total', resp.data['grand_total']['years'])

    def test_validated_filter(self):
        url = reverse('resumo-pnd')
        resp_all = self.client.get(url, **auth_header(self.user))
        resp_val = self.client.get(url + '?validated=true', **auth_header(self.user))
        self.assertEqual(resp_val.status_code, status.HTTP_200_OK)
        # validated filter should return 0 rows (no validated projects in test data)
        grand_val = float(resp_val.data['grand_total']['years']['total']['total'])
        self.assertEqual(grand_val, 0.0)


# ---------------------------------------------------------------------------
# Resumo Sector tests
# ---------------------------------------------------------------------------

class ResumoSectorTests(APITestCase):

    def setUp(self):
        self.pillar = make_pillar('SP1', 'Sector Test Pilar', order=20)
        self.sector1 = make_sector('TS1', 'Test Sector Alpha')
        self.sector2 = make_sector('TS2', 'Test Sector Beta')
        self.financier = make_financier('SectorFin', 'SF')
        self.ministry = make_ministry('Test Ministry Sec', 'TMSEC', self.pillar)
        self.user = make_user('test_sec_user', UserRole.DGP_ANALYST)

        self.proj1 = make_project('TSEC001', 'Proj Sec 1', self.ministry, self.financier,
                                  sector=self.sector1, pillar=self.pillar)
        make_programming(self.proj1, fiscal_year=2026, donations=3_000_000, loans=0, state=1_000_000)

        self.proj2 = make_project('TSEC002', 'Proj Sec 2', self.ministry, self.financier,
                                  sector=self.sector2, pillar=self.pillar)
        make_programming(self.proj2, fiscal_year=2026, donations=0, loans=2_000_000, state=500_000)

    def test_unauthenticated_returns_401(self):
        url = reverse('resumo-sector')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_returns_200(self):
        url = reverse('resumo-sector')
        resp = self.client.get(url, **auth_header(self.user))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_response_structure(self):
        url = reverse('resumo-sector')
        resp = self.client.get(url, **auth_header(self.user))
        self.assertIn('rows', resp.data)
        self.assertIn('grand_total', resp.data)

    def test_grand_total_matches_rows(self):
        url = reverse('resumo-sector')
        resp = self.client.get(url, **auth_header(self.user))
        grand = float(resp.data['grand_total']['years']['total']['total'])
        rows_sum = sum(float(row['years']['total']['total']) for row in resp.data['rows'])
        self.assertAlmostEqual(grand, rows_sum, places=2)

    def test_pct_sums_to_100(self):
        url = reverse('resumo-sector')
        resp = self.client.get(url, **auth_header(self.user))
        grand = float(resp.data['grand_total']['years']['total']['total'])
        if grand > 0:
            total_pct = sum(float(row['years']['total']['pct']) for row in resp.data['rows'])
            self.assertAlmostEqual(total_pct, 100.0, delta=0.1)

    def test_year_filter(self):
        url = reverse('resumo-sector')
        resp = self.client.get(url + '?year=2026', **auth_header(self.user))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        for row in resp.data['rows']:
            year_keys = [k for k in row['years'].keys() if k != 'total']
            self.assertEqual(year_keys, [2026])

    def test_empty_case(self):
        url = reverse('resumo-sector')
        resp = self.client.get(url, **auth_header(self.user))
        self.assertIsInstance(resp.data['rows'], list)


# ---------------------------------------------------------------------------
# Resumo Natureza Despesa tests
# ---------------------------------------------------------------------------

class ResumoNaturezaDespesaTests(APITestCase):

    def setUp(self):
        self.pillar = make_pillar('NP1', 'Nat Test Pilar', order=30)
        self.sector = make_sector('TN1', 'Test Nat Sector')
        self.financier = make_financier('NatFin', 'NF')
        self.ministry = make_ministry('Test Ministry Nat', 'TMNAT', self.pillar)
        self.user = make_user('test_nat_user', UserRole.DGP_ANALYST)
        self.en1 = make_expense_nature('TEST-FUNC', 'Test Funcionamento')
        self.en2 = make_expense_nature('TEST-INV', 'Test Investimento')

        self.proj1 = make_project('TNAT001', 'Proj Nat 1', self.ministry, self.financier,
                                  sector=self.sector, pillar=self.pillar)
        self.proj1.expense_nature = self.en1
        self.proj1.save()
        make_programming(self.proj1, fiscal_year=2026, donations=1_500_000, loans=0, state=500_000)
        make_programming(self.proj1, fiscal_year=2028, donations=2_000_000, loans=0, state=1_000_000)

        self.proj2 = make_project('TNAT002', 'Proj Nat 2', self.ministry, self.financier,
                                  sector=self.sector, pillar=self.pillar)
        self.proj2.expense_nature = self.en2
        self.proj2.save()
        make_programming(self.proj2, fiscal_year=2027, donations=800_000, loans=200_000, state=300_000)

    def test_unauthenticated_returns_401(self):
        url = reverse('resumo-natureza-despesa')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_returns_200(self):
        url = reverse('resumo-natureza-despesa')
        resp = self.client.get(url, **auth_header(self.user))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_response_structure(self):
        url = reverse('resumo-natureza-despesa')
        resp = self.client.get(url, **auth_header(self.user))
        self.assertIn('rows', resp.data)
        self.assertIn('grand_total', resp.data)

    def test_grand_total_matches_rows(self):
        url = reverse('resumo-natureza-despesa')
        resp = self.client.get(url, **auth_header(self.user))
        grand = float(resp.data['grand_total']['years']['total']['total'])
        rows_sum = sum(float(row['years']['total']['total']) for row in resp.data['rows'])
        self.assertAlmostEqual(grand, rows_sum, places=2)

    def test_pct_sums_to_100(self):
        url = reverse('resumo-natureza-despesa')
        resp = self.client.get(url, **auth_header(self.user))
        grand = float(resp.data['grand_total']['years']['total']['total'])
        if grand > 0:
            total_pct = sum(float(row['years']['total']['pct']) for row in resp.data['rows'])
            self.assertAlmostEqual(total_pct, 100.0, delta=0.1)

    def test_year_filter_2026(self):
        url = reverse('resumo-natureza-despesa')
        resp = self.client.get(url + '?year=2026', **auth_header(self.user))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        for row in resp.data['rows']:
            year_keys = [k for k in row['years'].keys() if k != 'total']
            self.assertEqual(year_keys, [2026])

    def test_empty_case_no_errors(self):
        url = reverse('resumo-natureza-despesa')
        resp = self.client.get(url, **auth_header(self.user))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsInstance(resp.data['rows'], list)

    def test_external_equals_donations_plus_loans(self):
        url = reverse('resumo-natureza-despesa')
        resp = self.client.get(url + '?year=2026', **auth_header(self.user))
        for row in resp.data['rows']:
            yr_data = row['years'].get(2026, {})
            ext = float(yr_data.get('external', 0))
            don = float(yr_data.get('donations', 0))
            loan = float(yr_data.get('loans', 0))
            self.assertAlmostEqual(ext, don + loan, places=5)

    def test_internal_equals_state(self):
        url = reverse('resumo-natureza-despesa')
        resp = self.client.get(url + '?year=2026', **auth_header(self.user))
        for row in resp.data['rows']:
            yr_data = row['years'].get(2026, {})
            internal = float(yr_data.get('internal', 0))
            state = float(yr_data.get('state', 0))
            self.assertAlmostEqual(internal, state, places=5)


# ---------------------------------------------------------------------------
# Resumo Prioridade Governo tests
# ---------------------------------------------------------------------------

class ResumoPrioridadeGovernoTests(APITestCase):

    def setUp(self):
        self.pillar = make_pillar('GP1', 'Gov Prior Pilar', order=40)
        self.sector = make_sector('TG1', 'Test GP Sector')
        self.financier = make_financier('GovFin', 'GF')
        self.ministry = make_ministry('Test Ministry GP', 'TMGP', self.pillar)
        self.user = make_user('test_gp_user', UserRole.DGP_ANALYST)
        self.gp1 = make_gov_priority('Prioridade Alfa', order=1)
        self.gp2 = make_gov_priority('Prioridade Beta', order=2)

        self.proj1 = make_project('TGP001', 'Proj GP 1', self.ministry, self.financier,
                                  sector=self.sector, pillar=self.pillar)
        self.proj1.gov_priority = self.gp1
        self.proj1.save()
        make_programming(self.proj1, fiscal_year=2026, donations=4_000_000, loans=1_000_000, state=2_000_000)

        self.proj2 = make_project('TGP002', 'Proj GP 2', self.ministry, self.financier,
                                  sector=self.sector, pillar=self.pillar)
        self.proj2.gov_priority = self.gp2
        self.proj2.save()
        make_programming(self.proj2, fiscal_year=2026, donations=1_000_000, loans=0, state=500_000)
        make_programming(self.proj2, fiscal_year=2029, donations=3_000_000, loans=500_000, state=1_000_000)

    def test_unauthenticated_returns_401(self):
        url = reverse('resumo-prioridade-governo')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_returns_200(self):
        url = reverse('resumo-prioridade-governo')
        resp = self.client.get(url, **auth_header(self.user))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_response_structure(self):
        url = reverse('resumo-prioridade-governo')
        resp = self.client.get(url, **auth_header(self.user))
        self.assertIn('rows', resp.data)
        self.assertIn('grand_total', resp.data)

    def test_grand_total_matches_rows(self):
        url = reverse('resumo-prioridade-governo')
        resp = self.client.get(url, **auth_header(self.user))
        grand = float(resp.data['grand_total']['years']['total']['total'])
        rows_sum = sum(float(row['years']['total']['total']) for row in resp.data['rows'])
        self.assertAlmostEqual(grand, rows_sum, places=2)

    def test_pct_sums_to_100(self):
        url = reverse('resumo-prioridade-governo')
        resp = self.client.get(url, **auth_header(self.user))
        grand = float(resp.data['grand_total']['years']['total']['total'])
        if grand > 0:
            total_pct = sum(float(row['years']['total']['pct']) for row in resp.data['rows'])
            self.assertAlmostEqual(total_pct, 100.0, delta=0.1)

    def test_year_filter(self):
        url = reverse('resumo-prioridade-governo')
        resp = self.client.get(url + '?year=2026', **auth_header(self.user))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        for row in resp.data['rows']:
            year_keys = [k for k in row['years'].keys() if k != 'total']
            self.assertEqual(year_keys, [2026])

    def test_empty_case_no_errors(self):
        # Empty case: filter to year with no data
        url = reverse('resumo-prioridade-governo')
        resp = self.client.get(url + '?year=2028', **auth_header(self.user))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # grand total should be zero
        grand = float(resp.data['grand_total']['years'].get(2028, {}).get('total', 0))
        self.assertEqual(grand, 0.0)

    def test_validated_filter_returns_200(self):
        url = reverse('resumo-prioridade-governo')
        resp = self.client.get(url + '?validated=true', **auth_header(self.user))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_total_key_in_years(self):
        url = reverse('resumo-prioridade-governo')
        resp = self.client.get(url, **auth_header(self.user))
        for row in resp.data['rows']:
            self.assertIn('total', row['years'])
        self.assertIn('total', resp.data['grand_total']['years'])
