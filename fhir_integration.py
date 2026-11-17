import os
import json
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
        resource_data=json.dumps(payload.resource_data, ensure_ascii=False)
    )
    db.add(db_fhir)
    db.commit()
    db.refresh(db_fhir)
    return {
        "id": db_fhir.id,
        "resource_type": db_fhir.resource_type,
        "resource_data": payload.resource_data
    }

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
    itens = db.query(models.FHIRItem).offset(skip).limit(limit).all()
    resultado = []
    for item in itens:
        dados = json.loads(item.resource_data) if isinstance(item.resource_data, str) else item.resource_data
        resultado.append({
            "id": item.id,
            "resource_type": item.resource_type,
            "resource_data": dados
        })
    return resultado


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
        "contact": [
            {
                "relationship": [{"text": "Contato de Emergência"}],
                "name": {"text": cidadao.contacto_responsavel}
            }
        ] if cidadao.contacto_responsavel else [],
        "extension": [
            {
                "url": "http://hl7.org/fhir/StructureDefinition/patient-bloodType",
                "valueString": cidadao.tipo_sanguineo
            },
            {
                "url": "http://saude-facil.gov.br/fhir/StructureDefinition/health-insurance",
                "valueBoolean": cidadao.possui_plano_saude
            }
        ]
    }
    return fhir_patient


@router.get("/prescricoes/{cidadao_id}", summary="Exportar Prescrições Médicas em Formato FHIR MedicationRequest R4")
def exportar_fhir_prescricoes(cidadao_id: int, db: Session = Depends(database.get_db)):
    cidadao = db.query(models.CidadaoPerfil).filter(models.CidadaoPerfil.id == cidadao_id).first()
    if not cidadao:
        raise HTTPException(status_code=404, detail="Cidadão não encontrado.")

    prescricoes = db.query(models.MedicamentoItem).filter(models.MedicamentoItem.cidadao_id == cidadao_id).all()
    recursos_fhir = []

    for p in prescricoes:
        recursos_fhir.append({
            "resourceType": "MedicationRequest",
            "id": f"rx-{p.id}",
            "identifier": [
                {
                    "system": "http://saude-facil.gov.br/fhir/qr-token",
                    "value": p.qr_code_token
                }
            ],
            "status": "completed" if p.dispensado else "active",
            "intent": "order",
            "category": [
                {
                    "text": "Uso Contínuo" if p.uso_continuo else "Temporário / Emergência"
                }
            ],
            "medicationCodeableConcept": {
                "text": f"{p.medicamento_nome} {p.dosagem}".strip()
            },
            "subject": {
                "reference": f"Patient/{cidadao.id}",
                "display": cidadao.nome_completo
            },
            "dosageInstruction": [
                {
                    "text": p.posologia,
                    "timing": {
                        "code": {"text": f"Alarmes: {p.horarios_alarme or 'Conforme prescrição'}"}
                    }
                }
            ],
            "dispenseRequest": {
                "quantity": {
                    "value": p.quantidade_disponibilizada,
                    "unit": "unidade(s)"
                }
            }
        })

    return {
        "resourceType": "Bundle",
        "type": "searchset",
        "total": len(recursos_fhir),
        "entry": [{"resource": r} for r in recursos_fhir]
    }


@router.get("/dispensacoes/{cidadao_id}", summary="Exportar Dispensações da Farmácia em Formato FHIR MedicationDispense R4")
def exportar_fhir_dispensacoes(cidadao_id: int, db: Session = Depends(database.get_db)):
    cidadao = db.query(models.CidadaoPerfil).filter(models.CidadaoPerfil.id == cidadao_id).first()
    if not cidadao:
        raise HTTPException(status_code=404, detail="Cidadão não encontrado.")

    dispensados = db.query(models.MedicamentoItem).filter(
        models.MedicamentoItem.cidadao_id == cidadao_id,
        models.MedicamentoItem.dispensado == True
    ).all()

    recursos_fhir = []
    for d in dispensados:
        recursos_fhir.append({
            "resourceType": "MedicationDispense",
            "id": f"disp-{d.id}",
            "identifier": [
                {
                    "system": "http://saude-facil.gov.br/fhir/qr-token",
                    "value": d.qr_code_token
                }
            ],
            "status": "completed",
            "category": {
                "text": "SUS - Farmácia Pública" if d.fornecido_pelo_sus else "Rede Privada com Desconto"
            },
            "medicationCodeableConcept": {
                "text": f"{d.medicamento_nome} {d.dosagem}".strip()
            },
            "subject": {
                "reference": f"Patient/{cidadao.id}",
                "display": cidadao.nome_completo
            },
            "authorizingPrescription": [
                {"reference": f"MedicationRequest/rx-{d.id}"}
            ],
            "quantity": {
                "value": d.quantidade_disponibilizada,
                "unit": "unidade(s)"
            },
            "whenHandedOver": d.data_dispensacao.isoformat() if d.data_dispensacao else datetime.utcnow().isoformat(),
            "dosageInstruction": [{"text": d.posologia}]
        })

    return {
        "resourceType": "Bundle",
        "type": "searchset",
        "total": len(recursos_fhir),
        "entry": [{"resource": r} for r in recursos_fhir]
    }


@router.get("/emergencia/{qr_token}", summary="Exportar Resumo Clínico de Emergência (QR Code) em FHIR Bundle Document R4")
def exportar_fhir_emergencia_qrcode(qr_token: str, db: Session = Depends(database.get_db)):
    emergencia = db.query(models.EmergencyItem).filter(models.EmergencyItem.qr_code_token == qr_token).first()
    if not emergencia:
        raise HTTPException(status_code=404, detail="Token de QR Code de emergência não encontrado.")

    entries = []

    if emergencia.cidadao_id:
        patient_resource = exportar_fhir_patient(emergencia.cidadao_id, db)
    else:
        patient_resource = {
            "resourceType": "Patient",
            "id": f"emerg-{emergencia.id}",
            "name": [{"use": "official", "text": emergencia.cidadao_nome}],
            "contact": [{
                "name": {"text": emergencia.contacto_emergencia_nome},
                "telecom": [{"system": "phone", "value": emergencia.contacto_emergencia_telefone}]
            }],
            "extension": [{
                "url": "http://hl7.org/fhir/StructureDefinition/patient-bloodType",
                "valueString": emergencia.tipo_sanguineo
            }]
        }
    entries.append({"resource": patient_resource})

    if emergencia.alergias:
        entries.append({
            "resource": {
                "resourceType": "AllergyIntolerance",
                "id": f"allergy-emerg-{emergencia.id}",
                "clinicalStatus": {"coding": [{"code": "active"}]},
                "criticality": "high",
                "code": {"text": emergencia.alergias},
                "patient": {"reference": f"Patient/{patient_resource['id']}"}
            }
        })

    if emergencia.condicoes_medicas:
        entries.append({
            "resource": {
                "resourceType": "Condition",
                "id": f"cond-emerg-{emergencia.id}",
                "clinicalStatus": {"coding": [{"code": "active"}]},
                "code": {"text": emergencia.condicoes_medicas},
                "subject": {"reference": f"Patient/{patient_resource['id']}"}
            }
        })

    if emergencia.cidadao_id:
        meds = db.query(models.MedicamentoCidadao).filter(
            models.MedicamentoCidadao.cidadao_id == emergencia.cidadao_id
        ).all()
        for m in meds:
            entries.append({
                "resource": {
                    "resourceType": "MedicationStatement",
                    "id": f"med-emerg-{m.id}",
                    "status": "active",
                    "medicationCodeableConcept": {"text": m.nome_medicamento},
                    "subject": {"reference": f"Patient/{emergencia.cidadao_id}"}
                }
            })

    return {
        "resourceType": "Bundle",
        "identifier": {
            "system": "http://saude-facil.gov.br/fhir/emergency-qr",
            "value": qr_token
        },
        "type": "document",
        "timestamp": datetime.utcnow().isoformat(),
        "entry": entries
    }


@router.get("/bundle/{cidadao_id}", summary="Exportar Pacote Clínico FHIR Bundle (Prontuário Unificado Completo)")
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

    if cidadao.alergias:
        fhir_bundle["entry"].append({
            "resource": {
                "resourceType": "AllergyIntolerance",
                "id": f"allergy-{cidadao_id}",
                "clinicalStatus": {"coding": [{"code": "active"}]},
                "code": {"text": cidadao.alergias},
                "patient": {"reference": f"Patient/{cidadao_id}"}
            }
        })

    if cidadao.condicoes_cronicas:
        fhir_bundle["entry"].append({
            "resource": {
                "resourceType": "Condition",
                "id": f"condition-{cidadao_id}",
                "clinicalStatus": {"coding": [{"code": "active"}]},
                "code": {"text": cidadao.condicoes_cronicas},
                "subject": {"reference": f"Patient/{cidadao_id}"}
            }
        })

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

    prescricoes_bundle = exportar_fhir_prescricoes(cidadao_id, db)
    fhir_bundle["entry"].extend(prescricoes_bundle["entry"])

    dispensacoes_bundle = exportar_fhir_dispensacoes(cidadao_id, db)
    fhir_bundle["entry"].extend(dispensacoes_bundle["entry"])

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
