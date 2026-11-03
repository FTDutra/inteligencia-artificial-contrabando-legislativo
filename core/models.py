from django.db import models
from django.contrib.auth.models import User
from django.core.cache import cache


class ConfiguracaoSeguranca(models.Model):
    """Singleton para parâmetros de força bruta."""
    max_tentativas = models.IntegerField(default=5, verbose_name="Máximo de Tentativas")
    tempo_bloqueio_minutos = models.IntegerField(default=15, verbose_name="Tempo de Bloqueio (min)")

    class Meta:
        verbose_name = "Configuração de Segurança"
        verbose_name_plural = "Configurações de Segurança"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
        cache.delete('config_seguranca')

    @classmethod
    def get_solo(cls):
        config = cache.get('config_seguranca')
        if not config:
            config, _ = cls.objects.get_or_create(pk=1)
            cache.set('config_seguranca', config, 3600)
        return config

    def __str__(self):
        return f"Segurança: {self.max_tentativas} tentativas / {self.tempo_bloqueio_minutos} min"


class MenuCabecalho(models.Model):
    """Menus dinâmicos do topo (Quem somos, Metodologia, Denúncia, etc.)."""
    titulo = models.CharField(max_length=100, verbose_name="Título do Menu")
    slug = models.SlugField(max_length=100, unique=True, verbose_name="Identificador (Slug)", help_text="Ex: quem-somos, metodologia, denuncia")
    conteudo = models.TextField(verbose_name="Conteúdo (Markdown)", blank=True, null=True)
    ordem = models.PositiveIntegerField(default=0, verbose_name="Ordem de Exibição")
    ativo = models.BooleanField(default=True, verbose_name="Ativo no Cabeçalho")

    class Meta:
        verbose_name = "Menu de Cabeçalho"
        verbose_name_plural = "Menus de Cabeçalho"
        ordering = ['ordem', 'id']

    def __str__(self):
        return f"{self.ordem} - {self.titulo}"


class ApresentacaoPlataforma(models.Model):
    """Singleton institucional em Markdown."""
    titulo = models.CharField(max_length=200, default="Apresentação", verbose_name="Título")
    conteudo = models.TextField(blank=True, null=True, verbose_name="Conteúdo Markdown")
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Apresentação da Plataforma"
        verbose_name_plural = "Apresentação da Plataforma"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)


class PerguntaPlataforma(models.Model):
    """Perguntas dinâmicas ordenadas por etapas numéricas customizáveis."""
    TIPO_CHOICES = [
        ('LIKERT_5', 'Escala Likert (1-5)'),
        ('SIM_NAO', 'Sim / Não'),
        ('TEXTO', 'Texto Livre'),
    ]

    enunciado = models.TextField(verbose_name="Enunciado")
    descricao = models.TextField(blank=True, null=True, verbose_name="Descrição (Markdown)")
    etapa_numero = models.PositiveIntegerField(default=1, verbose_name="Número da Etapa", help_text="Ex: 1 para Prelúdio/Início, 2 para Intróito, etc.")
    etapa_nome = models.CharField(max_length=100, blank=True, null=True, verbose_name="Nome da Etapa", help_text="Ex: Prelúdio, Intróito, Epílogo")
    tipo_resposta = models.CharField(max_length=20, choices=TIPO_CHOICES, verbose_name="Tipo de Resposta")
    agrupamento = models.CharField(max_length=100, blank=True, null=True, verbose_name="Agrupamento")
    ordem = models.PositiveIntegerField(default=0, verbose_name="Ordem dentro da Etapa")
    ativo = models.BooleanField(default=True, verbose_name="Ativo")

    class Meta:
        verbose_name = "Pergunta da Plataforma"
        verbose_name_plural = "Perguntas da Plataforma"
        ordering = ['etapa_numero', 'ordem', 'id']

    def __str__(self):
        nome_etapa = f" (Etapa {self.etapa_numero}: {self.etapa_nome})" if self.etapa_nome else f" (Etapa {self.etapa_numero})"
        return f"{nome_etapa} - {self.enunciado[:40]}"


class QuestaoControle(models.Model):
    """Repositório de MPs e Emendas para auditoria."""
    TAMANHO_CHOICES = [('P', 'Pequeno'), ('M', 'Médio'), ('G', 'Grande')]

    mp_numero = models.CharField(max_length=50, verbose_name="Número da MP")
    ano_mp = models.IntegerField(blank=True, null=True, verbose_name="Ano da MP")
    link_mp = models.URLField(max_length=500, blank=True, null=True, verbose_name="Link MP")
    numero_emenda = models.CharField(max_length=50, blank=True, null=True, verbose_name="Número Emenda")
    link_emenda = models.URLField(max_length=500, blank=True, null=True, verbose_name="Link Emenda")

    mp_ementa = models.TextField(verbose_name="Ementa da MP")
    mp_corpo = models.TextField(verbose_name="Corpo da MP")
    mp_motivacao = models.TextField(blank=True, null=True, verbose_name="Motivação")
    classificacao = models.CharField(max_length=100, verbose_name="Classificação")

    tamanho_char = models.IntegerField(blank=True, null=True, verbose_name="Tamanho (Chars)")
    tamanho_rotulo = models.CharField(max_length=1, choices=TAMANHO_CHOICES, blank=True, null=True, verbose_name="Rótulo")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Questão Controle"
        verbose_name_plural = "Questões Controle"
        ordering = ['id']

    def __str__(self):
        return f"MP {self.mp_numero} - {self.classificacao}"


class ConfiguracaoAplicacao(models.Model):
    """Parâmetros de exibição, seleção de questões e credenciais de IA com rotação."""
    SELECAO_CHOICES = [('ALEATORIO', 'Aleatório'), ('FIXO', 'Fixo (Sequencial)')]
    ORDEM_CHOICES = [
        ('ALEATORIO', 'Aleatória'),
        ('TAMANHO_ASC', 'Pequeno -> Médio -> Grande'),
        ('TAMANHO_DESC', 'Grande -> Médio -> Pequeno'),
    ]

    # Parâmetros de execução
    numero_questoes = models.PositiveIntegerField(default=10, verbose_name="Qtd. Questões por Sessão")
    modo_selecao = models.CharField(max_length=20, choices=SELECAO_CHOICES, default='ALEATORIO')
    ordem_apresentacao = models.CharField(max_length=20, choices=ORDEM_CHOICES, default='ALEATORIO')
    ativo = models.BooleanField(default=True)

    # Hugging Face
    huggingface_api_key = models.CharField(
        max_length=255, blank=True, null=True, verbose_name="Chave API Hugging Face"
    )

    # Chaves LLM (Principal + Rotação)
    llm_api_key_principal = models.CharField(
        max_length=255, blank=True, null=True, verbose_name="Chave API LLM (Principal)"
    )
    llm_api_key_reserva_1 = models.CharField(
        max_length=255, blank=True, null=True, verbose_name="Chave API LLM (Reserva 1 / Rotação)"
    )
    llm_api_key_reserva_2 = models.CharField(
        max_length=255, blank=True, null=True, verbose_name="Chave API LLM (Reserva 2 / Rotação)"
    )

    # Configuração do Modelo
    gemini_model_name = models.CharField(
        max_length=100, 
        default="gemini-2.5-flash", 
        verbose_name="Modelo Gemini",
        help_text="Ex: gemini-2.5-flash, gemini-2.5-pro, etc."
    )

    class Meta:
        verbose_name = "Configuração da Aplicação"
        verbose_name_plural = "Configurações da Aplicação"

    def get_llm_keys(self):
        """Retorna a lista com todas as chaves LLM cadastradas e não vazias para rotação."""
        keys = [self.llm_api_key_principal, self.llm_api_key_reserva_1, self.llm_api_key_reserva_2]
        return [k for k in keys if k]

    def __str__(self):
        return f"Configuração da Aplicação (Ativa: {self.ativo})"

class AnaliseEmenda(models.Model):
    """Armazena as emendas e o resultado das análises automatizadas."""
    STATUS_CHOICES = [
        ('aguardando', 'Aguardando'),
        ('processando', 'Processando'),
        ('concluido', 'Concluído'),
        ('erro', 'Erro'),
    ]

    # Chave única gerada no início do fluxo para unificar todas as etapas
    chave_unica = models.CharField(max_length=150, unique=True, verbose_name="Chave Única de Sessão")
    
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="analises_realizadas", verbose_name="Auditor Responsável")
    
    link_mp = models.URLField(max_length=500, blank=True, null=True, verbose_name="Link da Medida Provisória")
    numero_mp = models.CharField(max_length=100, verbose_name="Número da Medida Provisória")
    data_acesso = models.DateTimeField(verbose_name="Data de Acesso")
    ementa = models.TextField(verbose_name="Ementa")
    emenda = models.TextField(verbose_name="Texto da Emenda (TXT)")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='aguardando', verbose_name="Status da Análise")
    resultado_json = models.JSONField(blank=True, null=True, verbose_name="Resultado (JSON)")
    
    runtime = models.FloatField(default=0.0, verbose_name="Tempo de Execução (s)")
    resposta_questionario = models.JSONField(blank=True, null=True, verbose_name="Resultado questionario (JSON)")

    class Meta:
        verbose_name = "Análise de Emenda"
        verbose_name_plural = "Análises de Emendas"
        ordering = ['-data_acesso']

    def __str__(self):
        return f"MP {self.numero_mp} [{self.get_status_display()}] - ({self.chave_unica})"


class RespostaAuditor(models.Model):
    """Respostas dos usuários vinculadas às questões de controle e à chave única da sessão."""
    chave_unica = models.CharField(max_length=150, verbose_name="Chave Única de Sessão")
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name="respostas_controle")
    questao = models.ForeignKey(QuestaoControle, on_delete=models.CASCADE, related_name="respostas")
    resposta_marcada = models.TextField(verbose_name="Resposta")
    tempo_resposta_segundos = models.FloatField(blank=True, null=True, verbose_name="Tempo (s)")
    respondido_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Resposta de Questão de Controle"
        verbose_name_plural = "Respostas das Questões de Controle"


class LogExecucao(models.Model):
    """Armazena métricas de tempo e status detalhados de cada procedimento executado."""
    STATUS_CHOICES = [
        ('sucesso', 'Sucesso'),
        ('erro', 'Erro'),
    ]

    procedimento = models.CharField(max_length=150, verbose_name="Procedimento Executado")
    analise_emenda = models.ForeignKey(
        'AnaliseEmenda', 
        on_delete=models.SET_NULL, 
        blank=True, 
        null=True, 
        related_name="logs_execucao",
        verbose_name="Análise de Emenda Referenciada"
    )
    tempo_total_segundos = models.FloatField(verbose_name="Tempo Total (s)")
    tempo_bert_segundos = models.FloatField(default=0.0, verbose_name="Tempo BERT (s)")
    tempo_gemini_segundos = models.FloatField(default=0.0, verbose_name="Tempo Gemini (s)")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='sucesso', verbose_name="Status")
    detalhes = models.TextField(blank=True, null=True, verbose_name="Detalhes / Erro")
    modelo = models.TextField(blank=True, null=True, verbose_name="Modelo utilizado")
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name="Data/Hora da Execução")

    class Meta:
        verbose_name = "Log de Execução"
        verbose_name_plural = "Logs de Execução"
        ordering = ['-criado_em']