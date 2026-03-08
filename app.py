from flask import Flask, render_template, request, redirect, send_file
import os
import psycopg2
from datetime import datetime
from dotenv import load_dotenv

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

# =============================
# CARREGAR VARIÁVEIS DE AMBIENTE
# =============================
load_dotenv()

app = Flask(__name__)

# =============================
# CONFIGURAÇÃO DO BANCO
# =============================

DATABASE_URL = os.getenv("DATABASE_URL")

# Correção necessária para Render/Postgres
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

def get_connection():
    if not DATABASE_URL:
        raise Exception("DATABASE_URL não configurada")
    return psycopg2.connect(DATABASE_URL)

def criar_banco():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS registros (
        id SERIAL PRIMARY KEY,
        descricao TEXT NOT NULL,
        tipo TEXT NOT NULL,
        valor NUMERIC NOT NULL,
        data DATE NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS meses_fechados (
        id SERIAL PRIMARY KEY,
        mes INTEGER NOT NULL,
        ano INTEGER NOT NULL,
        UNIQUE(mes, ano)
    )
    """)

    conn.commit()
    cursor.close()
    conn.close()

try:
    if DATABASE_URL:
        criar_banco()
except Exception as e:
    print("Erro ao criar banco:", e)

# =============================
# FUNÇÃO RESUMO
# =============================

def calcular_resumo(registros):
    receitas = sum(float(r[3]) for r in registros if r[2] == "receita")
    despesas = sum(float(r[3]) for r in registros if r[2] == "despesa")
    saldo = receitas - despesas
    return receitas, despesas, saldo

# =============================
# VERIFICAR SE MÊS ESTÁ FECHADO
# =============================

def mes_esta_fechado(mes, ano):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT 1 FROM meses_fechados WHERE mes=%s AND ano=%s",
        (mes, ano)
    )

    fechado = cursor.fetchone() is not None

    cursor.close()
    conn.close()

    return fechado

# =============================
# ROTA PRINCIPAL
# =============================

@app.route("/", methods=["GET", "POST"])
def index():

    conn = get_connection()
    cursor = conn.cursor()

    if request.method == "POST":

        descricao = request.form["descricao"]
        tipo = request.form["tipo"]
        valor = float(request.form["valor"])
        data = request.form["data"]

        data_obj = datetime.strptime(data,"%Y-%m-%d")

        if mes_esta_fechado(data_obj.month, data_obj.year):
            return "Este mês já foi fechado e não aceita novos lançamentos."

        cursor.execute(
            "INSERT INTO registros (descricao, tipo, valor, data) VALUES (%s,%s,%s,%s)",
            (descricao, tipo, valor, data)
        )

        conn.commit()
        cursor.close()
        conn.close()

        return redirect("/")

    mes = request.args.get("mes")
    ano = request.args.get("ano")

    query = "SELECT * FROM registros"
    filtros = []
    valores = []

    if mes:
        filtros.append("EXTRACT(MONTH FROM data) = %s")
        valores.append(int(mes))

    if ano:
        filtros.append("EXTRACT(YEAR FROM data) = %s")
        valores.append(int(ano))

    if filtros:
        query += " WHERE " + " AND ".join(filtros)

    query += " ORDER BY data DESC"

    cursor.execute(query, valores)
    registros = cursor.fetchall()

    cursor.close()
    conn.close()

    receitas, despesas, saldo = calcular_resumo(registros)

    fechado = False
    if mes and ano:
        fechado = mes_esta_fechado(int(mes), int(ano))

    return render_template(
        "index.html",
        registros=registros,
        receitas=receitas,
        despesas=despesas,
        saldo=saldo,
        mes=mes,
        ano=ano,
        fechado=fechado
    )

# =============================
# FECHAR MÊS
# =============================

@app.route("/fechar_mes", methods=["POST"])
def fechar_mes():

    mes = int(request.form["mes"])
    ano = int(request.form["ano"])

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO meses_fechados (mes, ano) VALUES (%s,%s) ON CONFLICT DO NOTHING",
        (mes, ano)
    )

    conn.commit()

    cursor.close()
    conn.close()

    return redirect(f"/?mes={mes}&ano={ano}")

# =============================
# HISTÓRICO MENSAL
# =============================

@app.route("/historico")
def historico():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT
        EXTRACT(YEAR FROM data) as ano,
        EXTRACT(MONTH FROM data) as mes,
        SUM(CASE WHEN tipo='receita' THEN valor ELSE 0 END) as receitas,
        SUM(CASE WHEN tipo='despesa' THEN valor ELSE 0 END) as despesas
    FROM registros
    GROUP BY ano, mes
    ORDER BY ano DESC, mes DESC
    """)

    dados = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("historico.html", dados=dados)

# =============================
# COMPARATIVO ENTRE MESES
# =============================

@app.route("/comparativo")
def comparativo():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT
        EXTRACT(MONTH FROM data) as mes,
        SUM(CASE WHEN tipo='receita' THEN valor ELSE 0 END) as receitas,
        SUM(CASE WHEN tipo='despesa' THEN valor ELSE 0 END) as despesas
    FROM registros
    WHERE EXTRACT(YEAR FROM data) = EXTRACT(YEAR FROM CURRENT_DATE)
    GROUP BY mes
    ORDER BY mes
    """)

    dados = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("comparativo.html", dados=dados)

# =============================
# EXPORTAR PDF
# =============================

@app.route("/exportar_pdf")
def exportar_pdf():

    ano = request.args.get("ano")
    mes = request.args.get("mes")

    conn = get_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM registros"
    filtros = []
    valores = []

    if ano:
        filtros.append("EXTRACT(YEAR FROM data) = %s")
        valores.append(int(ano))

    if mes:
        filtros.append("EXTRACT(MONTH FROM data) = %s")
        valores.append(int(mes))

    if filtros:
        query += " WHERE " + " AND ".join(filtros)

    query += " ORDER BY data DESC"

    cursor.execute(query, valores)
    registros = cursor.fetchall()

    cursor.close()
    conn.close()

    file_path = "relatorio_financeiro.pdf"

    doc = SimpleDocTemplate(file_path)

    elementos = []
    styles = getSampleStyleSheet()

    elementos.append(Paragraph("Relatório Financeiro", styles['Title']))
    elementos.append(Spacer(1,20))

    dados = [["Data","Descrição","Tipo","Valor"]]

    for r in registros:
        dados.append([
            r[4].strftime("%d/%m/%Y"),
            r[1],
            r[2],
            f"{float(r[3]):.2f}"
        ])

    tabela = Table(dados)

    tabela.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#1F3A93')),
        ('TEXTCOLOR',(0,0),(-1,0),colors.white),
        ('GRID',(0,0),(-1,-1),0.5,colors.grey)
    ]))

    elementos.append(tabela)

    doc.build(elementos)

    return send_file(file_path, as_attachment=True)

# =============================
# EXECUÇÃO
# =============================

if __name__ == "__main__":
    port = int(os.environ.get("PORT",5000))
    app.run(host="0.0.0.0", port=port)