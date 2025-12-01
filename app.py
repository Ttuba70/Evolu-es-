import streamlit as st
import sys
import subprocess
import time

# --- 1. AUTO-INSTALAÇÃO (BLINDAGEM CONTRA ERROS) ---
# Este bloco força a instalação das ferramentas se elas não existirem
try:
    import pdfplumber
    import pandas as pd
    import xlsxwriter
except ImportError:
    st.warning("⚠️ Detectei ferramentas faltando. Instalando automaticamente... Aguarde 30 segundos.")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pdfplumber", "pandas", "openpyxl", "xlsxwriter"])
        st.success("✅ Instalação concluída! Atualizando a página...")
        time.sleep(2)
        st.rerun() # Recarrega o site com as ferramentas novas
    except Exception as e:
        st.error(f"Erro na auto-instalação: {e}")
        st.stop()

# Agora importamos com segurança
import pdfplumber
import pandas as pd
import re
import io
from datetime import datetime

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Evolução Salarial Automática", layout="wide")

# --- FUNÇÕES DE EXTRAÇÃO ---
def extrair_valor_monetario(texto):
    padrao = r'(\d{1,3}(?:\.\d{3})*,\d{2})'
    encontrados = re.findall(padrao, texto)
    return encontrados[-1] if encontrados else None

def processar_pdf(file):
    dados_gerais = []
    padrao_monetario_regex = r'(\d{1,3}(?:\.\d{3})*,\d{2})'

    with pdfplumber.open(file) as pdf:
        # Barra de progresso
        progress_text = "Lendo PDF..."
        my_bar = st.progress(0, text=progress_text)
        total_pages = len(pdf.pages)
        
        for i, page in enumerate(pdf.pages):
            my_bar.progress(int((i / total_pages) * 100), text=f"Lendo página {i+1}")
            texto = page.extract_text()
            if not texto: continue
            
            lines = texto.split('\n')
            
            # Data
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
                
                # Tenta ler colunas duplas (Banco do Brasil)
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

                    # Bases do Rodapé
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
                        
                    # Verbas normais
                    if len(descricao_limpa) > 2 and 'TOTAL' not in descricao_limpa.upper():
                        chave = descricao_limpa
                        if chave in dados_mes:
                            dados_mes[chave] = f"{dados_mes[chave]} | {valor_fmt}"
                        else:
                            dados_mes[chave] = valor_fmt
            
            if 'LÍQUIDO (Recibo)' not in dados_mes:
                 match_liq = re.search(r'(?:L[IÍ]QUIDO|VALOR LÍQUIDO).+?(\d{1,3}(?:\.\d{3})*,\d{2})', texto, re.IGNORECASE | re.DOTALL)
                 if match_liq: dados_mes['LÍQUIDO (Recibo)'] = match_liq.group(1)

            if len(dados_mes) > 1: 
                dados_gerais.append(dados_mes)
        my_bar.empty()

    return pd.DataFrame(dados_gerais)

# --- LOGIN ---
def check_password():
    if "password_correct" not in st.session_state:
        st.text_input("Senha:", type="password", key="password_input", on_change=lambda: st.session_state.update(password_correct=st.session_state.password_input == "advogado2025"))
        return False
    return st.session_state["password_correct"]

# --- INTERFACE ---
if check_password():
    st.markdown("## 📊 Extrator de Evolução Salarial")
    st.info("Este sistema corrige automaticamente erros de instalação. Se for a primeira vez, aguarde alguns segundos.")
    
    uploaded_file = st.file_uploader("Solte o PDF aqui", type="pdf")

    if uploaded_file:
        try:
            df = processar_pdf(io.BytesIO(uploaded_file.read()))
            if not df.empty:
                st.success(f"Sucesso! {len(df)} meses lidos.")
                
                # Ordenação
                cols = list(df.columns)
                if 'Mês/Ano' in cols: cols.remove('Mês/Ano'); cols.insert(0, 'Mês/Ano')
                bases = [c for c in cols if any(x in c.upper() for x in ['BASE', 'FGTS', 'LÍQUIDO', 'TOTAL'])]
                verbas = [c for c in cols if c not in bases and c != 'Mês/Ano']
                df = df[['Mês/Ano'] + sorted(verbas) + sorted(bases)]
                
                st.dataframe(df)
                
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                    df.to_excel(writer, index=False)
                
                st.download_button("⬇️ Baixar Excel", data=buffer, file_name="Evolucao.xlsx", mime="application/vnd.ms-excel")
            else:
                st.error("O PDF foi lido, mas não encontrei dados. O arquivo pode ser uma imagem (escaneado).")
        except Exception as e:
            st.error(f"Erro: {e}")
