import os
import json
import time
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from django.utils import timezone

from core.models import ConfiguracaoAplicacao, AnaliseEmenda, LogExecucao

_BERT_CACHE = {
    "tokenizer": None,
    "model": None,
    "repo_id": None
}

_GEMINI_CLIENT_CACHE = {
    "client": None,
    "active_key": None
}

MAX_LEN = 512


def _carregar_bert(repo_id="freddutra/legal-bertimbau-detector-jabutis"):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    
    if _BERT_CACHE["model"] is None or _BERT_CACHE["repo_id"] != repo_id:
        config = ConfiguracaoAplicacao.objects.filter(ativo=True).first()
        hf_token = config.huggingface_api_key if config and config.huggingface_api_key else os.environ.get("HUGGINGFACE_TOKEN")
        
        kwargs = {"token": hf_token} if hf_token else {}
        
        tokenizer = AutoTokenizer.from_pretrained(repo_id, **kwargs)
        model = AutoModelForSequenceClassification.from_pretrained(repo_id, **kwargs)
        
        model.to(device)
        model.eval()
        
        _BERT_CACHE["tokenizer"] = tokenizer
        _BERT_CACHE["model"] = model
        _BERT_CACHE["repo_id"] = repo_id
        
    return _BERT_CACHE["tokenizer"], _BERT_CACHE["model"], device


def _obter_dados_banco_gemini():
    config = ConfiguracaoAplicacao.objects.filter(ativo=True).first()
    
    modelo_banco = "gemini-2.5-flash"
    chaves = []
    
    if config:
        if config.gemini_model_name:
            modelo_banco = config.gemini_model_name.strip()
            
        if config.llm_api_key_principal:
            chaves.append(config.llm_api_key_principal)
        if config.llm_api_key_reserva_1:
            chaves.append(config.llm_api_key_reserva_1)
        if config.llm_api_key_reserva_2:
            chaves.append(config.llm_api_key_reserva_2)
            
    if not chaves and os.environ.get("GEMINI_API_KEY"):
        chaves.append(os.environ.get("GEMINI_API_KEY"))
        
    if not chaves:
        raise ValueError("Nenhuma chave de API da LLM (Gemini) foi configurada na base de dados ou ambiente.")
        
    return modelo_banco, chaves


def _gerar_com_multichaves_gemini(prompt, system_instruction):
    modelo_prioritario, chaves = _obter_dados_banco_gemini()
    
    modelos_candidatos = [modelo_prioritario]
    for m in ["gemini-3.5-flash-lite", "gemini-2.5-flash", "gemini-1.5-flash", "gemini-1.5-pro"]:
        if m not in modelos_candidatos:
            modelos_candidatos.append(m)

    ultimo_erro = None

    for modelo_atual in modelos_candidatos:
        for idx_chave, chave in enumerate(chaves):
            os.environ["GEMINI_API_KEY"] = chave
            client = genai.Client()
            _GEMINI_CLIENT_CACHE["client"] = client
            _GEMINI_CLIENT_CACHE["active_key"] = chave

            for tentativa in range(1, 3):
                try:
                    response = client.models.generate_content(
                        model=modelo_atual,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            temperature=0.1,
                            response_mime_type="application/json",
                            response_schema=AnaliseAuditoriaSchema,
                        ),
                    )
                    return response, modelo_atual
                except Exception as e:
                    ultimo_erro = e
                    erro_str = str(e)
                    
                    if "402" in erro_str or "RESOURCE_EXHAUSTED" in erro_str:
                        break
                    elif "503" in erro_str or "UNAVAILABLE" in erro_str or "high demand" in erro_str:
                        if tentativa < 2:
                            time.sleep(2)
                    else:
                        break

    raise Exception(f"Todas as chaves e modelos de fallback do Gemini falharam. Último erro: {str(ultimo_erro)}")


class AnaliseAuditoriaSchema(BaseModel):
    resposta_parecer: str = Field(
        description="Texto fluido, humano e em tom jurídico-institucional explicando a coerência do diagnóstico emitido pelo modelo."
    )
    resposta_resumo: str = Field(
        description="Resumo de 2 a 3 frases destacando os pontos essenciais do texto que motivaram a classificação."
    )


def executar_pipeline_analise(analise_emenda_id: int):
    inicio_total = time.perf_counter()
    tempo_bert = 0.0
    tempo_gemini = 0.0
    instancia = None
    procedimento_nome = "pipeline_sincrono_bert_gemini"
    modelo_utilizado = "desconhecido"

    try:
        instancia = AnaliseEmenda.objects.get(pk=analise_emenda_id)
        instancia.status = 'processando'
        instancia.save(update_fields=['status'])

        inicio_bert = time.perf_counter()
        tokenizer, model, device = _carregar_bert()
        
        texto_justificativa = str(instancia.emenda or "")
        palavras = texto_justificativa.split()
        if len(palavras) > 350:
            texto_justificativa = " ".join(palavras[:250]) + " " + " ".join(palavras[-100:])

        inputs = tokenizer(
            texto_justificativa,
            truncation=True,
            max_length=MAX_LEN,
            padding="max_length",
            return_tensors="pt"
        )
        inputs = {k: v.to(device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = model(**inputs)
            probs = torch.softmax(outputs.logits, dim=1).squeeze().tolist()

        p_saudavel = round(float(probs[0]), 4)
        p_jabuti = round(float(probs[1]), 4)

        is_jabuti = p_jabuti >= 0.5
        confianca_valor = p_jabuti if is_jabuti else p_saudavel

        if confianca_valor >= 0.80:
            nivel_confianca = "Alta"
        elif confianca_valor >= 0.65:
            nivel_confianca = "Média"
        else:
            nivel_confianca = "Baixa"

        classificacao_str = "norma_jabuti" if is_jabuti else "norma_saudavel"

        diagnostico_bert = {
            "diagnostico_bert": {
                "classificacao": classificacao_str,
                "probabilidades": {
                    "saudavel": p_saudavel,
                    "jabuti": p_jabuti
                },
                "nivel_confianca": nivel_confianca
            }
        }
        tempo_bert = round(time.perf_counter() - inicio_bert, 4)

        inicio_gemini = time.perf_counter()

        system_instruction = (
            "Você é um consultor jurídico sênior especializado em técnica legislativa e controle de constitucionalidade formal. "
            "Sua tarefa é analisar exclusivamente a **pertinência temática** (o nexo de afinidade lógica e material) "
            "entre a proposição principal (ementa) e a emenda apresentada, explicando o diagnóstico de um modelo BERT.\n\n"
            "Diretrizes de redação fundamentais:\n"
            "1. **Foco Estrito em Pertinência Temática:** Concentre sua análise na conexão de assunto, matéria e objetivo institucional.\n"
            "2. **Tom Institucional:** Adote uma linguagem de parecer jurídico claro e fundamentado.\n"
            "3. **Assertividade e overclaims:** Evite garantias absolutas ou certezas. Evite expressões como 'clara ausência' ou semelhantes. O modelo sugere tendências, não certezas."
        )

        prompt = f"""
--- PROPOSIÇÃO LEGISLATIVA PRINCIPAL ---
EMENTA:
{instancia.ementa}

--- EMENDA EM ANÁLISE ---
TEXTO DA EMENDA:
{instancia.emenda}

--- RESULTADO DO MODELO DE AUDITORIA (BERT) ---
{json.dumps(diagnostico_bert, ensure_ascii=False, indent=2)}

--- INSTRUÇÃO DE ANÁLISE ---
Elabore os campos solicitados avaliando a pertinência temática entre a ementa e a emenda.
"""

        response, modelo_utilizado = _gerar_com_multichaves_gemini(prompt, system_instruction)

        dados_llm = json.loads(response.text)
        tempo_gemini = round(time.perf_counter() - inicio_gemini, 4)

        resultado_consolidado = {
            "norma_jabuti": p_jabuti,
            "norma_saudavel": p_saudavel,
            "classificacao_final": classificacao_str,
            "nivel_confianca": nivel_confianca,
            "resposta_parecer": dados_llm.get("resposta_parecer"),
            "resposta_resumo": dados_llm.get("resposta_resumo"),
            "diagnostico_bert_detalhado": diagnostico_bert
        }

        runtime_total = round(time.perf_counter() - inicio_total, 4)

        instancia.status = 'concluido'
        instancia.resultado_json = resultado_consolidado
        instancia.runtime = runtime_total
        instancia.data_acesso = timezone.now()
        instancia.save()

        LogExecucao.objects.create(
            procedimento=procedimento_nome,
            analise_emenda=instancia,
            tempo_total_segundos=runtime_total,
            tempo_bert_segundos=tempo_bert,
            tempo_gemini_segundos=tempo_gemini,
            status='sucesso',
            modelo=modelo_utilizado,
            detalhes="Pipeline síncrono executado com sucesso."
        )

        return True, f"Análise executada com sucesso via {modelo_utilizado} (Runtime: {runtime_total}s)."

    except Exception as e:
        runtime_total = round(time.perf_counter() - inicio_total, 4)
        erro_msg = str(e)

        if instancia:
            instancia.status = 'erro'
            instancia.resultado_json = {"erro": erro_msg}
            instancia.runtime = runtime_total
            instancia.save(update_fields=['status', 'resultado_json', 'runtime'])

        LogExecucao.objects.create(
            procedimento=procedimento_nome,
            analise_emenda=instancia,
            tempo_total_segundos=runtime_total,
            tempo_bert_segundos=tempo_bert,
            tempo_gemini_segundos=tempo_gemini,
            status='erro',
            modelo=modelo_utilizado,
            detalhes=erro_msg
        )

        return False, erro_msg