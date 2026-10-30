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
from pathlib import Path
from typing import Dict, Any, Tuple, Optional, List, Union
import geopandas as gpd
import pandas as pd
import matplotlib.pyplot as plt

import ee
from src.config import (
    OUTPUTS_DIR, FILE_UCS_ESTADUAIS, VIS_CONFIGS, CRS_GEOGRAFICO
)
from src.gee_pipeline import (
    calculate_visible_extent,
    build_sentinel2_mosaics,
    fetch_rendered_basemap
)
from src.bdqueimadas import (
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


def processar_e_exportar_todos_os_mapas(
    nome_uc: str,
    data_inicio: str = "2025-08-01",
    data_fim: str = "2025-12-31",
    focos_source: Union[str, Path, ee.FeatureCollection] = "projects/ee-samuelsantosambientalcourse/assets/bdqueimadas_2025-08-01_2025-12-31",
    data_referencia_foco: Optional[str] = None,
    buffer_uc_metros: float = 0.0,
    output_prefix: Optional[str] = None
) -> Dict[str, Any]:
    """
    Executa o pipeline completo de ponta a ponta e exporta as 3 variantes de mapa:
    - Falsa Cor
    - Cor Natural
    - NBR
    
    Returns
    -------
    dict com caminhos dos arquivos exportados, métricas dos focos e referências cartográficas.
    """
    print(f"\n=======================================================")
    print(f" Início do Processamento de Focos: {nome_uc}")
    print(f" Período: {data_inicio} até {data_fim}")
    print(f"=======================================================\n")
    
    # 1. Carregar Geometria da UC
    gdf_uc = find_uc_by_name(nome_uc)
    col_nome = next((c for c in gdf_uc.columns if any(k in c.lower() for k in ["nome", "denominac", "uc"])), None)
    uc_real_name = gdf_uc[col_nome].iloc[0]
    uc_poly = gdf_uc.geometry.iloc[0]
    
    print(f"✓ UC selecionada: {uc_real_name}")
    
    # 2. Calcular Extensão Visível do Mapa Principal (Proporção 155 x 124 mm -> 1.25)
    bounds = gdf_uc.total_bounds  # xmin, ymin, xmax, ymax
    vis_extent = calculate_visible_extent(
        bounds[0], bounds[1], bounds[2], bounds[3],
        aspect_ratio=1.25,
        margin_pct=0.06
    )
    print(f"✓ Extensão do viewport calculada: {vis_extent}")
    
    # 3. Construir Mosaicos Sentinel-2 e NBR no GEE
    print("⏳ Processando mosaicos Sentinel-2 Harmonized (mediana com máscara de nuvens/brilho)...")
    s2_data = build_sentinel2_mosaics(vis_extent, data_inicio, data_fim)
    mosaico = s2_data["mosaico"]
    nbr = s2_data["nbr"]
    
    # 4. Ingestão e Classificação dos Focos de Queimada
    print("⏳ Ingerindo e classificando focos de queimada...")
    if isinstance(focos_source, str) and focos_source.startswith("projects/"):
        gdf_focos = load_focos_from_gee(focos_source, filter_geometry=s2_data["geometry"])
    elif isinstance(focos_source, (str, Path)) and Path(focos_source).exists():
        gdf_focos = load_focos_from_file(focos_source)
    else:
        # Tenta carregar do GEE caso seja string
        try:
            gdf_focos = load_focos_from_gee(str(focos_source), filter_geometry=s2_data["geometry"])
        except Exception:
            gdf_focos = gpd.GeoDataFrame(columns=["geometry", "data_apenas"], crs=CRS_GEOGRAFICO)
            
    # Filtro espacial no polígono da UC
    gdf_focos_uc = filter_focos_by_polygon(gdf_focos, uc_poly, buffer_meters=buffer_uc_metros)
    gdf_anteriores, gdf_recentes, metricas = classify_focos_by_date(gdf_focos_uc, data_referencia=data_referencia_foco)
    
    print(f"✓ Total de focos na UC: {metricas['total']}")
    print(f"  • Dia atual / Última obs. ({metricas['data_ultima_observacao']}): {metricas['recentes']}")
    print(f"  • Dias anteriores: {metricas['anteriores']}")
    
    # 5. Gerar as 3 Variantes de Mapa (Falsa Cor, Cor Natural, NBR)
    safe_name = uc_real_name.replace(" ", "_").replace("/", "-")
    prefix = output_prefix or f"Mapa_Fogo_{safe_name}"
    periodo_label = f"{data_inicio} a {data_fim}"
    
    resultados_exportados = {}
    
    basemap_variants = [
        ("falsa_cor", mosaico, VIS_CONFIGS["falsa_cor"]),
        ("cor_natural", mosaico, VIS_CONFIGS["cor_natural"]),
        ("nbr", nbr, VIS_CONFIGS["nbr"])
    ]
    
    for tipo_key, ee_layer, vis_spec in basemap_variants:
        print(f"\n⏳ Renderizando basemap: {vis_spec['nome']}...")
        try:
            # Baixar imagem renderizada
            basemap_array = fetch_rendered_basemap(
                ee_layer, vis_extent, vis_spec, dimensions=(1280, 1024)
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
        
    print(f"\n✓ Sucesso! Todas as 3 pranchas foram geradas e salvas em: {OUTPUTS_DIR}")
    return {
        "uc": uc_real_name,
        "metricas": metricas,
        "pranchas": resultados_exportados,
        "extent": vis_extent
    }
