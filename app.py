import streamlit as st
import pdfplumber
import pandas as pd
import re
import io
import sys
import subprocess

# --- 1. AUTO-INSTALAÇÃO (PREVENÇÃO DE ERROS) ---
try:
    import pdfplumber
    import xlsxwriter
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pdfplumber", "pandas", "openpyxl", "xlsxwriter"])
    import pdfplumber

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Calculadora de Evolução", layout="wide")

# --- FUNÇÕES DE EXTRAÇÃO ---

def extrair_valor_monetario(texto):
    """Localiza e retorna valores monetários no padrão BR."""
    padrao = r'(\d{1,3}(?:\.\d{3})*,\d{2})'
    encontrados = re.findall(padrao, texto)
    return encontrados[-1] if encontrados else None

def encontrar_data_competencia(texto):
    """
    Lógica avançada para encontrar Mês/Ano mesmo sem rótulo.
    Procura nas primeiras 10 linhas para evitar pegar datas aleatórias do corpo.
    """
    linhas_iniciais = texto.split('\n')[:15] # Analisa apenas o cabeçalho
    texto_cabecalho = "\n".join(linhas_iniciais).upper()

    # 1. Tenta achar com rótulos explícitos (Mais seguro)
    match_rotulo = re.search(r'(?:PER[ÍI]ODO|REF|M[ÊE]S/ANO|COMPET[ÊE]NCIA|DATA)[:\.\s-]*(\d{2}/\d{4}|[A-ZÇÃÕ]{3,9}[/\s-]+\d{4})', texto_cabecalho)
    if match_rotulo:
        return match_rotulo.group(1).strip()

    # 2. Tenta achar datas soltas no formato MM/AAAA ou MMM/AAAA
    # Ex: 01/2012, JAN/2012, JANEIRO/2012
    match_solto = re.search(r'\b(\d{2}/\d{4}|[A-ZÇÃÕ]{3,9}/\d{4})\b', texto_cabecalho)
    if match_solto:
        return match_solto.group(1).strip()

    # 3. Tenta achar Mês e Ano separados por espaço (comum em títulos)
    # Ex: "FOLHA DE PAGAMENTO JANEIRO 2012"
    match_titulo = re.search(r'\b(JANEIRO|FEVEREIRO|MAR[ÇC]O|ABRIL|MAIO|JUNHO|JULHO|AGOSTO|SETEMBRO|OUTUBRO|NOVEMBRO|DEZEMBRO)\s+(\d{4})\b', texto_cabecalho)
    if match_titulo:
        return f"{match_titulo.group(1)}/{match_titulo.group(2)}"

    return "Não Identificado"

def processar_pdf(file):
    dados_gerais = []
    padrao_monetario_regex = r'(\d{1,3}(?:\.\d{3})*,\d{2})'

    with pdfplumber.open(file) as pdf:
        st.info(f"Analisando {len(pdf.pages)} páginas do PDF...")
        
        for page in pdf.pages:
            texto = page.extract_text()
            if not texto: continue
            
            lines = texto.split('\n')
            
            # --- NOVA LÓGICA DE DATA ---
            mes_ano = encontrar_data_competencia(texto)
            
            # Se não achou data, tenta usar a da página anterior (caso seja continuação)
            if mes_ano == "Não Identificado" and len(dados_gerais) > 0:
                mes_ano = dados_gerais[-1]['Mês/Ano'] + " (Cont.)"

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
                    
                    # Limpeza
                    descricao_limpa = re.sub(r'^[0-9./-]+\s*[-]?\s*', '', descricao_raw).strip()
                    descricao_limpa = re.sub(r'[^\w\s/.-]', '', descricao_limpa).strip()
                    
                    if len(descricao_limpa) < 2: continue
                    
                    # Evita pegar o próprio ano como valor monetário se estiver solto
                    if "201" in valor_fmt and "," not in valor_fmt: continue 

                    # BASES DO RODAPÉ
                    if any(x in descricao_limpa.upper() for x in ['BASE', 'FGTS', 'TRIBUTÁVEL', 'LÍQUIDO', 'LIQUIDO', 'TOTAL']):
                        if 'BASE INSS' in descricao_limpa.upper():
                            dados_mes['BASE INSS (Rodapé)'] = valor_fmt
                        elif 'FGTS' in descricao_limpa.upper() and 'VALOR' not in descricao_limpa.upper() and 'BASE' in descricao_limpa.upper():
                            dados_mes['BASE FGTS'] = valor_fmt
                        elif 'VALOR FGTS' in descricao_limpa.upper() or 'DEPÓSITO FGTS' in descricao_limpa.upper():
                            dados_mes['Valor FGTS'] = valor_fmt
                        elif 'LÍQUIDO' in descricao_limpa.upper() or 'LIQUIDO' in descricao_limpa.upper():
                             dados_mes['LÍQUIDO (Recibo)'] = valor_fmt
                        continue
                        
                    # VERBAS NORMAIS
                    if len(descricao_limpa) > 2 and 'TOTAL' not in descricao_limpa.upper():
                        chave = descricao_limpa
                        if chave in dados_mes:
                            dados_mes[chave] = f"{dados_mes[chave]} | {valor_fmt}"
                        else:
                            dados_mes[chave] = valor_fmt
            
            # Captura Líquido (Backup)
            if 'LÍQUIDO (Recibo)' not in dados_mes:
                 match_liq = re.search(r'(?:L[IÍ]QUIDO|VALOR LÍQUIDO).+?(\d{1,3}(?:\.\d{3})*,\d{2})', texto, re.IGNORECASE | re.DOTALL)
                 if match_liq: dados_mes['LÍQUIDO (Recibo)'] = match_liq.group(1)

            if len(dados_mes) > 1: 
                dados_gerais.append(dados_mes)

    return pd.DataFrame(dados_gerais)

# --- LOGIN ---
def check_password():
    if "password_correct" not in st.session_state:
        st.text_input("Senha de Acesso:", type="password", key="password_input", on_change=lambda: st.session_state.update(password_correct=st.session_state.password_input == "advogado2025"))
        return False
    return st.session_state["password_correct"]

# --- INTERFACE ---
if check_password():
    st.markdown("<h1 style='text-align: center; color: #1E90FF;'>🌌 Extrator de Evolução Salarial</h1>", unsafe_allow_html=True)
    st.info("Atualização: Detecção aprimorada de Datas (Mês/Ano) e Colunas Duplas.")

    uploaded_file = st.file_uploader("Solte o PDF aqui", type="pdf")

    if uploaded_file:
        try:
            # Cria cópia do arquivo para debug se necessário
            bytes_data = uploaded_file.getvalue()
            file_buffer = io.BytesIO(bytes_data)
            
            df = processar_pdf(file_buffer)
            
            if not df.empty:
                st.success(f"✅ Sucesso! {len(df)} competências extraídas.")
                
                # Ordenação
                cols = list(df.columns)
                if 'Mês/Ano' in cols: cols.remove('Mês/Ano'); cols.insert(0, 'Mês/Ano')
                
                bases = [c for c in cols if any(x in c.upper() for x in ['BASE', 'FGTS', 'LÍQUIDO', 'TOTAL'])]
                verbas = [c for c in cols if c not in bases and c != 'Mês/Ano']
                
                df = df[['Mês/Ano'] + sorted(verbas) + sorted(bases)]
                
                st.dataframe(df, use_container_width=True)
                
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                    df.to_excel(writer, index=False, sheet_name='Evolucao')
                
                st.download_button("⬇️ Baixar Excel", data=buffer, file_name="Evolucao.xlsx", mime="application/vnd.ms-excel", type="primary")
                
                # --- ÁREA DE DEBUG (NOVIDADE) ---
                with st.expander("🕵️‍♂️ Ver Texto Bruto (Para Debug)"):
                    st.write("Se a data ainda estiver errada, veja como o robô leu a primeira página:")
                    pdf = pdfplumber.open(io.BytesIO(bytes_data))
                    st.text(pdf.pages[0].extract_text())
            else:
                st.error("O PDF foi lido, mas não encontrei dados tabulares.")
                
        except Exception as e:
            st.error(f"Erro técnico: {e}")
