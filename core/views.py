import uuid
import hashlib
import json
import random
import time
import re
import html
import markdown
import requests

from urllib.parse import urlparse
from pypdf import PdfReader
from django.utils import timezone
from django.utils.html import strip_tags
from django.utils.safestring import mark_safe
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.db.models import Q
from django.views.decorators.http import require_POST

from .models import (
    MenuCabecalho, 
    ApresentacaoPlataforma, 
    AnaliseEmenda, 
    QuestaoControle, 
    RespostaAuditor, 
    PerguntaPlataforma, 
    ConfiguracaoAplicacao
)
from .services.analisador import executar_pipeline_analise


def index_view(request):
    apresentacao = ApresentacaoPlataforma.objects.first()
    return render(request, 'core/index.html', {
        'apresentacao': apresentacao,
        'mostrar_logo': False,
    })


def pagina_dinamica_view(request, slug):
    menu = get_object_or_404(MenuCabecalho, slug=slug, ativo=True)
    menu.conteudo_html = markdown.markdown(
        menu.conteudo,
        extensions=['extra', 'nl2br', 'sane_lists']
    )
    return render(request, 'core/pagina_dinamica.html', {'menu': menu})


def analise_manual_view(request):
    if request.GET.get('reset') == '1':
        request.session.flush()
        return redirect('core:analise_manual')

    termo_aceito = request.session.get('termo_aceito', False)
    
    if request.method == 'POST' and 'aceitar_termo' in request.POST:
        request.session['termo_aceito'] = True
        
        if not request.session.get('uuid_auditor'):
            request.session['uuid_auditor'] = str(uuid.uuid4())
            
        if not request.session.get('chave_unica'):
            base_str = f"auditoria-{timezone.now().timestamp()}-{uuid.uuid4()}"
            request.session['chave_unica'] = hashlib.sha256(base_str.encode('utf-8')).hexdigest()[:12]
            
        return redirect('core:analise_manual')

    if not termo_aceito:
        apresentacao = ApresentacaoPlataforma.objects.first()
        return render(request, 'core/termo_aceite.html', {'apresentacao': apresentacao})

    usuario = request.user if request.user.is_authenticated else None
    chave_unica_sessao = request.session.get('chave_unica')
    
    if not chave_unica_sessao:
        request.session.flush()
        return redirect('core:analise_manual')
    
    if request.method == 'POST' and 'enviar_questionario_final' in request.POST:
        respostas_dict = {}
        for key, value in request.POST.items():
            if key.startswith('pergunta_') and value.strip():
                try:
                    pergunta_id = key.split('_')[1]
                    respostas_dict[f"pergunta_{pergunta_id}"] = value.strip()
                except Exception:
                    pass
        
        if chave_unica_sessao:
            try:
                analise_obj = AnaliseEmenda.objects.get(chave_unica=chave_unica_sessao)
                analise_obj.resposta_questionario = respostas_dict
                if usuario and not analise_obj.usuario:
                    analise_obj.usuario = usuario
                analise_obj.save(update_fields=['resposta_questionario', 'usuario'])
            except AnaliseEmenda.DoesNotExist:
                pass
        
        request.session['fluxo_concluido'] = True
        
        keys_to_clear = ['questoes_sessao_ids', 'respondidas_ids', 'termo_aceito', 'uuid_auditor', 'chave_unica']
        for k in keys_to_clear:
            if k in request.session:
                del request.session[k]
                
        return redirect('core:agradecimento')

    config = ConfiguracaoAplicacao.objects.filter(ativo=True).first()
    limite_questoes = config.numero_questoes if config else 10
    modo_selecao = config.modo_selecao if config else 'ALEATORIO'
    ordem_apresentacao = config.ordem_apresentacao if config else 'ALEATORIO'

    if 'questoes_sessao_ids' not in request.session:
        qs = QuestaoControle.objects.all()
        
        if ordem_apresentacao == 'TAMANHO_ASC':
            qs = qs.order_by('tamanho_char', 'id')
        elif ordem_apresentacao == 'TAMANHO_DESC':
            qs = qs.order_by('-tamanho_char', 'id')
        else:
            qs = qs.order_by('?')

        all_ids = list(qs.values_list('id', flat=True))
        if modo_selecao == 'ALEATORIO':
            random.shuffle(all_ids)
            
        request.session['questoes_sessao_ids'] = all_ids[:limite_questoes]
        request.session['respondidas_ids'] = []

    session_ids = request.session['questoes_sessao_ids']
    respondidas_ids = request.session.get('respondidas_ids', [])
    questoes_pendentes_ids = [qid for qid in session_ids if qid not in respondidas_ids]

    if questoes_pendentes_ids:
        questao_atual_id = questoes_pendentes_ids[0]
        questao_atual = get_object_or_404(QuestaoControle, id=questao_atual_id)
        
        if request.method == 'POST' and 'enviar_resposta_controle' in request.POST:
            resposta_marcada = request.POST.get('resposta_marcada')
            tempo_gasto = float(request.POST.get('tempo_resposta', 0))
            
            RespostaAuditor.objects.create(
                chave_unica=chave_unica_sessao,
                usuario=usuario,
                questao=questao_atual,
                resposta_marcada=resposta_marcada,
                tempo_resposta_segundos=tempo_gasto
            )
            
            respondidas_ids.append(questao_atual.id)
            request.session['respondidas_ids'] = respondidas_ids
            return redirect('core:analise_manual')

        return render(request, 'core/etapa_questoes_controle.html', {
            'questao': questao_atual,
            'total': len(session_ids),
            'restantes': len(questoes_pendentes_ids),
            'chave_unica': chave_unica_sessao
        })

    ultimas_analises = AnaliseEmenda.objects.all()[:10]
    perguntas_finais = PerguntaPlataforma.objects.filter(ativo=True).order_by('etapa_numero', 'ordem')

    return render(request, 'core/analise_manual.html', {
        'ultimas_analises': ultimas_analises,
        'perguntas_finais': perguntas_finais,
        'chave_unica': chave_unica_sessao
    })


@require_POST
def processar_pdf_ajax(request):
    if 'pdf_file' not in request.FILES:
        return JsonResponse({'sucesso': False, 'mensagem': 'Nenhum arquivo enviado.'}, status=400)
    
    pdf_file = request.FILES['pdf_file']
    
    try:
        reader = PdfReader(pdf_file)
        texto_completo = "".join([pagina.extract_text() + "\n" for pagina in reader.pages if pagina.extract_text()])
        
        texto_lower = texto_completo.lower()
        padrao_busca = r'(justificativa|justificação|motivação)(.*)'
        match = re.search(padrao_busca, texto_lower, re.DOTALL)
        
        texto_alvo = match.group(0) if match else texto_lower

        texto_limpo = html.escape(texto_alvo)
        texto_sanitizado = re.sub(r'[^\w\s\.,;:!?()\/\-\n–—]', '', texto_limpo)

        return JsonResponse({
            'sucesso': True,
            'texto_extraido': texto_sanitizado.strip()
        })
        
    except Exception as e:
        return JsonResponse({'sucesso': False, 'mensagem': f'Erro ao ler o PDF: {str(e)}'}, status=500)


@require_POST
def raspar_dados_mp_ajax(request):
    try:
        data = json.loads(request.body)
        url = data.get('link_mp', '').strip()
    except Exception:
        return JsonResponse({'sucesso': False, 'mensagem': 'Dados inválidos.'}, status=400)

    if not url or ('leg.br' not in url and 'gov.br' not in url):
        return JsonResponse({'sucesso': False, 'mensagem': 'URL oficial inválida.'}, status=400)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            return JsonResponse({'sucesso': False, 'mensagem': f'Erro ao acessar o portal (HTTP {response.status_code}).'}, status=400)

        soup = BeautifulSoup(response.content, 'html.parser')
        
        texto_ementa = ""
        div_ementa = soup.find('div', class_=re.compile(r'sf-bloco-paragrafos-condensados'))
        if div_ementa:
            p_ementa = div_ementa.find('strong', string=re.compile(r'Ementa:', re.IGNORECASE))
            if p_ementa and p_ementa.parent:
                span_txt = p_ementa.parent.find('span')
                if span_txt:
                    texto_ementa = span_txt.get_text(strip=True)

        titulo_pagina = soup.find('title')
        numero_mp_encontrado = "Medida Provisória"
        if titulo_pagina:
            match_mp = re.search(r'MPV\s*\d+/\d+|MP\s*\d+/\d+|\d+/\d+', titulo_pagina.get_text(), re.IGNORECASE)
            if match_mp:
                numero_mp_encontrado = match_mp.group(0)

        return JsonResponse({
            'sucesso': True,
            'numero_mp': numero_mp_encontrado,
            'ementa': texto_ementa or "Ementa não localizada automaticamente na página."
        })

    except Exception as e:
        return JsonResponse({'sucesso': False, 'mensagem': f'Erro de conexão com o site oficial: {str(e)}'}, status=500)


def disparar_analise_ajax(request):
    if request.method != 'POST':
        return JsonResponse({
            'sucesso': False,
            'mensagem': 'Método não permitido para este endpoint.'
        }, status=405)

    try:
        chave_sessao = request.session.get('chave_unica')
        if not request.session.get('termo_aceito') or not chave_sessao:
            return JsonResponse({
                'sucesso': False, 
                'mensagem': 'Acesso negado. É necessário aceitar os termos da sessão para executar análises.'
            }, status=403)

        dados = json.loads(request.body)
        
        numero_mp = strip_tags(dados.get('numero_mp', '')).strip()
        link_mp = strip_tags(dados.get('link_mp', '')).strip()
        ementa = strip_tags(dados.get('ementa', '')).strip()
        emenda = strip_tags(dados.get('emenda', '')).strip()

        if not link_mp:
            return JsonResponse({'sucesso': False, 'mensagem': 'O link da proposição é obrigatório.'})
            
        parsed_url = urlparse(link_mp)
        domain = parsed_url.netloc.lower()
        if not (domain.endswith('.leg.br') or domain.endswith('.gov.br')):
            return JsonResponse({
                'sucesso': False, 
                'mensagem': 'A URL informada deve pertencer a um domínio oficial (.leg.br ou .gov.br).'
            })

        analise, created = AnaliseEmenda.objects.get_or_create(
            chave_unica=chave_sessao,
            defaults={
                'numero_mp': numero_mp,
                'link_mp': link_mp,
                'ementa': ementa,
                'emenda': emenda,
                'data_acesso': timezone.now(),
                'status': 'aguardando',
                'usuario': request.user if request.user.is_authenticated else None
            }
        )

        if not created:
            analise.numero_mp = numero_mp
            analise.link_mp = link_mp
            analise.ementa = ementa
            analise.emenda = emenda
            analise.status = 'aguardando'
            analise.save()

        sucesso, mensagem = executar_pipeline_analise(analise.id)
        analise.refresh_from_db()

        if not sucesso:
            return JsonResponse({
                'sucesso': False,
                'mensagem': f"Falha na execução do pipeline: {mensagem}"
            }, status=500)

        return JsonResponse({
            'sucesso': True,
            'status_final': analise.status,
            'runtime': analise.runtime,
            'chave_unica': analise.chave_unica,
            'resultado': analise.resultado_json
        })

    except Exception as e:
        return JsonResponse({'sucesso': False, 'mensagem': str(e)}, status=500)


def historico_analises_view(request):
    query = request.GET.get('q', '').strip() if request.method == 'GET' else ''
    status_filtro = request.GET.get('status', '').strip() if request.method == 'GET' else ''

    analises_qs = AnaliseEmenda.objects.select_related('usuario').all().order_by('-data_acesso')

    if query:
        analises_qs = analises_qs.filter(
            Q(numero_mp__icontains=query) |
            Q(ementa__icontains=query) |
            Q(chave_unica__icontains=query)
        )

    if status_filtro:
        analises_qs = analises_qs.filter(status=status_filtro)

    paginator = Paginator(analises_qs, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'query': query,
        'status_filtro': status_filtro,
        'status_choices': AnaliseEmenda.STATUS_CHOICES,
    }
    return render(request, 'core/historico_analises.html', context)


def agradecimento_view(request):
    if not request.session.get('fluxo_concluido', False):
        return redirect('core:analise_manual')
        
    request.session.flush()
    return render(request, 'core/agradecimento.html')


def handler_404(request, exception):
    context = {'codigo_erro': 404}
    return render(request, 'core/erro.html', context, status=404)


def handler_405(request, exception=None, *args, **kwargs):
    context = {'codigo_erro': 405}
    return render(request, 'core/erro.html', context, status=405)


def handler_500(request):
    context = {'codigo_erro': 500}
    return render(request, 'core/erro.html', context, status=500)


def detalhe_analise_view(request, analise_id):
    analise = get_object_or_404(AnaliseEmenda, id=analise_id)
    perguntas_finais = PerguntaPlataforma.objects.filter(ativo=True).order_by('etapa_numero', 'ordem')

    context = {
        'analise': analise,
        'perguntas_finais': perguntas_finais,
    }
    return render(request, 'core/detalhe_analise.html', context)