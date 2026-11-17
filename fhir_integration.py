import os
import re
import json
import uuid
import requests
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
import database, models
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from requests.exceptions import RequestException

router = APIRouter()

# ==========================================
# 0. CONFIGURAÇÕES E PERFIS OFICIAIS RNDS (BR-CORE)
# ==========================================
AUTH_URL = os.getenv("RNDS_AUTH_URL", "https://ehr-auth-hmg.saude.gov.br/api/token")
EHR_BASE_URL = os.getenv("RNDS_EHR_URL", "https://ehr-services.hmg.saude.gov.br/fhir/r4")
DEFAULT_CNES = os.getenv("RNDS_CNES", "2492555")
DEFAULT_ESTABELECIMENTO = os.getenv("RNDS_ESTABELECIMENTO", "Unidade de Saúde - Rede SUAS Saúde +Fácil")

RNDS_PROFILES = {
    "bundle_rac": "http://www.saude.gov.br/fhir/r4/StructureDefinition/BRRegistroAtendimentoClinico-1.0",
    "composition": "http://www.saude.gov.br/fhir/r4/StructureDefinition/BRDocumentoClinico-1.0",
    "individuo": "http://www.saude.gov.br/fhir/r4/StructureDefinition/BRIndividuo-1.0",
    "estabelecimento": "http://www.saude.gov.br/fhir/r4/StructureDefinition/BREstabelecimentoSaude-1.0",
    "alergia": "http://www.saude.gov.br/fhir/r4/StructureDefinition/BRAlergiaReacaoAdversa-1.0",
    "condicao": "http://www.saude.gov.br/fhir/r4/StructureDefinition/BRDiagnosticoAvaliado-1.0",
    "medicamento": "http://www.saude.gov.br/fhir/r4/StructureDefinition/BRMedicamento-1.0",
    "prescricao": "http://www.saude.gov.br/fhir/r4/StructureDefinition/BRPrescricaoMedicamento-1.0",
    "dispensacao": "http://www.saude.gov.br/fhir/r4/StructureDefinition/BRDispensacaoMedicamento-1.0",
    "observacao": "http://www.saude.gov.br/fhir/r4/StructureDefinition/BRObservacaoClinica-1.0",
}

RNDS_NAMING_SYSTEMS = {
    "cns": "http://rnds.saude.gov.br/fhir/r4/NamingSystem/cns",
    "cpf": "http://rnds.saude.gov.br/fhir/r4/NamingSystem/cpf",
    "cnes": "http://rnds.saude.gov.br/fhir/r4/NamingSystem/cnes",
    "catmat": "http://www.saude.gov.br/fhir/r4/CodeSystem/BRMedicamento",
    "ciap2": "http://www.saude.gov.br/fhir/r4/CodeSystem/BRCIAP2",
}


def _somente_digitos(valor: Optional[str]) -> str:
    if not valor:
        return ""
    return re.sub(r"\D", "", str(valor))


def gerar_operation_outcome(issues: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Constrói um recurso oficial HL7 FHIR R4 OperationOutcome conforme exigido
    pela RNDS para validação estrutural e semântica de Bundles.
    """
    if not issues:
        issues = [
            {
                "severity": "information",
                "code": "informational",
                "details": {
                    "text": "Bundle FHIR R4 validado com sucesso e aderente aos perfis BR-Core da RNDS."
                },
                "expression": ["Bundle"],
            }
        ]

    return {
        "resourceType": "OperationOutcome",
        "id": str(uuid.uuid4()),
        "meta": {
            "lastUpdated": datetime.now(timezone.utc).isoformat(),
            "profile": ["http://hl7.org/fhir/StructureDefinition/OperationOutcome"],
        },
        "issue": issues,
    }


def validar_bundle_rnds(bundle: Dict[str, Any]) -> Dict[str, Any]:
    """
    Valida os requisitos obrigatórios da RNDS (BR-Core):
    - Bundle.type == 'document' com Composition na primeira entrada
    - fullUrl em todas as entradas
    - meta.profile oficial da RNDS nos recursos
    - Patient (BRIndividuo-1.0) com CPF (11 dígitos) ou CNS (15 dígitos) válido
    - Organization (BREstabelecimentoSaude-1.0) com CNES válido de 7 dígitos
    """
    issues: List[Dict[str, Any]] = []

    if bundle.get("resourceType") != "Bundle":
        issues.append({
            "severity": "fatal",
            "code": "invalid",
            "details": {"text": "O recurso raiz deve ser 'Bundle'."},
            "expression": ["Bundle.resourceType"],
        })
        return gerar_operation_outcome(issues)

    if bundle.get("type") != "document":
        issues.append({
            "severity": "error",
            "code": "value",
            "details": {"text": "Para submissão oficial à RNDS, Bundle.type deve ser 'document'."},
            "expression": ["Bundle.type"],
        })

    bundle_profiles = bundle.get("meta", {}).get("profile", [])
    if not any("saude.gov.br/fhir/r4/StructureDefinition" in p for p in bundle_profiles):
        issues.append({
            "severity": "error",
            "code": "required",
            "details": {"text": "Bundle.meta.profile oficial da RNDS ausente."},
            "expression": ["Bundle.meta.profile"],
        })

    entries = bundle.get("entry", [])
    if not entries:
        issues.append({
            "severity": "error",
            "code": "required",
            "details": {"text": "Bundle.entry não pode ser vazio."},
            "expression": ["Bundle.entry"],
        })
        return gerar_operation_outcome(issues)

    # Na RNDS, a primeira entrada de um Bundle document DEVE ser Composition
    primeiro_recurso = entries[0].get("resource", {}).get("resourceType")
    if primeiro_recurso != "Composition":
        issues.append({
            "severity": "error",
            "code": "structure",
            "details": {"text": f"A primeira entrada de um Bundle 'document' deve ser 'Composition', encontrado '{primeiro_recurso}'."},
            "expression": ["Bundle.entry[0].resource.resourceType"],
        })

    tem_paciente = False
    tem_estabelecimento = False

    for idx, entry in enumerate(entries):
        prefixo = f"Bundle.entry[{idx}]"
        if not entry.get("fullUrl"):
            issues.append({
                "severity": "error",
                "code": "required",
                "details": {"text": "Toda entrada em Bundle.entry deve conter 'fullUrl'."},
                "expression": [f"{prefixo}.fullUrl"],
            })

        res = entry.get("resource", {})
        rtype = res.get("resourceType")
        rprofiles = res.get("meta", {}).get("profile", [])

        if not rprofiles:
            issues.append({
                "severity": "warning",
                "code": "required",
                "details": {"text": f"Recurso '{rtype}' sem meta.profile BR-Core declarado."},
                "expression": [f"{prefixo}.resource.meta.profile"],
            })

        if rtype == "Patient":
            tem_paciente = True
            identificadores = res.get("identifier", [])
            tem_id_valido = False

            for ident in identificadores:
                sys = ident.get("system", "")
                val = _somente_digitos(ident.get("value"))
                if sys == RNDS_NAMING_SYSTEMS["cpf"]:
                    if len(val) == 11:
                        tem_id_valido = True
                    else:
                        issues.append({
                            "severity": "error",
                            "code": "invalid",
                            "details": {"text": f"CPF inválido em BRIndividuo-1.0 ('{val}'): deve conter exatamente 11 dígitos numéricos."},
                            "expression": [f"{prefixo}.resource.identifier"],
                        })
                elif sys == RNDS_NAMING_SYSTEMS["cns"]:
                    if len(val) == 15:
                        tem_id_valido = True
                    else:
                        issues.append({
                            "severity": "error",
                            "code": "invalid",
                            "details": {"text": f"CNS inválido em BRIndividuo-1.0 ('{val}'): deve conter exatamente 15 dígitos numéricos."},
                            "expression": [f"{prefixo}.resource.identifier"],
                        })

            if not tem_id_valido:
                issues.append({
                    "severity": "error",
                    "code": "required",
                    "details": {"text": "BRIndividuo-1.0 exige ao menos um identificador nacional válido: CPF (11 dígitos) ou CNS (15 dígitos)."},
                    "expression": [f"{prefixo}.resource.identifier"],
                })

            if not res.get("name"):
                issues.append({
                    "severity": "error",
                    "code": "required",
                    "details": {"text": "BRIndividuo-1.0 exige o nome oficial do cidadão (Patient.name)."},
                    "expression": [f"{prefixo}.resource.name"],
                })

        if rtype == "Organization":
            tem_estabelecimento = True
            cnes_ok = False
            for ident in res.get("identifier", []):
                if ident.get("system") == RNDS_NAMING_SYSTEMS["cnes"]:
                    cnes_digits = _somente_digitos(ident.get("value"))
                    if len(cnes_digits) == 7:
                        cnes_ok = True
            if not cnes_ok:
                issues.append({
                    "severity": "error",
                    "code": "invalid",
                    "details": {"text": "BREstabelecimentoSaude-1.0 exige CNES válido com 7 dígitos."},
                    "expression": [f"{prefixo}.resource.identifier"],
                })

    if not tem_paciente:
        issues.append({
            "severity": "error",
            "code": "required",
            "details": {"text": "Bundle RNDS deve conter obrigatoriamente um recurso Patient (BRIndividuo-1.0)."},
            "expression": ["Bundle.entry"],
        })

    if not tem_estabelecimento:
        issues.append({
            "severity": "error",
            "code": "required",
            "details": {"text": "Bundle RNDS deve conter um recurso Organization (BREstabelecimentoSaude-1.0) com CNES."},
            "expression": ["Bundle.entry"],
        })

    return gerar_operation_outcome(issues)


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
# 3. ENDPOINTS DE EXPORTAÇÃO AUTOMÁTICA R4 / RNDS (BR-CORE)
# ==========================================

@router.get("/patient/{cidadao_id}", summary="Exportar Perfil do Cidadão em Formato FHIR Patient R4 (BRIndividuo-1.0)")
def exportar_fhir_patient(cidadao_id: int, db: Session = Depends(database.get_db)):
    cidadao = db.query(models.CidadaoPerfil).filter(models.CidadaoPerfil.id == cidadao_id).first()
    if not cidadao:
        raise HTTPException(status_code=404, detail="Cidadão não encontrado.")

    identificadores = []
    cpf_limpo = _somente_digitos(getattr(cidadao, "cpf", None))
    if cpf_limpo:
        identificadores.append({
            "use": "official",
            "system": RNDS_NAMING_SYSTEMS["cpf"],
            "value": cpf_limpo,
        })

    cns_val = _somente_digitos(getattr(cidadao, "cartao_sus", None) or getattr(cidadao, "cns", None))
    if cns_val:
        identificadores.append({
            "use": "official",
            "system": RNDS_NAMING_SYSTEMS["cns"],
            "value": cns_val,
        })

    partes_nome = (cidadao.nome_completo or "").strip().split()
    family_name = partes_nome[-1] if len(partes_nome) > 1 else cidadao.nome_completo
    given_names = partes_nome[:-1] if len(partes_nome) > 1 else [cidadao.nome_completo]

    fhir_patient = {
        "resourceType": "Patient",
        "id": str(cidadao.id),
        "meta": {
            "lastUpdated": datetime.now(timezone.utc).isoformat(),
            "profile": [RNDS_PROFILES["individuo"]],
        },
        "identifier": identificadores,
        "active": True,
        "name": [
            {
                "use": "official",
                "text": cidadao.nome_completo,
                "family": family_name,
                "given": given_names,
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
        nome_completo_med = f"{p.medicamento_nome} {p.dosagem}".strip()
        recursos_fhir.append({
            "resourceType": "MedicationRequest",
            "id": f"rx-{p.id}",
            "meta": {
                "profile": [RNDS_PROFILES["prescricao"]],
            },
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
                "coding": [{"system": RNDS_NAMING_SYSTEMS["catmat"], "display": nome_completo_med}],
                "text": nome_completo_med,
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
        "entry": [{"fullUrl": f"urn:uuid:{uuid.uuid4()}", "resource": r} for r in recursos_fhir]
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
        nome_completo_med = f"{d.medicamento_nome} {d.dosagem}".strip()
        recursos_fhir.append({
            "resourceType": "MedicationDispense",
            "id": f"disp-{d.id}",
            "meta": {
                "profile": [RNDS_PROFILES["dispensacao"]],
            },
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
                "coding": [{"system": RNDS_NAMING_SYSTEMS["catmat"], "display": nome_completo_med}],
                "text": nome_completo_med,
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
            "whenHandedOver": d.data_dispensacao.isoformat() if d.data_dispensacao else datetime.now(timezone.utc).isoformat(),
            "dosageInstruction": [{"text": d.posologia}]
        })

    return {
        "resourceType": "Bundle",
        "type": "searchset",
        "total": len(recursos_fhir),
        "entry": [{"fullUrl": f"urn:uuid:{uuid.uuid4()}", "resource": r} for r in recursos_fhir]
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
            "meta": {"profile": [RNDS_PROFILES["individuo"]]},
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
    entries.append({"fullUrl": f"urn:uuid:{uuid.uuid4()}", "resource": patient_resource})

    if emergencia.alergias:
        entries.append({
            "fullUrl": f"urn:uuid:{uuid.uuid4()}",
            "resource": {
                "resourceType": "AllergyIntolerance",
                "id": f"allergy-emerg-{emergencia.id}",
                "meta": {"profile": [RNDS_PROFILES["alergia"]]},
                "clinicalStatus": {"coding": [{"code": "active"}]},
                "criticality": "high",
                "code": {"text": emergencia.alergias},
                "patient": {"reference": f"Patient/{patient_resource['id']}"}
            }
        })

    if emergencia.condicoes_medicas:
        entries.append({
            "fullUrl": f"urn:uuid:{uuid.uuid4()}",
            "resource": {
                "resourceType": "Condition",
                "id": f"cond-emerg-{emergencia.id}",
                "meta": {"profile": [RNDS_PROFILES["condicao"]]},
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
                "fullUrl": f"urn:uuid:{uuid.uuid4()}",
                "resource": {
                    "resourceType": "MedicationStatement",
                    "id": f"med-emerg-{m.id}",
                    "meta": {"profile": [RNDS_PROFILES["medicamento"]]},
                    "status": "active",
                    "medicationCodeableConcept": {
                        "coding": [{"system": RNDS_NAMING_SYSTEMS["catmat"], "display": m.nome_medicamento}],
                        "text": m.nome_medicamento,
                    },
                    "subject": {"reference": f"Patient/{emergencia.cidadao_id}"}
                }
            })

    return {
        "resourceType": "Bundle",
        "meta": {"profile": [RNDS_PROFILES["bundle_rac"]]},
        "identifier": {
            "system": "http://saude-facil.gov.br/fhir/emergency-qr",
            "value": qr_token
        },
        "type": "document",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "entry": entries
    }


def _montar_bundle_rnds_completo(cidadao_id: int, cnes: str, db: Session) -> Dict[str, Any]:
    cidadao = db.query(models.CidadaoPerfil).filter(models.CidadaoPerfil.id == cidadao_id).first()
    if not cidadao:
        raise HTTPException(status_code=404, detail="Cidadão não encontrado.")

    medicamentos = db.query(models.MedicamentoCidadao).filter(models.MedicamentoCidadao.cidadao_id == cidadao_id).all()
    automedicacoes = db.query(models.AutomedicacaoLog).filter(models.AutomedicacaoLog.cidadao_id == cidadao_id).all()

    agora_iso = datetime.now(timezone.utc).isoformat()
    bundle_uuid = str(uuid.uuid4())
    comp_uuid = str(uuid.uuid4())
    patient_uuid = str(uuid.uuid4())
    org_uuid = str(uuid.uuid4())
    cnes_limpo = _somente_digitos(cnes)

    patient_data = exportar_fhir_patient(cidadao_id, db)

    organization_resource = {
        "resourceType": "Organization",
        "id": org_uuid,
        "meta": {
            "lastUpdated": agora_iso,
            "profile": [RNDS_PROFILES["estabelecimento"]],
        },
        "identifier": [
            {
                "use": "official",
                "system": RNDS_NAMING_SYSTEMS["cnes"],
                "value": cnes_limpo,
            }
        ],
        "active": True,
        "name": DEFAULT_ESTABELECIMENTO,
    }

    entries: List[Dict[str, Any]] = [
        {"fullUrl": f"urn:uuid:{patient_uuid}", "resource": patient_data},
        {"fullUrl": f"urn:uuid:{org_uuid}", "resource": organization_resource},
    ]
    secoes_composition: List[Dict[str, Any]] = []

    if cidadao.alergias:
        allergy_uuid = str(uuid.uuid4())
        entries.append({
            "fullUrl": f"urn:uuid:{allergy_uuid}",
            "resource": {
                "resourceType": "AllergyIntolerance",
                "id": f"allergy-{cidadao_id}",
                "meta": {"profile": [RNDS_PROFILES["alergia"]]},
                "clinicalStatus": {"coding": [{"code": "active"}]},
                "code": {"text": cidadao.alergias},
                "patient": {"reference": f"Patient/{cidadao_id}"}
            }
        })
        secoes_composition.append({
            "title": "Alergias e Reações Adversas",
            "entry": [{"reference": f"urn:uuid:{allergy_uuid}"}],
        })

    if cidadao.condicoes_cronicas:
        cond_uuid = str(uuid.uuid4())
        entries.append({
            "fullUrl": f"urn:uuid:{cond_uuid}",
            "resource": {
                "resourceType": "Condition",
                "id": f"condition-{cidadao_id}",
                "meta": {"profile": [RNDS_PROFILES["condicao"]]},
                "clinicalStatus": {"coding": [{"code": "active"}]},
                "code": {
                    "coding": [{"system": RNDS_NAMING_SYSTEMS["ciap2"], "display": cidadao.condicoes_cronicas}],
                    "text": cidadao.condicoes_cronicas,
                },
                "subject": {"reference": f"Patient/{cidadao_id}"}
            }
        })
        secoes_composition.append({
            "title": "Condições Crônicas Avaliadas",
            "entry": [{"reference": f"urn:uuid:{cond_uuid}"}],
        })

    refs_meds: List[Dict[str, str]] = []
    for med in medicamentos:
        med_uuid = str(uuid.uuid4())
        entries.append({
            "fullUrl": f"urn:uuid:{med_uuid}",
            "resource": {
                "resourceType": "MedicationStatement",
                "id": f"med-{med.id}",
                "meta": {"profile": [RNDS_PROFILES["medicamento"]]},
                "status": "active",
                "medicationCodeableConcept": {
                    "coding": [{"system": RNDS_NAMING_SYSTEMS["catmat"], "display": med.nome_medicamento}],
                    "text": med.nome_medicamento,
                },
                "subject": {"reference": f"Patient/{cidadao_id}"},
                "note": [{"text": f"Tipo de Prescrição: {med.tipo_presricao} | Alarme configurado: {med.horarios_alarme or 'N/A'}"}]
            }
        })
        refs_meds.append({"reference": f"urn:uuid:{med_uuid}"})

    prescricoes_bundle = exportar_fhir_prescricoes(cidadao_id, db)
    entries.extend(prescricoes_bundle["entry"])

    dispensacoes_bundle = exportar_fhir_dispensacoes(cidadao_id, db)
    entries.extend(dispensacoes_bundle["entry"])

    for auto in automedicacoes:
        auto_uuid = str(uuid.uuid4())
        entries.append({
            "fullUrl": f"urn:uuid:{auto_uuid}",
            "resource": {
                "resourceType": "Observation",
                "id": f"auto-{auto.id}",
                "meta": {"profile": [RNDS_PROFILES["observacao"]]},
                "status": "final",
                "code": {"text": "Automedicação Registada via Scanner (Alerta Preventivo)"},
                "subject": {"reference": f"Patient/{cidadao_id}"},
                "valueString": auto.nome_medicamento,
                "effectiveDateTime": auto.data_registo.isoformat() if auto.data_registo else agora_iso,
            }
        })
        refs_meds.append({"reference": f"urn:uuid:{auto_uuid}"})

    if refs_meds:
        secoes_composition.append({
            "title": "Medicamentos e Farmacovigilância",
            "entry": refs_meds,
        })

    # Composition raiz obrigatório para Bundle type="document" na RNDS
    composition_resource = {
        "resourceType": "Composition",
        "id": comp_uuid,
        "meta": {
            "lastUpdated": agora_iso,
            "profile": [RNDS_PROFILES["composition"]],
        },
        "status": "final",
        "type": {
            "coding": [{
                "system": "http://www.saude.gov.br/fhir/r4/CodeSystem/BRTipoDocumento",
                "code": "RAC",
                "display": "Registro de Atendimento Clínico",
            }]
        },
        "subject": {"reference": f"urn:uuid:{patient_uuid}"},
        "date": agora_iso,
        "author": [{"reference": f"urn:uuid:{org_uuid}"}],
        "title": "Registro Clínico Intersetorial SUAS Saúde / Saúde +Fácil",
        "custodian": {"reference": f"urn:uuid:{org_uuid}"},
        "section": secoes_composition,
    }

    entries.insert(0, {"fullUrl": f"urn:uuid:{comp_uuid}", "resource": composition_resource})

    return {
        "resourceType": "Bundle",
        "id": bundle_uuid,
        "meta": {
            "lastUpdated": agora_iso,
            "profile": [RNDS_PROFILES["bundle_rac"]],
        },
        "identifier": {
            "system": f"http://rnds.saude.gov.br/fhir/r4/NamingSystem/bundle-{cnes_limpo}",
            "value": bundle_uuid,
        },
        "type": "document",
        "timestamp": agora_iso,
        "entry": entries,
    }


@router.get(
    "/bundle/{cidadao_id}",
    summary="Exportar Pacote Clínico FHIR Bundle (Padrão RNDS BR-Core)",
    description="Gera o Bundle FHIR R4 no padrão document com meta.profile oficiais da RNDS (BRIndividuo-1.0, CNES, CNS/CPF, CATMAT) e validação opcional OperationOutcome."
)
def exportar_fhir_bundle_completo(
    cidadao_id: int,
    cnes: str = Query(default=DEFAULT_CNES, description="Código CNES de 7 dígitos da unidade solicitante"),
    validar_estrito: bool = Query(default=False, description="Se True, bloqueia com HTTP 422 e OperationOutcome se houver pendências RNDS"),
    db: Session = Depends(database.get_db)
):
    bundle = _montar_bundle_rnds_completo(cidadao_id, cnes, db)
    outcome = validar_bundle_rnds(bundle)
    erros = [i for i in outcome["issue"] if i["severity"] in ("error", "fatal")]

    if validar_estrito and erros:
        return JSONResponse(status_code=422, content=outcome)

    return bundle


@router.post(
    "/validar-rnds/{cidadao_id}",
    summary="Validar Conformidade RNDS e Gerar OperationOutcome",
    description="Audita o Bundle do cidadão contra as regras obrigatórias da RNDS (BRIndividuo-1.0, CPF/CNS, CNES, Composition) e retorna um OperationOutcome oficial HL7 FHIR R4."
)
def validar_conformidade_rnds(
    cidadao_id: int,
    cnes: str = Query(default=DEFAULT_CNES, description="Código CNES de 7 dígitos da unidade solicitante"),
    db: Session = Depends(database.get_db)
):
    bundle = _montar_bundle_rnds_completo(cidadao_id, cnes, db)
    outcome = validar_bundle_rnds(bundle)
    erros = [i for i in outcome["issue"] if i["severity"] in ("error", "fatal")]
    return JSONResponse(status_code=422 if erros else 200, content=outcome)


# ==========================================
# 4. MÓDULOS DE CONEXÃO COM O SUS (RNDS)
# ==========================================

def obter_token_rnds() -> str:
    cert_path = os.getenv("RNDS_CERT_PATH", "certificado.pem")

    if not os.path.exists(cert_path):
        raise HTTPException(
            status_code=500,
            detail=f"Arquivo de certificado ICP-Brasil não encontrado em: {cert_path}"
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
def enviar_dados_para_sus(
    cidadao_id: int,
    profissional_cns: str,
    cnes: str = Query(default=DEFAULT_CNES, description="Código CNES de 7 dígitos da unidade solicitante"),
    db: Session = Depends(database.get_db)
):
    bundle_data = _montar_bundle_rnds_completo(cidadao_id, cnes, db)
    outcome = validar_bundle_rnds(bundle_data)
    erros = [i for i in outcome["issue"] if i["severity"] in ("error", "fatal")]

    if erros:
        return JSONResponse(status_code=422, content=outcome)

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
                "operation_outcome_local": outcome,
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
    cpf_limpo = _somente_digitos(cpf)

    headers = {
        "Accept": "application/json",
        "X-Authorization-Server": f"Bearer {access_token}",
        "Authorization": profissional_cns
    }

    try:
        response = requests.get(
            f"{EHR_BASE_URL}/Patient",
            params={"identifier": f"{RNDS_NAMING_SYSTEMS['cpf']}|{cpf_limpo}"},
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
