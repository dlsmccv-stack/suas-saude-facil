from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import database

router = APIRouter()

@router.get("/")
def listar_fhir():
    return {"mensagem": "Módulo de Interoperabilidade FHIR R4 Operacional"}
