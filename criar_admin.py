import getpass
import sys

from app import db, seguranca


def main() -> int:
    db.iniciar()
    usuario = input("Usuário: ").strip()
    senha = getpass.getpass(f"Senha (mínimo {seguranca.SENHA_MINIMA} caracteres): ")
    if getpass.getpass("Repita a senha: ") != senha:
        print("As senhas não conferem.")
        return 1
    try:
        with db.transacao() as con:
            seguranca.criar_admin(con, usuario, senha)
    except seguranca.UsuarioExistente:
        print("Esse usuário já existe.")
        return 1
    except ValueError as e:
        print(e)
        return 1
    print("Admin criado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
