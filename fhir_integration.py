from pydantic import BaseModel
from typing import Optional

class FHIRPatientResource(BaseModel):
    resourceType: str = "Patient"
    id: str
    nome_completo: str
    genero: str
    data_nascimento: str

class FHIRObservationResource(BaseModel):
    resourceType: str = "Observation"
    id: str
    patient_id: str
    status: str = "final"
    codigo_exame: str
    resultado_valor: str
