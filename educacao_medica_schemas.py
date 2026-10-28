from pydantic import BaseModel, Field
from datetime import datetime

class EducacaoMedicaCreate(BaseModel):
    titulo_curso: str = Field(..., description="Título do curso ou módulo formativo", example="Manejo Clínico Avançado em Urgências")
    especialidade: str = Field(..., description="Especialidade médica ou área de atuação", example="Urgência & Emergência")
    parceiro_industria: str = Field(..., description="Entidade ou parceiro industrial patrocinador/responsável", example="Laboratório Farmacêutico XYZ")
    descricao_conteudo: str = Field(..., description="Descrição detalhada do conteúdo programático", example="Abordagem prática baseada em evidências para suporte avançado de vida.")
    link_material_estudo: str = Field(..., description="Link de acesso aos materiais ou aulas do curso", example="https://ead.saudefacil.org/material/urgencias")
    pontos_credito_cme: int = Field(..., description="Créditos de Educação Médica Continuada (CME) atribuídos", example=10)

    class Config:
        json_schema_extra = {
            "example": {
                "titulo_curso": "Manejo Clínico Avançado em Urgências",
                "especialidade": "Urgência & Emergência",
                "parceiro_industria": "Laboratório Farmacêutico XYZ",
                "descricao_conteudo": "Abordagem prática baseada em evidências para suporte avançado de vida.",
                "link_material_estudo": "https://ead.saudefacil.org/material/urgencias",
                "pontos_credito_cme": 10
            }
        }

class EducacaoMedicaResponse(BaseModel):
    id: int = Field(..., description="Identificador único do curso na base de dados", example=1)
    titulo_curso: str = Field(..., description="Título do curso", example="Manejo Clínico Avançado em Urgências")
    especialidade: str = Field(..., description="Especialidade médica", example="Urgência & Emergência")
    parceiro_industria: str = Field(..., description="Parceiro da indústria", example="Laboratório Farmacêutico XYZ")
    descricao_conteudo: str = Field(..., description="Descrição do conteúdo", example="Abordagem prática baseada em evidências para suporte avançado de vida.")
    link_material_estudo: str = Field(..., description="Link do material", example="https://ead.saudefacil.org/material/urgencias")
    pontos_credito_cme: int = Field(..., description="Créditos CME", example=10)
    data_publicacao: datetime = Field(..., description="Data e hora de publicação do curso", example="2026-10-28T14:30:00")

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 1,
                "titulo_curso": "Manejo Clínico Avançado em Urgências",
                "especialidade": "Urgência & Emergência",
                "parceiro_industria": "Laboratório Farmacêutico XYZ",
                "descricao_conteudo": "Abordagem prática baseada em evidências para suporte avançado de vida.",
                "link_material_estudo": "https://ead.saudefacil.org/material/urgencias",
                "pontos_credito_cme": 10,
                "data_publicacao": "2026-10-28T14:30:00"
            }
        }
