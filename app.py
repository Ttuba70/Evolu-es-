def processar_pdf(file):
    """
    Função aprimorada para leitura robusta de PDFs com estruturas de coluna 
    complexas, focando na separação de colunas duplas e extração correta de bases.
    """
    import re
    import pdfplumber
    import pandas as pd
    
    dados_gerais = []
    # Padrão para valores monetários brasileiros (1.000,00)
    padrao_monetario_regex = r'(\d{1,3}(?:\.\d{3})*,\d{2})'

    with pdfplumber.open(file) as pdf:
        st.info(f"Lendo {len(pdf.pages)} páginas do PDF...")
        
        for page in pdf.pages:
            texto = page.extract_text()
            if not texto: continue
            
            lines = texto.split('\n')
            
            # Extração da data
            mes_ano = "Não Identificado"
            match_data = re.search(r'(?:Período:|Data de Crédito:).*?([A-ZÀ-ZÇÃÕ]{3,9}[/\s]+\d{4}|\d{2}/\d{4})', texto, re.IGNORECASE)
            if match_data: mes_ano = match_data.group(1).strip()
            dados_mes = {'Mês/Ano': mes_ano}
            
            for line in lines:
                line = line.strip()
                verbas_encontradas = []

                # 1. TENTA ENCONTRAR DUAS VERBAS JUNTAS NA LINHA (Resolve o problema do Banco do Brasil)
                match_coluna_dupla = re.search(
                    r'(.+?)\s+' + padrao_monetario_regex + r'\s+(.+?)\s+' + padrao_monetario_regex, 
                    line
                )
                
                if match_coluna_dupla:
                    # Se achou duas colunas de verbas, processa ambas:
                    verbas_encontradas.append((match_coluna_dupla.group(1), match_coluna_dupla.group(2))) 
                    verbas_encontradas.append((match_coluna_dupla.group(3), match_coluna_dupla.group(4)))
                else:
                    # 2. TENTA ENCONTRAR VERBA ÚNICA POR LINHA
                    match_single = re.search(r'(.+?)\s+' + padrao_monetario_regex + r'$', line)
                    if match_single:
                        verbas_encontradas.append((match_single.group(1), match_single.group(2)))

                for descricao_raw, valor_fmt in verbas_encontradas:
                    if not valor_fmt: continue
                    
                    # TENTATIVA DE CONVERSÃO SEGURA (para evitar o crash e o valor zero)
                    try:
                        valor_float = float(valor_fmt.replace('.', '').replace(',', '.'))
                    except ValueError:
                        continue 
                        
                    # Limpeza da descrição
                    descricao_limpa = re.sub(r'^[0-9./-]+\s*[-]?\s*', '', descricao_raw).strip()
                    descricao_limpa = re.sub(r'[^\w\s/.-]', '', descricao_limpa).strip()

                    # REGRA CRÍTICA: Captura de Bases do Rodapé (Estritamente)
                    if any(x in descricao_limpa.upper() for x in ['BASE INSS', 'FGTS:', 'TRIBUTÁVEL INSS']):
                        if 'BASE INSS' in descricao_limpa.upper() or 'TRIBUTÁVEL INSS' in descricao_limpa.upper():
                            dados_mes['BASE INSS (Rodapé)'] = valor_fmt
                        elif 'FGTS:' in descricao_limpa.upper():
                            dados_mes['BASE FGTS'] = valor_fmt
                        elif 'VALOR FGTS' in descricao_limpa.upper() or 'DEPÓSITO FGTS' in descricao_limpa.upper():
                            dados_mes['Valor FGTS'] = valor_fmt
                        continue
                        
                    # Adicionar Rubrica (REGRA: Separação Total)
                    if len(descricao_limpa) > 2 and 'TOTAL' not in descricao_limpa.upper() and 'LÍQUIDO' not in descricao_limpa.upper():
                        chave = descricao_limpa
                        if chave in dados_mes:
                            # Concatena os valores para a mesma rubrica (ex: 2x Salário Padrão)
                            dados_mes[chave] = f"{dados_mes[chave]} | {valor_fmt}"
                        else:
                            dados_mes[chave] = valor_fmt
            
            # Captura Líquido (Garante que seja o último valor significativo)
            match_liquido = re.search(r'(?:L[IÍ]QUIDO).*?(\d{1,3}(?:\.\d{3})*,\d{2})', texto, re.IGNORECASE | re.DOTALL)
            if match_liquido:
                dados_mes['VALOR LÍQUIDO'] = match_liquido.group(1).strip()

            if len(dados_mes) > 1: dados_gerais.append(dados_mes)

    return pd.DataFrame(dados_gerais)
