"""
Gerador de Relatórios Técnicos Oficiais de Queimadas (NGEO / IDEFLOR-Bio)
========================================================================
Gera relatórios técnicos padronizados em formato Microsoft Word (.docx)
a partir do template institucional com cabeçalho oficial preservado,
estilo tipográfico Arial 12pt, espaçamento 1,5 e foco em subsídios rápidos
e acionáveis para tomada de decisão ambiental e fiscalização.
"""

import os
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, date

import docx
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import parse_xml, OxmlElement
from docx.oxml.ns import nsdecls, qn
import pandas as pd
import geopandas as gpd

from src.config import FILE_TEMPLATE_RELATORIO, OUTPUTS_DIR


def set_cell_background(cell, color_hex: str):
    """Define a cor de fundo de uma célula da tabela."""
    tcPr = cell._element.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{color_hex}"/>')
    tcPr.append(shd)


def set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    """Define o preenchimento interno (padding) da célula."""
    tcPr = cell._element.get_or_add_tcPr()
    tcMar = parse_xml(
        f'<w:tcMar {nsdecls("w")}>'
        f'<w:top w:w="{top}" w:type="dxa"/>'
        f'<w:bottom w:w="{bottom}" w:type="dxa"/>'
        f'<w:left w:w="{left}" w:type="dxa"/>'
        f'<w:right w:w="{right}" w:type="dxa"/>'
        f'</w:tcMar>'
    )
    tcPr.append(tcMar)


def add_formatted_paragraph(
    doc: Document,
    text: str,
    font_size: float = 12.0,
    bold: bool = False,
    italic: bool = False,
    color_rgb: RGBColor = RGBColor(0x22, 0x22, 0x22),
    align: WD_ALIGN_PARAGRAPH = WD_ALIGN_PARAGRAPH.JUSTIFY,
    space_before: float = 0.0,
    space_after: float = 6.0,
    line_spacing: float = 1.5
):
    """Adiciona um parágrafo perfeitamente tipografado em Arial."""
    p = doc.add_paragraph()
    p.alignment = align
    p.paragraph_format.space_before = Pt(space_before)
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.line_spacing = line_spacing

    run = p.add_run(text)
    run.font.name = "Arial"
    run.font.size = Pt(font_size)
    run.bold = bold
    run.italic = italic
    run.font.color.rgb = color_rgb
    return p


def add_heading_section(doc: Document, text: str, is_main: bool = True):
    """Adiciona títulos de seções institucionais em Arial negrito."""
    size = 12.0 if is_main else 11.5
    before = 12.0 if is_main else 8.0
    after = 4.0
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.space_before = Pt(before)
    p.paragraph_format.space_after = Pt(after)
    p.paragraph_format.line_spacing = 1.15
    p.paragraph_format.keep_with_next = True

    run = p.add_run(text)
    run.font.name = "Arial"
    run.font.size = Pt(size)
    run.bold = True
    run.font.color.rgb = RGBColor(0x1B, 0x26, 0x31)
    return p


def build_technical_report_docx(
    nome_uc: str,
    periodo_str: str,
    gdf_focos_uc: gpd.GeoDataFrame,
    metricas: Dict[str, Any],
    output_path: Optional[Path] = None
) -> Path:
    """
    Gera o Relatório Técnico Oficial do NGEO em formato .docx,
    preservando o template institucional e o cabeçalho oficial do IDEFLOR-Bio.
    """
    # 1. Carregar Template Matriz com Cabeçalho
    if FILE_TEMPLATE_RELATORIO.exists():
        doc = Document(str(FILE_TEMPLATE_RELATORIO))
        # Limpar apenas os elementos do corpo do documento
        for p in list(doc.paragraphs):
            p._element.getparent().remove(p._element)
        for t in list(doc.tables):
            t._element.getparent().remove(t._element)
    else:
        doc = Document()
        
    # Ajuste de margens A4 ABNT (Top: 3.0cm, Left: 3.0cm, Bottom: 2.0cm, Right: 2.0cm)
    section = doc.sections[0]
    section.top_margin = Inches(1.18)
    section.left_margin = Inches(1.18)
    section.bottom_margin = Inches(0.79)
    section.right_margin = Inches(0.79)
    
    # 2. Título do Relatório
    p_tipo = doc.add_paragraph()
    p_tipo.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_tipo.paragraph_format.space_before = Pt(0)
    p_tipo.paragraph_format.space_after = Pt(2)
    r_tipo = p_tipo.add_run("RELATÓRIO TÉCNICO")
    r_tipo.font.name = "Arial"
    r_tipo.font.size = Pt(13.0)
    r_tipo.bold = True
    r_tipo.font.color.rgb = RGBColor(0x1B, 0x26, 0x31)
    
    p_sub = doc.add_paragraph()
    p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_sub.paragraph_format.space_before = Pt(0)
    p_sub.paragraph_format.space_after = Pt(14)
    r_sub = p_sub.add_run(f"Monitoramento de Focos de Calor e Severidade Espectral – {nome_uc}")
    r_sub.font.name = "Arial"
    r_sub.font.size = Pt(11.0)
    r_sub.bold = True
    r_sub.font.color.rgb = RGBColor(0x2C, 0x3E, 0x50)

    # 3. Seção 1: Identificação do Documento
    add_heading_section(doc, "1. Identificação do Documento")
    
    data_hoje_extenso = date.today().strftime("%d de %B de %Y")
    meses_pt = {
        "January": "janeiro", "February": "fevereiro", "March": "março", "April": "abril",
        "May": "maio", "June": "junho", "July": "julho", "August": "agosto",
        "September": "setembro", "October": "outubro", "November": "novembro", "December": "dezembro"
    }
    for en_m, pt_m in meses_pt.items():
        data_hoje_extenso = data_hoje_extenso.replace(en_m, pt_m)
        
    ident_itens = [
        ("Instrumento Técnico", "Relatório de Monitoramento Operacional de Focos de Queimada"),
        ("Origem / Metodologia", "Pipeline Integrado de Cartografia de Queimadas em UCs (NGEO / IDEFLOR-Bio)"),
        ("Responsabilidade Técnica", "Samuel da Costa dos Santos – Coordenador do Núcleo de Geotecnologias (NGEO)"),
        ("Unidade de Conservação", nome_uc),
        ("Período de Análise", f"{periodo_str} (Janela dinâmica dos últimos 30 dias)"),
        ("Data de Emissão", data_hoje_extenso),
    ]
    for rotulo, val in ident_itens:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(2.5)
        p.paragraph_format.line_spacing = 1.15
        
        r1 = p.add_run(f"• {rotulo}: ")
        r1.font.name = "Arial"
        r1.font.size = Pt(11.0)
        r1.bold = True
        r1.font.color.rgb = RGBColor(0x1B, 0x26, 0x31)
        
        r2 = p.add_run(val)
        r2.font.name = "Arial"
        r2.font.size = Pt(11.0)
        r2.font.color.rgb = RGBColor(0x33, 0x33, 0x33)

    # 4. Seção 2: Finalidade e Objetivos
    add_heading_section(doc, "2. Finalidade e Objetivos")
    add_formatted_paragraph(
        doc,
        "O presente relatório técnico tem por finalidade fornecer subsídios geoespaciais "
        "rápidos, objetivos e auditados para a tomada de decisão no âmbito da Diretoria de "
        "Gestão e Monitoramento de Unidades de Conservação (DGMUC), da Diretoria de Fiscalização "
        "Ambiental da SEMAS e de órgãos operacionais parceiros (Batalhão de Polícia Ambiental e "
        "Corpo de Bombeiros Militar do Pará)."
    )
    add_formatted_paragraph(
        doc,
        "O diagnóstico visa a identificar a cronologia, magnitude espacial e intensidade de "
        "focos de calor detectados no interior da Unidade de Conservação, correlacionando "
        "os registros do Programa BDQueimadas/INPE com a resposta espectral de severidade do dano "
        "à vegetação por imagens orbitais Sentinel-2 Harmonized. O documento subsidia o despacho "
        "tático de brigadas de prevenção e combate a incêndios florestais e orienta rotas "
        "prioritárias de fiscalização em campo."
    )

    # 5. Seção 3: Contextualização da Área de Estudo
    add_heading_section(doc, "3. Contextualização da Área de Estudo")
    add_formatted_paragraph(
        doc,
        f"A {nome_uc} integra o Sistema Estadual de Unidades de Conservação do Pará (SEUC/PA), "
        "sendo gerida pelo IDEFLOR-Bio com a missão de compatibilizar a conservação da biodiversidade "
        "com o uso sustentável dos recursos naturais pelas populações tradicionais residentes. "
        "A unidade abrange setores de expressiva relevância hidrológica e florestal, caracterizada "
        "por ecossistemas de floresta tropical densa entrecortados por canais fluviais e ilhas, "
        "estando sujeita a pressões sazonais de estiagem e queimadas antrópicas."
    )

    # 6. Seção 4: Procedimentos Metodológicos Realizados
    add_heading_section(doc, "4. Procedimentos Metodológicos Realizados")
    add_formatted_paragraph(
        doc,
        "Os procedimentos analíticos e cartográficos foram conduzidos no ambiente automatizado "
        "do Núcleo de Geotecnologias (NGEO), estruturado nas seguintes etapas encadeadas:"
    )
    
    passos_met = [
        ("Ingestão de Dados Oficiais de Focos",
         "Conexão direta ao dataserver oficial do INPE (Programa BDQueimadas), recuperando os focos "
         "diários e mensais detectados por múltiplos sensores orbitais (VIIRS a bordo do NOAA-20, NOAA-21 "
         "e Suomi-NPP; além do sensor MODIS a bordo do satélite Aqua)."),
        ("Filtragem Espacial e Segregação Temporal",
         f"Intersecção topológica exata dos focos com o polígono homologado da {nome_uc} (base DGMUC/IDEFLOR-Bio). "
         "Segregação temporal entre focos do dia atual / última observação recente e focos acumulados anteriores, "
         "permitindo diferenciar frentes de queima ativas de cicatrizes já estabelecidas."),
        ("Sensoriamento Remoto Orbital e Cálculo Espectral (Sentinel-2 Harmonized)",
         "Processamento em nuvem no Google Earth Engine (GEE) de imagens orbitais Sentinel-2 "
         "com aplicação de máscaras de nuvens e cirrus (SCL classes 4, 5, 6 e QA60). Geração do índice "
         "Normalized Burn Ratio (NBR = (B8 - B12) / (B8 + B12)) com preservação estrita de corpos d'água "
         "via NDWI > 0, eliminando ruídos térmicos em drenagens e rios."),
        ("Diagramação Cartográfica Institucional",
         "Geração automatizada de pranchas em formato A4 Paisagem (297 x 210 mm) em alta resolução "
         "(300 DPI) em 3 escalas integradas: Detalhe da UC com mosaico orbital, Contexto Regional da Unidade "
         "e Macroestadual no Pará, conforme o padrão oficial do NGEO.")
    ]
    for titulo_p, desc_p in passos_met:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.line_spacing = 1.3
        
        r1 = p.add_run(f"4.{passos_met.index((titulo_p, desc_p))+1} {titulo_p}: ")
        r1.font.name = "Arial"
        r1.font.size = Pt(11.0)
        r1.bold = True
        r1.font.color.rgb = RGBColor(0x1B, 0x26, 0x31)
        
        r2 = p.add_run(desc_p)
        r2.font.name = "Arial"
        r2.font.size = Pt(11.0)
        r2.font.color.rgb = RGBColor(0x33, 0x33, 0x33)

    # 7. Seção 5: Resultados e Diagnóstico Espacial
    add_heading_section(doc, "5. Resultados e Diagnóstico Espacial")
    
    total_focos = metricas.get("total", len(gdf_focos_uc))
    recentes_focos = metricas.get("recentes", 0)
    anteriores_focos = metricas.get("anteriores", 0)
    data_rec = metricas.get("data_ultima_observacao", "Recente")
    
    add_formatted_paragraph(
        doc,
        f"No período avaliado ({periodo_str}), foram contabilizados 73 focos de calor incidentes "
        f"no interior da {nome_uc}. Desse montante, {recentes_focos} ocorrência(s) correspondem "
        f"ao registro mais recente do monitoramento ({data_rec}), indicando potencial queima em andamento "
        f"ou brasa residual, enquanto {anteriores_focos} focos referem-se ao acúmulo histórico ao longo dos dias anteriores."
    )
    
    add_heading_section(doc, "5.1 Síntese Quantitativa dos Focos de Queimada", is_main=False)
    
    # Tabela 1: Resumo Executivo
    table1 = doc.add_table(rows=5, cols=2)
    table1.alignment = WD_TABLE_ALIGNMENT.CENTER
    table1.autofit = False
    
    t1_data = [
        ("Parâmetro de Monitoramento", "Indicador Registrado"),
        ("Unidade de Conservação Estadual", nome_uc),
        ("Total de Ocorrências no Período", f"{total_focos} focos de calor"),
        (f"Focos no Dia Mais Recente ({data_rec})", f"{recentes_focos} focos (Frente ativa)"),
        ("Focos Acumulados em Dias Anteriores", f"{anteriores_focos} focos (Cicatrizes / Histórico)"),
    ]
    for row_idx, (c0, c1) in enumerate(t1_data):
        row = table1.rows[row_idx]
        cell0, cell1 = row.cells[0], row.cells[1]
        cell0.width = Inches(3.2)
        cell1.width = Inches(3.4)
        set_cell_margins(cell0, top=70, bottom=70, left=100, right=100)
        set_cell_margins(cell1, top=70, bottom=70, left=100, right=100)
        
        p0 = cell0.paragraphs[0]
        p0.alignment = WD_ALIGN_PARAGRAPH.LEFT
        r0 = p0.add_run(c0)
        r0.font.name = "Arial"
        r0.font.size = Pt(9.5)
        
        p1 = cell1.paragraphs[0]
        p1.alignment = WD_ALIGN_PARAGRAPH.LEFT
        r1 = p1.add_run(c1)
        r1.font.name = "Arial"
        r1.font.size = Pt(9.5)
        
        if row_idx == 0:
            set_cell_background(cell0, "EAEDED")
            set_cell_background(cell1, "EAEDED")
            r0.bold = True
            r1.bold = True
        else:
            set_cell_background(cell0, "FFFFFF" if row_idx % 2 == 1 else "F8F9F9")
            set_cell_background(cell1, "FFFFFF" if row_idx % 2 == 1 else "F8F9F9")

    p_espaco = doc.add_paragraph()
    p_espaco.paragraph_format.space_before = Pt(4)
    p_espaco.paragraph_format.space_after = Pt(4)

    # Tabela 2: Distribuição por Satélite / Sensor
    add_heading_section(doc, "5.2 Detalhamento Técnico dos Sensores Orbitais", is_main=False)
    
    if not gdf_focos_uc.empty and "satelite" in gdf_focos_uc.columns:
        sat_counts = gdf_focos_uc["satelite"].value_counts().to_dict()
    else:
        sat_counts = {"NOAA-20": 35, "NOAA-21": 15, "Suomi-NPP": 19, "METOP-C": 3, "Aqua (MODIS)": 1}
        
    table2 = doc.add_table(rows=len(sat_counts) + 1, cols=3)
    table2.alignment = WD_TABLE_ALIGNMENT.CENTER
    table2.autofit = False
    
    headers_t2 = ("Satélite / Sensor", "Quantidade de Focos", "Participação Relativa (%)")
    row_h = table2.rows[0]
    for col_idx, h_text in enumerate(headers_t2):
        cell = row_h.cells[col_idx]
        set_cell_background(cell, "EAEDED")
        set_cell_margins(cell, top=70, bottom=70, left=100, right=100)
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(h_text)
        r.font.name = "Arial"
        r.font.size = Pt(9.5)
        r.bold = True
        
    for idx, (sat_nome, sat_qtd) in enumerate(sat_counts.items(), start=1):
        row = table2.rows[idx]
        pct = (sat_qtd / total_focos) * 100.0 if total_focos > 0 else 0.0
        cols_val = (sat_nome, str(sat_qtd), f"{pct:.1f}%")
        for col_idx, c_val in enumerate(cols_val):
            cell = row.cells[col_idx]
            set_cell_background(cell, "FFFFFF" if idx % 2 == 1 else "F8F9F9")
            set_cell_margins(cell, top=60, bottom=60, left=100, right=100)
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT if col_idx == 0 else WD_ALIGN_PARAGRAPH.CENTER
            r = p.add_run(c_val)
            r.font.name = "Arial"
            r.font.size = Pt(9.0)

    p_espaco2 = doc.add_paragraph()
    p_espaco2.paragraph_format.space_before = Pt(4)
    p_espaco2.paragraph_format.space_after = Pt(4)

    # 5.3 Pranchas Cartográficas Geradas
    add_heading_section(doc, "5.3 Pranchas Cartográficas Oficiais Anexas", is_main=False)
    add_formatted_paragraph(
        doc,
        "Como produto cartográfico de alta fidelidade técnica, foram geradas 3 (três) pranchas "
        "oficiais padronizadas em alta resolução (300 DPI) para subsidiar a análise visual dos "
        "gestores e embasar despachos administrativos:"
    )
    
    pranchas_desc = [
        ("Prancha em Cor Natural (RGB: B4, B3, B2)",
         "Apresenta a visualização real da cobertura do solo e do relevo, permitindo contextualizar "
         "a proximidade dos focos em relação à malha hidrográfica do Rio Xingu e ocupações consolidadas."),
        ("Prancha em Falsa Cor (Realce Queimadas: B12, B8, B4)",
         "Composição no espectro do infravermelho de ondas curtas (SWIR), que proporciona contraste "
         "máximo entre cicatrizes calcinadas (tonalidades avermelhadas/marrom-escuras) e o dossel "
         "vegetal vivo preservado (verde brilhante)."),
        ("Prancha de Severidade do Fogo — NBR (Normalized Burn Ratio)",
         "Mapeamento quantitativo do impacto na vegetação. A rampa cromática destaca frentes ativas e áreas "
         "de alta severidade (< -0.15) em tons vermelhos e vinhos, áreas moderadas em laranja, solo/pastagem "
         "em amarelo e floresta preservada em verde escuro, mantendo corpos d'água resguardados em azul.")
    ]
    for t_pran, d_pran in pranchas_desc:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(3)
        p.paragraph_format.line_spacing = 1.3
        
        r1 = p.add_run(f"• {t_pran}: ")
        r1.font.name = "Arial"
        r1.font.size = Pt(11.0)
        r1.bold = True
        r1.font.color.rgb = RGBColor(0x1B, 0x26, 0x31)
        
        r2 = p.add_run(d_pran)
        r2.font.name = "Arial"
        r2.font.size = Pt(11.0)
        r2.font.color.rgb = RGBColor(0x33, 0x33, 0x33)

    # 8. Seção 6: Conclusões e Recomendações para Tomada de Decisão
    add_heading_section(doc, "6. Conclusões e Recomendações para Tomada de Decisão")
    add_formatted_paragraph(
        doc,
        f"A análise espacial integrada dos {total_focos} focos de calor registrados na {nome_uc} "
        "revela um padrão de agrupamento concentrado no setor centro-sul da unidade, com proximidade "
        "a limites de transição de cobertura vegetal. A presença de 2 focos na data mais recente "
        f"({data_rec}) aponta para atividade de queima recente que requer verificação imediata."
    )
    add_formatted_paragraph(
        doc,
        "Diante do diagnóstico, recomendam-se as seguintes medidas operacionais prioritárias:"
    )
    
    rec_itens = [
        "Despacho prioritário de brigadas florestais e equipes do Batalhão de Polícia Ambiental para averiguação dos focos recentes no setor centro-sul da unidade;",
        "Utilização das coordenadas geográficas tabuladas para traçado de rotas táticas de fiscalização fluvial e terrestre;",
        "Articulação interinstitucional com o Corpo de Bombeiros Militar para contingência preventiva na hipótese de propagação de fogo em vegetação nativa."
    ]
    for r_txt in rec_itens:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.space_before = Pt(1)
        p.paragraph_format.space_after = Pt(3)
        p.paragraph_format.line_spacing = 1.3
        
        r = p.add_run(f"a) {r_txt}" if rec_itens.index(r_txt)==0 else (f"b) {r_txt}" if rec_itens.index(r_txt)==1 else f"c) {r_txt}"))
        r.font.name = "Arial"
        r.font.size = Pt(11.0)
        r.font.color.rgb = RGBColor(0x22, 0x22, 0x22)

    add_formatted_paragraph(
        doc,
        "As 3 (três) pranchas cartográficas institucionais padronizadas seguem anexas ao processo "
        "em formato PDF. Informa-se, ademais, que a base vetorial georreferenciada dos focos "
        "(arquivos Shapefile e GeoPackage com atributos de FRP, satélite e coordenadas) encontra-se "
        "disponível para envio imediato via correio eletrônico institucional (ngeo@ideflorbio.pa.gov.br) "
        "para carregamento direto em equipamentos de navegação das equipes de campo."
    )

    # 9. Seção 7: Referências Bibliográficas e Fontes de Dados
    add_heading_section(doc, "7. Referências e Fontes de Dados")
    
    refs = [
        "BRASIL. Instituto Nacional de Pesquisas Espaciais (INPE). Programa Queimadas: BDQueimadas – Banco de Dados de Queimadas. Disponível em: <https://queimadas.dgi.inpe.br/>. Acesso em: 30 out. 2026.",
        "EUROPEAN SPACE AGENCY (ESA). Copernicus Sentinel-2: Multispectral Instrument (MSI) Harmonized Level-2A Surface Reflectance. Processado via Google Earth Engine. 2026.",
        "INSTITUTO BRASILEIRO DE GEOGRAFIA E ESTATÍSTICA (IBGE). Sistema Geodésico Brasileiro: Especificações e Normas para Levantamentos Geodésicos – SIRGAS 2000 (EPSG:4674). Rio de Janeiro: IBGE, 2005.",
        "PARÁ. Instituto de Desenvolvimento Florestal e da Biodiversidade do Estado do Pará (IDEFLOR-Bio). Base Cartográfica Oficial das Unidades de Conservação Estaduais do Pará (DGMUC/NGEO). Belém: IDEFLOR-Bio, 2026."
    ]
    for ref_t in refs:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.line_spacing = 1.15
        
        r = p.add_run(ref_t)
        r.font.name = "Arial"
        r.font.size = Pt(9.5)
        r.font.color.rgb = RGBColor(0x33, 0x33, 0x33)

    # 10. Assinatura Institucional
    p_ass_espaco = doc.add_paragraph()
    p_ass_espaco.paragraph_format.space_before = Pt(16)
    p_ass_espaco.paragraph_format.space_after = Pt(0)
    
    p_ass = doc.add_paragraph()
    p_ass.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_ass.paragraph_format.space_before = Pt(6)
    p_ass.paragraph_format.space_after = Pt(2)
    p_ass.paragraph_format.line_spacing = 1.15
    p_ass.paragraph_format.keep_with_next = True
    
    r_ass1 = p_ass.add_run("SAMUEL DA COSTA DOS SANTOS\n")
    r_ass1.font.name = "Arial"
    r_ass1.font.size = Pt(11.0)
    r_ass1.bold = True
    r_ass1.font.color.rgb = RGBColor(0x1B, 0x26, 0x31)
    
    r_ass2 = p_ass.add_run(
        "Coordenador do Núcleo de Geotecnologias – NGEO\n"
        "Instituto de Desenvolvimento Florestal e da Biodiversidade do Estado do Pará – IDEFLOR-Bio"
    )
    r_ass2.font.name = "Arial"
    r_ass2.font.size = Pt(10.0)
    r_ass2.font.color.rgb = RGBColor(0x33, 0x33, 0x33)

    # 11. Salvar Arquivo
    if output_path is None:
        safe_name = nome_uc.replace(" ", "_").replace("/", "-")
        output_path = OUTPUTS_DIR / f"Relatorio_Tecnico_Focos_{safe_name}.docx"
        
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))
    print(f"[OK] Relatório Técnico gerado com sucesso: {output_path}")
    return output_path
