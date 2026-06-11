"""
Tests des transitions de workflow.

Transitions testées :
  RASCUNHO  → SUBMETIDO  (agent ou DGP)
  SUBMETIDO → VALIDADO   (DGP/VALIDATOR)
  SUBMETIDO → RASCUNHO   (rejet DGP)
  VALIDADO  → RASCUNHO   (déverrouillage ADMIN)

Transitions interdites :
  RASCUNHO  → VALIDADO   directement
  VALIDADO  → SUBMETIDO
  Agent modifie un projet SUBMETIDO/VALIDADO
  Agent soumet un projet d'un autre ministère
"""
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import UserRole
from sigip.models import WorkflowStatus
from .factories import (
    make_ministry, make_user, make_project, make_financier,
    make_pillar, make_sector,
)


def auth_header(user):
    refresh = RefreshToken.for_user(user)
    return {'HTTP_AUTHORIZATION': f'Bearer {refresh.access_token}'}


class WorkflowTransitionTests(APITestCase):

    def setUp(self):
        self.pillar = make_pillar('P2', 'Pilar 2', order=2)
        self.sector = make_sector('22', 'Infraestruturas')
        self.financier = make_financier('BAD', 'BAD')

        self.ministry = make_ministry('MINEDU', 'MINEDU', self.pillar)
        self.agent = make_user('agent_edu', UserRole.MINISTRY_AGENT, ministry=self.ministry)
        self.dgp = make_user('dgp_ana', UserRole.DGP_ANALYST)
        self.validator = make_user('validator1', UserRole.VALIDATOR)
        self.admin = make_user('admin1', UserRole.ADMIN)
        self.reader = make_user('reader1', UserRole.READER)

        # Projet de base en RASCUNHO
        self.project = make_project(
            '777777777', 'Projecto Workflow', self.ministry, self.financier,
            workflow=WorkflowStatus.RASCUNHO,
        )

    # ------------------------------------------------------------------
    # RASCUNHO → SUBMETIDO
    # ------------------------------------------------------------------

    def test_agent_can_submit_own_project(self):
        url = reverse('project-submit', args=[self.project.pk])
        resp = self.client.post(url, {}, format='json', **auth_header(self.agent))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.project.refresh_from_db()
        self.assertEqual(self.project.workflow_status, WorkflowStatus.SUBMETIDO)

    def test_dgp_can_submit_project(self):
        url = reverse('project-submit', args=[self.project.pk])
        resp = self.client.post(url, {}, format='json', **auth_header(self.dgp))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.project.refresh_from_db()
        self.assertEqual(self.project.workflow_status, WorkflowStatus.SUBMETIDO)

    def test_reader_cannot_submit(self):
        url = reverse('project-submit', args=[self.project.pk])
        resp = self.client.post(url, {}, format='json', **auth_header(self.reader))
        self.assertIn(resp.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])

    def test_cannot_submit_already_submitted(self):
        """Soumettre un projet déjà SUBMETIDO doit échouer."""
        self.project.workflow_status = WorkflowStatus.SUBMETIDO
        self.project.save()
        url = reverse('project-submit', args=[self.project.pk])
        resp = self.client.post(url, {}, format='json', **auth_header(self.dgp))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_agent_of_other_ministry_cannot_submit(self):
        """Agent d'un autre ministère ne peut pas soumettre ce projet."""
        other_min = make_ministry('Outro Min', 'OUTRO', self.pillar)
        other_agent = make_user('other_agent', UserRole.MINISTRY_AGENT, ministry=other_min)
        url = reverse('project-submit', args=[self.project.pk])
        resp = self.client.post(url, {}, format='json', **auth_header(other_agent))
        # 404 car non visible dans son queryset
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    # ------------------------------------------------------------------
    # SUBMETIDO → VALIDADO
    # ------------------------------------------------------------------

    def test_dgp_can_validate_submitted_project(self):
        self.project.workflow_status = WorkflowStatus.SUBMETIDO
        self.project.save()
        url = reverse('project-validate-project', args=[self.project.pk])
        resp = self.client.post(url, {}, format='json', **auth_header(self.dgp))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.project.refresh_from_db()
        self.assertEqual(self.project.workflow_status, WorkflowStatus.VALIDADO)

    def test_validator_can_validate_submitted_project(self):
        self.project.workflow_status = WorkflowStatus.SUBMETIDO
        self.project.save()
        url = reverse('project-validate-project', args=[self.project.pk])
        resp = self.client.post(url, {}, format='json', **auth_header(self.validator))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.project.refresh_from_db()
        self.assertEqual(self.project.workflow_status, WorkflowStatus.VALIDADO)

    def test_agent_cannot_validate(self):
        self.project.workflow_status = WorkflowStatus.SUBMETIDO
        self.project.save()
        url = reverse('project-validate-project', args=[self.project.pk])
        resp = self.client.post(url, {}, format='json', **auth_header(self.agent))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_cannot_validate_rascunho_directly(self):
        """On ne peut pas valider un projet en RASCUNHO directement."""
        url = reverse('project-validate-project', args=[self.project.pk])
        resp = self.client.post(url, {}, format='json', **auth_header(self.dgp))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    # ------------------------------------------------------------------
    # SUBMETIDO → RASCUNHO (rejet)
    # ------------------------------------------------------------------

    def test_dgp_can_reject_submitted_project(self):
        self.project.workflow_status = WorkflowStatus.SUBMETIDO
        self.project.save()
        url = reverse('project-reject', args=[self.project.pk])
        resp = self.client.post(
            url,
            {'rejection_note': 'Orçamento incompleto.'},
            format='json',
            **auth_header(self.dgp),
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.project.refresh_from_db()
        self.assertEqual(self.project.workflow_status, WorkflowStatus.RASCUNHO)
        self.assertEqual(self.project.rejection_note, 'Orçamento incompleto.')

    def test_reject_without_note_still_works(self):
        """La note de rejet est optionnelle."""
        self.project.workflow_status = WorkflowStatus.SUBMETIDO
        self.project.save()
        url = reverse('project-reject', args=[self.project.pk])
        resp = self.client.post(url, {}, format='json', **auth_header(self.dgp))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_agent_cannot_reject(self):
        self.project.workflow_status = WorkflowStatus.SUBMETIDO
        self.project.save()
        url = reverse('project-reject', args=[self.project.pk])
        resp = self.client.post(
            url, {'rejection_note': 'test'}, format='json', **auth_header(self.agent)
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    # ------------------------------------------------------------------
    # Verrouillage VALIDADO
    # ------------------------------------------------------------------

    def test_agent_cannot_update_validated_project(self):
        """Un projet VALIDADO est verrouillé pour l'agent."""
        self.project.workflow_status = WorkflowStatus.VALIDADO
        self.project.save()
        url = reverse('project-detail', args=[self.project.pk])
        resp = self.client.patch(
            url, {'title': 'Alteração bloqueada'}, format='json', **auth_header(self.agent)
        )
        self.assertIn(resp.status_code, [
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        ])

    def test_dgp_cannot_update_validated_project(self):
        """DGP_ANALYST ne peut pas non plus modifier un projet VALIDADO."""
        self.project.workflow_status = WorkflowStatus.VALIDADO
        self.project.save()
        url = reverse('project-detail', args=[self.project.pk])
        resp = self.client.patch(
            url, {'title': 'Test DGP patch'}, format='json', **auth_header(self.dgp)
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_update_validated_project(self):
        """ADMIN peut modifier un projet VALIDADO."""
        self.project.workflow_status = WorkflowStatus.VALIDADO
        self.project.save()
        url = reverse('project-detail', args=[self.project.pk])
        resp = self.client.patch(
            url, {'title': 'Alteração pelo Admin'}, format='json', **auth_header(self.admin)
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    # ------------------------------------------------------------------
    # VALIDADO → RASCUNHO (déverrouillage ADMIN)
    # ------------------------------------------------------------------

    def test_admin_can_unlock_validated_project(self):
        self.project.workflow_status = WorkflowStatus.VALIDADO
        self.project.save()
        url = reverse('project-unlock', args=[self.project.pk])
        resp = self.client.post(
            url,
            {'rejection_note': 'Revisão necessária.'},
            format='json',
            **auth_header(self.admin),
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.project.refresh_from_db()
        self.assertEqual(self.project.workflow_status, WorkflowStatus.RASCUNHO)

    def test_dgp_cannot_unlock_validated_project(self):
        self.project.workflow_status = WorkflowStatus.VALIDADO
        self.project.save()
        url = reverse('project-unlock', args=[self.project.pk])
        resp = self.client.post(url, {}, format='json', **auth_header(self.dgp))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    # ------------------------------------------------------------------
    # Suppression
    # ------------------------------------------------------------------

    def test_cannot_delete_validated_project(self):
        """On ne peut pas supprimer un projet VALIDADO."""
        self.project.workflow_status = WorkflowStatus.VALIDADO
        self.project.save()
        url = reverse('project-detail', args=[self.project.pk])
        resp = self.client.delete(url, **auth_header(self.admin))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_agent_can_delete_draft_project(self):
        """Un agent peut supprimer un projet RASCUNHO (soft delete)."""
        url = reverse('project-detail', args=[self.project.pk])
        resp = self.client.delete(url, **auth_header(self.agent))
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.project.refresh_from_db()
        self.assertTrue(self.project.is_deleted)
