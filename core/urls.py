from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.index_view, name='index'),
    path('analise/', views.analise_manual_view, name='analise_manual'),
    path('analise/executar/', views.disparar_analise_ajax, name='disparar_analise_ajax'),
    path('ajax/processar-pdf/', views.processar_pdf_ajax, name='processar_pdf_ajax'),
    path('ajax/raspar-mp/', views.raspar_dados_mp_ajax, name='raspar_dados_mp_ajax'),
    path('pagina/<slug:slug>/', views.pagina_dinamica_view, name='pagina_dinamica'),
    path('agradecimento/', views.agradecimento_view, name='agradecimento'),
    path('historico/', views.historico_analises_view, name='historico_analises'),
    path('historico/analise/<int:analise_id>/', views.detalhe_analise_view, name='detalhe_analise'),
]