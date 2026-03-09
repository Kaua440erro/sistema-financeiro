from flask import Flask, render_template, request, redirect, send_file
import sqlite3
from datetime import datetime
from reportlab.pdfgen import canvas
import io

app = Flask(__name__)

DB = "financeiro.db"


def conectar():
    return sqlite3.connect(DB)


def criar_tabela():
    conn = conectar()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS registros (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        descricao TEXT,
        tipo TEXT,
        valor REAL,
        data DATE
    )
    """)

    conn.commit()
    conn.close()


criar_tabela()


@app.route("/", methods=["GET", "POST"])
def index():

    conn = conectar()
    c = conn.cursor()

    if request.method == "POST":

        descricao = request.form["descricao"]
        tipo = request.form["tipo"]
        valor = float(request.form["valor"])
        data = request.form["data"]

        c.execute(
            "INSERT INTO registros (descricao, tipo, valor, data) VALUES (?, ?, ?, ?)",
            (descricao, tipo, valor, data),
        )

        conn.commit()
        return redirect("/")

    c.execute("SELECT * FROM registros ORDER BY data DESC")
    registros = c.fetchall()

    receitas = sum(r[3] for r in registros if r[2] == "receita")
    despesas = sum(r[3] for r in registros if r[2] == "despesa")
    saldo = receitas - despesas

    conn.close()

    return render_template(
        "index.html",
        registros=registros,
        receitas=receitas,
        despesas=despesas,
        saldo=saldo,
    )


@app.route("/historico")
def historico():

    conn = conectar()
    c = conn.cursor()

    c.execute("SELECT * FROM registros ORDER BY data DESC")
    registros = c.fetchall()

    conn.close()

    return render_template("historico.html", registros=registros)


@app.route("/comparativo")
def comparativo():

    conn = conectar()
    c = conn.cursor()

    c.execute("""
    SELECT strftime('%m', data) as mes,
    SUM(CASE WHEN tipo='receita' THEN valor ELSE 0 END),
    SUM(CASE WHEN tipo='despesa' THEN valor ELSE 0 END)
    FROM registros
    GROUP BY mes
    """)

    dados = c.fetchall()

    meses = []
    receitas = []
    despesas = []

    for d in dados:
        meses.append(d[0])
        receitas.append(d[1])
        despesas.append(d[2])

    conn.close()

    return render_template(
        "comparativo.html",
        meses=meses,
        receitas=receitas,
        despesas=despesas
    )


@app.route("/fechar_mes")
def fechar_mes():

    conn = conectar()
    c = conn.cursor()

    c.execute("DELETE FROM registros")

    conn.commit()
    conn.close()

    return redirect("/")


@app.route("/exportar_pdf")
def exportar_pdf():

    conn = conectar()
    c = conn.cursor()

    c.execute("SELECT * FROM registros ORDER BY data DESC")
    registros = c.fetchall()

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)

    y = 800
    pdf.drawString(200, 820, "Relatório Financeiro")

    for r in registros:

        linha = f"{r[4]} | {r[1]} | {r[2]} | R$ {r[3]}"
        pdf.drawString(50, y, linha)

        y -= 20

        if y < 50:
            pdf.showPage()
            y = 800

    pdf.save()

    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="relatorio_financeiro.pdf",
        mimetype="application/pdf",
    )


if __name__ == "__main__":
    app.run(debug=True)