import streamlit as st
import pdfplumber
import pandas as pd
import re
import io

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Matriz de Evolução Salarial", layout="wide")

# --- FUNÇÕES DE EXTRAÇÃO ---

def extrair_valor_monetario(texto):
    """Localiza e retorna valores monetários no padrão BR (X.XXX,XX)."""
    # Regex ajustado para capturar valores monetários com precisão
    padrao = r'(\d{1,3}(?:\.\d{3})*,\d{2})'
    encontrados = re.findall(padrao, texto)
    # Retorna o último valor encontrado na linha (geralmente é o valor final da rubrica)
    return encontrados[-1] if encontrados else None

def processar_pdf(file):
    """Lê o PDF e extrai dados com lógica de colunas duplas."""
    dados_gerais = []
    # Regex para identificar moeda
    padrao_monetario_regex = r'(\d{1,3}(?:\.\d{3})*,\d{2})'

    with pdfplumber.open(file) as pdf:
        # Barra de progresso visual
        progress_text = "Operação em andamento. Analisando páginas..."
        my_bar = st.progress(0, text=progress_text)
        total_pages = len(pdf.pages)
        
        for i, page in enumerate(pdf.pages):
            # Atualiza barra de progresso
            percent_complete = int((i / total_pages) * 100)
            my_bar.progress(percent_complete, text=f"Analisando página {i+1} de {total_pages}")

            texto = page.extract_text()
            if not texto: continue
            
            lines = texto.split('\n')
            
            # --- 1. Extração da Data (Competência) ---
            mes_ano = "Não Identificado"
            # Tenta achar "Período: MM/AAAA" ou "Mês/Ano: MMM/AAAA"
            match_data = re.search(r'(?:Período|Periodo|Mês/Ano|Data)[:\.\s-]*(\d{2}/\d{4}|[A-ZÀ-ZÇÃÕ]{3,9}[/\s]+\d{4})', texto, re.IGNORECASE)
            if match_data:
                mes_ano = match_data.group(1).strip()
            else:
                # Tenta achar datas soltas tipo "01/2020" ou "JAN/2020" no topo
                match_gen = re.search(r'\b(\d{2}/\d{4})\b', texto)
                if match_gen: mes_ano = match_gen.group(1)
            
            dados_mes = {'Mês/Ano': mes_ano}
            
            # --- 2. Extração das Verbas ---
            for line in lines:
                line = line.strip()
                if not line: continue
                
                verbas_encontradas = []

                # A) TENTA ENCONTRAR DUAS VERBAS NA MESMA LINHA (Layout Banco do Brasil)
                # Ex: "Salário 2.000,00  INSS 200,00"
                match_coluna_dupla = re.search(
                    r'(.+?)\s+' + padrao_monetario_regex + r'\s+(.+?)\s+' + padrao_monetario_regex, 
                    line
                )
                
                if match_coluna_dupla:
                    verbas_encontradas.append((match_coluna_dupla.group(1), match_coluna_dupla.group(2))) 
                    verbas_encontradas.append((match_coluna_dupla.group(3), match_coluna_dupla.group(4)))
                else:
                    # B) TENTA ENCONTRAR VERBA ÚNICA (Layout Padrão)
                    match_single = re.search(r'(.+?)\s+' + padrao_monetario_regex + r'$', line)
                    if match_single:
                        verbas_encontradas.append((match_single.group(1), match_single.group(2)))

                # Processa o que encontrou na linha
                for descricao_raw, valor_fmt in verbas_encontradas:
                    if not valor_fmt: continue
                    
                    # Limpeza da descrição (Tira códigos numéricos do início)
                    descricao_limpa = re.sub(r'^[0-9./-]+\s*[-]?\s*', '', descricao_raw).strip()
                    descricao_limpa = re.sub(r'[^\w\s/.-]', '', descricao_limpa).strip()
                    
                    # Ignora linhas inúteis
                    if len(descricao_limpa) < 2: continue
                    if "PÁGINA" in descricao_limpa.upper(): continue

                    # --- REGRA CRÍTICA: Captura de BASES (Rodapé) ---
                    termos_base = ['BASE', 'FGTS', 'TRIBUTÁVEL', 'LÍQUIDO', 'LIQUIDO', 'TOTAL']
                    
                    if any(x in descricao_limpa.upper() for x in termos_base):
                        # INSS
                        if 'BASE INSS' in descricao_limpa.upper() or 'TRIBUTÁVEL INSS' in descricao_limpa.upper():
                            dados_mes['BASE INSS (Rodapé)'] = valor_fmt
                        # FGTS
                        elif 'FGTS' in descricao_limpa.upper() and 'VALOR' not in descricao_limpa.upper() and 'BASE' in descricao_limpa.upper():
                            dados_mes['BASE FGTS'] = valor_fmt
                        elif 'VALOR FGTS' in descricao_limpa.upper() or 'DEPÓSITO FGTS' in descricao_limpa.upper():
                            dados_mes['Valor FGTS'] = valor_fmt
                        # LÍQUIDO (Captura de segurança, caso não pegue no final)
                        elif 'LÍQUIDO' in descricao_limpa.upper() or 'LIQUIDO' in descricao_limpa.upper():
                             dados_mes['LÍQUIDO (Recibo)'] = valor_fmt
                        # TOTAIS (Bruto e Desconto)
                        elif 'TOTAL VENCIMENTOS' in descricao_limpa.upper() or 'TOTAL PROVENTOS' in descricao_limpa.upper():
                            dados_mes['TOTAL BRUTO'] = valor_fmt
                        elif 'TOTAL DESCONTOS' in descricao_limpa.upper():
                             dados_mes['TOTAL DESCONTOS'] = valor_fmt
                        continue
                        
                    # --- REGRA GERAL: Verbas Normais ---
                    # Se não é base nem total, é verba.
                    # Evita duplicatas exatas sobrescrevendo
                    chave = descricao_limpa
                    if chave in dados_mes:
                        # Se já tem (ex: duas linhas de "Salário"), concatena para conferência
                        dados_mes[chave] = f"{dados_mes[chave]} | {valor_fmt}"
                    else:
                        dados_mes[chave] = valor_fmt
            
            # Busca Líquido (Tenta achar pelo padrão visual final se não achou na linha)
            if 'LÍQUIDO (Recibo)' not in dados_mes:
                 match_liq = re.search(r'(?:L[IÍ]QUIDO|VALOR LÍQUIDO).+?(\d{1,3}(?:\.\d{3})*,\d{2})', texto, re.IGNORECASE | re.DOTALL)
                 if match_liq:
                     dados_mes['LÍQUIDO (Recibo)'] = match_liq.group(1)

            # Só adiciona se encontrou dados relevantes
            if len(dados_mes) > 1: 
                dados_gerais.append(dados_mes)
        
        my_bar.empty()

    return pd.DataFrame(dados_gerais)

# --- LOGIN ---
def check_password():
    """Retorna True se o usuário logar corretamente."""
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

# --- INTERFACE PRINCIPAL ---

if check_password():
    # Cabeçalho Futurista
    st.markdown("""
    <style>
    .big-font { font-size:30px !important; font-weight: bold; color: #4F8BF9; }
    .sub-font { font-size:16px !important; color: #666; }
    </style>
    """, unsafe_allow_html=True)
    
    st.markdown('<p class="big-font">🌌 Matriz de Evolução Salarial</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-font">Sistema Avançado de Extração de Dados de Holerites (Multi-Layout)</p>', unsafe_allow_html=True)
    st.divider()

    uploaded_file = st.file_uploader("📡 INPUT: Transmitir Arquivo PDF", type="pdf")

    if uploaded_file is not None:
        try:
            # Processamento
            file_buffer = io.BytesIO(uploaded_file.read())
            df = processar_pdf(file_buffer)

            if not df.empty:
                st.success(f"✅ ANÁLISE CONCLUÍDA: {len(df)} competências identificadas.")
                
                # Reorganização Inteligente das Colunas
                cols = list(df.columns)
                
                # 1. Mês/Ano primeiro
                if 'Mês/Ano' in cols: cols.remove('Mês/Ano'); cols.insert(0, 'Mês/Ano')
                
                # 2. Bases e Líquidos por último
                bases = [c for c in cols if any(x in c.upper() for x in ['BASE', 'FGTS', 'LÍQUIDO', 'TOTAL'])]
                verbas = [c for c in cols if c not in bases and c != 'Mês/Ano']
                
                cols_ordenadas = ['Mês/Ano'] + sorted(verbas) + sorted(bases)
                # Filtra apenas colunas que realmente existem
                cols_finais = [c for c in cols_ordenadas if c in df.columns]
                
                df = df[cols_finais]

                # Visualização
                st.dataframe(df, use_container_width=True)

                # Download
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                    df.to_excel(writer, index=False, sheet_name='Evolucao')
                
                st.download_button(
                    label="💾 DOWNLOAD: Baixar Planilha Excel (.xlsx)",
                    data=buffer,
                    file_name="Evolucao_Salarial_Analitica.xlsx",
                    mime="application/vnd.ms-excel",
                    type="primary"
                )
            else:
                st.warning("⚠️ O sistema leu o arquivo, mas não encontrou tabelas salariais reconhecíveis. Verifique se o PDF é pesquisável (não escaneado).")

        except Exception as e:
            st.error(f"❌ Erro Crítico no Processamento: {e}")
            st.info("Dica: Se o erro persistir, verifique se o arquivo PDF não está protegido por senha ou corrompido.")
