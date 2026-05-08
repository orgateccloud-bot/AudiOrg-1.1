"""
Cria o usuário admin inicial diretamente no banco SQLAlchemy.

Diferente do endpoint /auth/seed (que exige header X-Seed-Token e env
ADMIN_INITIAL_PASSWORD), este script é interativo e roda local —
ideal para bootstrap de dev. NÃO usar em produção.

Uso:
    python scripts/seed_admin.py                       # interativo
    python scripts/seed_admin.py admin@orgatec.com.br MinhaSenha123
"""
from __future__ import annotations

import getpass
import sys
from pathlib import Path

# Garante que a raiz do projeto está no sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Carrega config.env antes de importar o resto
import os
for nome in ("config.env", ".env"):
    p = ROOT / nome
    if not p.exists():
        continue
    for linha in p.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        k, _, v = linha.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v
    break

from api.auth.security import hash_password  # noqa: E402
from nfa_extractor.infrastructure.database_v2 import (  # noqa: E402
    Base, SessionLocal, User, engine,
)


def main() -> int:
    # Garante schema
    Base.metadata.create_all(bind=engine)

    # Args ou prompt interativo
    if len(sys.argv) >= 3:
        email, senha = sys.argv[1], sys.argv[2]
        nome = sys.argv[3] if len(sys.argv) >= 4 else "Administrador ORGATEC"
    else:
        print(">> Bootstrap de admin (banco local)")
        email = input("E-mail [admin@orgatec.com.br]: ").strip() or "admin@orgatec.com.br"
        nome = input("Nome [Administrador ORGATEC]: ").strip() or "Administrador ORGATEC"
        senha = getpass.getpass("Senha (min 8 chars): ").strip()
        if len(senha) < 8:
            print("ERRO: senha precisa ter ao menos 8 caracteres.")
            return 2

    db = SessionLocal()
    try:
        existente = db.query(User).filter(User.email == email).first()
        if existente:
            existente.hashed_password = hash_password(senha)
            existente.role = "admin"
            existente.is_active = True
            existente.nome = nome
            db.commit()
            print(f"[OK] admin atualizado: {email} (id={existente.id})")
            return 0

        admin = User(
            nome=nome,
            email=email,
            hashed_password=hash_password(senha),
            role="admin",
            is_active=True,
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)
        print(f"[OK] admin criado: {email} (id={admin.id})")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
