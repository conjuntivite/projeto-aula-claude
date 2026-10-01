import csv
import io

from app.validacao import EXPERIENCIAS

CABECALHO = ["Nome", "E-mail", "Curso", "Período", "Experiência com IA", "Inscrito em"]


def neutralizar(valor) -> str:
    # Decisão 8 (CSV): célula que começa com = + - @ tab ou CR vira fórmula no Excel.
    # O apóstrofo força texto. Protege quem abre o arquivo.
    s = str(valor)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def gerar_csv(inscritos) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    w.writerow(CABECALHO)
    for i in inscritos:
        w.writerow([neutralizar(i["nome"]), neutralizar(i["email"]), neutralizar(i["curso"]),
                    f"{i['periodo']}º", EXPERIENCIAS[i["experiencia"]], i["criado_em"]])
    return "﻿" + buf.getvalue()  # BOM: o Excel pt-BR reconhece UTF-8
