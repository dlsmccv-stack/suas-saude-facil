from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import database, models
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime

router = APIRouter()

# ==========================================
# 1. SCHEMAS ORIGINAIS (Mantidos do seu código)
# ==========================================

class FHIRResourceCreate(BaseModel):
    resource_type: str = Field(..., description="Tipo do recurso FHIR R4 (ex: Patient, Observation, Encounter)", example="Patient")
    resource_data: Dict[str, Any] = Field(..., description="Payload completo do recurso em formato FHIR R4 JSON", example={
        "resourceType": "Patient",
        "name": [{"use": "official", "family": "Silva", "given": ["Maria"]}]
    })

    class Config:
        json_schema_extra = {
            "example": {
                "resource_type": "Patient",
                "resource_data": {
                    "resourceType": "Patient",
                    "name": [{"use": "official", "family": "Silva", "given": ["Maria"]}]
                }
            }
        }

class FHIRResourceResponse(BaseModel):
    id: int = Field(..., description="Identificador interno do registo FHIR na base de dados", example=1)
    resource_type: str = Field(..., description="Tipo do recurso FHIR", example="Patient")
    resource_data: Dict[str, Any] = Field(..., description="Dados do recurso FHIR R4", example={
        "resourceType": "Patient",
        "name": [{"use": "official", "family": "Silva", "given": ["Maria"]}]
    })

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 1,
                "resource_type": "Patient",
                "resource_data": {
                    "resourceType": "Patient",
                    "name": [{"use": "official", "family": "Silva", "given": ["Maria"]}]
                }
            }
        }


# ==========================================
# 2. ENDPOINTS GENÉRICOS (O seu código original)
# ==========================================

@router.post(
    "/",
    response_model=FHIRResourceResponse,
    summary="Submeter Recurso FHIR R4",
    description="Recebe e armazena um recurso clínico estruturado de acordo com o padrão internacional FHIR R4 para interoperabilidade em saúde."
)
def criar_recurso_fhir(
    payload: FHIRResourceCreate,
    db: Session = Depends(database.get_db)
):
    db_fhir = models.FHIRItem(
        resource_type=payload.resource_type,
        resource_data=payload.resource_data
    )
    db.add(db_fhir)
    db.commit()
    db.refresh(db_fhir)
    return db_fhir

@router.get(
    "/",
    response_model=List[FHIRResourceResponse],
    summary="Listar Recursos FHIR",
    description="Retorna a lista de todos os recursos clínicos interoperáveis armazenados no formato FHIR R4."
)
def listar_recursos_fhir(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(database.get_db)
):
    return db.query(models.FHIRItem).offset(skip).limit(limit).all()


# ==========================================
# 3. ENDPOINTS DE EXPORTAÇÃO AUTOMÁTICA R4
# ==========================================

@router.get("/patient/{cidadao_id}", summary="Exportar Perfil do Cidadão em Formato FHIR Patient R4")
def exportar_fhir_patient(cidadao_id: int, db: Session = Depends(database.get_db)):
    cidadao = db.query(models.CidadaoPerfil).filter(models.CidadaoPerfil.id == cidadao_id).first()
    if not cidadao:
        raise HTTPException(status_code=404, detail="Cidadão não encontrado.")

    fhir_patient = {
        "resourceType": "Patient",
        "id": str(cidadao.id),
        "identifier": [
            {
                "system": "http://www.saude.gov.br/fhir/r4/StructureDefinition/BRCPF",
                "value": cidadao.cpf
            }
        ],
        "active": True,
        "name": [
            {
                "use": "official",
                "text": cidadao.nome_completo
            }
        ],
        "extension": [
            {
                "url": "http://hl7.org/fhir/StructureDefinition/patient-bloodType",
                "valueString": cidadao.tipo_sanguineo
            },
            {
                "url": "http://saude-facil.gov.br/fhir/StructureDefinition/emergency-contact",
                "valueString": cidadao.contacto_responsavel
            },
            {
                "url": "http://saude-facil.gov.br/fhir/StructureDefinition/health-insurance",
                "valueBoolean": cidadao.possui_plano_saude
            }
        ]
    }
    return fhir_patient


@router.get("/bundle/{cidadao_id}", summary="Exportar Pacote Clínico FHIR Bundle (Prontuário Unificado do Cidadão)")
def exportar_fhir_bundle_completo(cidadao_id: int, db: Session = Depends(database.get_db)):
    cidadao = db.query(models.CidadaoPerfil).filter(models.CidadaoPerfil.id == cidadao_id).first()
    if not cidadao:
        raise HTTPException(status_code=404, detail="Cidadão não encontrado.")

    medicamentos = db.query(models.MedicamentoCidadao).filter(models.MedicamentoCidadao.cidadao_id == cidadao_id).all()
    automedicacoes = db.query(models.AutomedicacaoLog).filter(models.AutomedicacaoLog.cidadao_id == cidadao_id).all()

    fhir_bundle = {
        "resourceType": "Bundle",
        "type": "collection",
        "timestamp": datetime.utcnow().isoformat(),
        "entry": []
    }

    # Adiciona Recurso Patient
    patient_data = exportar_fhir_patient(cidadao_id, db)
    fhir_bundle["entry"].append({"resource": patient_data})

    # Adiciona Medicamentos Registados (Uso Contínuo e Temporários/Emergência)
    for med in medicamentos:
        fhir_bundle["entry"].append({
            "resource": {
                "resourceType": "MedicationStatement",
                "id": f"med-{med.id}",
                "status": "active",
                "medicationCodeableConcept": {"text": med.nome_medicamento},
                "subject": {"reference": f"Patient/{cidadao_id}"},
                "note": [{"text": f"Tipo de Prescrição: {med.tipo_presricao} | Alarme configurado: {med.horarios_alarme or 'N/A'}"}]
            }
        })

    # Adiciona Logs de Automedicação Preventiva
    for auto in automedicacoes:
        fhir_bundle["entry"].append({
            "resource": {
                "resourceType": "Observation",
                "id": f"auto-{auto.id}",
                "status": "final",
                "code": {"text": "Automedicação Registada via Scanner (Alerta Preventivo)"},
                "subject": {"reference": f"Patient/{cidadao_id}"},
                "valueString": auto.nome_medicamento,
                "effectiveDateTime": auto.data_registo.isoformat()
            }
        })

    return fhir_bundle
