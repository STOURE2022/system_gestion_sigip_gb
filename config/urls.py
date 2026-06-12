"""
SIGIP-GB – Root URL configuration
"""
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import TemplateView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView
from sigip.resumo_views import (
    ResumoPNDView, ResumoSectorView,
    ResumoNaturezaDespesaView, ResumoPrioridadeGovernoView,
    ResumoFuncaoEstadoView, ResumoFuncionamentoInvestimentoView,
    ResumoExportView,
)

admin.site.site_header = 'SIGIP-GB – Administração'
admin.site.site_title = 'SIGIP-GB'
admin.site.index_title = 'Gestão do Investimento Público – Guiné-Bissau'

urlpatterns = [
    # Admin
    path('admin/', admin.site.urls),

    # API
    path('api/v1/', include('sigip.urls')),
    path('api/v1/auth/', include('core.urls')),

    # Resumo (Síntese) endpoints
    path('api/v1/resumo/pnd/', ResumoPNDView.as_view(), name='resumo-pnd'),
    path('api/v1/resumo/sector/', ResumoSectorView.as_view(), name='resumo-sector'),
    path('api/v1/resumo/natureza_despesa/', ResumoNaturezaDespesaView.as_view(), name='resumo-natureza-despesa'),
    path('api/v1/resumo/prioridade_governo/', ResumoPrioridadeGovernoView.as_view(), name='resumo-prioridade-governo'),
    path('api/v1/resumo/funcao_estado/', ResumoFuncaoEstadoView.as_view(), name='resumo-funcao-estado'),
    path('api/v1/resumo/funcionamento_investimento/', ResumoFuncionamentoInvestimentoView.as_view(), name='resumo-func-inv'),
    path('api/v1/resumo/export/', ResumoExportView.as_view(), name='resumo-export'),

    # OpenAPI / Swagger
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # Landing page publique
    path('', TemplateView.as_view(template_name='landing.html'), name='home'),

    # SPA — application complète (toutes les sous-routes /app/*)
    re_path(r'^app(/.*)?$', TemplateView.as_view(template_name='index.html'), name='app'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    try:
        import debug_toolbar
        urlpatterns = [path('__debug__/', include(debug_toolbar.urls))] + urlpatterns
    except ImportError:
        pass
