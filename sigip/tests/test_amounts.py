"""
Tests de cohérence des montants de programmation annuelle.

Vérifie :
1. Montants négatifs refusés (donations, loans, state_contribution).
2. Année hors plage 2026-2030 refusée.
3. Doublon d'année dans le bulk refusé.
4. Upsert bulk crée / met à jour les AnnualProgramming correctement.
5. total_cost du projet est recalculé après un bulk.
6. Agent ne peut pas modifier la programmation d'un projet SUBMETIDO.
"""
from decimal import Decimal
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import UserRole
from sigip.models import AnnualProgramming, WorkflowStatus
from .factories import (
    make_ministry, make_user, make_project, make_financier,
    make_pillar, make_sector, make_programming,
)


def auth_header(user):
    refresh = RefreshToken.for_user(user)
    return {'HTTP_AUTHORIZATION': f'Bearer {refresh.access_token}'}


ANOS_PIP = [2026, 2027, 2028, 2029, 2030]


def full_programming(donations=0, loans=0, state=0):
    """Retourne une liste de 5 années avec les mêmes montants."""
    return [
        {
            'fiscal_year': y,
            'donations': str(donations),
            'loans': str(loans),
            'state_contribution': str(state),
        }
        for y in ANOS_PIP
    ]


class ProgrammingAmountTests(APITestCase):

    def setUp(self):
        self.pillar = make_pillar('P3', 'Pilar 3', order=3)
        self.sector = make_sector('33', 'Saúde')
        self.financier = make_financier('BM', 'BM')

        self.ministry = make_ministry('MINSAUDE', 'MINSAUDE', self.pillar)
        self.agent = make_user('agent_saude', UserRole.MINISTRY_AGENT, ministry=self.ministry)
        self.dgp = make_user('dgp_saude', UserRole.DGP_ANALYST)
        self.admin = make_user('admin_saude', UserRole.ADMIN)

        self.project = make_project(
            '888888888', 'Projecto Saúde', self.ministry, self.financier,
        )

    def _bulk_url(self):
        return reverse('project-programming-bulk', args=[self.project.pk])

    # ------------------------------------------------------------------
    # 1. Montants négatifs
    # ------------------------------------------------------------------

    def test_negative_donations_rejected(self):
        payload = {'programmings': [
            {'fiscal_year': 2026, 'donations': '-1000', 'loans': '0', 'state_contribution': '0'}
        ]}
        resp = self.client.post(self._bulk_url(), payload, format='json', **auth_header(self.agent))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_negative_loans_rejected(self):
        payload = {'programmings': [
            {'fiscal_year': 2026, 'donations': '0', 'loans': '-500', 'state_contribution': '0'}
        ]}
        resp = self.client.post(self._bulk_url(), payload, format='json', **auth_header(self.agent))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_negative_state_contribution_rejected(self):
        payload = {'programmings': [
            {'fiscal_year': 2026, 'donations': '0', 'loans': '0', 'state_contribution': '-100'}
        ]}
        resp = self.client.post(self._bulk_url(), payload, format='json', **auth_header(self.agent))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_zero_amounts_accepted(self):
        """Zéro est valide (projet sans programmation pour une année)."""
        payload = {'programmings': full_programming(0, 0, 0)}
        resp = self.client.post(self._bulk_url(), payload, format='json', **auth_header(self.agent))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    # ------------------------------------------------------------------
    # 2. Année hors plage
    # ------------------------------------------------------------------

    def test_year_out_of_range_rejected(self):
        payload = {'programmings': [
            {'fiscal_year': 2025, 'donations': '100', 'loans': '0', 'state_contribution': '0'}
        ]}
        resp = self.client.post(self._bulk_url(), payload, format='json', **auth_header(self.agent))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_year_2031_rejected(self):
        payload = {'programmings': [
            {'fiscal_year': 2031, 'donations': '100', 'loans': '0', 'state_contribution': '0'}
        ]}
        resp = self.client.post(self._bulk_url(), payload, format='json', **auth_header(self.agent))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    # ------------------------------------------------------------------
    # 3. Doublon d'année
    # ------------------------------------------------------------------

    def test_duplicate_year_rejected(self):
        payload = {'programmings': [
            {'fiscal_year': 2026, 'donations': '100', 'loans': '0', 'state_contribution': '0'},
            {'fiscal_year': 2026, 'donations': '200', 'loans': '0', 'state_contribution': '0'},
        ]}
        resp = self.client.post(self._bulk_url(), payload, format='json', **auth_header(self.agent))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('duplicados', str(resp.data).lower())

    # ------------------------------------------------------------------
    # 4. Upsert correct
    # ------------------------------------------------------------------

    def test_bulk_creates_five_programming_rows(self):
        """Un bulk de 5 années crée 5 AnnualProgramming."""
        payload = {'programmings': full_programming(donations=1000000, loans=500000, state=100000)}
        resp = self.client.post(self._bulk_url(), payload, format='json', **auth_header(self.agent))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        count = AnnualProgramming.objects.filter(project=self.project, version=1).count()
        self.assertEqual(count, 5)

    def test_bulk_updates_existing_row(self):
        """Un deuxième bulk met à jour les lignes existantes (pas de doublon)."""
        # Premier bulk
        payload = {'programmings': full_programming(donations=500000)}
        self.client.post(self._bulk_url(), payload, format='json', **auth_header(self.agent))
        # Deuxième bulk : mise à jour
        payload2 = {'programmings': full_programming(donations=900000)}
        resp = self.client.post(self._bulk_url(), payload2, format='json', **auth_header(self.agent))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Toujours 5 lignes (pas de duplication)
        count = AnnualProgramming.objects.filter(project=self.project, version=1).count()
        self.assertEqual(count, 5)
        # La valeur a bien été mise à jour
        row = AnnualProgramming.objects.get(project=self.project, fiscal_year=2026, version=1)
        self.assertEqual(row.donations, Decimal('900000'))

    # ------------------------------------------------------------------
    # 5. Recalcul du total_cost
    # ------------------------------------------------------------------

    def test_total_cost_recalculated_after_bulk(self):
        """total_cost du projet est recalculé après un bulk programming."""
        # 5 ans × (1 000 000 donations + 0 + 0) = 5 000 000
        payload = {'programmings': full_programming(donations=1000000)}
        self.client.post(self._bulk_url(), payload, format='json', **auth_header(self.agent))
        self.project.refresh_from_db()
        self.assertEqual(self.project.total_cost, Decimal('5000000'))

    def test_total_cost_mixed_sources(self):
        """total_cost tient compte des 3 sources."""
        # 5 ans × (100 + 200 + 50) = 1750
        payload = {'programmings': full_programming(donations=100, loans=200, state=50)}
        self.client.post(self._bulk_url(), payload, format='json', **auth_header(self.agent))
        self.project.refresh_from_db()
        self.assertEqual(self.project.total_cost, Decimal('1750'))

    # ------------------------------------------------------------------
    # 6. Verrou SUBMETIDO
    # ------------------------------------------------------------------

    def test_agent_cannot_edit_programming_of_submitted_project(self):
        """Agent ne peut pas modifier la programmation d'un projet SUBMETIDO."""
        self.project.workflow_status = WorkflowStatus.SUBMETIDO
        self.project.save()
        payload = {'programmings': full_programming(donations=999999)}
        resp = self.client.post(self._bulk_url(), payload, format='json', **auth_header(self.agent))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('rascunho', str(resp.data).lower())

    def test_dgp_can_edit_programming_of_submitted_project(self):
        """DGP peut modifier la programmation même si SUBMETIDO."""
        self.project.workflow_status = WorkflowStatus.SUBMETIDO
        self.project.save()
        payload = {'programmings': full_programming(donations=300000)}
        resp = self.client.post(self._bulk_url(), payload, format='json', **auth_header(self.dgp))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    # ------------------------------------------------------------------
    # 7. Cohérence AnnualProgramming individuel (endpoint /programming/)
    # ------------------------------------------------------------------

    def test_individual_programming_negative_rejected_via_api(self):
        """Via l'endpoint /programming/ individuel, valeurs négatives refusées."""
        url = reverse('programming-list')
        payload = {
            'project': self.project.pk,
            'fiscal_year': 2027,
            'donations': '-100',
            'loans': '0',
            'state_contribution': '0',
            'version': 1,
        }
        resp = self.client.post(url, payload, format='json', **auth_header(self.dgp))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
