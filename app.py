import streamlit as st
import os
import sys
import subprocess

# --- 1. FORÇAR INSTALAÇÃO DAS FERRAMENTAS (AUTO-CORREÇÃO) ---
# Isso garante que funcione mesmo se o requirements.txt falhar
def install_packages():
    packages = ["pdfplumber", "pandas", "openpyxl", "xlsxwriter"]
    for package in packages:
        try:
            __import__(package)
        except ImportError:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])

install_packages()

# Agora importamos as bibliotecas com segurança
import pdfplumber
import pandas as pd
import re
import io
import xlsxwriter

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Calculadora de Evolução", layout="wide")

# --- FUNÇÕES DE EXTRAÇÃO ---

def extrair_valor_monetario(texto):
    """Localiza e retorna valores monetários no padrão BR (X.XXX,XX)."""
    padrao = r'(\d{1,3}(?:\.\d{3})*,\d{2})'
    encontrados = re.findall(padrao, texto)
    return encontrados[-1] if encontrados else None

def processar_pdf(file):
    """Lê o PDF e extrai dados com lógica de colunas duplas."""
    dados_gerais = []
    padrao_monetario_regex = r'(\d{1,3}(?:\.\d{3})*,\d{2})'

    with pdfplumber.open(file) as pdf:
        st.info(f"Analisando {len(pdf.pages)} páginas do PDF...")
        
        for page in pdf.pages:
            texto = page.extract_text()
            if not texto: continue
            
            lines = texto.split('\n')
            
            # Extração da data
            mes_ano = "Não Identificado"
            match_data = re.search(r'(?:Período|Periodo|Mês/Ano|Data)[:\.\s-]*(\d{2}/\d{4}|[A-ZÀ-ZÇÃÕ]{3,9}[/\s]+\d{4})', texto, re.IGNORECASE)
            if match_data:
                mes_ano = match_data.group(1).strip()
            else:
                match_gen = re.search(r'\b(\d{2}/\d{4})\b', texto)
                if match_gen: mes_ano = match_gen.group(1)
            
            dados_mes = {'Mês/Ano': mes_ano}
            
            for line in lines:
                line = line.strip()
                if not line: continue
                
                verbas_encontradas = []

                # A) TENTA ENCONTRAR DUAS VERBAS NA MESMA LINHA
                match_coluna_dupla = re.search(
                    r'(.+?)\s+' + padrao_monetario_regex + r'\s+(.+?)\s+' + padrao_monetario_regex, 
                    line
                )
                
                if match_coluna_dupla:
                    verbas_encontradas.append((match_coluna_dupla.group(1), match_coluna_dupla.group(2))) 
                    verbas_encontradas.append((match_coluna_dupla.group(3), match_coluna_dupla.group(4)))
                else:
                    # B) TENTA ENCONTRAR VERBA ÚNICA
                    match_single = re.search(r'(.+?)\s+' + padrao_monetario_regex + r'$', line)
                    if match_single:
                        verbas_encontradas.append((match_single.group(1), match_single.group(2)))

                for descricao_raw, valor_fmt in verbas_encontradas:
                    if not valor_fmt: continue
                    
                    try:
                        valor_float = float(valor_fmt.replace('.', '').replace(',', '.'))
                    except:
                        continue

                    descricao_limpa = re.sub(r'^[0-9./-]+\s*[-]?\s*', '', descricao_raw).strip()
                    descricao_limpa = re.sub(r'[^\w\s/.-]', '', descricao_limpa).strip()
                    
                    if len(descricao_limpa) < 2: continue
                    if "PÁGINA" in descricao_limpa.upper(): continue

                    # REGRA CRÍTICA: BASES DO RODAPÉ
                    if any(x in descricao_limpa.upper() for x in ['BASE', 'FGTS', 'TRIBUTÁVEL', 'LÍQUIDO', 'LIQUIDO', 'TOTAL']):
                        if 'BASE INSS' in descricao_limpa.upper() or 'TRIBUTÁVEL INSS' in descricao_limpa.upper():
                            dados_mes['BASE INSS (Rodapé)'] = valor_fmt
                        elif 'FGTS' in descricao_limpa.upper() and 'VALOR' not in descricao_limpa.upper() and 'BASE' in descricao_limpa.upper():
                            dados_mes['BASE FGTS'] = valor_fmt
                        elif 'VALOR FGTS' in descricao_limpa.upper() or 'DEPÓSITO FGTS' in descricao_limpa.upper():
                            dados_mes['Valor FGTS'] = valor_fmt
                        elif 'LÍQUIDO' in descricao_limpa.upper() or 'LIQUIDO' in descricao_limpa.upper():
                             dados_mes['LÍQUIDO (Recibo)'] = valor_fmt
                        continue
                        
                    # Adicionar Rubrica
                    if len(descricao_limpa) > 2 and 'TOTAL' not in descricao_limpa.upper() and valor_float > 0:
                        chave = descricao_limpa
                        if chave in dados_mes:
                            dados_mes[chave] = f"{dados_mes[chave]} | {valor_fmt}"
                        else:
                            dados_mes[chave] = valor_fmt
            
            # Busca Líquido de segurança
            if 'LÍQUIDO (Recibo)' not in dados_mes:
                 match_liq = re.search(r'(?:L[IÍ]QUIDO|VALOR LÍQUIDO).+?(\d{1,3}(?:\.\d{3})*,\d{2})', texto, re.IGNORECASE | re.DOTALL)
                 if match_liq:
                     dados_mes['LÍQUIDO (Recibo)'] = match_liq.group(1)

            if len(dados_mes) > 1: 
                dados_gerais.append(dados_mes)

    return pd.DataFrame(dados_gerais)

# --- LOGIN ---
def check_password():
    def password_entered():
        if st.session_state["password"] == "advogado2025":
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("Senha de Acesso:", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("Senha incorreta.", type="password", on_change=password_entered, key="password")
        return False
    else:
        return True

# --- INTERFACE ---
if check_password():
    st.markdown("<h1 style='text-align: center; color: #1E90FF;'>🌌 Matriz de Evolução Salarial</h1>", unsafe_allow_html=True)
    st.markdown("---")

    uploaded_file = st.file_uploader("📡 INPUT: Transmitir Arquivo PDF", type="pdf")

    if uploaded_file is not None:
        try:
            file_buffer = io.BytesIO(uploaded_file.read())
            df = processar_pdf(file_buffer)

            if not df.empty:
                st.success(f"✅ SUCESSO! {len(df)} competências extraídas.")
                
                # Reorganização das colunas
                cols = list(df.columns)
                if 'Mês/Ano' in cols: cols.remove('Mês/Ano'); cols.insert(0, 'Mês/Ano')
                bases = [c for c in cols if any(x in c.upper() for x in ['BASE', 'FGTS', 'LÍQUIDO', 'TOTAL'])]
                verbas = [c for c in cols if c not in bases and c != 'Mês/Ano']
                cols_finais = ['Mês/Ano'] + sorted(verbas) + sorted(bases)
                # Filtra colunas que existem de fato
                df = df[[c for c in cols_finais if c in df.columns]]

                st.dataframe(df, use_container_width=True)

                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                    df.to_excel(writer, index=False, sheet_name='Evolucao')
                
                st.download_button(
                    label="💾 DOWNLOAD EXCEL",
                    data=buffer,
                    file_name="Evolucao_Salarial.xlsx",
                    mime="application/vnd.ms-excel"
                )
            else:
                st.warning("⚠️ O arquivo foi lido, mas nenhum dado tabular foi encontrado. Verifique se é um PDF pesquisável.")

        except Exception as e:
            st.error(f"❌ Erro: {e}")
