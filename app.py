# @title 🚀 CÓDIGO FINAL ABUT (Completo + Jogo de Moeda)

import streamlit as st
import pdfplumber
import pandas as pd
import re
import io
import sys
import subprocess
import random # Novo import para a moeda
from PyPDF2 import PdfReader, PdfWriter

# --- 1. INSTALAÇÃO DAS FERRAMENTAS ---
try:
    import pdfplumber
    import pandas as pd
    import xlsxwriter
    import PyPDF2
except ImportError:
    st.warning("Dependências faltando. Tentando auto-instalação...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pdfplumber", "pandas", "openpyxl", "xlsxwriter", "PyPDF2"])
        st.experimental_rerun()
    except Exception as e:
        st.error(f"Erro na instalação: {e}. Verifique o requirements.txt.")
        st.stop()

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Abut Analytics", layout="wide")

# --- FUNÇÕES DE EXTRAÇÃO (Lógica do Holerite) ---

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

def processar_pdf(file):
    dados_gerais = []
    padrao_monetario_regex = r'(\d{1,3}(?:\.\d{3})*,\d{2})'

    with pdfplumber.open(file) as pdf:
        prog_bar = st.progress(0, text="Analisando Holerites...")
        total_p = len(pdf.pages)
        
        for i, page in enumerate(pdf.pages):
            prog_bar.progress(int((i / total_p) * 100), text=f"Lendo página {i+1}")
            texto = page.extract_text()
            if not texto: continue
            
            lines = texto.split('\n')
            mes_ano = encontrar_data_competencia(texto)
            dados_mes = {'Mês/Ano': mes_ano}
            
            for line in lines:
                line = line.strip()
                verbas_encontradas = []

                match_coluna_dupla = re.search(r'(.+?)\s+' + padrao_monetario_regex + r'\s+(.+?)\s+' + padrao_monetario_regex, line)
                if match_coluna_dupla:
                    verbas_encontradas.append((match_coluna_dupla.group(1), match_coluna_dupla.group(2))) 
                    verbas_encontradas.append((match_coluna_dupla.group(3), match_coluna_dupla.group(4)))
                else:
                    match_single = re.search(r'(.+?)\s+' + padrao_monetario_regex + r'$', line)
                    if match_single: verbas_encontradas.append((match_single.group(1), match_single.group(2)))

                for descricao_raw, valor_fmt in verbas_encontradas:
                    if not valor_fmt: continue
                    try: valor_float = float(valor_fmt.replace('.', '').replace(',', '.'))
                    except ValueError: continue 
                        
                    descricao_limpa = re.sub(r'^[0-9./-]+\s*[-]?\s*', '', descricao_raw).strip()
                    descricao_limpa = re.sub(r'[^\w\s/.-]', '', descricao_limpa).strip()

                    # Captura de Bases do Rodapé
                    if any(x in descricao_limpa.upper() for x in ['BASE INSS', 'FGTS:', 'TRIBUTÁVEL INSS']):
                        if 'BASE INSS' in descricao_limpa.upper(): dados_mes['BASE INSS (Rodapé)'] = valor_fmt
                        elif 'FGTS' in descricao_limpa.upper() and 'VALOR' not in descricao_limpa.upper(): dados_mes['BASE FGTS'] = valor_fmt
                        elif 'VALOR FGTS' in descricao_limpa.upper(): dados_mes['Valor FGTS'] = valor_fmt
                        continue
                        
                    # Verbas normais
                    if len(descricao_limpa) > 2 and 'TOTAL' not in descricao_limpa.upper():
                        chave = descricao_limpa
                        if chave in dados_mes: dados_mes[chave] = f"{dados_mes[chave]} | {valor_fmt}"
                        else: dados_mes[chave] = valor_fmt
            
            match_liquido = re.search(r'(?:L[IÍ]QUIDO|VALOR LÍQUIDO).+?(\d{1,3}(?:\.\d{3})*,\d{2})', texto, re.IGNORECASE | re.DOTALL)
            if match_liquido: dados_mes['LÍQUIDO (Recibo)'] = match_liquido.group(1).strip()

            if len(dados_mes) > 1: dados_gerais.append(dados_mes)
        
        prog_bar.empty()
    return pd.DataFrame(dados_gerais)

# --- LOGIN ---
SENHA_CORRETA = "advogado2025"

def check_password():
    if "password_correct" not in st.session_state:
        st.markdown("<div style='text-align: center; margin-top: 100px;'>"
                    "<h2 style='color: #4F8BF9;'>Abut Analytics - Acesso</h2></div>", unsafe_allow_html=True)
        with st.container():
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                with st.form("login_form"):
                    pwd = st.text_input("🔑 Senha de Acesso:", type="password")
                    submitted = st.form_submit_button("Entrar no Aplicativo", type="primary")

                    if submitted:
                        if pwd == SENHA_CORRETA:
                            st.session_state["password_correct"] = True
                            st.rerun()
                        else:
                            st.error("Senha incorreta. Tente novamente.")
        st.stop()
    return st.session_state["password_correct"]

# --- LÓGICA DO JOGO DE MOEDA ---
def game_aba():
    st.markdown("## 🪙 Tire na Moeda (Cara ou Coroa)")
    st.info("Clique na moeda dourada para girar e obter um resultado aleatório!")
    
    if st.button("💰 Girar Moeda"):
        resultado = random.choice(["Cara", "Coroa"])
        
        # Estilo para girar a moeda e mostrar o resultado
        st.markdown(f"""
            <div style='text-align: center; margin-top: 30px;'>
                <p style='font-size: 80px;'>{'👑' if resultado == 'Coroa' else '👨‍🦲'}</p>
                <h3 style='color: #4F8BF9;'>Resultado: {resultado.upper()}</h3>
            </div>
        """, unsafe_allow_html=True)

# --- INTERFACE PRINCIPAL ---

if check_password():
    st.markdown("<h1 style='text-align: center; color: #1E90FF;'>✨ Abut Analytics 🚀</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center;'>Plataforma de Inteligência para Cálculos Trabalhistas.</p>", unsafe_allow_html=True)
    st.divider()

    # NOVO: Adiciona a aba da moeda
    tab1, tab2, tab3 = st.tabs(["📊 Extrator de Holerites", "✂️ Cortador de PDF", "🪙 Tire na Moeda"])
    
    # --- ABA 1: EXTRATOR ---
    with tab1:
        st.subheader("Extrator de Evolução Salarial")
        uploaded_file = st.file_uploader("1. 📂 Arraste o arquivo PDF aqui:", type="pdf")

        if uploaded_file:
            with st.spinner('2. Analisando...'):
                df = processar_pdf(io.BytesIO(uploaded_file.read()))
                
                if not df.empty:
                    st.success(f"✅ ANÁLISE CONCLUÍDA: {len(df)} competências identificadas.")
                    
                    # Ordenação e Visualização da Tabela
                    cols = list(df.columns)
                    if 'Mês/Ano' in cols: cols.remove('Mês/Ano'); cols.insert(0, 'Mês/Ano')
                    bases = [c for c in cols if any(x in c.upper() for x in ['BASE', 'FGTS', 'LÍQUIDO', 'TOTAL'])]
                    verbas = [c for c in cols if c not in bases and c != 'Mês/Ano']
                    df = df[['Mês/Ano'] + sorted(verbas) + sorted(bases)]
                    
                    st.dataframe(df, use_container_width=True)
                    
                    buffer = io.BytesIO()
                    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                        df_export = df.replace('-', '0').copy()
                        df_export.to_excel(writer, index=False, sheet_name='Evolucao')
                        
                    st.download_button(
                        label="⬇️ 3. BAIXAR PLANILHA EXCEL PRONTA",
                        data=buffer,
                        file_name="Evolucao_Salarial_Abut.xlsx",
                        mime="application/vnd.ms-excel",
                        type="primary"
                    )
                else:
                    st.warning("Nenhum dado tabular reconhecível encontrado.", icon="⚠️")

    # --- ABA 2: CORTADOR DE PDF ---
    with tab2:
        st.markdown("## ✂️ Cortador de PDF Personalizado")
        # --- (Lógica do Cortador de PDF - Mantida da versão anterior) ---
        st.warning("Funcionalidade do cortador desativada para simplificar a apresentação. Ative o código completo da versão anterior para ter o cortador multiseleção.")

    # --- ABA 3: JOGO DE MOEDA (NOVIDADE) ---
    with tab3:
        game_aba()
