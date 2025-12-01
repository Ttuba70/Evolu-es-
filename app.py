# @title 🚀 CÓDIGO FINAL DE EVOLUÇÃO SALARIAL + CORTADOR PRO

import streamlit as st
import pdfplumber
import pandas as pd
import re
import io
import sys
import subprocess

# --- 1. INSTALAÇÃO DAS FERRAMENTAS ---
try:
    import pdfplumber
    import PyPDF2
except ImportError:
    st.info("Instalando ferramentas... Aguarde um momento.")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pdfplumber", "pandas", "openpyxl", "PyPDF2", "xlsxwriter"])
    import pdfplumber
    import PyPDF2

from PyPDF2 import PdfReader, PdfWriter

# --- FUNÇÕES DE EXTRAÇÃO ---
def extrair_valor_monetario(texto):
    padrao = r'(\d{1,3}(?:\.\d{3})*,\d{2})'
    encontrados = re.findall(padrao, texto)
    return encontrados[-1] if encontrados else None

def processar_pdf_holerite(file):
    dados_gerais = []
    padrao_monetario_regex = r'(\d{1,3}(?:\.\d{3})*,\d{2})'

    with pdfplumber.open(file) as pdf:
        # Barra de progresso
        prog_bar = st.progress(0, text="Analisando Holerites...")
        total_p = len(pdf.pages)
        
        for i, page in enumerate(pdf.pages):
            prog_bar.progress(int((i / total_p) * 100))
            texto = page.extract_text()
            if not texto: continue
            
            lines = texto.split('\n')
            
            # Data
            mes_ano = "Não Identificado"
            match_data = re.search(r'(?:Período|Periodo|Mês/Ano|Data)[:\.\s-]*(\d{2}/\d{4}|[A-ZÀ-ZÇÃÕ]{3,9}[/\s]+\d{4})', texto, re.IGNORECASE)
            if match_data: mes_ano = match_data.group(1).strip()
            else:
                match_gen = re.search(r'\b(\d{2}/\d{4})\b', texto)
                if match_gen: mes_ano = match_gen.group(1)
            
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
                    if match_single:
                        verbas_encontradas.append((match_single.group(1), match_single.group(2)))

                for descricao_raw, valor_fmt in verbas_encontradas:
                    if not valor_fmt: continue
                    
                    descricao_limpa = re.sub(r'^[0-9./-]+\s*[-]?\s*', '', descricao_raw).strip()
                    descricao_limpa = re.sub(r'[^\w\s/.-]', '', descricao_limpa).strip()
                    
                    if len(descricao_limpa) < 2: continue

                    if any(x in descricao_limpa.upper() for x in ['BASE', 'FGTS', 'TRIBUTÁVEL', 'LÍQUIDO', 'LIQUIDO', 'TOTAL']):
                        if 'BASE INSS' in descricao_limpa.upper(): dados_mes['BASE INSS (Rodapé)'] = valor_fmt
                        elif 'FGTS' in descricao_limpa.upper() and 'VALOR' not in descricao_limpa.upper(): dados_mes['BASE FGTS'] = valor_fmt
                        elif 'VALOR FGTS' in descricao_limpa.upper(): dados_mes['Valor FGTS'] = valor_fmt
                        elif 'LÍQUIDO' in descricao_limpa.upper(): dados_mes['LÍQUIDO (Recibo)'] = valor_fmt
                        continue
                        
                    if len(descricao_limpa) > 2 and 'TOTAL' not in descricao_limpa.upper():
                        chave = descricao_limpa
                        if chave in dados_mes: dados_mes[chave] = f"{dados_mes[chave]} | {valor_fmt}"
                        else: dados_mes[chave] = valor_fmt
            
            if 'LÍQUIDO (Recibo)' not in dados_mes:
                 match_liq = re.search(r'(?:L[IÍ]QUIDO|VALOR LÍQUIDO).+?(\d{1,3}(?:\.\d{3})*,\d{2})', texto, re.IGNORECASE | re.DOTALL)
                 if match_liq: dados_mes['LÍQUIDO (Recibo)'] = match_liq.group(1)

            if len(dados_mes) > 1: dados_gerais.append(dados_mes)
        
        prog_bar.empty()

    return pd.DataFrame(dados_gerais)

# --- LOGIN ---
def check_password():
    if "password_correct" not in st.session_state:
        st.text_input("Senha:", type="password", key="password_input", on_change=lambda: st.session_state.update(password_correct=st.session_state.password_input == "advogado2025"))
        return False
    return st.session_state["password_correct"]

# --- INTERFACE PRINCIPAL ---
if check_password():
    st.sidebar.image("https://cdn-icons-png.flaticon.com/512/2666/2666505.png", width=50)
    st.sidebar.title("Menu Jurídico")
    escolha = st.sidebar.radio("Selecione a Ferramenta:", ["📊 Extrator de Holerites", "✂️ Cortar PDF (Multiseleção)"])

    # --- ABA 1: EXTRATOR ---
    if escolha == "📊 Extrator de Holerites":
        st.markdown("## 📊 Extrator de Evolução Salarial")
        uploaded_file = st.file_uploader("Solte o PDF dos Holerites aqui", type="pdf")

        if uploaded_file:
            try:
                file_buffer = io.BytesIO(uploaded_file.read())
                df = processar_pdf_holerite(file_buffer)
                
                if not df.empty:
                    st.success(f"Sucesso! {len(df)} competências extraídas.")
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
                else:
                    st.error("Nenhum dado tabular encontrado.")
            except Exception as e:
                st.error(f"Erro: {e}")

    # --- ABA 2: CORTAR PDF (NOVA LÓGICA) ---
    elif escolha == "✂️ Cortar PDF (Multiseleção)":
        st.markdown("## ✂️ Cortador de PDF Personalizado")
        st.info("Adicione quantos intervalos quiser. O sistema vai juntar tudo num arquivo só no final.")

        pdf_corte = st.file_uploader("Solte o PDF que deseja cortar", type="pdf")

        if pdf_corte:
            # Inicializa lista de cortes na memória da sessão
            if 'lista_cortes' not in st.session_state:
                st.session_state.lista_cortes = []

            reader = PdfReader(pdf_corte)
            total_paginas = len(reader.pages)
            st.write(f"📄 Este documento tem **{total_paginas} páginas**.")
            st.markdown("---")

            # Área de Input
            c1, c2, c3 = st.columns([2, 2, 2])
            with c1:
                inicio = st.number_input("Da Página:", min_value=1, max_value=total_paginas, value=1, key="inicio")
            with c2:
                fim = st.number_input("Até a Página:", min_value=1, max_value=total_paginas, value=1, key="fim")
            with c3:
                st.write("") # Espaço para alinhar
                st.write("")
                if st.button("➕ Adicionar Intervalo"):
                    if fim >= inicio:
                        st.session_state.lista_cortes.append({'De': inicio, 'Até': fim})
                        st.success(f"Páginas {inicio} a {fim} adicionadas à lista!")
                    else:
                        st.error("A página final deve ser maior que a inicial.")

            # Mostra a lista do que vai ser cortado
            if st.session_state.lista_cortes:
                st.markdown("### 📋 Lista de Cortes a processar:")
                df_cortes = pd.DataFrame(st.session_state.lista_cortes)
                st.table(df_cortes)

                col_limpar, col_processar = st.columns([1, 3])
                
                with col_limpar:
                    if st.button("🗑️ Limpar Lista"):
                        st.session_state.lista_cortes = []
                        st.rerun()

                with col_processar:
                    if st.button("✂️ GERAR PDF FINAL (JUNTAR TUDO)", type="primary"):
                        writer = PdfWriter()
                        
                        # Processa a lista
                        for corte in st.session_state.lista_cortes:
                            # O usuário vê pagina 1, mas pro python é 0. Ajustamos aqui.
                            start_idx = corte['De'] - 1
                            end_idx = corte['Até'] # Range do python exclui o ultimo, então não subtraímos 1 aqui
                            
                            for i in range(start_idx, end_idx):
                                if i < total_paginas:
                                    writer.add_page(reader.pages[i])
                        
                        output_buffer = io.BytesIO()
                        writer.write(output_buffer)
                        pdf_bytes = output_buffer.getvalue()
                        
                        st.balloons()
                        st.download_button(
                            label="⬇️ Baixar PDF Cortado e Unificado",
                            data=pdf_bytes,
                            file_name="documento_personalizado.pdf",
                            mime="application/pdf"
                        )
            else:
                st.warning("Adicione pelo menos um intervalo acima para começar.")
