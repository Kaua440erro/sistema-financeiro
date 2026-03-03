from flask import Flask, render_template, request, redirect, send_file
import os
import psycopg2
from datetime import datetime
from dotenv import load_dotenv

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.units import inch

# Backend correto do Matplotlib para servidor
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# =============================
# CARREGAR VARIÁVEIS DE AMBIENTE
# =============================
load_dotenv()

app = Flask(__name__)

# =============================
# CONFIGURAÇÃO DO BANCO (NEON)
# =============================

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL não encontrada. Verifique seu arquivo .env")

def get_connection():
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

    conn.commit()
    cursor.close()
    conn.close()

criar_banco()

# =============================
# FUNÇÃO RESUMO
# =============================

def calcular_resumo(registros):
    receitas = sum(float(r[3]) for r in registros if r[2] == "receita")
    despesas = sum(float(r[3]) for r in registros if r[2] == "despesa")
    saldo = receitas - despesas
    return receitas, despesas, saldo

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

        cursor.execute(
            "INSERT INTO registros (descricao, tipo, valor, data) VALUES (%s, %s, %s, %s)",
            (descricao, tipo, valor, data)
        )
        conn.commit()
        cursor.close()
        conn.close()
        return redirect("/")

    cursor.execute("SELECT * FROM registros ORDER BY data DESC")
    registros = cursor.fetchall()

    cursor.close()
    conn.close()

    receitas, despesas, saldo = calcular_resumo(registros)

    return render_template(
        "index.html",
        registros=registros,
        receitas=receitas,
        despesas=despesas,
        saldo=saldo
    )

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

    receitas, despesas, saldo = calcular_resumo(registros)

    file_path = "relatorio_financeiro.pdf"
    grafico_path = "grafico_temp.png"

    doc = SimpleDocTemplate(file_path)
    elementos = []
    styles = getSampleStyleSheet()

    elementos.append(Paragraph("Relatório Financeiro", styles['Title']))
    elementos.append(Spacer(1, 0.3 * inch))

    # Tabela principal
    dados = [["Data", "Descrição", "Tipo", "Valor (R$)"]]
    for r in registros:
        dados.append([
            r[4].strftime("%d/%m/%Y"),
            r[1],
            r[2].capitalize(),
            f"{float(r[3]):.2f}"
        ])

    tabela = Table(dados, colWidths=[1.2 * inch, 2 * inch, 1 * inch, 1.2 * inch])
    tabela.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1F3A93')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (-1, 1), (-1, -1), 'RIGHT'),
    ]))

    elementos.append(tabela)
    elementos.append(Spacer(1, 0.5 * inch))

    # Gráfico
    plt.figure()
    plt.bar(['Receitas', 'Despesas'], [receitas, despesas])
    plt.title('Receitas vs Despesas')
    plt.savefig(grafico_path)
    plt.close()

    elementos.append(Image(grafico_path, width=4 * inch, height=3 * inch))
    elementos.append(Spacer(1, 0.5 * inch))

    # Resumo
    resumo = [
        ["Total Receitas", f"R$ {receitas:.2f}"],
        ["Total Despesas", f"R$ {despesas:.2f}"],
        ["Saldo Final", f"R$ {saldo:.2f}"]
    ]

    resumo_tabela = Table(resumo, colWidths=[3 * inch, 2 * inch])
    resumo_tabela.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#D5DBDB')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
    ]))

    elementos.append(resumo_tabela)

    doc.build(elementos)

    if os.path.exists(grafico_path):
        os.remove(grafico_path)

    return send_file(file_path, as_attachment=True)

# =============================
# EXECUÇÃO
# =============================

if __name__ == "__main__":
    app.run(debug=True)