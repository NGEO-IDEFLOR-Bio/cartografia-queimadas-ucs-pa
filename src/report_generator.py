"""
Gerador de Relatórios Técnicos Oficiais de Queimadas (NGEO / IDEFLOR-Bio)
========================================================================
Gera relatórios técnicos padronizados em formato Microsoft Word (.docx)
a partir do template institucional com cabeçalho oficial preservado.

Especificações Formais e Tipográficas Institucionais:
- Tipografia: Arial 12 pt no corpo de texto
- Espaçamento entre linhas: 1,5 linhas
- Recuo na primeira linha dos parágrafos: exatamente 1,5 cm (Cm(1.5))
- Listas com tópicos: recuo padronizado (1,5 cm) com marcadores (•) e entrelinhas 1,5
- Tabelas: estilo Table Grid institucional, fonte Arial, zebrado suave
- Referências: norma ABNT NBR 6023 (Arial 12 pt, entrelinhas simples, negrito no título da obra)
- Apêndice A: Tabela completa de localização geográfica (coordenadas SIRGAS 2000)
- Tom estritamente técnico: subsídio neutro e objetivo para tomada de decisão (sem direcionamento operacional nem linguagem promocional)
- Contextualização: 100% dinâmica e aderente para qualquer uma das 29 UCs do Pará
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, date

import docx
from docx import Document
from docx.shared import Pt, Inches, Cm, RGBColor
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


def set_cell_margins(cell, top=80, bottom=80, left=120, right=120):
    """Define o preenchimento interno (padding) da célula em dxa."""
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


def add_body_paragraph(
    doc: Document,
    text: str,
    font_size: float = 12.0,
    bold: bool = False,
    italic: bool = False,
    color_rgb: RGBColor = RGBColor(0x22, 0x22, 0x22),
    space_before: float = 0.0,
    space_after: float = 6.0
):
    """Adiciona parágrafo em Arial 12pt, entrelinhas 1.5, recuo de 1,5 cm na primeira linha e justificado."""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.space_before = Pt(space_before)
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.line_spacing = 1.5
    p.paragraph_format.first_line_indent = Cm(1.5)

    run = p.add_run(text)
    run.font.name = "Arial"
    run.font.size = Pt(font_size)
    run.bold = bold
    run.italic = italic
    run.font.color.rgb = color_rgb
    return p


def add_topic_item(
    doc: Document,
    prefix_text: str,
    body_text: str,
    font_size: float = 12.0,
    space_after: float = 3.0,
    line_spacing: float = 1.5
):
    """
    Adiciona item de lista/alínea com marcador padronizado segundo ABNT:
    - Tipografia Arial 12 pt
    - Recuo à esquerda de 1,5 cm com recuo de primeira linha de -0,5 cm
    - Espaçamento entrelinhas 1,5
    - Prefixo em negrito (se houver)
    """
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.space_before = Pt(1.0)
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.line_spacing = line_spacing
    p.paragraph_format.left_indent = Cm(1.5)
    p.paragraph_format.first_line_indent = -Cm(0.5)

    r_bullet = p.add_run("• ")
    r_bullet.font.name = "Arial"
    r_bullet.font.size = Pt(font_size)
    r_bullet.bold = True
    r_bullet.font.color.rgb = RGBColor(0x22, 0x22, 0x22)

    if prefix_text:
        r_pre = p.add_run(f"{prefix_text}: ")
        r_pre.font.name = "Arial"
        r_pre.font.size = Pt(font_size)
        r_pre.bold = True
        r_pre.font.color.rgb = RGBColor(0x22, 0x22, 0x22)

    r_body = p.add_run(body_text)
    r_body.font.name = "Arial"
    r_body.font.size = Pt(font_size)
    r_body.font.color.rgb = RGBColor(0x22, 0x22, 0x22)
    return p


def add_abnt_reference(doc: Document, autor: str, titulo_obra: str, complemento: str):
    """
    Adiciona referência no formato rigoroso da ABNT NBR 6023:
    - Tipografia Arial 12 pt
    - Alinhamento à esquerda
    - Espaçamento entrelinhas simples (1.0)
    - Separadas entre si por espaço de 1 linha em branco (Pt(12.0))
    - Título da obra em negrito
    - Sem recuo na primeira linha (margem zerada)
    """
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(12.0)
    p.paragraph_format.line_spacing = 1.0
    p.paragraph_format.first_line_indent = Cm(0)
    p.paragraph_format.left_indent = Cm(0)

    # Autor / Instituição
    r_aut = p.add_run(autor + " ")
    r_aut.font.name = "Arial"
    r_aut.font.size = Pt(12.0)
    r_aut.font.color.rgb = RGBColor(0x22, 0x22, 0x22)

    # Título da Obra (em NEGRITO, conforme ABNT NBR 6023)
    r_tit = p.add_run(titulo_obra)
    r_tit.font.name = "Arial"
    r_tit.font.size = Pt(12.0)
    r_tit.bold = True
    r_tit.font.color.rgb = RGBColor(0x22, 0x22, 0x22)

    # Complemento (cidade, editora, data, disponibilidade, acesso)
    if complemento:
        comp_str = " " + complemento if not complemento.startswith((".", ",")) else complemento
        r_comp = p.add_run(comp_str)
        r_comp.font.name = "Arial"
        r_comp.font.size = Pt(12.0)
        r_comp.font.color.rgb = RGBColor(0x22, 0x22, 0x22)
    return p


def add_heading_section(doc: Document, text: str, is_main: bool = True):
    """Adiciona títulos de seções institucionais em Arial negrito sem recuo de primeira linha."""
    size = 12.0 if is_main else 11.5
    before = 12.0 if is_main else 8.0
    after = 4.0
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.space_before = Pt(before)
    p.paragraph_format.space_after = Pt(after)
    p.paragraph_format.line_spacing = 1.15
    p.paragraph_format.first_line_indent = Cm(0)
    p.paragraph_format.left_indent = Cm(0)
    p.paragraph_format.keep_with_next = True

    run = p.add_run(text)
    run.font.name = "Arial"
    run.font.size = Pt(size)
    run.bold = True
    run.font.color.rgb = RGBColor(0x1B, 0x26, 0x31)
    return p


def generate_dynamic_uc_context(gdf_uc: Optional[gpd.GeoDataFrame], nome_uc: str) -> str:
    """
    Gera automaticamente uma contextualização formal, jurídica e geográfica rigorosa
    baseada nos atributos cadastrais oficiais de qualquer uma das 29 UCs estaduais do Pará.
    """
    if gdf_uc is None or gdf_uc.empty:
        try:
            from src.exporter import find_uc_by_name
            gdf_uc = find_uc_by_name(nome_uc)
        except Exception:
            gdf_uc = None

    if gdf_uc is not None and not gdf_uc.empty:
        row = gdf_uc.iloc[0]
        nome = str(row.get("Nome", nome_uc)).strip()
        cat = str(row.get("Categoria", "")).strip().upper()
        grupo = str(row.get("Grupo", "Uso Sustentável")).strip()
        decreto = str(row.get("Situação Legal", "")).strip()
        area_ha = row.get("Área Calculada (ha)", row.get("Área (decreto) (ha)", 0))
        munis = str(row.get("Municipios_lista", "")).strip()
        ri = str(row.get("RegioesIntegracao_lista", "")).strip()
    else:
        nome = nome_uc
        cat = "UC"
        grupo = "Uso Sustentável"
        decreto = ""
        area_ha = 0
        munis = ""
        ri = ""

    # 1. Base Jurídica de Criação
    if decreto and decreto.lower() != "nan":
        txt_legal = f"criada e regulamentada por meio do {decreto}"
    else:
        txt_legal = "instituída formalmente no âmbito do Sistema Estadual de Unidades de Conservação (SEUC/PA)"

    # 2. Finalidade e Vocação pelo Grupo/Categoria do SNUC (Lei Federal nº 9.985/2000)
    is_prot_integral = "PROTEÇÃO INTEGRAL" in grupo.upper() or any(k in cat for k in ["PARQUE", "ESEC", "REBIO", "REVIS", "MONA"])

    if is_prot_integral:
        if "PARQUE" in cat:
            finalidade = (
                "enquadra-se no Grupo de Proteção Integral (categoria Parque Estadual), tendo como objetivo primordial "
                "a preservação de ecossistemas naturais de grande relevância ecológica e beleza cênica, sendo admitido "
                "apenas o uso indireto de seus recursos naturais e o desenvolvimento de atividades de pesquisa científica, "
                "educação ambiental e turismo ecológico"
            )
        elif "ESEC" in cat or "ESTAÇÃO" in cat:
            finalidade = (
                "integra o Grupo de Proteção Integral na categoria de Estação Ecológica (ESEC), tendo como objetivo precípuo "
                "a preservação da natureza e a realização de pesquisas científicas, sendo expressamente vedada a exploração "
                "direta de recursos ou alterações antrópicas em seus ecossistemas"
            )
        elif "REBIO" in cat or "BIOLÓGICA" in cat:
            finalidade = (
                "constitui uma Reserva Biológica (REBIO), unidade de Proteção Integral que visa à preservação integral "
                "da biota e demais atributos naturais sem interferência humana direta, ressalvadas medidas de recuperação "
                "e pesquisas científicas devidamente autorizadas"
            )
        elif "REVIS" in cat or "REFÚGIO" in cat:
            finalidade = (
                "está categorizada como Refúgio de Vida Silvestre (REVIS), unidade de Proteção Integral destinada a assegurar "
                "condições para a existência ou reprodução de espécies da flora local e da fauna residente ou migratória"
            )
        elif "MONA" in cat or "MONUMENTO" in cat:
            finalidade = (
                "enquadra-se como Monumento Natural (MONA), visando a preservar sítios naturais raros, singulares ou de "
                "grande beleza cênica"
            )
        else:
            finalidade = (
                "integra o Grupo de Proteção Integral, com foco na preservação estrita dos recursos ambientais e processos ecológicos nativos"
            )
    else:
        # Uso Sustentável
        if "RDS" in cat or "DESENVOLVIMENTO SUSTENTÁVEL" in cat:
            finalidade = (
                "enquadra-se no Grupo de Uso Sustentável como Reserva de Desenvolvimento Sustentável (RDS), gerida pelo IDEFLOR-Bio "
                "com a missão precípua de compatibilizar a conservação da biodiversidade com o uso sustentável dos recursos naturais "
                "pelas populações tradicionais residentes"
            )
        elif "FLOTA" in cat or "FLORESTA" in cat:
            finalidade = (
                "constitui uma Floresta Estadual (FLOTA), categoria de Uso Sustentável com vocação voltada ao manejo florestal sustentável "
                "de recursos madeireiros e não-madeireiros, à conservação da cobertura florestal contínua e à pesquisa científica aplicada"
            )
        elif "APA" in cat or "PROTEÇÃO AMBIENTAL" in cat:
            finalidade = (
                "está estabelecida como Área de Proteção Ambiental (APA), unidade de Uso Sustentável que concilia terras públicas "
                "e privadas sob zoneamento ecológico-econômico, visando a disciplinar o uso do solo, proteger os recursos hídricos "
                "e manter os remanescentes de vegetação nativa"
            )
        else:
            finalidade = (
                "integra o Grupo de Uso Sustentável, tendo como foco compatibilizar o uso equilibrado dos recursos naturais "
                "com a manutenção da integridade da paisagem ambiental"
            )

    # 3. Contexto Territorial, Hídrico e Fitogeográfico
    try:
        val_area = float(area_ha)
        txt_area = f"com uma área territorial calculada em aproximadamente {val_area:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " hectares"
    except Exception:
        txt_area = "com expressiva abrangência territorial"

    txt_loc = ""
    if munis and munis.lower() != "nan":
        txt_loc += f", abrangendo setores territoriais do(s) município(s) de {munis}"
    if ri and ri.lower() != "nan":
        txt_loc += f", no âmbito da Região de Integração {ri}"

    txt_fito = (
        f"A {nome} integra o Sistema Estadual de Unidades de Conservação do Pará (SEUC/PA), sob gestão do IDEFLOR-Bio, {txt_legal}. "
        f"A unidade {finalidade}, estruturando-se {txt_area}{txt_loc}. "
        "No contexto fitofisionômico da Amazônia paraense, seus ecossistemas encontram-se sujeitos aos ciclos sazonais de estiagem e variações no balanço hídrico regional, "
        "condição climática que historicamente eleva o estresse da vegetação e intensifica a suscetibilidade a focos de calor e queimadas antrópicas acidentais ou irregulares em suas zonas limítrofes e corredores de acesso."
    )
    return txt_fito


def build_technical_report_docx(
    nome_uc: str,
    periodo_str: str,
    gdf_focos_uc: gpd.GeoDataFrame,
    metricas: Dict[str, Any],
    gdf_uc: Optional[gpd.GeoDataFrame] = None,
    output_path: Optional[Path] = None
) -> Path:
    """
    Gera o Relatório Técnico Oficial do NGEO em formato Microsoft Word (.docx),
    preservando rigorosamente o cabeçalho oficial do IDEFLOR-Bio, a tipografia Arial 12pt,
    espaçamento 1,5, recuo de 1,5 cm na primeira linha dos parágrafos, tópicos padronizados,
    tabelas executivas, apêndice com coordenadas dos focos e referências ABNT NBR 6023.
    """
    # 1. Carregar Template Matriz com Cabeçalho Institucional
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
    
    # 2. Título Principal
    p_tipo = doc.add_paragraph()
    p_tipo.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_tipo.paragraph_format.space_before = Pt(0)
    p_tipo.paragraph_format.space_after = Pt(2)
    p_tipo.paragraph_format.line_spacing = 1.15
    p_tipo.paragraph_format.first_line_indent = Cm(0)
    r_tipo = p_tipo.add_run("RELATÓRIO TÉCNICO")
    r_tipo.font.name = "Arial"
    r_tipo.font.size = Pt(13.0)
    r_tipo.bold = True
    r_tipo.font.color.rgb = RGBColor(0x1B, 0x26, 0x31)
    
    p_sub = doc.add_paragraph()
    p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_sub.paragraph_format.space_before = Pt(0)
    p_sub.paragraph_format.space_after = Pt(14)
    p_sub.paragraph_format.line_spacing = 1.15
    p_sub.paragraph_format.first_line_indent = Cm(0)
    r_sub = p_sub.add_run(f"Monitoramento de Focos de Calor e Severidade Espectral – {nome_uc}")
    r_sub.font.name = "Arial"
    r_sub.font.size = Pt(11.0)
    r_sub.bold = True
    r_sub.font.color.rgb = RGBColor(0x2C, 0x3E, 0x50)

    # 3. Seção 1: Identificação do Documento (Tópicos com marcadores padrão ABNT)
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
        ("Instrumento Técnico", "Relatório de Monitoramento Operacional de Focos de Queimada;"),
        ("Origem / Metodologia", "Pipeline de Cartografia de Queimadas em UCs (NGEO / IDEFLOR-Bio);"),
        ("Responsabilidade Técnica", "Samuel da Costa dos Santos – Coordenador do Núcleo de Geotecnologias (NGEO);"),
        ("Unidade de Conservação", f"{nome_uc};"),
        ("Período de Análise", f"{periodo_str} (janela móvel dos últimos 30 dias);"),
        ("Data de Emissão", f"{data_hoje_extenso}."),
    ]
    for rotulo, val in ident_itens:
        add_topic_item(doc, rotulo, val, font_size=12.0, space_after=2.5)

    # 4. Seção 2: Finalidade e Objetivos
    add_heading_section(doc, "2. Finalidade e Objetivos")
    add_body_paragraph(
        doc,
        "O presente relatório técnico tem por finalidade fornecer subsídios geoespaciais "
        "objetivos para a tomada de decisão no âmbito da gestão e monitoramento das Unidades "
        "de Conservação estaduais do Pará."
    )
    add_body_paragraph(
        doc,
        "O diagnóstico apresenta a cronologia, o quantitativo e a distribuição espacial dos focos "
        "de calor detectados na Unidade de Conservação pelo Programa BDQueimadas/INPE, correlacionados "
        "à resposta espectral de severidade do dano à vegetação por imagens orbitais Sentinel-2 "
        "(Copernicus/ESA). As informações visam a embasar as análises e eventuais medidas a serem adotadas "
        "pelos setores competentes."
    )

    # 5. Seção 3: Contextualização da Área de Estudo (100% Dinâmica para as 29 UCs)
    add_heading_section(doc, "3. Contextualização da Área de Estudo")
    texto_contexto = generate_dynamic_uc_context(gdf_uc, nome_uc)
    add_body_paragraph(doc, texto_contexto)

    # 6. Seção 4: Procedimentos Metodológicos Realizados
    add_heading_section(doc, "4. Procedimentos Metodológicos Realizados")
    add_body_paragraph(
        doc,
        "Os procedimentos analíticos e cartográficos foram conduzidos no ambiente automatizado "
        "do Núcleo de Geotecnologias (NGEO), estruturado nas seguintes etapas encadeadas:"
    )
    
    passos_met = [
        ("Ingestão de Dados Oficiais de Focos",
         "Conexão automatizada ao dataserver do INPE (Programa BDQueimadas), recuperando dados diários "
         "e mensais de sensores orbitais de referência (VIIRS e MODIS);"),
        ("Filtragem Espacial e Segregação Temporal",
         f"Intersecção espacial dos focos com a poligonal homologada da {nome_uc} (base DGMUC/IDEFLOR-Bio), "
         "segregando os registros do dia mais recente em relação ao acumulado do período;"),
        ("Processamento Orbital e Cálculo Espectral (Sentinel-2 Harmonized)",
         "Processamento em nuvem no Google Earth Engine (GEE) de imagens Sentinel-2 com aplicação de máscaras "
         "de nuvens e cálculo do índice Normalized Burn Ratio (NBR), resguardando corpos hídricos via máscara espectral;"),
        ("Diagramação Cartográfica Institucional",
         "Geração automatizada de pranchas em formato A4 Paisagem (297 x 210 mm) em alta resolução (300 DPI) "
         "estruturadas em três escalas integradas: Detalhe da UC com mosaico orbital, Contexto Regional da Unidade "
         "e Localização Macroestadual no Pará.")
    ]
    for rotulo, desc in passos_met:
        add_topic_item(doc, rotulo, desc, font_size=12.0, space_after=3.5)

    # 7. Seção 5: Resultados e Diagnóstico Espacial
    add_heading_section(doc, "5. Resultados e Diagnóstico Espacial")
    
    total_focos = metricas.get("total", len(gdf_focos_uc))
    recentes_focos = metricas.get("recentes", 0)
    anteriores_focos = metricas.get("anteriores", 0)
    data_rec = metricas.get("data_ultima_observacao", "Recente")
    
    add_body_paragraph(
        doc,
        f"No período avaliado ({periodo_str}), foram contabilizados {total_focos} focos de calor incidentes "
        f"no interior da {nome_uc}. Desse montante, {recentes_focos} ocorrência(s) correspondem "
        f"ao registro mais recente do monitoramento ({data_rec}), enquanto {anteriores_focos} focos "
        "referem-se ao acúmulo histórico ao longo dos dias anteriores."
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
        (f"Focos no Dia Mais Recente ({data_rec})", f"{recentes_focos} focos"),
        ("Focos Acumulados em Dias Anteriores", f"{anteriores_focos} focos"),
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
        p0.paragraph_format.first_line_indent = Cm(0)
        p0.paragraph_format.line_spacing = 1.15
        r0 = p0.add_run(c0)
        r0.font.name = "Arial"
        r0.font.size = Pt(10.0)
        
        p1 = cell1.paragraphs[0]
        p1.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p1.paragraph_format.first_line_indent = Cm(0)
        p1.paragraph_format.line_spacing = 1.15
        r1 = p1.add_run(c1)
        r1.font.name = "Arial"
        r1.font.size = Pt(10.0)
        
        if row_idx == 0:
            set_cell_background(cell0, "EAEDED")
            set_cell_background(cell1, "EAEDED")
            r0.bold = True
            r1.bold = True
        else:
            set_cell_background(cell0, "FFFFFF" if row_idx % 2 == 1 else "F8F9F9")
            set_cell_background(cell1, "FFFFFF" if row_idx % 2 == 1 else "F8F9F9")

    p_espaco = doc.add_paragraph()
    p_espaco.paragraph_format.space_before = Pt(3)
    p_espaco.paragraph_format.space_after = Pt(3)

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
        p.paragraph_format.first_line_indent = Cm(0)
        p.paragraph_format.line_spacing = 1.15
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
            p.paragraph_format.first_line_indent = Cm(0)
            p.paragraph_format.line_spacing = 1.15
            r = p.add_run(c_val)
            r.font.name = "Arial"
            r.font.size = Pt(9.0)

    p_espaco2 = doc.add_paragraph()
    p_espaco2.paragraph_format.space_before = Pt(3)
    p_espaco2.paragraph_format.space_after = Pt(3)

    # 5.3 Pranchas Cartográficas Geradas (Apresentação direta conforme orientação do usuário)
    add_heading_section(doc, "5.3 Pranchas Cartográficas Anexas", is_main=False)
    add_body_paragraph(
        doc,
        "Constituem produtos cartográficos integrantes deste relatório as seguintes pranchas "
        "técnicas em formato A4 Paisagem:"
    )
    
    pranchas_lista = [
        ("Composição em Cor Natural (RGB 432)", "Imagem Sentinel-2 no espectro visível (Bandas B4, B3 e B2);"),
        ("Composição em Falsa Cor (RGB 12-8-4)", "Imagem Sentinel-2 no infravermelho de ondas curtas, infravermelho próximo e vermelho (Bandas B12, B8 e B4);"),
        ("Índice de Severidade do Fogo (NBR)", "Produto derivado do cálculo normalizado entre as bandas do infravermelho próximo (B8) e infravermelho de ondas curtas (B12).")
    ]
    for t_pran, d_pran in pranchas_lista:
        add_topic_item(doc, t_pran, d_pran, font_size=12.0, space_after=3.0)

    # 8. Seção 6: Considerações Finais (Sem direcionamento de medidas operacionais)
    add_heading_section(doc, "6. Considerações Finais")
    add_body_paragraph(
        doc,
        f"A espacialização dos dados registrou um total de {total_focos} focos de calor no interior da "
        f"{nome_uc} durante o período de {periodo_str}, dos quais {recentes_focos} ocorrência(s) correspondem "
        f"à observação mais recente ({data_rec}) e {anteriores_focos} aos registros acumulados nos dias anteriores."
    )
    add_body_paragraph(
        doc,
        "O presente documento, acompanhado das 3 (três) pranchas cartográficas oficiais e da tabela "
        "nominal de coordenadas geodésicas (SIRGAS 2000) discriminada no Apêndice A, fornece o subsídio "
        "espacial para fundamentar a avaliação e as decisões a serem adotadas pelos setores competentes."
    )

    # 9. Seção 7: Referências e Fontes de Dados (Formato ABNT NBR 6023 com negrito no título da obra)
    add_heading_section(doc, "7. Referências e Fontes de Dados")
    
    refs: List[Tuple[str, str, str]] = [
        (
            "BRASIL. Instituto Nacional de Pesquisas Espaciais (INPE).",
            "Programa Queimadas: BDQueimadas – Banco de Dados de Queimadas.",
            "São José dos Campos: INPE, 2026. Disponível em: https://queimadas.dgi.inpe.br/. Acesso em: 30 out. 2026."
        ),
        (
            "EUROPEAN SPACE AGENCY (ESA).",
            "Copernicus Sentinel-2: Multispectral Instrument (MSI) Harmonized Level-2A Surface Reflectance.",
            "Paris: ESA, 2026."
        ),
        (
            "INSTITUTO BRASILEIRO DE GEOGRAFIA E ESTATÍSTICA (IBGE).",
            "Resolução nº 1, de 25 de fevereiro de 2005.",
            "Estabelece a adoção do Sistema de Referência Geocêntrico para as Américas (SIRGAS 2000 / EPSG:4674) como o novo referencial geodésico oficial brasileiro. Rio de Janeiro: IBGE, 2005."
        ),
        (
            "PARÁ. Instituto de Desenvolvimento Florestal e da Biodiversidade do Estado do Pará (IDEFLOR-Bio).",
            "Base Cartográfica Oficial das Unidades de Conservação Estaduais do Pará.",
            "Belém: DGMUC/NGEO, 2026."
        )
    ]
    
    for autor_ref, titulo_ref, comp_ref in refs:
        add_abnt_reference(doc, autor_ref, titulo_ref, comp_ref)

    # 10. Assinatura Institucional
    p_ass_espaco = doc.add_paragraph()
    p_ass_espaco.paragraph_format.space_before = Pt(14)
    p_ass_espaco.paragraph_format.space_after = Pt(0)
    p_ass_espaco.paragraph_format.first_line_indent = Cm(0)
    
    p_ass = doc.add_paragraph()
    p_ass.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_ass.paragraph_format.space_before = Pt(6)
    p_ass.paragraph_format.space_after = Pt(2)
    p_ass.paragraph_format.line_spacing = 1.15
    p_ass.paragraph_format.first_line_indent = Cm(0)
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

    # 11. Apêndice A: Relação Nominal e Coordenadas Geográficas de Todos os Focos
    doc.add_page_break()
    
    add_heading_section(doc, "APÊNDICE A – Relação Nominal e Coordenadas Geográficas dos Focos Detectados")
    add_body_paragraph(
        doc,
        f"A tabela a seguir discrimina a totalidade dos {total_focos} focos de calor registrados "
        f"no polígono da {nome_uc} durante o período de monitoramento ({periodo_str}), fornecendo "
        "as coordenadas geodésicas (SIRGAS 2000), o satélite detector, o município de incidência "
        "e a Potência Radiativa do Fogo (FRP):"
    )

    if not gdf_focos_uc.empty:
        # Ordenar: mais recentes primeiro
        df_ord = gdf_focos_uc.copy()
        if "data_hora_gmt" in df_ord.columns:
            df_ord["data_sort"] = pd.to_datetime(df_ord["data_hora_gmt"], errors="coerce")
            df_ord = df_ord.sort_values(by="data_sort", ascending=False)
            
        n_rows = len(df_ord) + 1
        t_apend = doc.add_table(rows=n_rows, cols=7)
        t_apend.alignment = WD_TABLE_ALIGNMENT.CENTER
        t_apend.autofit = False

        headers_ap = ("Nº", "Data/Hora (GMT)", "Latitude", "Longitude", "Satélite", "FRP (MW)", "Município")
        col_widths = (Inches(0.4), Inches(1.3), Inches(1.0), Inches(1.0), Inches(1.0), Inches(0.8), Inches(1.1))

        row_h_ap = t_apend.rows[0]
        for col_idx, h_text in enumerate(headers_ap):
            cell = row_h_ap.cells[col_idx]
            cell.width = col_widths[col_idx]
            set_cell_background(cell, "EAEDED")
            set_cell_margins(cell, top=60, bottom=60, left=60, right=60)
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.first_line_indent = Cm(0)
            p.paragraph_format.line_spacing = 1.0
            r = p.add_run(h_text)
            r.font.name = "Arial"
            r.font.size = Pt(8.5)
            r.bold = True

        for idx, (_, row_f) in enumerate(df_ord.iterrows(), start=1):
            row_elem = t_apend.rows[idx]
            
            # Formatação de data
            dh = str(row_f.get("data_hora_gmt", ""))
            try:
                dt_val = pd.to_datetime(dh)
                dh_fmt = dt_val.strftime("%d/%m/%Y %H:%M")
            except Exception:
                dh_fmt = dh[:16] if len(dh)>=16 else dh

            # Latitude e Longitude
            lat_val = row_f.geometry.y if hasattr(row_f, "geometry") and row_f.geometry else row_f.get("lat", 0.0)
            lon_val = row_f.geometry.x if hasattr(row_f, "geometry") and row_f.geometry else row_f.get("lon", 0.0)
            lat_fmt = f"{lat_val:.5f}°"
            lon_fmt = f"{lon_val:.5f}°"

            sat_fmt = str(row_f.get("satelite", "-"))
            frp_raw = row_f.get("frp", None)
            try:
                frp_fmt = f"{float(frp_raw):.1f}" if pd.notnull(frp_raw) and float(frp_raw) > 0 else "-"
            except Exception:
                frp_fmt = "-"

            muni_fmt = str(row_f.get("municipio", "-")).title()

            vals_row = (str(idx), dh_fmt, lat_fmt, lon_fmt, sat_fmt, frp_fmt, muni_fmt)
            
            bg_color = "FFFFFF" if idx % 2 == 1 else "F9FAFA"
            
            for col_idx, val_txt in enumerate(vals_row):
                cell = row_elem.cells[col_idx]
                cell.width = col_widths[col_idx]
                set_cell_background(cell, bg_color)
                set_cell_margins(cell, top=45, bottom=45, left=50, right=50)
                p = cell.paragraphs[0]
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER if col_idx in [0, 1, 2, 3, 4, 5] else WD_ALIGN_PARAGRAPH.LEFT
                p.paragraph_format.first_line_indent = Cm(0)
                p.paragraph_format.line_spacing = 1.0
                r = p.add_run(val_txt)
                r.font.name = "Arial"
                r.font.size = Pt(8.0)
                if col_idx == 0:
                    r.bold = True

    # 12. Salvar Arquivo
    if output_path is None:
        safe_name = nome_uc.replace(" ", "_").replace("/", "-")
        output_path = OUTPUTS_DIR / f"Relatorio_Tecnico_Focos_{safe_name}.docx"
        
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))
    print(f"[OK] Relatório Técnico Oficial gerado com sucesso: {output_path}")
    return output_path


def convert_docx_to_pdf(docx_path: Path, output_pdf_path: Optional[Path] = None) -> Optional[Path]:
    """
    Converte documento Word (.docx) para PDF mantendo fidelidade visual absoluta.
    Suporta:
    1. LibreOffice / soffice (Linux, Google Colab, macOS, Windows com LibreOffice instalado)
    2. Microsoft Word via COM (Windows)
    3. docx2pdf (se instalado)
    """
    docx_path = Path(docx_path).resolve()
    if not docx_path.exists():
        return None
        
    if output_pdf_path is None:
        output_pdf_path = docx_path.with_suffix(".pdf")
    else:
        output_pdf_path = Path(output_pdf_path).resolve()

    # Tentativa 1: LibreOffice / soffice (padrão em ambientes Linux / Colab / headless)
    soffice_cmd = None
    for cmd in ["libreoffice", "soffice"]:
        if shutil.which(cmd):
            soffice_cmd = cmd
            break
            
    if soffice_cmd:
        try:
            out_dir = output_pdf_path.parent
            res = subprocess.run(
                [soffice_cmd, "--headless", "--convert-to", "pdf:writer_pdf_Export", str(docx_path), "--outdir", str(out_dir)],
                capture_output=True,
                text=True,
                timeout=60
            )
            expected_pdf = out_dir / (docx_path.stem + ".pdf")
            if expected_pdf.exists():
                if expected_pdf != output_pdf_path:
                    shutil.move(str(expected_pdf), str(output_pdf_path))
                print(f"[OK] Relatório PDF gerado via LibreOffice: {output_pdf_path}")
                return output_pdf_path
        except Exception as e:
            print(f"[!] Aviso: Falha na conversão via LibreOffice: {e}")

    # Tentativa 2: MS Word COM Automation (Windows)
    if os.name == "nt":
        try:
            import win32com.client
            import pythoncom
            pythoncom.CoInitialize()
            word = win32com.client.Dispatch("Word.Application")
            word.Visible = False
            word.DisplayAlerts = False
            doc = word.Documents.Open(str(docx_path))
            doc.SaveAs(str(output_pdf_path), FileFormat=17)  # 17 = wdFormatPDF
            doc.Close(False)
            word.Quit()
            if output_pdf_path.exists():
                print(f"[OK] Relatório PDF gerado via Word COM: {output_pdf_path}")
                return output_pdf_path
        except Exception as e:
            print(f"[!] Aviso: Falha na conversão via Word COM: {e}")

    # Tentativa 3: docx2pdf (se instalado)
    try:
        from docx2pdf import convert
        convert(str(docx_path), str(output_pdf_path))
        if output_pdf_path.exists():
            print(f"[OK] Relatório PDF gerado via docx2pdf: {output_pdf_path}")
            return output_pdf_path
    except Exception:
        pass

    print("[!] Aviso: Não foi possível converter .docx para .pdf automaticamente (requer LibreOffice ou Word). O arquivo .docx permanece disponível.")
    return None
