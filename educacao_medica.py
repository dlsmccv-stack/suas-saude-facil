from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import database

router = APIRouter()

@router.get("/")
def listar_educacao():
    return {"mensagem": "Módulo de Educação Médica & Indústria Farmacêutica Operacional"}
