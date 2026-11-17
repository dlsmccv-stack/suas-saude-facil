import numpy as np
import pandas as pd
from datetime import datetime
from typing import List, Dict, Any
from pydantic import BaseModel, Field
from sklearn.ensemble import RandomForestClassifier


# Modelo Pydantic para estruturar e validar os dados no Swagger (sem additionalProp1)
class PatientDataSchema(BaseModel):
    idade: int = Field(..., example=68, description="Idade do paciente")
    comorbidades_score: int = Field(
        ..., example=3, description="Pontuação de comorbidades"
    )
    qtd_medicamentos: int = Field(
        ..., example=5, description="Quantidade de medicamentos em uso"
    )
    historico_alergia: int = Field(
        ..., example=1, description="Histórico de alergia (0 ou 1)"
    )
    sinal_vital_critico: int = Field(
        ..., example=1, description="Presença de sinal vital crítico (0 ou 1)"
    )


class AdverseEventPredictor:

    def __init__(self):
        self.model = RandomForestClassifier(n_estimators=100, random_state=42)
        self.is_trained = False
        self._treinar_modelo_inicial()

    def _treinar_modelo_inicial(self):
        np.random.seed(42)
        n_samples = 200

        dados_ficticios = {
            "idade": np.random.randint(18, 90, size=n_samples),
            "comorbidades_score": np.random.randint(0, 5, size=n_samples),
            "qtd_medicamentos": np.random.randint(1, 10, size=n_samples),
            "historico_alergia": np.random.randint(0, 2, size=n_samples),
            "sinal_vital_critico": np.random.randint(0, 2, size=n_samples),
        }

        df = pd.DataFrame(dados_ficticios)
        df["evento_adverso_ocorreu"] = (
            (df["sinal_vital_critico"] == 1) & (df["comorbidades_score"] >= 2)
        ).astype(int)

        X = df[
            [
                "idade",
                "comorbidades_score",
                "qtd_medicamentos",
                "historico_alergia",
                "sinal_vital_critico",
            ]
        ]
        y = df["evento_adverso_ocorreu"]

        self.model.fit(X, y)
        self.is_trained = True

    def predict_risk(self, patient_data: dict) -> dict:
        if not self.is_trained:
            raise ValueError("O modelo não está treinado.")

        df_input = pd.DataFrame([patient_data])
        probability = self.model.predict_proba(df_input)[0][1]

        risk_level = (
            "Alto"
            if probability > 0.7
            else ("Moderado" if probability > 0.4 else "Baixo")
        )

        return {
            "risco_score": round(float(probability), 4),
            "nivel_alerta": risk_level,
            "requer_capacitacao_automatica": bool(probability > 0.4),
        }

    def analisar_farmacovigilancia_cidadao(
        self,
        cidadao: Any,
        medicamentos_app: List[Any],
        prescricoes_farmacia: List[Any],
        automedicacoes: List[Any],
        triagens: List[Any] = None,
        idade_estimada: int = 55,
    ) -> Dict[str, Any]:
        """
        Cruza automaticamente perfil clínico, alergias, medicamentos prescritos,
        automedicações registradas no scanner e histórico de triagem de Manchester.
        """
        triagens = triagens or []
        alertas_clinicos = []

        # 1. Consolida todos os medicamentos (App + Prescrições + Automedicação)
        lista_prescritos = [m.nome_medicamento for m in medicamentos_app] + [
            f"{p.medicamento_nome} {p.dosagem}".strip() for p in prescricoes_farmacia
        ]
        lista_automedicacao = [a.nome_medicamento for a in automedicacoes]
        todos_medicamentos = lista_prescritos + lista_automedicacao
        todos_lower = " | ".join(todos_medicamentos).lower()

        alergias_texto = (cidadao.alergias or "").strip()
        condicoes_texto = (cidadao.condicoes_cronicas or "").strip()

        # 2. Verificação de Alergia Direta e Cruzada
        if alergias_texto:
            itens_alergia = [a.strip().lower() for a in alergias_texto.split(",") if a.strip()]
            for alergia in itens_alergia:
                if alergia and alergia in todos_lower:
                    alertas_clinicos.append({
                        "tipo": "ALERGIA_CRITICA",
                        "severidade": "Alta",
                        "descricao": f"Risco de reação alérgica grave: paciente possui alergia registada a '{alergia.upper()}' e há medicamento compatível no prontuário/automedicação.",
                    })
                if "penicilina" in alergia and any(
                    x in todos_lower for x in ["amoxicilina", "ampicilina", "benzetacil"]
                ):
                    alertas_clinicos.append({
                        "tipo": "ALERGIA_CRUZADA_BETA_LACTAMICO",
                        "severidade": "Alta",
                        "descricao": "Alergia cruzada detectada: paciente alérgico a Penicilina com registro de derivado beta-lactâmico (Amoxicilina/Ampicilina).",
                    })

        # 3. Interação Automedicação x Hipertensão / Anti-hipertensivos
        anti_inflamatorios = [
            "ibuprofeno",
            "diclofenaco",
            "nimesulida",
            "cetoprofeno",
            "naproxeno",
            "meloxicam",
        ]
        tem_aine = any(aine in " | ".join(lista_automedicacao).lower() for aine in anti_inflamatorios)
        hipertenso_ou_iec = ("hipertens" in condicoes_texto.lower()) or any(
            med in todos_lower
            for med in ["losartana", "captopril", "enalapril", "hidroclorotiazida", "anlodipino"]
        )
        if tem_aine and hipertenso_ou_iec:
            alertas_clinicos.append({
                "tipo": "INTERACAO_AUTOMEDICACAO_HIPERTENSAO",
                "severidade": "Moderada a Alta",
                "descricao": "Uso de anti-inflamatório (AINE) via automedicação em paciente hipertenso/em uso de anti-hipertensivo: risco de redução do efeito pressórico e sobrecarga renal.",
            })

        # 4. Polifarmácia (>= 5 medicamentos únicos)
        qtd_total_meds = len(set([m.lower().strip() for m in todos_medicamentos if m.strip()]))
        if qtd_total_meds >= 5:
            alertas_clinicos.append({
                "tipo": "POLIFARMACIA",
                "severidade": "Moderada",
                "descricao": f"Polifarmácia detectada ({qtd_total_meds} fármacos ativos/registados). Recomenda-se revisão farmacoterapêutica.",
            })

        # 5. Calcula features para o RandomForestClassifier
        comorbidades_list = [c.strip() for c in condicoes_texto.split(",") if c.strip()]
        comorbidades_score = min(4, len(comorbidades_list) + (1 if len(lista_automedicacao) > 0 else 0))
        historico_alergia = 1 if alergias_texto else 0

        triagem_critica = any(
            (t.cor_prioridade or "").lower() in ["vermelho", "laranja", "emergencia", "muito urgente"]
            for t in triagens
        )
        sinal_vital_critico = 1 if (
            triagem_critica or any(a["severidade"] == "Alta" for a in alertas_clinicos)
        ) else 0

        predicao_ml = self.predict_risk({
            "idade": idade_estimada,
            "comorbidades_score": comorbidades_score,
            "qtd_medicamentos": max(1, qtd_total_meds),
            "historico_alergia": historico_alergia,
            "sinal_vital_critico": sinal_vital_critico,
        })

        # 6. Sincroniza severidade clínica com o nível de risco integrado
        nivel_final = predicao_ml["nivel_alerta"]
        severidades = [a["severidade"] for a in alertas_clinicos]

        if "Alta" in severidades:
            nivel_final = "Alto"
        elif "Moderada a Alta" in severidades and nivel_final == "Baixo":
            nivel_final = "Moderado"
        elif "Moderada" in severidades and nivel_final == "Baixo":
            nivel_final = "Moderado"

        manchester_sugerido = (
            "Laranja (Muito Urgente - 10 min)"
            if nivel_final == "Alto"
            else ("Amarelo (Urgente - 50 min)" if nivel_final == "Moderado" else "Verde (Pouco Urgente - 120 min)")
        )

        fhir_risk_assessment = {
            "resourceType": "RiskAssessment",
            "status": "final",
            "subject": {
                "reference": f"Patient/{cidadao.id}",
                "display": cidadao.nome_completo,
            },
            "occurrenceDateTime": datetime.utcnow().isoformat(),
            "prediction": [
                {
                    "outcome": {"text": "Risco de Evento Adverso Medicamentoso / Interação Clínica"},
                    "probabilityDecimal": predicao_ml["risco_score"],
                    "qualitativeRisk": {"text": nivel_final},
                }
            ],
            "note": [{"text": a["descricao"]} for a in alertas_clinicos],
        }

        return {
            "cidadao_id": cidadao.id,
            "cidadao_nome": cidadao.nome_completo,
            "resumo_clinico_analisado": {
                "condicoes_cronicas": condicoes_texto or "Nenhuma registada",
                "alergias": alergias_texto or "Nenhuma registada",
                "medicamentos_prescritos_ou_app": lista_prescritos,
                "automedicacoes_scanner": lista_automedicacao,
                "total_farmacos_unicos": qtd_total_meds,
            },
            "score_ia_random_forest": predicao_ml["risco_score"],
            "nivel_risco_integrado": nivel_final,
            "prioridade_manchester_sugerida": manchester_sugerido,
            "alertas_farmacovigilancia": alertas_clinicos,
            "recurso_fhir_r4": fhir_risk_assessment,
        }


ai_predictor = AdverseEventPredictor()
