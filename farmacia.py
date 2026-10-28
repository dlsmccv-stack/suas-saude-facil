from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import database

router = APIRouter()

@router.get("/")
def listar_farmacia():
    return {"mensagem": "Módulo de Farmácia Digital Operacional"}
