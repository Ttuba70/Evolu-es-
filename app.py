# @title 🚀 Código Completo da Aplicação Streamlit (app.py)
import streamlit as st
import pdfplumber
import pandas as pd
import re
import io
import sys
import subprocess

# --- Instalação das dependências (Garante que tudo funciona no Colab/Streamlit Cloud) ---
try:
    import pdfplumber
except ImportError:
    st.info("Instalando ferramentas necessárias... Aguarde.")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pdfplumber", "pandas", "openpyxl"])
    import pdfplumber

# --- CONFIGURAÇÃO DA PÁGINA E LOGIN ---
st.set_page_config(page_title="Calculadora de Evolução", layout="wide")

def check_password():
    # Senha definida para uso simples. Usuário pode mudar aqui.
    if "password_correct" not in st.session_state:
        st.text_input("Senha de Acesso:", type="password", on_change=lambda: st.session_state.update(password_correct=st.session_state.password == "advogado2025"), key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("Senha incorreta. Tente novamente:", type="password", on_change=lambda: st.session_state.update(password_correct=st.session_state.password == "advogado2025"), key="password")
        return False
    return True

# --- LÓGICA DE EXTRAÇÃO DE DADOS ---

def extrair_valor_monetario(texto):
    """Localiza e formata valores monetários no padrão BR."""
    padrao = r'(\d{1,3}(?:\.\d{3})*,\d{2})'
    encontrados = re.findall(padrao, texto)
    if encontrados:
        valor_str = encontrados[-1]
        try:
            float(valor_str.replace('.', '').replace(',', '.'))
            return valor_str
        except:
            return None
    return None

def processar_pdf(file):
    dados_gerais = []
    
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            texto = page.extract_text()
            if not texto: continue
            
            lines = texto.split('\n')
            mes_ano = "Não Identificado"
            match_data = re.search(r'(?:Período:|Data de Crédito:).*?([A-Z]{3,9}/\d{4}|\d{2}/\d{4})', texto, re.IGNORECASE)
            if match_data:
                mes_ano = match_data.group(1).strip()
            
            dados_mes = {'Mês/Ano': mes_ano}
            
            for line in lines:
                valor_fmt = extrair_valor_monetario(line)
                
                if valor_fmt:
                    descricao = line.replace(valor_fmt, '').strip()
                    
                    # REGRA CRÍTICA: Extrai bases do rodapé (exatamente o que está escrito)
                    if 'BASE' in descricao.upper() or 'FGTS' in descricao.upper():
                        if 'INSS:' in descricao or 'TRIBUTÁVEL INSS' in descricao.upper():
                            dados_mes['BASE INSS (Rodapé)'] = valor_fmt
                        elif 'FGTS:' in descricao and 'VALOR' not in descricao.upper():
                            dados_mes['BASE FGTS'] = valor_fmt
                        elif 'VALOR FGTS' in descricao.upper() or 'DEPÓSITO FGTS' in descricao.upper():
                            dados_mes['Valor FGTS'] = valor_fmt
                        continue
                        
                    # Pega Verbas (Qualquer linha que termine em valor)
                    descricao_limpa = re.sub(r'^[0-9./-]+\s*[-]?\s*', '', descricao)
                    descricao_limpa = re.sub(r'[^\w\s/.-]', '', descricao_limpa).strip()
                    
                    if len(descricao_limpa) > 2 and 'TOTAL' not in descricao_limpa.upper() and 'LÍQUIDO' not in descricao_limpa.upper():
                        # Utiliza a lógica de separação total (cada código = 1 coluna)
                        if descricao_limpa in dados_mes:
                            # Se a verba tem 2 linhas (ex: salário Padrão da Caixa), concatena ou soma
                            dados_mes[descricao_limpa] = f"{dados_mes[descricao_limpa]} | {valor_fmt}"
                        else:
                            dados_mes[descricao_limpa] = valor_fmt
            
            # Captura o Líquido (separadamente)
            match_liquido = re.search(r'L[IÍ]QUIDO.*?\n.*?([\d\.]+,\d{2})', texto, re.IGNORECASE | re.DOTALL)
            if match_liquido:
                dados_mes['VALOR LÍQUIDO'] = match_liquido.group(1).strip()


            if len(dados_mes) > 1:
                dados_gerais.append(dados_mes)

    return pd.DataFrame(dados_gerais)

# --- INTERFACE DO SITE (APÓS LOGIN) ---

if check_password():
    st.title("📊 Sistema de Evolução Salarial - Multiempresas")
    st.subheader("Ferramenta Analítica para Holerites")
    st.markdown("---")

    uploaded_file = st.file_uploader("1. Arraste e solte o arquivo PDF aqui (Holerites ou Processo):", type="pdf")

    if uploaded_file is not None:
        st.info("Atenção: O processamento pode levar alguns segundos, especialmente em arquivos longos.", icon="⏳")
        
        # Cria um arquivo temporário em memória (BytesIO) para o pdfplumber ler
        file_buffer = io.BytesIO(uploaded_file.read())

        with st.spinner('2. Analisando PDF e extraindo todas as verbas...'):
            try:
                df = processar_pdf(file_buffer)
                
                if not df.empty:
                    st.success(f"✅ Sucesso! {len(df)} meses processados.")

                    # Reorganiza e exibe a tabela
                    cols = list(df.columns)
                    if 'Mês/Ano' in cols: cols.remove('Mês/Ano'); cols.insert(0, 'Mês/Ano')
                    
                    # Joga Bases e Líquido para o final
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
                        file_name="Evolucao_Salarial_Analitica.xlsx",
                        mime="application/vnd.ms-excel"
                    )
                else:
                    st.warning("Não foi possível extrair dados de holerite deste PDF. O arquivo pode estar escaneado.", icon="⚠️")
                    
            except Exception as e:
                st.error(f"❌ Ocorreu um erro no processamento: {e}", icon="🚨")