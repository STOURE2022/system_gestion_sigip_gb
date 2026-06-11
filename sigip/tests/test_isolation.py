"""
Tests d'isolation entre ministères.

Règles vérifiées :
1. Un MINISTRY_AGENT ne voit que les projets de son ministère.
2. Un MINISTRY_AGENT ne peut pas créer un projet pour un autre ministère.
3. Un MINISTRY_AGENT ne peut pas modifier un projet d'un autre ministère.
4. Un MINISTRY_AGENT sans ministry rattaché reçoit un 403 explicite.
5. Un DGP_ANALYST voit tous les projets.
"""
from decimal import Decimal
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import UserRole
from sigip.models import WorkflowStatus
from .factories import (
    make_ministry, make_user, make_project, make_financier, make_pillar, make_sector,
)


def auth_header(user):
    refresh = RefreshToken.for_user(user)
    return {'HTTP_AUTHORIZATION': f'Bearer {refresh.access_token}'}


class MinistryIsolationTests(APITestCase):

    def setUp(self):
        self.pillar = make_pillar('P1', 'Pilar 1')
        self.sector = make_sector('11', 'Governação')
        self.financier = make_financier()

        # Deux ministères distincts
        self.min_a = make_ministry('Ministério A', 'MINA', self.pillar)
        self.min_b = make_ministry('Ministério B', 'MINB', self.pillar)

        # Agents
        self.agent_a = make_user('agent_a', UserRole.MINISTRY_AGENT, ministry=self.min_a)
        self.agent_b = make_user('agent_b', UserRole.MINISTRY_AGENT, ministry=self.min_b)
        self.agent_no_min = make_user('agent_nomin', UserRole.MINISTRY_AGENT, ministry=None)
        self.dgp = make_user('dgp_user', UserRole.DGP_ANALYST, ministry=None)

        # Projets
        self.proj_a = make_project('111111111', 'Projecto A1', self.min_a,
                                   self.financier)
        self.proj_b = make_project('222222222', 'Projecto B1', self.min_b,
                                   self.financier)

    # ------------------------------------------------------------------
    # 1. Lecture : cloisonnement
    # ------------------------------------------------------------------

    def test_agent_a_sees_only_ministry_a_projects(self):
        """Agent A ne doit voir que les projets du Ministère A."""
        url = reverse('project-list')
        resp = self.client.get(url, **auth_header(self.agent_a))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        codes = [p['code'] for p in resp.data.get('results', resp.data)]
        self.assertIn('111111111', codes)
        self.assertNotIn('222222222', codes)

    def test_agent_b_sees_only_ministry_b_projects(self):
        """Agent B ne doit pas voir les projets du Ministère A."""
        url = reverse('project-list')
        resp = self.client.get(url, **auth_header(self.agent_b))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        codes = [p['code'] for p in resp.data.get('results', resp.data)]
        self.assertNotIn('111111111', codes)
        self.assertIn('222222222', codes)

    def test_dgp_sees_all_projects(self):
        """DGP_ANALYST doit voir tous les projets."""
        url = reverse('project-list')
        resp = self.client.get(url, **auth_header(self.dgp))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        codes = [p['code'] for p in resp.data.get('results', resp.data)]
        self.assertIn('111111111', codes)
        self.assertIn('222222222', codes)

    def test_agent_a_cannot_retrieve_ministry_b_project(self):
        """Agent A ne peut pas lire le détail d'un projet de Ministère B."""
        url = reverse('project-detail', args=[self.proj_b.pk])
        resp = self.client.get(url, **auth_header(self.agent_a))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    # ------------------------------------------------------------------
    # 2. Création : auto-assignment du ministère
    # ------------------------------------------------------------------

    def test_agent_a_creates_project_for_own_ministry(self):
        """Agent A crée un projet — ministry est automatiquement son ministère."""
        url = reverse('project-list')
        payload = {
            'code': '333333333',
            'title': 'Nouveau Projecto A',
            'ministry': self.min_b.pk,  # tentative de choisir l'autre ministère
            'sector': self.sector.pk,
            'pillar': self.pillar.pk,
            'principal_financier': self.financier.pk,
            'status': 'IDENTIFIED',
            'total_cost': '0',
        }
        resp = self.client.post(url, payload, format='json', **auth_header(self.agent_a))
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        # Le ministry doit être forcé à min_a, pas min_b
        from sigip.models import Project
        proj = Project.objects.get(code='333333333')
        self.assertEqual(proj.ministry_id, self.min_a.pk)

    def test_agent_a_creates_project_gets_rascunho_status(self):
        """Un projet créé par un agent doit être en RASCUNHO."""
        url = reverse('project-list')
        payload = {
            'code': '444444444',
            'title': 'Projecto Rascunho',
            'ministry': self.min_a.pk,
            'sector': self.sector.pk,
            'pillar': self.pillar.pk,
            'principal_financier': self.financier.pk,
            'status': 'IDENTIFIED',
            'total_cost': '0',
        }
        resp = self.client.post(url, payload, format='json', **auth_header(self.agent_a))
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        from sigip.models import Project
        proj = Project.objects.get(code='444444444')
        self.assertEqual(proj.workflow_status, WorkflowStatus.RASCUNHO)

    # ------------------------------------------------------------------
    # 3. Modification : cloisonnement inter-ministères
    # ------------------------------------------------------------------

    def test_agent_a_cannot_update_ministry_b_project(self):
        """Agent A ne peut pas modifier un projet du Ministère B."""
        url = reverse('project-detail', args=[self.proj_b.pk])
        resp = self.client.patch(
            url, {'title': 'Hackeado'}, format='json', **auth_header(self.agent_a)
        )
        # 404 car le projet n'est pas dans son queryset
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    # ------------------------------------------------------------------
    # 4. Agent sans ministère → 403 explicite
    # ------------------------------------------------------------------

    def test_agent_without_ministry_gets_403_on_create(self):
        """Agent sans ministère reçoit 403 avec message explicite."""
        url = reverse('project-list')
        payload = {
            'code': '555555555',
            'title': 'Test',
            'ministry': self.min_a.pk,
            'sector': self.sector.pk,
            'pillar': self.pillar.pk,
            'principal_financier': self.financier.pk,
            'status': 'IDENTIFIED',
            'total_cost': '0',
        }
        resp = self.client.post(url, payload, format='json', **auth_header(self.agent_no_min))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('ministério', str(resp.data).lower())

    def test_agent_without_ministry_sees_empty_list(self):
        """Agent sans ministère reçoit une liste vide, pas d'erreur 500."""
        url = reverse('project-list')
        resp = self.client.get(url, **auth_header(self.agent_no_min))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = resp.data.get('results', resp.data)
        self.assertEqual(len(results), 0)

    # ------------------------------------------------------------------
    # 5. Code unique
    # ------------------------------------------------------------------

    def test_duplicate_code_rejected(self):
        """Un code projet déjà existant est refusé."""
        url = reverse('project-list')
        payload = {
            'code': '111111111',  # déjà utilisé par proj_a
            'title': 'Duplicata',
            'ministry': self.min_a.pk,
            'sector': self.sector.pk,
            'pillar': self.pillar.pk,
            'principal_financier': self.financier.pk,
            'status': 'IDENTIFIED',
            'total_cost': '0',
        }
        resp = self.client.post(url, payload, format='json', **auth_header(self.agent_a))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('code', str(resp.data).lower())

    # ------------------------------------------------------------------
    # 6. Montant négatif refusé
    # ------------------------------------------------------------------

    def test_negative_total_cost_rejected(self):
        """Un total_cost négatif doit être refusé."""
        url = reverse('project-list')
        payload = {
            'code': '666666666',
            'title': 'Projecto Negativo',
            'ministry': self.min_a.pk,
            'sector': self.sector.pk,
            'pillar': self.pillar.pk,
            'principal_financier': self.financier.pk,
            'status': 'IDENTIFIED',
            'total_cost': '-1000',
        }
        resp = self.client.post(url, payload, format='json', **auth_header(self.agent_a))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
