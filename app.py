import streamlit as st
import pdfplumber
import pandas as pd
import re
import io
import sys
import subprocess
from PyPDF2 import PdfReader, PdfWriter

# --- 1. AUTO-INSTALAÇÃO (PREVENÇÃO DE ERROS) ---
try:
    import pdfplumber
    import xlsxwriter
    import PyPDF2
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pdfplumber", "pandas", "openpyxl", "xlsxwriter", "PyPDF2"])
    import pdfplumber
    import PyPDF2

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Ferramentas Jurídicas", layout="wide")

# --- FUNÇÕES DE EXTRAÇÃO (CALCULADORA) ---
def extrair_valor_monetario(texto):
    padrao = r'(\d{1,3}(?:\.\d{3})*,\d{2})'
    encontrados = re.findall(padrao, texto)
    return encontrados[-1] if encontrados else None

def encontrar_data_competencia(texto):
    linhas_iniciais = texto.split('\n')[:15]
    texto_cabecalho = "\n".join(linhas_iniciais).upper()
    
    match_rotulo = re.search(r'(?:PER[ÍI]ODO|REF|M[ÊE]S/ANO|COMPET[ÊE]NCIA|DATA)[:\.\s-]*(\d{2}/\d{4}|[A-ZÇÃÕ]{3,9}[/\s-]+\d{4})', texto_cabecalho)
    if match_rotulo: return match_rotulo.group(1).strip()
    
    match_solto = re.search(r'\b(\d{2}/\d{4}|[A-ZÇÃÕ]{3,9}/\d{4})\b', texto_cabecalho)
    if match_solto: return match_solto.group(1).strip()
    
    match_titulo = re.search(r'\b(JANEIRO|FEVEREIRO|MAR[ÇC]O|ABRIL|MAIO|JUNHO|JULHO|AGOSTO|SETEMBRO|OUTUBRO|NOVEMBRO|DEZEMBRO)\s+(\d{4})\b', texto_cabecalho)
    if match_titulo: return f"{match_titulo.group(1)}/{match_titulo.group(2)}"
    
    return "Não Identificado"

def processar_pdf_extracao(file):
    dados_gerais = []
    padrao_monetario_regex = r'(\d{1,3}(?:\.\d{3})*,\d{2})'

    with pdfplumber.open(file) as pdf:
        # Barra de progresso apenas na aba de extração
        my_bar = st.progress(0, text="Lendo PDF...")
        total_pages = len(pdf.pages)
        
        for i, page in enumerate(pdf.pages):
            my_bar.progress(int((i / total_pages) * 100), text=f"Lendo página {i+1}")
            texto = page.extract_text()
            if not texto: continue
            lines = texto.split('\n')
            
            mes_ano = encontrar_data_competencia(texto)
            if mes_ano == "Não Identificado" and len(dados_gerais) > 0:
                mes_ano = dados_gerais[-1]['Mês/Ano'] + " (Cont.)"
            
            dados_mes = {'Mês/Ano': mes_ano}
            
            for line in lines:
                line = line.strip()
                if not line: continue
                verbas_encontradas = []

                match_coluna_dupla = re.search(r'(.+?)\s+' + padrao_monetario_regex + r'\s+(.+?)\s+' + padrao_monetario_regex, line)
                if match_coluna_dupla:
                    verbas_encontradas.append((match_coluna_dupla.group(1), match_coluna_dupla.group(2))) 
                    verbas_encontradas.append((match_coluna_dupla.group(3), match_coluna_dupla.group(4)))
                else:
                    match_single = re.search(r'(.+?)\s+' + padrao_monetario_regex + r'$', line)
                    if match_single:
                        verbas_encontradas.append((match_single.group(1), match_single.group(2)))

                for descricao_raw, valor_fmt in verbas_encontradas:
                    if not valor_fmt: continue
                    descricao_limpa = re.sub(r'^[0-9./-]+\s*[-]?\s*', '', descricao_raw).strip()
                    descricao_limpa = re.sub(r'[^\w\s/.-]', '', descricao_limpa).strip()
                    if len(descricao_limpa) < 2: continue
                    if "201" in valor_fmt and "," not in valor_fmt: continue 

                    if any(x in descricao_limpa.upper() for x in ['BASE', 'FGTS', 'TRIBUTÁVEL', 'LÍQUIDO', 'LIQUIDO', 'TOTAL']):
                        if 'BASE INSS' in descricao_limpa.upper(): dados_mes['BASE INSS (Rodapé)'] = valor_fmt
                        elif 'FGTS' in descricao_limpa.upper() and 'VALOR' not in descricao_limpa.upper() and 'BASE' in descricao_limpa.upper(): dados_mes['BASE FGTS'] = valor_fmt
                        elif 'VALOR FGTS' in descricao_limpa.upper() or 'DEPÓSITO FGTS' in descricao_limpa.upper(): dados_mes['Valor FGTS'] = valor_fmt
                        elif 'LÍQUIDO' in descricao_limpa.upper() or 'LIQUIDO' in descricao_limpa.upper(): dados_mes['LÍQUIDO (Recibo)'] = valor_fmt
                        continue
                        
                    if len(descricao_limpa) > 2 and 'TOTAL' not in descricao_limpa.upper():
                        chave = descricao_limpa
                        if chave in dados_mes: dados_mes[chave] = f"{dados_mes[chave]} | {valor_fmt}"
                        else: dados_mes[chave] = valor_fmt
            
            if 'LÍQUIDO (Recibo)' not in dados_mes:
                 match_liq = re.search(r'(?:L[IÍ]QUIDO|VALOR LÍQUIDO).+?(\d{1,3}(?:\.\d{3})*,\d{2})', texto, re.IGNORECASE | re.DOTALL)
                 if match_liq: dados_mes['LÍQUIDO (Recibo)'] = match_liq.group(1)

            if len(dados_mes) > 1: dados_gerais.append(dados_mes)
        my_bar.empty()
    return pd.DataFrame(dados_gerais)

# --- LOGIN ---
def check_password():
    if "password_correct" not in st.session_state:
        st.text_input("Senha:", type="password", key="password_input", on_change=lambda: st.session_state.update(password_correct=st.session_state.password_input == "advogado2025"))
        return False
    return st.session_state["password_correct"]

# --- INTERFACE PRINCIPAL ---
if check_password():
    
    # Menu lateral para trocar de ferramenta
    st.sidebar.title("🧰 Menu de Ferramentas")
    escolha = st.sidebar.radio("Escolha o que fazer:", ["📊 Extrator de Holerites", "✂️ Cortar/Dividir PDF"])

    # --- ABA 1: EXTRATOR (Seu código original melhorado) ---
    if escolha == "📊 Extrator de Holerites":
        st.markdown("<h1 style='color: #1E90FF;'>📊 Extrator de Evolução Salarial</h1>", unsafe_allow_html=True)
        st.info("Use esta aba para gerar o Excel dos holerites.")
        
        uploaded_file = st.file_uploader("Solte o PDF dos Holerites aqui", type="pdf", key="upload_extrator")

        if uploaded_file:
            try:
                bytes_data = uploaded_file.getvalue()
                file_buffer = io.BytesIO(bytes_data)
                df = processar_pdf_extracao(file_buffer)
                
                if not df.empty:
                    st.success(f"✅ Sucesso! {len(df)} competências extraídas.")
                    
                    cols = list(df.columns)
                    if 'Mês/Ano' in cols: cols.remove('Mês/Ano'); cols.insert(0, 'Mês/Ano')
                    bases = [c for c in cols if any(x in c.upper() for x in ['BASE', 'FGTS', 'LÍQUIDO', 'TOTAL'])]
                    verbas = [c for c in cols if c not in bases and c != 'Mês/Ano']
                    df = df[['Mês/Ano'] + sorted(verbas) + sorted(bases)]
                    
                    st.dataframe(df, use_container_width=True)
                    
                    buffer = io.BytesIO()
                    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                        df.to_excel(writer, index=False)
                    
                    st.download_button("⬇️ Baixar Excel", data=buffer, file_name="Evolucao.xlsx", mime="application/vnd.ms-excel", type="primary")
                    
                    with st.expander("🕵️‍♂️ Ver Texto Bruto (Para Debug)"):
                        pdf = pdfplumber.open(io.BytesIO(bytes_data))
                        st.text(pdf.pages[0].extract_text())
                else:
                    st.error("Nenhum dado encontrado.")
            except Exception as e:
                st.error(f"Erro técnico: {e}")

    # --- ABA 2: CORTAR PDF (Nova Funcionalidade) ---
    elif escolha == "✂️ Cortar/Dividir PDF":
        st.markdown("<h1 style='color: #FF4B4B;'>✂️ Cortador de PDF</h1>", unsafe_allow_html=True)
        st.info("Use esta aba para separar páginas ou dividir um PDF grande.")

        pdf_corte = st.file_uploader("Solte o PDF que deseja cortar", type="pdf", key="upload_corte")

        if pdf_corte:
            reader = PdfReader(pdf_corte)
            total_paginas = len(reader.pages)
            st.write(f"📄 O arquivo possui **{total_paginas} páginas**.")

            modo_corte = st.radio("Como deseja cortar?", ["Selecionar Intervalo (ex: pág 1 a 5)", "Selecionar Páginas Específicas (ex: 1, 3, 5)"])

            if modo_corte == "Selecionar Intervalo (ex: pág 1 a 5)":
                col1, col2 = st.columns(2)
                inicio = col1.number_input("Página Inicial", min_value=1, max_value=total_pages, value=1)
                fim = col2.number_input("Página Final", min_value=inicio, max_value=total_pages, value=min(5, total_pages))
                
                paginas_selecionadas = list(range(inicio-1, fim)) # Python começa em 0
            
            else:
                paginas_input = st.text_input("Digite os números das páginas separados por vírgula (ex: 1, 5, 10)")
                paginas_selecionadas = []
                if paginas_input:
                    try:
                        paginas_selecionadas = [int(p.strip())-1 for p in paginas_input.split(",") if p.strip().isdigit()]
                        paginas_selecionadas = [p for p in paginas_selecionadas if 0 <= p < total_paginas]
                    except:
                        st.error("Formato inválido. Use números e vírgulas.")

            if st.button("✂️ Cortar e Baixar PDF"):
                if not paginas_selecionadas:
                    st.warning("Nenhuma página selecionada.")
                else:
                    writer = PdfWriter()
                    for p in paginas_selecionadas:
                        writer.add_page(reader.pages[p])
                    
                    # Salvar em memória
                    output_buffer = io.BytesIO()
                    writer.write(output_buffer)
                    pdf_bytes = output_buffer.getvalue()
                    
                    st.success("PDF Cortado com sucesso!")
                    st.download_button(
                        label="⬇️ Baixar PDF Cortado",
                        data=pdf_bytes,
                        file_name="documento_cortado.pdf",
                        mime="application/pdf",
                        type="primary"
                    )
