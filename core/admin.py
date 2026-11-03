import io
import csv
import json
from django import forms
from django.contrib import admin, messages
from django.db import models
from django.forms import Textarea
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.urls import path
from django.utils.html import format_html

from .models import (
    ConfiguracaoSeguranca,
    MenuCabecalho,
    ApresentacaoPlataforma,
    PerguntaPlataforma,
    QuestaoControle,
    ConfiguracaoAplicacao,
    RespostaAuditor,
    AnaliseEmenda,
    LogExecucao
)


def safe_int(val):
    if not val:
        return None
    try:
        return int(float(str(val).strip()))
    except (ValueError, TypeError):
        return None


def sanitizar_celula_csv(valor):
    texto = str(valor or '')
    if texto.startswith(('=', '+', '-', '@')):
        return f"'{texto}"
    return texto


class MapeamentoCSVForm(forms.Form):
    CAMPOS_MODEL = [
        ('mp_numero', 'Número da MP (mp_numero)'),
        ('ano_mp', 'Ano da MP (ano_mp)'),
        ('link_mp', 'Link da MP (link_mp)'),
        ('numero_emenda', 'Número da Emenda (numero_emenda)'),
        ('link_emenda', 'Link da Emenda (link_emenda)'),
        ('mp_ementa', 'Ementa da MP (mp_ementa)'),
        ('mp_corpo', 'Corpo da MP (mp_corpo)'),
        ('mp_motivacao', 'Motivação da MP (mp_motivacao)'),
        ('classificacao', 'Classificação/Rótulo (classificacao)'),
        ('tamanho_char', 'Tamanho em Caracteres (tamanho_char)'),
        ('tamanho_rotulo', 'Tamanho Rótulo [P/M/G] (tamanho_rotulo)'),
    ]

    arquivo_csv = forms.FileField(
        label="Arquivo CSV",
        help_text="Selecione o arquivo CSV com codificação UTF-8."
    )
    delimitador = forms.ChoiceField(
        choices=[(';', 'Ponto e vírgula (;)'), (',', 'Vírgula (,)'), ('\t', 'Tabulação (\t)')],
        initial=';',
        label="Delimitador do CSV"
    )

    def __init__(self, *args, cabecalhos=None, **kwargs):
        super().__init__(*args, **kwargs)
        if cabecalhos:
            choices_colunas = [('', '-- Ignorar Campo --')] + [(col, col) for col in cabecalhos]
            
            for campo_nome, campo_label in self.CAMPOS_MODEL:
                def_val = next((col for col in cabecalhos if col.strip().lower() == campo_nome.lower()), '')
                self.fields[f'map_{campo_nome}'] = forms.ChoiceField(
                    choices=choices_colunas,
                    required=False,
                    initial=def_val,
                    label=f"Mapear: {campo_label}"
                )


class RespostaAuditorInline(admin.TabularInline):
    model = RespostaAuditor
    extra = 0
    readonly_fields = ('usuario', 'resposta_marcada', 'tempo_resposta_segundos', 'respondido_em')
    can_delete = False
    show_change_link = True
    classes = ('collapse',)


@admin.register(ConfiguracaoSeguranca)
class ConfiguracaoSegurancaAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'max_tentativas', 'tempo_bloqueio_minutos']

    def has_add_permission(self, request):
        return not self.model.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MenuCabecalho)
class MenuCabecalhoAdmin(admin.ModelAdmin):
    list_display = ['titulo', 'ordem', 'slug', 'ativo']
    list_display_links = ['titulo']
    list_editable = ['ordem', 'ativo']
    search_fields = ['titulo', 'slug', 'conteudo']
    prepopulated_fields = {'slug': ('titulo',)}

    formfield_overrides = {
        models.TextField: {'widget': Textarea(attrs={'class': 'markdown-editor'})},
    }

    class Media:
        css = {
            'all': ('https://cdn.jsdelivr.net/npm/easymde/dist/easymde.min.css',)
        }
        js = (
            'https://cdn.jsdelivr.net/npm/easymde/dist/easymde.min.js',
            'core/js/admin_markdown.js',
        )


@admin.register(ApresentacaoPlataforma)
class ApresentacaoPlataformaAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'atualizado_em']

    formfield_overrides = {
        models.TextField: {'widget': Textarea(attrs={'class': 'markdown-editor'})},
    }

    class Media:
        css = {'all': ('https://cdn.jsdelivr.net/npm/easymde/dist/easymde.min.css',)}
        js = (
            'https://cdn.jsdelivr.net/npm/easymde/dist/easymde.min.js',
            'core/js/admin_markdown.js',
        )

    def has_add_permission(self, request):
        return not self.model.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PerguntaPlataforma)
class PerguntaPlataformaAdmin(admin.ModelAdmin):
    list_display = [
        'etapa_badge',
        'ordem',
        'enunciado_curto',
        'badge_tipo_resposta',
        'ativo'
    ]
    list_display_links = ['enunciado_curto']
    list_filter = ['etapa_numero', 'tipo_resposta', 'agrupamento', 'ativo']
    search_fields = ['enunciado', 'descricao', 'agrupamento', 'etapa_nome']
    list_editable = ['ativo', 'ordem']

    formfield_overrides = {
        models.TextField: {'widget': Textarea(attrs={'class': 'markdown-editor', 'rows': 3})},
    }

    class Media:
        css = {'all': ('https://cdn.jsdelivr.net/npm/easymde/dist/easymde.min.css',)}
        js = (
            'https://cdn.jsdelivr.net/npm/easymde/dist/easymde.min.js',
            'core/js/admin_markdown.js',
        )

    fieldsets = (
        ('Configuração da Etapa e Ordem', {
            'fields': (('etapa_numero', 'etapa_nome'), ('ordem', 'ativo')),
            'description': 'Configure a numeração sequencial da etapa e a ordem de exibição da pergunta.'
        }),
        ('Classificação', {
            'fields': ('agrupamento', 'tipo_resposta'),
        }),
        ('Conteúdo', {
            'fields': ('enunciado', 'descricao'),
        }),
    )

    @admin.display(description="Etapa", ordering="etapa_numero")
    def etapa_badge(self, obj):
        nome = f" - {obj.etapa_nome}" if obj.etapa_nome else ""
        return format_html(
            '<span style="background-color: #0284c7; color: white; padding: 3px 8px; border-radius: 4px; font-weight: 500; font-size: 11px;">Etapa {}{}</span>',
            obj.etapa_numero,
            nome
        )

    @admin.display(description="Enunciado")
    def enunciado_curto(self, obj):
        return (obj.enunciado[:60] + '...') if len(obj.enunciado) > 60 else obj.enunciado

    @admin.display(description="Tipo de Resposta")
    def badge_tipo_resposta(self, obj):
        labels = {
            'LIKERT_5': 'Likert (1-5)',
            'SIM_NAO': 'Sim / Não',
            'TEXTO': 'Texto Livre',
        }
        return format_html(
            '<span style="border: 1px solid #cbd5e1; padding: 2px 6px; border-radius: 4px; font-size: 11px;">{}</span>',
            labels.get(obj.tipo_resposta, obj.tipo_resposta)
        )


@admin.register(QuestaoControle)
class QuestaoControleAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'mp_numero',
        'ano_mp',
        'numero_emenda',
        'classificacao',
        'tamanho_rotulo',
        'tamanho_char',
        'criado_em',
    )
    list_filter = ('tamanho_rotulo', 'classificacao', 'ano_mp')
    search_fields = (
        'mp_numero',
        'numero_emenda',
        'mp_ementa',
        'mp_corpo',
        'mp_motivacao',
        'classificacao',
    )
    ordering = ('id',)
    list_per_page = 25
    inlines = [RespostaAuditorInline]

    change_list_template = "admin/questaocontrole_changelist.html"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'importar-csv/',
                self.admin_site.admin_view(self.importar_csv_view),
                name='questaocontrole_importar_csv',
            ),
        ]
        return custom_urls + urls

    def importar_csv_view(self, request):
        cabecalhos = None

        if request.method == 'POST':
            if 'carregar_cabecalhos' in request.POST:
                csv_file = request.FILES.get('arquivo_csv')
                delimitador = request.POST.get('delimitador', ';')

                if not csv_file or not csv_file.name.endswith('.csv'):
                    self.message_user(request, "Por favor, envie um arquivo com extensão .csv", level=messages.ERROR)
                    return redirect('admin:core_questaocontrole_importar_csv')

                decoded_file = csv_file.read().decode('utf-8-sig')
                request.session['csv_data_raw'] = decoded_file
                request.session['csv_delimitador'] = delimitador

                reader = csv.reader(io.StringIO(decoded_file), delimiter=delimitador)
                cabecalhos = next(reader, [])
                request.session['csv_cabecalhos'] = cabecalhos
                form = MapeamentoCSVForm(cabecalhos=cabecalhos)

            elif 'processar_importacao' in request.POST:
                decoded_file = request.session.get('csv_data_raw')
                delimitador = request.session.get('csv_delimitador', ';')

                if not decoded_file:
                    self.message_user(request, "Sessão de importação expirada. Envie o arquivo novamente.", level=messages.ERROR)
                    return redirect('admin:core_questaocontrole_importar_csv')

                reader = csv.DictReader(io.StringIO(decoded_file), delimiter=delimitador)
                importados, erros = 0, 0

                mapa_campos = {
                    'mp_numero': request.POST.get('map_mp_numero'),
                    'ano_mp': request.POST.get('map_ano_mp'),
                    'link_mp': request.POST.get('map_link_mp'),
                    'numero_emenda': request.POST.get('map_numero_emenda'),
                    'link_emenda': request.POST.get('map_link_emenda'),
                    'mp_ementa': request.POST.get('map_mp_ementa'),
                    'mp_corpo': request.POST.get('map_mp_corpo'),
                    'mp_motivacao': request.POST.get('map_mp_motivacao'),
                    'classificacao': request.POST.get('map_classificacao'),
                    'tamanho_char': request.POST.get('map_tamanho_char'),
                    'tamanho_rotulo': request.POST.get('map_tamanho_rotulo'),
                }

                def get_val(row, field_key):
                    col = mapa_campos.get(field_key)
                    val = row.get(col, '').strip() if col else ''
                    return sanitizar_celula_csv(val)

                objetos_para_criar = []
                for linha in reader:
                    try:
                        val_rotulo = get_val(linha, 'tamanho_rotulo').upper() or None
                        if val_rotulo not in ['P', 'M', 'G']:
                            val_rotulo = None

                        obj = QuestaoControle(
                            mp_numero=get_val(linha, 'mp_numero'),
                            ano_mp=safe_int(get_val(linha, 'ano_mp')),
                            link_mp=get_val(linha, 'link_mp') or None,
                            numero_emenda=get_val(linha, 'numero_emenda') or None,
                            link_emenda=get_val(linha, 'link_emenda') or None,
                            mp_ementa=get_val(linha, 'mp_ementa'),
                            mp_corpo=get_val(linha, 'mp_corpo'),
                            mp_motivacao=get_val(linha, 'mp_motivacao') or None,
                            classificacao=get_val(linha, 'classificacao'),
                            tamanho_char=safe_int(get_val(linha, 'tamanho_char')),
                            tamanho_rotulo=val_rotulo,
                        )
                        objetos_para_criar.append(obj)
                        importados += 1
                    except Exception:
                        erros += 1

                if objetos_para_criar:
                    QuestaoControle.objects.bulk_create(objetos_para_criar)
                    self.message_user(
                        request,
                        f"{importados} registros importados com sucesso! ({erros} erros)",
                        level=messages.SUCCESS,
                    )

                request.session.pop('csv_data_raw', None)
                request.session.pop('csv_delimitador', None)
                request.session.pop('csv_cabecalhos', None)

                opts = self.model._meta
                return redirect(f'admin:{opts.app_label}_{opts.model_name}_changelist')

        else:
            cabecalhos = request.session.get('csv_cabecalhos')
            form = MapeamentoCSVForm(cabecalhos=cabecalhos)

        context = {
            **self.admin_site.each_context(request),
            'title': 'Importar Questões de Controle via CSV',
            'form': form,
            'cabecalhos': cabecalhos,
            'opts': self.model._meta,
        }
        return render(request, 'admin/importar_csv_mapeamento.html', context)


@admin.register(ConfiguracaoAplicacao)
class ConfiguracaoAplicacaoAdmin(admin.ModelAdmin):
    list_display = (
        'id', 
        'numero_questoes', 
        'modo_selecao', 
        'ordem_apresentacao', 
        'gemini_model_name', 
        'ativo'
    )
    
    fieldsets = (
        ('Parâmetros de Exibição e Seleção', {
            'fields': ('numero_questoes', 'modo_selecao', 'ordem_apresentacao', 'ativo')
        }),
        ('Hugging Face', {
            'fields': ('huggingface_api_key',),
        }),
        ('Pool de Chaves LLM (Rotação e Redundância)', {
            'fields': (
                'llm_api_key_principal',
                'llm_api_key_reserva_1',
                'llm_api_key_reserva_2',
                'gemini_model_name',
            ),
            'description': 'Cadastre a chave principal e até duas chaves de contingência/rotação para contornar limites de taxa (rate limit).'
        }),
    )

    def has_add_permission(self, request):
        return not self.model.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RespostaAuditor)
class RespostaAuditorAdmin(admin.ModelAdmin):
    list_display = ('id', 'usuario', 'mp_numero_display', 'classificacao_display', 'tamanho_display', 'respondido_em')
    list_filter = ('questao__tamanho_rotulo', 'questao__classificacao', 'respondido_em', 'usuario')
    search_fields = ('usuario__username', 'questao__mp_numero', 'resposta_marcada')
    actions = ['exportar_respostas_csv']
    list_select_related = ('usuario', 'questao')

    @admin.display(description="MP Número", ordering="questao__mp_numero")
    def mp_numero_display(self, obj):
        return obj.questao.mp_numero

    @admin.display(description="Classificação", ordering="questao__classificacao")
    def classificacao_display(self, obj):
        return obj.questao.classificacao

    @admin.display(description="Tamanho", ordering="questao__tamanho_rotulo")
    def tamanho_display(self, obj):
        return obj.questao.get_tamanho_rotulo_display()

    @admin.action(description="Exportar Respostas Selecionadas (CSV / Excel)")
    def exportar_respostas_csv(self, request, queryset):
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = 'attachment; filename="export_respostas_controle.csv"'

        writer = csv.writer(response, delimiter=';')
        writer.writerow([
            'ID_Resposta', 'User_ID', 'Username', 'Email', 
            'Questao_ID', 'MP_Numero', 'Classificacao', 'Tamanho_Rotulo', 'Tamanho_Char',
            'Resposta_Marcada', 'Tempo_Segundos', 'Data_Resposta'
        ])

        for r in queryset.select_related('usuario', 'questao'):
            writer.writerow([
                r.id,
                r.usuario.id,
                r.usuario.username,
                r.usuario.email,
                r.questao.id,
                r.questao.mp_numero,
                r.questao.classificacao,
                r.questao.get_tamanho_rotulo_display(),
                r.questao.tamanho_char,
                r.resposta_marcada,
                r.tempo_resposta_segundos,
                r.respondido_em.strftime("%Y-%m-%d %H:%M:%S")
            ])

        return response


@admin.register(AnaliseEmenda)
class AnaliseEmendaAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'numero_mp',
        'chave_unica',
        'status',
        'data_acesso',
        'usuario',
    )
    list_filter = ('status', 'data_acesso')
    search_fields = ('numero_mp', 'chave_unica', 'ementa', 'emenda')
    readonly_fields = ('data_acesso', 'runtime')
    list_select_related = ('usuario',)
    actions = ['exportar_json']

    @admin.action(description="Exportar Selecionados em JSON (Recomendado)")
    def exportar_json(self, request, queryset):
        dados = []
        for obj in queryset:
            respostas_controle = list(
                RespostaAuditor.objects.filter(chave_unica=obj.chave_unica)
                .values('id', 'questao_id', 'resposta_marcada', 'tempo_resposta_segundos', 'respondido_em')
            )

            dados.append({
                'id': obj.id,
                'chave_unica': obj.chave_unica,
                'numero_mp': obj.numero_mp,
                'link_mp': obj.link_mp,
                'data_acesso': obj.data_acesso.isoformat() if obj.data_acesso else None,
                'ementa': obj.ementa,
                'emenda': obj.emenda,
                'status': obj.status,
                'status_display': obj.get_status_display(),
                'runtime': obj.runtime,
                'usuario': obj.usuario.username if obj.usuario else None,
                'resultado_ia': obj.resultado_json,
                'resposta_questionario_final': obj.resposta_questionario,
                'respostas_questoes_controle': respostas_controle
            })

        response = HttpResponse(
            json.dumps(dados, ensure_ascii=False, indent=2),
            content_type='application/json; charset=utf-8'
        )
        response['Content-Disposition'] = 'attachment; filename="export_analises_completas.json"'
        return response


@admin.register(LogExecucao)
class LogExecucaoAdmin(admin.ModelAdmin):
    list_display = ('id', 'procedimento', 'analise_emenda', 'modelo', 'tempo_total_segundos', 'tempo_bert_segundos', 'tempo_gemini_segundos', 'status', 'criado_em')
    list_filter = ('status', 'procedimento', 'modelo', 'criado_em')
    search_fields = ('procedimento', 'detalhes', 'modelo', 'analise_emenda__numero_mp')
    readonly_fields = ('criado_em', 'tempo_total_segundos', 'tempo_bert_segundos', 'tempo_gemini_segundos', 'modelo')