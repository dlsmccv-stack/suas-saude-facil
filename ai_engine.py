import numpy as np
import pandas as pd
from pydantic import BaseModel, Field
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split


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


ai_predictor = AdverseEventPredictor()
