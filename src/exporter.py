"""
Orquestrador de Exportação Multi-Basemaps e Relatório Síntese
============================================================
Coordena a geração automatizada das três pranchas cartográficas solicitadas:
1. Falsa Cor (Realce Queimadas - SWIR/NIR/Red)
2. Cor Natural (RGB)
3. NBR (Normalized Burn Ratio - Severidade do Fogo)
Exportando em PNG alta resolução (300 DPI) e PDF vetorial para cada versão.
"""

import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Tuple, Optional, List, Union
import geopandas as gpd
import pandas as pd
import matplotlib.pyplot as plt

import ee
from src.config import (
    OUTPUTS_DIR, FILE_UCS_ESTADUAIS, VIS_CONFIGS, CRS_GEOGRAFICO,
    OCORRENCIA_MARGIN_PCT, OCORRENCIA_MIN_SPAN_DEG, OCORRENCIA_FALLBACK_UC_MARGIN
)
from src.gee_pipeline import (
    calculate_visible_extent,
    build_sentinel2_mosaics,
    fetch_rendered_basemap
)
from src.bdqueimadas import (
    fetch_bdqueimadas_inpe,
    load_focos_from_gee,
    load_focos_from_file,
    classify_focos_by_date,
    filter_focos_by_polygon
)
from src.layout_engine import render_mapa_prancha


def _strip_accents(text: str) -> str:
    """Normaliza texto removendo acentos e convertendo para minúsculas."""
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    ).lower().strip()


def list_all_ucs() -> List[str]:
    """Retorna a lista oficial de todas as Unidades de Conservação cadastradas no GeoJSON."""
    if not FILE_UCS_ESTADUAIS.exists():
        raise FileNotFoundError(f"Base de UCs não encontrada em: {FILE_UCS_ESTADUAIS}")
        
    gdf = gpd.read_file(FILE_UCS_ESTADUAIS)
    col_nome = next((c for c in gdf.columns if any(k in c.lower() for k in ["nome", "denominac", "uc"])), None)
    if not col_nome:
        raise ValueError("Coluna de denominação da UC não encontrada no GeoJSON.")
        
    return sorted(gdf[col_nome].dropna().unique().tolist())


def find_uc_by_name(nome_uc: str) -> gpd.GeoDataFrame:
    """
    Localiza uma Unidade de Conservação Estadual no cadastro oficial por busca flexível
    insensível a acentuação e termos como 'APA', 'PARQUE', etc.
    """
    if not FILE_UCS_ESTADUAIS.exists():
        raise FileNotFoundError(f"Base de UCs não encontrada em: {FILE_UCS_ESTADUAIS}")
        
    gdf = gpd.read_file(FILE_UCS_ESTADUAIS)
    if gdf.crs != CRS_GEOGRAFICO:
        gdf = gdf.to_crs(CRS_GEOGRAFICO)
        
    col_nome = next((c for c in gdf.columns if any(k in c.lower() for k in ["nome", "denominac", "uc"])), None)
    if not col_nome:
        raise ValueError("Coluna de denominação da UC não encontrada no GeoJSON.")
        
    # Busca 1: correspondência exata
    match = gdf[gdf[col_nome].str.lower() == nome_uc.strip().lower()]
    if not match.empty:
        return match.iloc[[0]]
        
    # Busca 2: correspondência sem acentos
    target_clean = _strip_accents(nome_uc)
    names_clean = gdf[col_nome].apply(_strip_accents)
    
    # 2.1. Tentar match direto da string limpa inteira
    mask = names_clean.str.contains(target_clean, regex=False)
    match = gdf[mask]
    if not match.empty:
        return match.iloc[[0]]
        
    # 2.2. Stopwords de categorias e conectivos
    stopwords = {
        "area", "protecao", "ambiental", "parque", "estadual", "reserva",
        "floresta", "refugio", "estacao", "ecologica", "biologica", "vida",
        "silvestre", "desenvolvimento", "sustentavel", "monumento", "natural",
        "apa", "flota", "revis", "rebio", "esec", "mona", "rds", "pema",
        "de", "do", "da", "dos", "das", "e", "em", "no", "na"
    }
    terms = [t for t in target_clean.replace("-", " ").replace("/", " ").split() if len(t) > 2 and t not in stopwords]
    
    # Tentar match pelos termos distintivos (ex: 'marajo', 'combu', 'maicuru', 'iriri', 'trombetas')
    if terms:
        for term in terms:
            mask_term = names_clean.str.contains(term, regex=False)
            if mask_term.any():
                return gdf[mask_term].iloc[[0]]
                
    # Se termo 'pema' for buscado diretamente
    if "pema" in target_clean:
        match_pema = gdf[names_clean.str.contains("monte alegre", regex=False)]
        if not match_pema.empty:
            return match_pema.iloc[[0]]
                
    # Se não encontrar, lança erro com todas as 29 UCs oficiais listadas
    ucs_oficiais = list_all_ucs()
    lista_fmt = "\n".join(f"  • {u}" for u in ucs_oficiais)
    raise ValueError(
        f"Unidade de Conservação '{nome_uc}' não localizada no cadastro oficial.\n"
        f"Total de {len(ucs_oficiais)} UCs disponíveis em ucs_estaduais.geojson:\n{lista_fmt}"
    )


def calculate_occurrence_extent(
    gdf_focos: gpd.GeoDataFrame,
    uc_bounds: Tuple[float, float, float, float],
    aspect_ratio: float = 1.25,
    margin_pct: float = OCORRENCIA_MARGIN_PCT,
    min_span_deg: float = OCORRENCIA_MIN_SPAN_DEG
) -> Tuple[float, float, float, float]:
    """
    Calcula o enquadramento do mapa principal com zoom na OCORRÊNCIA.

    Usa a bounding box dos focos do período (e não o limite integral da UC),
    com margem de contexto, janela mínima para focos muito agrupados e ajuste
    exato ao aspect ratio do quadro cartográfico (155 x 124 mm -> 1.25).
    Se não houver focos, preserva o enquadramento total da UC.
    """
    if gdf_focos is None or gdf_focos.empty:
        return calculate_visible_extent(
            uc_bounds[0], uc_bounds[1], uc_bounds[2], uc_bounds[3],
            aspect_ratio=aspect_ratio,
            margin_pct=OCORRENCIA_FALLBACK_UC_MARGIN
        )

    fxmin, fymin, fxmax, fymax = gdf_focos.total_bounds
    cx = (fxmin + fxmax) / 2.0
    cy = (fymin + fymax) / 2.0

    # Janela mínima: evita zoom extremo quando todos os focos estão no mesmo pixel
    span_x = max(fxmax - fxmin, min_span_deg)
    span_y = max(fymax - fymin, min_span_deg)

    xmin, xmax = cx - span_x / 2.0, cx + span_x / 2.0
    ymin, ymax = cy - span_y / 2.0, cy + span_y / 2.0

    # Margem de contexto ao redor das ocorrências
    w = xmax - xmin
    h = ymax - ymin
    xmin -= w * margin_pct
    xmax += w * margin_pct
    ymin -= h * margin_pct
    ymax += h * margin_pct

    # Ajuste fino ao aspect ratio do viewport, sem deformar a geografia
    w_curr = xmax - xmin
    h_curr = ymax - ymin
    curr_ratio = w_curr / h_curr if h_curr else aspect_ratio

    if curr_ratio < aspect_ratio:
        delta = (h_curr * aspect_ratio - w_curr) / 2.0
        xmin -= delta
        xmax += delta
    else:
        delta = (w_curr / aspect_ratio - h_curr) / 2.0
        ymin -= delta
        ymax += delta

    return (xmin, ymin, xmax, ymax)


def processar_e_exportar_todos_os_mapas(
    nome_uc: str,
    data_inicio: Optional[str] = None,
    data_fim: Optional[str] = None,
    dias_analise: int = 30,
    focos_source: Union[str, Path, ee.FeatureCollection] = "BDQUEIMADAS",
    data_referencia_foco: Optional[str] = None,
    metodo_severidade: str = "DNBR",
    buffer_uc_metros: float = 0.0,
    output_prefix: Optional[str] = None
) -> Dict[str, Any]:
    """
    Executa o pipeline completo de ponta a ponta e exporta as 3 variantes de mapa:
    - Falsa Cor
    - Cor Natural
    - Severidade do Fogo (opções: 'DNBR' bi-temporal, 'MAPBIOMAS' Coleção 11 ou 'NBR' clássico)
    
    Parameters
    ----------
    metodo_severidade : str
        'DNBR': Análise bi-temporal contínua (dNBR = NBR_pré - NBR_pós).
        'MAPBIOMAS' (recomendado): classificação categórica da cicatriz de queima
        (dNBR) por cobertura da terra (MapBiomas C11), contextualizando
        pastagem, savana e campo natural na classificação de fogo.
        'NBR': NBR unitemporal clássico.
    focos_source : Union[str, Path, ee.FeatureCollection]
        'BDQUEIMADAS' (padrão): Baixa automaticamente os focos oficiais do INPE/BDQueimadas.
        Ou caminho de arquivo local (.csv, .geojson, .shp) ou asset do GEE.
    """
    # Janela temporal automática: últimos 30 dias por padrão
    if data_fim is None:
        data_fim = date.today().strftime("%Y-%m-%d")
    if data_inicio is None:
        dt_f = datetime.strptime(data_fim, "%Y-%m-%d").date()
        data_inicio = (dt_f - timedelta(days=dias_analise)).strftime("%Y-%m-%d")

    print(f"\n=======================================================")
    print(f" Início do Processamento de Focos: {nome_uc}")
    print(f" Período: {data_inicio} até {data_fim}")
    print(f" Método de Severidade Espectral: {metodo_severidade.upper()}")
    print(f"=======================================================\n")
    
    # 1. Carregar Geometria da UC
    gdf_uc = find_uc_by_name(nome_uc)
    col_nome = next((c for c in gdf_uc.columns if any(k in c.lower() for k in ["nome", "denominac", "uc"])), None)
    uc_real_name = gdf_uc[col_nome].iloc[0]
    uc_poly = gdf_uc.geometry.iloc[0]
    
    print(f"[OK] UC selecionada: {uc_real_name}")
    
    # 2. Ingestão dos Focos de Queimada (necessária antes de definir o zoom)
    print("[*] Ingerindo focos de queimada...")
    is_bdqueimadas_auto = (
        focos_source is None
        or (isinstance(focos_source, str) and focos_source.upper() in ["BDQUEIMADAS", "INPE", "AUTO", "BD_QUEIMADAS"])
    )

    if is_bdqueimadas_auto:
        # Download 100% automático e inteligente do INPE BDQueimadas
        gdf_focos = fetch_bdqueimadas_inpe(data_inicio=data_inicio, data_fim=data_fim)
    elif isinstance(focos_source, str) and focos_source.startswith("projects/"):
        uc_geometry_ee = ee.Geometry(uc_poly.__geo_interface__)
        gdf_focos = load_focos_from_gee(focos_source, filter_geometry=uc_geometry_ee)
    elif isinstance(focos_source, (str, Path)) and Path(focos_source).exists():
        gdf_focos = load_focos_from_file(focos_source)
    else:
        # Fallback resiliente
        try:
            uc_geometry_ee = ee.Geometry(uc_poly.__geo_interface__)
            gdf_focos = load_focos_from_gee(str(focos_source), filter_geometry=uc_geometry_ee)
        except Exception:
            gdf_focos = fetch_bdqueimadas_inpe(data_inicio=data_inicio, data_fim=data_fim)

    # Filtro espacial no polígono da UC
    gdf_focos_uc = filter_focos_by_polygon(gdf_focos, uc_poly, buffer_meters=buffer_uc_metros)

    # 3. Zoom do Mapa Principal na OCORRÊNCIA (fallback: limite integral da UC)
    bounds = gdf_uc.total_bounds  # xmin, ymin, xmax, ymax
    vis_extent = calculate_occurrence_extent(gdf_focos_uc, bounds, aspect_ratio=1.25)
    if gdf_focos_uc.empty:
        print(f"[OK] Sem focos no período: enquadramento total da UC -> {vis_extent}")
    else:
        print(f"[OK] Zoom do mapa principal na ocorrência ({len(gdf_focos_uc)} focos) -> {vis_extent}")

    # 4. Construir Mosaicos Sentinel-2 e Severidade (dNBR / MapBiomas / NBR) no GEE
    print(f"[*] Processando mosaicos orbitais e índice de severidade ({metodo_severidade.upper()})...")
    s2_data = build_sentinel2_mosaics(
        vis_extent, data_inicio, data_fim, metodo_severidade=metodo_severidade
    )
    mosaico = s2_data["mosaico"]
    severidade_layer = s2_data["nbr"]
    tipo_sev_key = s2_data.get("tipo_severidade", "dnbr")

    # 5. Classificação Temporal dos Focos (recentes < 48h vs. pretéritos)
    dt_referencia = data_referencia_foco or data_fim
    gdf_anteriores, gdf_recentes, metricas = classify_focos_by_date(
        gdf_focos_uc, data_referencia=dt_referencia, limiar_dias_recente=2
    )

    print(f"[OK] Total de focos na UC: {metricas['total']}")
    if metricas.get("tem_foco_recente"):
        print(f"  • [MAPA QUENTE] Focos ativos recentes (< 48h - {metricas['data_ultima_observacao']}): {metricas['recentes']}")
        print(f"  • Focos pretéritos anteriores: {metricas['anteriores']}")
    else:
        dias_info = f" (último registro há {metricas['dias_desde_ultimo']} dias)" if metricas.get("dias_desde_ultimo") is not None else ""
        print(f"  • [MAPA FRIO] Sem focos ativos nas últimas 48h{dias_info}.")
        print(f"  • Focos acumulados no período: {metricas['anteriores']} (Último registro em {metricas['data_ultima_observacao']})")
    
    # 6. Gerar as 3 Variantes de Mapa (Falsa Cor, Cor Natural, Severidade dNBR/MapBiomas/NBR)
    safe_name = uc_real_name.replace(" ", "_").replace("/", "-")
    prefix = output_prefix or f"Mapa_Fogo_{safe_name}"
    periodo_label = f"{data_inicio} a {data_fim}"
    
    resultados_exportados = {}
    
    spec_sev = VIS_CONFIGS.get(tipo_sev_key, VIS_CONFIGS.get("dnbr", VIS_CONFIGS["nbr"]))
    basemap_variants = [
        ("falsa_cor", mosaico, VIS_CONFIGS["falsa_cor"]),
        ("cor_natural", mosaico, VIS_CONFIGS["cor_natural"]),
        (tipo_sev_key, severidade_layer, spec_sev)
    ]
    
    for tipo_key, ee_layer, vis_spec in basemap_variants:
        print(f"\n[*] Renderizando basemap: {vis_spec['nome']}...")
        try:
            # Baixar imagem renderizada (preservando corpos d'água no NBR/dNBR)
            is_sev = any(k in tipo_key.lower() for k in ["nbr", "dnbr", "severidade"])
            w_mask = s2_data.get("water_mask") if is_sev else None
            basemap_array = fetch_rendered_basemap(
                ee_layer, vis_extent, vis_spec, water_mask=w_mask
            )
        except Exception as e:
            print(f"! Erro ao obter basemap do GEE para {tipo_key}: {e}")
            basemap_array = None
            
        # Nomes dos arquivos de saída
        out_png = OUTPUTS_DIR / f"{prefix}_{tipo_key.upper()}.png"
        out_pdf = OUTPUTS_DIR / f"{prefix}_{tipo_key.upper()}.pdf"
        
        # Renderizar prancha cartográfica
        fig = render_mapa_prancha(
            nome_uc=uc_real_name,
            gdf_uc=gdf_uc,
            gdf_anteriores=gdf_anteriores,
            gdf_recentes=gdf_recentes,
            basemap_img=basemap_array,
            basemap_extent=vis_extent,
            tipo_basemap=vis_spec["nome"],
            periodo_str=periodo_label,
            metricas=metricas,
            legenda_severidade=s2_data.get("legenda_severidade"),
            legenda_titulo=s2_data.get("legenda_titulo"),
            output_path=out_png
        )
        
        # Exportar também versão vetorial em PDF
        fig.savefig(out_pdf, format="pdf", bbox_inches="tight", pad_inches=0.02)
        plt.close(fig)
        
        resultados_exportados[tipo_key] = {
            "png": str(out_png),
            "pdf": str(out_pdf),
            "titulo": vis_spec["nome"]
        }
        
    # 7. Gerar Planilha Excel Estruturada (.xlsx) e Pacote Geoespacial Google Earth (.kml)
    excel_path = None
    kml_path = None
    try:
        from src.excel_exporter import export_focos_to_excel
        excel_out = OUTPUTS_DIR / f"Tabela_Focos_{safe_name}.xlsx"
        export_focos_to_excel(
            gdf_focos=gdf_focos_uc,
            nome_uc=uc_real_name,
            periodo_str=periodo_label,
            output_path=excel_out,
            metricas=metricas
        )
        excel_path = str(excel_out)
    except Exception as e:
        print(f"[!] Aviso: Não foi possível gerar planilha Excel: {e}")

    try:
        from src.kml_generator import export_focos_to_kml
        kml_out = OUTPUTS_DIR / f"Focos_Queimada_{safe_name}.kml"
        export_focos_to_kml(
            gdf_focos=gdf_focos_uc,
            gdf_uc=gdf_uc,
            nome_uc=uc_real_name,
            output_path=kml_out,
            metricas=metricas
        )
        kml_path = str(kml_out)
    except Exception as e:
        print(f"[!] Aviso: Não foi possível gerar pacote KML: {e}")

    # 8. Gerar Relatório Técnico Oficial (.docx e .pdf) para Subsídio Imediato à Decisão
    relatorio_path = None
    relatorio_pdf_path = None
    try:
        from src.report_generator import build_technical_report_docx, convert_docx_to_pdf
        doc_out = OUTPUTS_DIR / f"Relatorio_Tecnico_Focos_{safe_name}.docx"
        build_technical_report_docx(
            nome_uc=uc_real_name,
            periodo_str=periodo_label,
            gdf_focos_uc=gdf_focos_uc,
            metricas=metricas,
            gdf_uc=gdf_uc,
            output_path=doc_out
        )
        relatorio_path = str(doc_out)

        # Conversão automática para PDF
        pdf_out = convert_docx_to_pdf(doc_out)
        if pdf_out:
            relatorio_pdf_path = str(pdf_out)
    except Exception as e:
        print(f"[!] Aviso: Não foi possível gerar relatório técnico: {e}")
        
    print(f"\n[OK] Sucesso! Pranchas, Relatório Técnico, Planilha Excel e KML salvos em: {OUTPUTS_DIR}")
    return {
        "uc": uc_real_name,
        "metricas": metricas,
        "pranchas": resultados_exportados,
        "relatorio_docx": relatorio_path,
        "relatorio_pdf": relatorio_pdf_path,
        "planilha_excel": excel_path,
        "pacote_kml": kml_path,
        "extent": vis_extent
    }
