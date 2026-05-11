"""ORGATEC – Rotas de Clientes (CRUD protegido por JWT)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.auth.security import TokenData, get_current_user
from api.dependencies import get_db
from api.schemas import ClienteCreate, ClienteResponse
from nfa_extractor.infrastructure.database_v2 import Cliente

router = APIRouter(prefix="/clientes", tags=["Clientes"])


@router.get("/", response_model=list[ClienteResponse])
def listar_clientes(
    db: Session = Depends(get_db),
    _: TokenData = Depends(get_current_user),
):
    return db.query(Cliente).all()


@router.post("/", status_code=201, response_model=ClienteResponse)
def criar_cliente(
    client: ClienteCreate,
    db: Session = Depends(get_db),
    _: TokenData = Depends(get_current_user),
):
    if db.query(Cliente).filter_by(cpf_cnpj=client.cpf_cnpj).first():
        raise HTTPException(status_code=409, detail="CPF/CNPJ já cadastrado.")
    novo = Cliente(nome=client.nome, cpf_cnpj=client.cpf_cnpj)
    db.add(novo)
    db.commit()
    db.refresh(novo)
    return novo


@router.delete("/{client_id}", status_code=204)
def remover_cliente(
    client_id: int,
    db: Session = Depends(get_db),
    _: TokenData = Depends(get_current_user),
):
    cliente = db.query(Cliente).filter_by(id=client_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    db.delete(cliente)
    db.commit()
