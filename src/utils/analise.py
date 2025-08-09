"""
Módulo de Análise Tarifária - Sistema SEGER

Este módulo implementa uma análise tarifária completa e clara, substituindo
a função confusa analisar_eficiencia_energetica. 

Funcionalidades:
1. Detecção automática da modalidade tarifária atual
2. Otimização para todas as modalidades disponíveis  
3. Relatório estruturado com economia esperada
4. Comparação clara entre modalidades

Autor: Sistema SEGER - Análise Tarifária
Data: 2025-07-29
"""

from typing import List, Dict, Any, Optional, Tuple
import logging
from dataclasses import dataclass
from enum import Enum
from flask import current_app

from .tarifas import (
    calcular_tarifa_verde, 
    calcular_tarifa_azul,
    calcular_tarifa_bt
)
from ..optmization import opt_tarifa_verde, opt_tarifa_azul


def _log_info(message: str):
    """Helper para logs que funciona dentro e fora do contexto Flask"""
    try:
        current_app.logger.info(message)
    except RuntimeError:
        # Fora do contexto Flask, usa logging padrão
        logging.info(message)


def _log_error(message: str):
    """Helper para logs de erro que funciona dentro e fora do contexto Flask"""
    try:
        current_app.logger.error(message)
    except RuntimeError:
        # Fora do contexto Flask, usa logging padrão
        logging.error(message)


class ModalidadeTarifaria(Enum):
    """Enum para modalidades tarifárias brasileiras"""
    VERDE = "verde"
    AZUL = "azul"  
    CONVENCIONAL = "convencional"
    BRANCA = "branca"
    DESCONHECIDA = "desconhecida"


@dataclass
class ResultadoOtimizacao:
    """Classe para resultados de otimização por modalidade"""
    modalidade: ModalidadeTarifaria
    custo_atual: float
    custo_otimizado: float
    economia_anual: float
    economia_percentual: float
    demanda_otima: Dict[str, float]  # Ex: {"fora_ponta": 150, "ponta": 80}
    viavel: bool
    observacoes: List[str]


@dataclass
class AnaliseCompleta:
    """Resultado completo da análise tarifária"""
    modalidade_atual: ModalidadeTarifaria
    parametros_atuais: Dict[str, Any]
    resultados_otimizacao: List[ResultadoOtimizacao]
    melhor_opcao: ResultadoOtimizacao
    economia_maxima: float
    recomendacoes: List[str]
    dados_mensais: List[Dict[str, Any]]
    resumo_executivo: Dict[str, Any]


class AnalisadorTarifario:
    """
    Classe principal para análise tarifária completa
    """
    
    def __init__(self, fatura_dados: List[Dict[str, Any]], 
                 tarifas_disponiveis: Dict[str, Any],
                 tarifa_ere: float = 0.05,
                 pis: Optional[float] = None,
                 cofins: Optional[float] = None, 
                 icms: Optional[float] = None):
        """
        Inicializa o analisador tarifário
        
        Args:
            fatura_dados: Lista de dados extraídos das faturas
            tarifas_disponiveis: Dict com todas as modalidades tarifárias disponíveis
            tarifa_ere: Tarifa de Energia Reativa Excedente
            pis, cofins, icms: Alíquotas de impostos customizadas
        """
        self.fatura_dados = fatura_dados
        self.tarifas = tarifas_disponiveis
        self.tarifa_ere = tarifa_ere
        self.pis = pis
        self.cofins = cofins 
        self.icms = icms
        
        # Dados calculados
        self.modalidade_atual = None
        self.parametros_atuais = {}
        self.consumo_total = self._calcular_consumo_total()
        self.demanda_maxima = self._calcular_demanda_maxima()
        
        _log_info(f"Analisador inicializado - {len(fatura_dados)} faturas, consumo total: {self.consumo_total['total']:.2f} kWh")
    
    def _calcular_consumo_total(self) -> Dict[str, float]:
        """Calcula consumo total por período"""
        total = {"ponta": 0.0, "fora_ponta": 0.0, "total": 0.0}
        
        for fatura in self.fatura_dados:
            consumo = fatura.get("consumo_ativo", {})
            total["ponta"] += consumo.get("ponta_kwh", 0.0)
            total["fora_ponta"] += consumo.get("fora_ponta_kwh", 0.0)
            total["total"] += consumo.get("total_kwh", 0.0)
            
        return total
    
    def _calcular_demanda_maxima(self) -> Dict[str, float]:
        """Calcula demanda máxima registrada por período"""
        maxima = {"ponta": 0.0, "fora_ponta": 0.0}
        
        for fatura in self.fatura_dados:
            demanda = fatura.get("demanda", {})
            demandas_max = demanda.get("maxima", [])
            
            for d in demandas_max:
                periodo = d.get("periodo", "")
                valor = d.get("valor_kw", 0.0)
                
                if periodo == "ponta":
                    maxima["ponta"] = max(maxima["ponta"], valor)
                elif periodo == "fora_ponta":
                    maxima["fora_ponta"] = max(maxima["fora_ponta"], valor)
                    
        return maxima
    
    def detectar_modalidade_atual(self) -> ModalidadeTarifaria:
        """
        Detecta automaticamente a modalidade tarifária atual
        baseada nos dados das faturas (modalidade extraída + estrutura de demanda)
        """
        _log_info("Detectando modalidade tarifária atual...")
        
        # Analisa primeira fatura para detectar modalidade
        if not self.fatura_dados:
            return ModalidadeTarifaria.DESCONHECIDA
            
        primeira_fatura = self.fatura_dados[0]
        identificacao = primeira_fatura.get("identificacao", {})
        demanda = primeira_fatura.get("demanda", {})
        
        # 1. Verifica modalidade extraída diretamente da fatura
        modalidade_extraida = identificacao.get("modalidade", "").lower()
        if modalidade_extraida:
            _log_info(f"Modalidade extraída da fatura: {modalidade_extraida}")
            
            if modalidade_extraida == "azul":
                # Para azul, deve ter demandas separadas
                demanda_fp = demanda.get("contratada_fp_kw", 0.0)
                demanda_p = demanda.get("contratada_p_kw", 0.0)
                
                if demanda_fp > 0 and demanda_p > 0:
                    self.parametros_atuais = {
                        "demanda_ponta": demanda_p,
                        "demanda_fora_ponta": demanda_fp
                    }
                    return ModalidadeTarifaria.AZUL
                else:
                    _log_info("Modalidade Azul indicada mas sem demandas P/FP - usando estrutura para detectar")
                    
            elif modalidade_extraida == "verde":
                # Para verde, pode ter demanda única ou FP
                demanda_fp = demanda.get("contratada_fp_kw", 0.0)
                demanda_geral = demanda.get("contratada_kw", 0.0)
                
                demanda_contratada = demanda_fp if demanda_fp > 0 else demanda_geral
                if demanda_contratada > 0:
                    self.parametros_atuais = {
                        "demanda_contratada": demanda_contratada
                    }
                    return ModalidadeTarifaria.VERDE
                    
            elif modalidade_extraida in ["convencional", "branca"]:
                return ModalidadeTarifaria.CONVENCIONAL
        
        # 2. Se não detectou pela modalidade extraída, usa estrutura de demanda
        _log_info("Detectando modalidade pela estrutura de demanda contratada...")
        
        demanda_fp = demanda.get("contratada_fp_kw", 0.0)
        demanda_p = demanda.get("contratada_p_kw", 0.0)
        demanda_geral = demanda.get("contratada_kw", 0.0)
        
        # Se não há nenhuma demanda contratada = BT (Convencional)
        if demanda_fp <= 0 and demanda_p <= 0 and demanda_geral <= 0:
            return ModalidadeTarifaria.CONVENCIONAL
            
        # Se há demanda separada ponta/fora ponta = Azul
        if demanda_fp > 0 and demanda_p > 0:
            self.parametros_atuais = {
                "demanda_ponta": demanda_p,
                "demanda_fora_ponta": demanda_fp
            }
            _log_info(f"Modalidade Azul detectada - Ponta: {demanda_p}kW, FP: {demanda_fp}kW")
            return ModalidadeTarifaria.AZUL
            
        # Se há apenas demanda fora ponta ou geral = Verde
        elif demanda_fp > 0 or demanda_geral > 0:
            demanda_contratada = demanda_fp if demanda_fp > 0 else demanda_geral
            self.parametros_atuais = {
                "demanda_contratada": demanda_contratada
            }
            _log_info(f"Modalidade Verde detectada - Demanda: {demanda_contratada}kW")
            return ModalidadeTarifaria.VERDE
            
        _log_info("Não foi possível detectar modalidade - marcando como desconhecida")
        return ModalidadeTarifaria.DESCONHECIDA
    
    def otimizar_modalidade_verde(self) -> ResultadoOtimizacao:
        """Otimiza para modalidade Verde"""
        _log_info("Otimizando modalidade Verde...")
        
        if "verde" not in self.tarifas:
            return ResultadoOtimizacao(
                modalidade=ModalidadeTarifaria.VERDE,
                custo_atual=0.0,
                custo_otimizado=0.0,
                economia_anual=0.0,
                economia_percentual=0.0,
                demanda_otima={},
                viavel=False,
                observacoes=["Tarifas Verde não disponíveis"]
            )
        
        try:
            # Calcula custo atual usando demanda detectada
            demanda_atual = self.parametros_atuais.get("demanda_contratada", 
                          self.parametros_atuais.get("demanda_fora_ponta", 100.0))
            custo_atual, _ = calcular_tarifa_verde(
                self.fatura_dados, 
                self.tarifas["verde"], 
                self.tarifa_ere, 
                demanda_atual,
                self.pis, self.cofins, self.icms
            )
            
            # Otimização
            resultado_opt = opt_tarifa_verde(
                self.fatura_dados,
                self.tarifas["verde"],
                self.tarifa_ere,
                30,  # down_bound
                1000,  # up_bound  
                self.pis, self.cofins, self.icms
            )
            
            demanda_otima = resultado_opt["demanda_otima"]
            custo_otimizado = resultado_opt["custo_otimo"]
            economia = custo_atual - custo_otimizado
            economia_pct = (economia / custo_atual) * 100 if custo_atual > 0 else 0.0
            
            observacoes = []
            if demanda_otima < demanda_atual:
                observacoes.append(f"Redução de demanda de {demanda_atual:.0f} para {demanda_otima:.0f} kW")
            elif demanda_otima > demanda_atual:
                observacoes.append(f"Aumento de demanda de {demanda_atual:.0f} para {demanda_otima:.0f} kW")
            
            return ResultadoOtimizacao(
                modalidade=ModalidadeTarifaria.VERDE,
                custo_atual=custo_atual,
                custo_otimizado=custo_otimizado,
                economia_anual=economia,
                economia_percentual=economia_pct,
                demanda_otima={"contratada": demanda_otima},
                viavel=economia > 0,
                observacoes=observacoes
            )
            
        except Exception as e:
            _log_error(f"Erro na otimização Verde: {e}")
            return ResultadoOtimizacao(
                modalidade=ModalidadeTarifaria.VERDE,
                custo_atual=0.0,
                custo_otimizado=0.0,
                economia_anual=0.0,
                economia_percentual=0.0,
                demanda_otima={},
                viavel=False,
                observacoes=[f"Erro no cálculo: {str(e)}"]
            )
    
    def otimizar_modalidade_azul(self) -> ResultadoOtimizacao:
        """Otimiza para modalidade Azul"""
        _log_info("Otimizando modalidade Azul...")
        
        if "azul" not in self.tarifas:
            return ResultadoOtimizacao(
                modalidade=ModalidadeTarifaria.AZUL,
                custo_atual=0.0,
                custo_otimizado=0.0,
                economia_anual=0.0,
                economia_percentual=0.0,
                demanda_otima={},
                viavel=False,
                observacoes=["Tarifas Azul não disponíveis"]
            )
        
        try:
            # Calcula custo atual usando demandas detectadas
            demanda_p_atual = self.parametros_atuais.get("demanda_ponta", 
                            self.parametros_atuais.get("demanda_contratada", 100.0))
            demanda_fp_atual = self.parametros_atuais.get("demanda_fora_ponta",
                             self.parametros_atuais.get("demanda_contratada", 100.0))
            
            custo_atual, _ = calcular_tarifa_azul(
                self.fatura_dados,
                self.tarifas["azul"],
                self.tarifa_ere,
                [demanda_fp_atual, demanda_p_atual],
                self.pis, self.cofins, self.icms
            )
            
            # Otimização
            resultado_opt = opt_tarifa_azul(
                self.fatura_dados,
                self.tarifas["azul"],
                self.tarifa_ere,
                1000  # up_bound
            )
            
            demanda_p_otima = resultado_opt["demanda_p_otima"]
            demanda_fp_otima = resultado_opt["demanda_fp_otima"]
            custo_otimizado = resultado_opt["custo_otimo"]
            economia = custo_atual - custo_otimizado
            economia_pct = (economia / custo_atual) * 100 if custo_atual > 0 else 0.0
            
            observacoes = []
            if demanda_p_otima != demanda_p_atual:
                observacoes.append(f"Demanda ponta: {demanda_p_atual:.0f} → {demanda_p_otima:.0f} kW")
            if demanda_fp_otima != demanda_fp_atual:
                observacoes.append(f"Demanda fora ponta: {demanda_fp_atual:.0f} → {demanda_fp_otima:.0f} kW")
            
            return ResultadoOtimizacao(
                modalidade=ModalidadeTarifaria.AZUL,
                custo_atual=custo_atual,
                custo_otimizado=custo_otimizado,
                economia_anual=economia,
                economia_percentual=economia_pct,
                demanda_otima={
                    "ponta": demanda_p_otima,
                    "fora_ponta": demanda_fp_otima
                },
                viavel=economia > 0,
                observacoes=observacoes
            )
            
        except Exception as e:
            _log_error(f"Erro na otimização Azul: {e}")
            return ResultadoOtimizacao(
                modalidade=ModalidadeTarifaria.AZUL,
                custo_atual=0.0,
                custo_otimizado=0.0,
                economia_anual=0.0,
                economia_percentual=0.0,
                demanda_otima={},
                viavel=False,
                observacoes=[f"Erro no cálculo: {str(e)}"]
            )
    
    def analisar_completo(self) -> AnaliseCompleta:
        """
        Executa análise tarifária completa
        
        Returns:
            AnaliseCompleta: Objeto com todos os resultados da análise
        """
        _log_info("Iniciando análise tarifária completa...")
        
        # Detecta modalidade atual
        self.modalidade_atual = self.detectar_modalidade_atual()
        
        # Executa otimizações para todas modalidades
        resultados = []
        
        # Verde
        resultado_verde = self.otimizar_modalidade_verde()
        resultados.append(resultado_verde)
        
        # Azul
        resultado_azul = self.otimizar_modalidade_azul()
        resultados.append(resultado_azul)
        
        # Encontra melhor opção baseada no menor custo global
        resultados_viaveis = [r for r in resultados if r.viavel]
        if resultados_viaveis:
            # Seleciona a opção com o menor custo otimizado (menor custo global)
            melhor_opcao = min(resultados_viaveis, key=lambda x: x.custo_otimizado)
            
            # Calcula economia real comparando com o custo atual da modalidade atual
            custo_atual_real = next((r.custo_atual for r in resultados if r.modalidade == self.modalidade_atual), 0.0)
            economia_maxima = max(0.0, custo_atual_real - melhor_opcao.custo_otimizado)
        else:
            # Se nenhuma opção é viável, usa a atual
            atual = next((r for r in resultados if r.modalidade == self.modalidade_atual), resultados[0])
            melhor_opcao = atual
            economia_maxima = 0.0
        
        # Gera recomendações
        recomendacoes = self._gerar_recomendacoes(resultados, melhor_opcao)
        
        # Resumo executivo
        resumo = self._gerar_resumo_executivo(resultados, melhor_opcao)
        
        _log_info(f"Análise concluída - Modalidade atual: {self.modalidade_atual.value}, "
                  f"Melhor opção: {melhor_opcao.modalidade.value}, "
                  f"Economia: R$ {economia_maxima:.2f}")
        
        return AnaliseCompleta(
            modalidade_atual=self.modalidade_atual,
            parametros_atuais=self.parametros_atuais,
            resultados_otimizacao=resultados,
            melhor_opcao=melhor_opcao,
            economia_maxima=economia_maxima,
            recomendacoes=recomendacoes,
            dados_mensais=self._extrair_dados_mensais(),
            resumo_executivo=resumo
        )
    
    def _gerar_recomendacoes(self, resultados: List[ResultadoOtimizacao], 
                           melhor_opcao: ResultadoOtimizacao) -> List[str]:
        """Gera recomendações baseadas nos resultados"""
        recomendacoes = []
        
        # Calcula economia real comparando com o custo atual da modalidade atual
        custo_atual_real = next((r.custo_atual for r in resultados if r.modalidade == self.modalidade_atual), 0.0)
        economia_real = max(0.0, custo_atual_real - melhor_opcao.custo_otimizado)
        economia_percentual_real = (economia_real / custo_atual_real) * 100 if custo_atual_real > 0 else 0.0
        
        if melhor_opcao.modalidade == self.modalidade_atual:
            if economia_real > 0:
                recomendacoes.append(f"Manter modalidade {melhor_opcao.modalidade.value.title()} "
                                   f"mas ajustar demanda contratada para economia de "
                                   f"R$ {economia_real:.2f} anuais")
            else:
                recomendacoes.append(f"Modalidade atual ({self.modalidade_atual.value.title()}) "
                                   f"já está otimizada")
        else:
            if economia_real > 0:
                recomendacoes.append(f"Migrar para modalidade {melhor_opcao.modalidade.value.title()} "
                                   f"para economia de R$ {economia_real:.2f} anuais "
                                   f"({economia_percentual_real:.1f}%)")
            else:
                recomendacoes.append(f"Modalidade {melhor_opcao.modalidade.value.title()} tem menor custo "
                                   f"mas sem economia significativa em relação à atual")
        
        # Verifica padrão de consumo
        if self.consumo_total["ponta"] > 0:
            percentual_ponta = (self.consumo_total["ponta"] / self.consumo_total["total"]) * 100
            if percentual_ponta > 20:
                recomendacoes.append(f"Alto consumo na ponta ({percentual_ponta:.1f}%) - "
                                   f"considere ações de gestão de demanda")
        
        return recomendacoes
    
    def _gerar_resumo_executivo(self, resultados: List[ResultadoOtimizacao], 
                              melhor_opcao: ResultadoOtimizacao) -> Dict[str, Any]:
        """Gera resumo executivo da análise"""
        # Calcula economia real comparando com o custo atual da modalidade atual
        custo_atual_real = next((r.custo_atual for r in resultados if r.modalidade == self.modalidade_atual), 0.0)
        economia_real = max(0.0, custo_atual_real - melhor_opcao.custo_otimizado)
        economia_percentual_real = (economia_real / custo_atual_real) * 100 if custo_atual_real > 0 else 0.0
        
        return {
            "modalidade_atual": self.modalidade_atual.value,
            "modalidade_recomendada": melhor_opcao.modalidade.value,
            "mudanca_necessaria": melhor_opcao.modalidade != self.modalidade_atual,
            "economia_anual_maxima": economia_real,
            "economia_percentual_maxima": economia_percentual_real,
            "payback_meses": self._calcular_payback_com_economia_real(melhor_opcao, economia_real),
            "consumo_total_kwh": self.consumo_total["total"],
            "demanda_maxima_kw": max(self.demanda_maxima.values()),
            "periodo_analisado": f"{len(self.fatura_dados)} meses",
            "viabilidade": "Alta" if economia_percentual_real > 10 else 
                          "Média" if economia_percentual_real > 5 else "Baixa"
        }
    
    def _calcular_payback(self, resultado: ResultadoOtimizacao) -> float:
        """Calcula payback em meses (estimativa)"""
        # Estimativa de custos de mudança (análise técnica, adequações)
        custo_mudanca = 5000.0  # R$ 5.000 estimado
        
        if resultado.economia_anual <= 0:
            return float('inf')
            
        return (custo_mudanca / resultado.economia_anual) * 12
    
    def _calcular_payback_com_economia_real(self, resultado: ResultadoOtimizacao, economia_real: float) -> float:
        """Calcula payback em meses usando economia real"""
        # Estimativa de custos de mudança (análise técnica, adequações)
        custo_mudanca = 5000.0  # R$ 5.000 estimado
        
        if economia_real <= 0:
            return float('inf')
            
        return (custo_mudanca / economia_real) * 12
    
    def _extrair_dados_mensais(self) -> List[Dict[str, Any]]:
        """Extrai dados mensais calculando valores usando funções de cálculo tarifário"""
        dados_mensais = []
        
        _log_info(f"Calculando valores mensais para modalidade: {self.modalidade_atual.value}")
        
        # Para cada mês, calcula o valor usando a tarifa atual
        for fatura in self.fatura_dados:
            identificacao = fatura.get("identificacao", {})
            consumo = fatura.get("consumo_ativo", {})
            demanda = fatura.get("demanda", {})
            
            mes_ref = identificacao.get("mes_referencia", "N/A")
            valor_calculado = 0.0
            
            # Calcula valor para este mês específico usando modalidade atual
            try:
                if self.modalidade_atual == ModalidadeTarifaria.VERDE and "verde" in self.tarifas:
                    demanda_atual = self.parametros_atuais.get("demanda_contratada", 
                                  self.parametros_atuais.get("demanda_fora_ponta", 100.0))
                    
                    # Calcula apenas para esta fatura específica
                    custo_total, detalhes = calcular_tarifa_verde(
                        [fatura],  # Apenas esta fatura
                        self.tarifas["verde"], 
                        self.tarifa_ere, 
                        demanda_atual,
                        self.pis, self.cofins, self.icms
                    )
                    
                    # Se retornou detalhes mensais, pega o valor desta fatura
                    if detalhes and len(detalhes) > 0:
                        valor_calculado = detalhes[0].get("valor_fatura", custo_total / 12)
                    else:
                        valor_calculado = custo_total / len(self.fatura_dados)
                        
                elif self.modalidade_atual == ModalidadeTarifaria.AZUL and "azul" in self.tarifas:
                    demanda_p_atual = self.parametros_atuais.get("demanda_ponta", 100.0)
                    demanda_fp_atual = self.parametros_atuais.get("demanda_fora_ponta", 100.0)
                    
                    # Calcula apenas para esta fatura específica
                    custo_total, detalhes = calcular_tarifa_azul(
                        [fatura],  # Apenas esta fatura
                        self.tarifas["azul"],
                        self.tarifa_ere,
                        [demanda_fp_atual, demanda_p_atual],
                        self.pis, self.cofins, self.icms
                    )
                    
                    # Se retornou detalhes mensais, pega o valor desta fatura
                    if detalhes and len(detalhes) > 0:
                        valor_calculado = detalhes[0].get("valor_fatura", custo_total / 12)
                    else:
                        valor_calculado = custo_total / len(self.fatura_dados)
                        
                else:
                    # Se modalidade desconhecida ou tarifas não disponíveis, tenta estimar
                    _log_info(f"Modalidade {self.modalidade_atual.value} - usando estimativa básica")
                    # Estimativa simples baseada no consumo (valor placeholder)
                    consumo_total = consumo.get("total_kwh", 0.0)
                    if consumo_total > 0:
                        valor_calculado = consumo_total * 0.5  # Tarifa estimada de R$ 0,50/kWh
                    
            except Exception as e:
                _log_error(f"Erro no cálculo mensal para {mes_ref}: {e}")
                valor_calculado = 0.0
            
            dados_mensais.append({
                "mes_referencia": mes_ref,
                "consumo_ponta_kwh": consumo.get("ponta_kwh", 0.0),
                "consumo_fora_ponta_kwh": consumo.get("fora_ponta_kwh", 0.0),
                "consumo_total_kwh": consumo.get("total_kwh", 0.0),
                "demanda_maxima_kw": max([d.get("valor_kw", 0.0) for d in demanda.get("maxima", [])]) if demanda.get("maxima") else 0.0,
                "valor_fatura": round(valor_calculado, 2)
            })
            
            _log_info(f"Mês {mes_ref}: R$ {valor_calculado:.2f}")
        
        # Ordena cronologicamente por mês/ano
        def _parse_mes_ref(mes_ref: str) -> tuple:
            """Converte 'MM/YYYY' para tuple (ano, mês) para ordenação"""
            try:
                if "/" in mes_ref:
                    mes, ano = mes_ref.split("/")
                    return (int(ano), int(mes))
                else:
                    return (9999, 99)  # Coloca datas inválidas no final
            except:
                return (9999, 99)
        
        dados_mensais.sort(key=lambda x: _parse_mes_ref(x["mes_referencia"]))
        _log_info(f"Dados mensais ordenados cronologicamente - {len(dados_mensais)} meses")
            
        return dados_mensais


def analisar_tarifas_completo(fatura_dados: List[Dict[str, Any]], 
                            tarifas_disponiveis: Dict[str, Any],
                            tarifa_ere: float = 0.05,
                            pis: Optional[float] = None,
                            cofins: Optional[float] = None,
                            icms: Optional[float] = None) -> Dict[str, Any]:
    """
    Função principal para análise tarifária completa
    
    Args:
        fatura_dados: Lista de dados das faturas
        tarifas_disponiveis: Dicionário com tarifas por modalidade (já convertidas para kWh)
        tarifa_ere: Tarifa de energia reativa excedente
        pis, cofins, icms: Alíquotas de impostos customizadas
        
    Returns:
        Dict com resultado completo da análise
    """
    analisador = AnalisadorTarifario(
        fatura_dados=fatura_dados,
        tarifas_disponiveis=tarifas_disponiveis,
        tarifa_ere=tarifa_ere,
        pis=pis,
        cofins=cofins,
        icms=icms
    )
    
    resultado = analisador.analisar_completo()
    
    # Converte para dict para serialização JSON, garantindo compatibilidade
    def to_json_safe(obj):
        """Converte valores para serem JSON-serializáveis"""
        if isinstance(obj, bool):
            return obj  # bool é JSON-serializável
        elif hasattr(obj, 'value'):  # Enum
            return obj.value
        return obj
    
    return {
        "modalidade_atual": resultado.modalidade_atual.value,
        "parametros_atuais": resultado.parametros_atuais,
        "resultados_otimizacao": [
            {
                "modalidade": r.modalidade.value,
                "custo_atual": float(r.custo_atual),
                "custo_otimizado": float(r.custo_otimizado),
                "economia_anual": float(r.economia_anual),
                "economia_percentual": float(r.economia_percentual),
                "demanda_otima": r.demanda_otima,
                "viavel": bool(r.viavel),
                "observacoes": r.observacoes
            }
            for r in resultado.resultados_otimizacao
        ],
        "melhor_opcao": {
            "modalidade": resultado.melhor_opcao.modalidade.value,
            "custo_atual": float(resultado.melhor_opcao.custo_atual),
            "custo_otimizado": float(resultado.melhor_opcao.custo_otimizado),
            "economia_anual": float(resultado.melhor_opcao.economia_anual),
            "economia_percentual": float(resultado.melhor_opcao.economia_percentual),
            "demanda_otima": resultado.melhor_opcao.demanda_otima,
            "viavel": bool(resultado.melhor_opcao.viavel),
            "observacoes": resultado.melhor_opcao.observacoes
        },
        "economia_maxima": float(resultado.economia_maxima),
        "recomendacoes": resultado.recomendacoes,
        "dados_mensais": resultado.dados_mensais,
        "resumo_executivo": {
            **resultado.resumo_executivo,
            "mudanca_necessaria": bool(resultado.melhor_opcao.modalidade != resultado.modalidade_atual)
        }
    }