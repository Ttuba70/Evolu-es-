# @title 🚀 CÓDIGO COMPLETO E CORRIGIDO DA APLICAÇÃO STREAMLIT (app.py)

import streamlit as st
import pdfplumber
import pandas as pd
import re
import io
import sys
import subprocess

# --- 1. INSTALAÇÃO DAS FERRAMENTAS (Garante que tudo funciona) ---
try:
    import pdfplumber
except ImportError:
    st.info("Instalando ferramentas necessárias... Aguarde...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pdfplumber", "pandas", "openpyxl"])
    st.success("Instalação concluída!")
    import pdfplumber

# --- FUNÇÕES DE UTILIDADE ---

def extrair_valor_monetario(texto):
    """Localiza e formata valores monetários no padrão BR."""
    padrao = r'(\d{1,3}(?:\.\d{3})*,\d{2})'
    encontrados = re.findall(padrao, texto)
    if encontrados:
        valor_str = encontrados[-1]
        try:
            # Não converte para float aqui, apenas retorna a string limpa
            return valor_str
        except:
            return None
    return None

# --- LÓGICA DE PROCESSAMENTO CENTRAL (CORRIGIDA) ---

def processar_pdf(file):
    """
    Lê o PDF e extrai dados, com lógica aprimorada para detecção de 
    colunas duplas e extração de rubricas e bases.
    """
    dados_gerais = []
    
    with pdfplumber.open(file) as pdf:
        st.info(f"Lendo {len(pdf.pages)} páginas do PDF...")
        
        for page in pdf.pages:
            texto = page.extract_text()
            if not texto: continue
            
            lines = texto.split('\n')
            
            # Extração da data
            mes_ano = "Não Identificado"
            match_data = re.search(r'(?:Período:|Data de Crédito:).*?([A-ZÀ-ZÇÃÕ]{3,9}[/\s]+\d{4}|\d{2}/\d{4})', texto, re.IGNORECASE)
            if match_data:
                mes_ano = match_data.group(1).strip()
            else:
                match_gen = re.search(r'\b(\d{2}/\d{4})\b', texto)
                if match_gen: mes_ano = match_gen.group(1)
            
            dados_mes = {'Mês/Ano': mes_ano}
            
            for line in lines:
                line = line.strip()
                verbas_encontradas = []

                # 1. TENTA ENCONTRAR DUAS VERBAS JUNTAS NA LINHA (Padrao Banco do Brasil)
                padrao_monetario_regex = r'(\d{1,3}(?:\.\d{3})*,\d{2})'
                match_coluna_dupla = re.search(
                    r'(.+?)\s+' + padrao_monetario_regex + r'\s+(.+?)\s+' + padrao_monetario_regex, 
                    line
                )
                
                if match_coluna_dupla:
                    # Se achou duas colunas de verbas, processa ambas:
                    verbas_encontradas.append((match_coluna_dupla.group(1), match_coluna_dupla.group(2))) 
                    verbas_encontradas.append((match_coluna_dupla.group(3), match_coluna_dupla.group(4)))
                else:
                    # 2. TENTA ENCONTRAR VERBA ÚNICA POR LINHA (Padrao holerite comum)
                    match_single = re.search(r'(.+?)\s+' + padrao_monetario_regex + r'$', line)
                    if match_single:
                        verbas_encontradas.append((match_single.group(1), match_single.group(2)))

                for descricao_raw, valor_fmt in verbas_encontradas:
                    if not valor_fmt: continue
                    
                    # Limpeza da descrição
                    descricao_limpa = re.sub(r'^[0-9./-]+\s*[-]?\s*', '', descricao_raw).strip()
                    descricao_limpa = re.sub(r'[^\w\s/.-]', '', descricao_limpa).strip()
                    
                    # REGRA CRÍTICA: Captura de Bases e Totais (Rodapé/Sumário)
                    if any(x in descricao_limpa.upper() for x in ['BASE', 'FGTS', 'TRIBUTÁVEL', 'LÍQUIDO']):
                        # Se for BASE, salva na chave específica do Rodapé
                        if 'BASE INSS' in descricao_limpa.upper() or 'TRIBUTÁVEL INSS' in descricao_limpa.upper():
                            dados_mes['BASE INSS (Rodapé)'] = valor_fmt
                        elif 'FGTS' in descricao_limpa.upper() and 'VALOR' not in descricao_limpa.upper():
                            dados_mes['BASE FGTS'] = valor_fmt
                        elif 'VALOR FGTS' in descricao_limpa.upper() or 'DEPÓSITO FGTS' in descricao_limpa.upper():
                            dados_mes['Valor FGTS'] = valor_fmt
                        elif 'VALOR LÍQUIDO' in descricao_limpa.upper() or 'LÍQUIDO' in descricao_limpa.upper():
                             # Será capturado ao final, mas salvamos o valor aqui para robustez
                             pass 
                        continue
                        
                    # Adicionar Rubrica (REGRA: Separação Total)
                    if len(descricao_limpa) > 2 and 'TOTAL' not in descricao_limpa.upper():
                        chave = descricao_limpa
                        if chave in dados_mes:
                            # Se a verba já existe, a nova lógica exige rastreabilidade:
                            dados_mes[chave] = f"{dados_mes[chave]} | {valor_fmt}"
                        else:
                            dados_mes[chave] = valor_fmt
            
            # Captura Líquido (Garante que seja o último valor significativo)
            match_liquido = re.search(r'(?:L[IÍ]QUIDO|VALOR LIQUIDO).+?(\d{1,3}(?:\.\d{3})*,\d{2})', texto, re.IGNORECASE | re.DOTALL)
            if match_liquido:
                dados_mes['VALOR LÍQUIDO'] = match_liquido.group(1).strip()

            if len(dados_mes) > 1: dados_gerais.append(dados_mes)

    return pd.DataFrame(dados_gerais)

# --- CONFIGURAÇÃO DA PÁGINA E LOGIN ---
st.set_page_config(page_title="Calculadora de Evolução", layout="wide")

def check_password():
    # Senha hardcoded para facilitar: 'advogado2025'
    if "password_correct" not in st.session_state:
        st.text_input("Senha de Acesso:", type="password", on_change=lambda: st.session_state.update(password_correct=st.session_state.password == "advogado2025"), key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("Senha incorreta. Tente novamente:", type="password", on_change=lambda: st.session_state.update(password_correct=st.session_state.password == "advogado2025"), key="password")
        return False
    return True

# --- INTERFACE DO SITE (APÓS LOGIN) ---
if check_password():
    st.title("📊 Sistema de Evolução Salarial - Multiempresas")
    st.subheader("Ferramenta Analítica para Holerites")
    st.markdown("---")

    uploaded_file = st.file_uploader("1. Arraste e solte o arquivo PDF aqui:", type="pdf")

    if uploaded_file is not None:
        st.info("Atenção: O processamento pode levar alguns segundos, especialmente em arquivos longos.", icon="⏳")
        
        # Cria um buffer de arquivo para o pdfplumber ler
        file_buffer = io.BytesIO(uploaded_file.read())

        with st.spinner('2. Analisando PDF e extraindo todas as verbas...'):
            try:
                df = processar_pdf(file_buffer)
                
                if not df.empty:
                    st.success(f"✅ Processamento concluído! {len(df)} meses encontrados.")

                    # Reorganiza a tabela (Mês/Ano, Bases e Líquido no final)
                    cols = list(df.columns)
                    if 'Mês/Ano' in cols: cols.remove('Mês/Ano'); cols.insert(0, 'Mês/Ano')
                    
                    bases = [c for c in cols if 'BASE' in c.upper() or 'FGTS' in c.upper() or 'LÍQUIDO' in c.upper()]
                    for b in bases:
                        if b in cols:
                            cols.remove(b)
                            cols.append(b)
                    
                    df = df[cols]
                    
                    st.dataframe(df.style.format(precision=2), height=300)
                    
                    # Botão de Download
                    buffer = io.BytesIO()
                    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                        df.to_excel(writer, index=False, sheet_name='Evolucao')
                        
                    st.download_button(
                        label="3. BAIXAR PLANILHA EXCEL PRONTA",
                        data=buffer,
                        file_name="Evolucao_Salarial_Analitica_CORRIGIDA.xlsx",
                        mime="application/vnd.ms-excel"
                    )
                else:
                    st.warning("Não foi possível extrair dados de holerite deste PDF. O arquivo pode estar escaneado.", icon="⚠️")
                    
            except Exception as e:
                st.error(f"❌ Ocorreu um erro no processamento: {e}", icon="🚨")
