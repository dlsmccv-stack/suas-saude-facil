import os
import getpass
import requests
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import database, models
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime
from requests.exceptions import RequestException

router = APIRouter()

# ==========================================
# 0. CONFIGURAÇÕES DA RNDS (HOMOLOGAÇÃO)
# ==========================================
AUTH_URL = "https://ehr-auth-hmg.saude.gov.br/api/token"
EHR_BASE_URL = "https://ehr-services.hmg.saude.gov.br/fhir/r4"

# ==========================================
# 1. SCHEMAS ORIGINAIS
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
# 2. ENDPOINTS GENÉRICOS
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

    patient_data = exportar_fhir_patient(cidadao_id, db)
    fhir_bundle["entry"].append({"resource": patient_data})

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


# ==========================================
# 4. MÓDULOS DE CONEXÃO COM O SUS (RNDS)
# ==========================================

def obter_token_rnds() -> str:
    # Aponta para o arquivo .pem configurado no ambiente
    cert_path = os.getenv("RNDS_CERT_PATH", "certificado.pem")

    if not os.path.exists(cert_path):
        raise HTTPException(
            status_code=500,
            detail=f"Arquivo de certificado não encontrado em: {cert_path}"
        )

    try:
        response = requests.get(
            AUTH_URL,
            cert=cert_path,
            timeout=30
        )

        if response.status_code == 200:
            token_data = response.json()
            return token_data.get("access_token")
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Falha na autenticação RNDS: {response.status_code} - {response.text}"
            )
    except RequestException as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Erro de conexão com o servidor de Auth da RNDS: {str(e)}"
        )


@router.post("/enviar-sus/{cidadao_id}", summary="Enviar Prontuário do Cidadão para o SUS (RNDS)")
def enviar_dados_para_sus(cidadao_id: int, profissional_cns: str, db: Session = Depends(database.get_db)):
    bundle_data = exportar_fhir_bundle_completo(cidadao_id, db)
    access_token = obter_token_rnds()

    if not access_token:
        raise HTTPException(status_code=500, detail="Não foi possível obter o token de acesso da RNDS.")

    headers = {
        "Content-Type": "application/json",
        "X-Authorization-Server": f"Bearer {access_token}",
        "Authorization": profissional_cns
    }

    try:
        response = requests.post(
            f"{EHR_BASE_URL}/Bundle",
            json=bundle_data,
            headers=headers,
            timeout=30
        )

        if response.status_code in [200, 201]:
            return {
                "status": "Sucesso",
                "mensagem": "Dados enviados e integrados ao SUS com sucesso!",
                "resposta_rnds": response.json()
            }
        else:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Erro retornado pela RNDS: {response.text}"
            )

    except RequestException as e:
        raise HTTPException(
            status_code=502,
            detail=f"Erro de comunicação ao enviar os dados para os serviços EHR da RNDS: {str(e)}"
        )


@router.get("/consultar-sus/paciente/{cpf}", summary="Consultar Paciente na Base Nacional do SUS (RNDS)")
def consultar_paciente_sus(cpf: str, profissional_cns: str):
    access_token = obter_token_rnds()

    headers = {
        "Accept": "application/json",
        "X-Authorization-Server": f"Bearer {access_token}",
        "Authorization": profissional_cns
    }

    try:
        response = requests.get(
            f"{EHR_BASE_URL}/Patient",
            params={"identifier": f"http://www.saude.gov.br/fhir/r4/StructureDefinition/BRCPF|{cpf}"},
            headers=headers,
            timeout=30
        )
        try:
            dados = response.json() if response.text else None
        except ValueError:
            dados = response.text

        return {
            "status_http_rnds": response.status_code,
            "resposta_rnds": dados
        }
    except RequestException as e:
        raise HTTPException(
            status_code=502,
            detail=f"Erro ao consultar paciente na RNDS: {str(e)}"
        )
