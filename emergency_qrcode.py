from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import database

router = APIRouter()

@router.get("/")
def listar_emergencia():
    return {"mensagem": "Módulo de QR Code de Emergência & SAMU Operacional"}
