"""
SIGIP-GB URL patterns  –  /api/v1/
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    PillarViewSet, SectorViewSet, GovPriorityViewSet,
    MinistryViewSet, FinancierViewSet, ExpenseNatureViewSet,
    ProjectViewSet, AnnualProgrammingViewSet, DisbursementViewSet,
    PPProjectViewSet, PIPVersionViewSet,
    DashboardView, ExecutionDashboardView, ImportView
)

router = DefaultRouter()
router.register('pillars', PillarViewSet, basename='pillar')
router.register('sectors', SectorViewSet, basename='sector')
router.register('gov-priorities', GovPriorityViewSet, basename='gov-priority')
router.register('ministries', MinistryViewSet, basename='ministry')
router.register('financiers', FinancierViewSet, basename='financier')
router.register('expense-natures', ExpenseNatureViewSet, basename='expense-nature')
router.register('projects', ProjectViewSet, basename='project')
router.register('programming', AnnualProgrammingViewSet, basename='programming')
router.register('disbursements', DisbursementViewSet, basename='disbursement')
router.register('ppp-projects', PPProjectViewSet, basename='ppp-project')
router.register('pip-versions', PIPVersionViewSet, basename='pip-version')

urlpatterns = [
    path('', include(router.urls)),
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
    path('dashboard/execution/', ExecutionDashboardView.as_view(), name='dashboard-execution'),
    path('import/', ImportView.as_view(), name='import'),
]
