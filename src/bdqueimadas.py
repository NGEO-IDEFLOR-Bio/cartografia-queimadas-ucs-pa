"""
Módulo de Ingestão e Classificação de Focos de Queimada (BDQueimadas / INPE)
==========================================================================
Baixa e processa automaticamente focos de calor/incêndio diretamente do
dataserver oficial do INPE (BDQueimadas), com suporte a cache local,
filtro espacial por Unidade de Conservação e classificação temporal estrita
(dias anteriores vs. dia atual da análise ou última observação).
"""

from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, Any, Tuple, Optional, List, Union
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

import ee
from src.config import (
    RAW_DIR, CRS_GEOGRAFICO, CRS_WGS84,
    FOCOS_ANTERIORES_FILL, FOCOS_ANTERIORES_STROKE,
    FOCOS_RECENTES_FILL, FOCOS_RECENTES_STROKE
)

# URLs Oficiais do Dataserver BDQueimadas / INPE
INPE_DIARIO_URL = "https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/diario/Brasil/focos_diario_br_{date_str}.csv"
INPE_MENSAL_URL = "https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/mensal/Brasil/focos_mensal_br_{month_str}.csv"


def fetch_bdqueimadas_inpe(
    data_inicio: str,
    data_fim: str,
    estado_id: int = 15  # 15 = Pará (IBGE)
) -> gpd.GeoDataFrame:
    """
    Baixa automaticamente os focos de queimada do INPE/BDQueimadas para o Estado do Pará.
    Utiliza arquivos diários para datas recentes (últimos 30 dias) e arquivos mensais consolidados
    para períodos históricos, salvando em cache local na pasta data/raw/.
    
    Parameters
    ----------
    data_inicio : str
        Data inicial no formato 'AAAA-MM-DD'.
    data_fim : str
        Data final no formato 'AAAA-MM-DD'.
    estado_id : int
        Código IBGE do Estado (15 para Pará).
    """
    dt_start = datetime.strptime(data_inicio, "%Y-%m-%d").date()
    dt_end = datetime.strptime(data_fim, "%Y-%m-%d").date()
    
    if dt_start > dt_end:
        raise ValueError(f"Data inicial ({data_inicio}) não pode ser maior que a final ({data_fim}).")
        
    print(f"[*] Baixando dados oficiais BDQueimadas/INPE para o Pará ({data_inicio} até {data_fim})...")
    
    dfs_coletados = []
    
    # Avaliar se o período é recente (dentro dos últimos 30 dias)
    hoje = date.today()
    dias_atras = (hoje - dt_start).days
    
    # Caso seja período recente (<= 30 dias), buscar arquivos diários
    if dias_atras <= 30 and (dt_end - dt_start).days <= 31:
        curr = dt_start
        while curr <= dt_end:
            date_str = curr.strftime("%Y%m%d")
            cache_file = RAW_DIR / f"inpe_pa_{date_str}.csv.gz"
            
            if cache_file.exists():
                df_day = pd.read_csv(cache_file, compression="gzip")
            else:
                url = INPE_DIARIO_URL.format(date_str=date_str)
                try:
                    df_raw = pd.read_csv(url)
                    # Filtrar Estado do Pará
                    df_day = df_raw[(df_raw["estado_id"] == estado_id) | (df_raw["estado"].str.contains("Par", na=False))].copy()
                    df_day.to_csv(cache_file, compression="gzip", index=False)
                except Exception as e:
                    # Pode ocorrer para o próprio dia de hoje se o arquivo ainda estiver sendo gerado
                    df_day = pd.DataFrame()
                    
            if not df_day.empty:
                dfs_coletados.append(df_day)
            curr += timedelta(days=1)
            
    else:
        # Período histórico ou multi-mensal: buscar arquivos mensais consolidados
        # Gerar lista de meses únicos no intervalo
        meses_unicos = []
        curr = dt_start.replace(day=1)
        while curr <= dt_end:
            meses_unicos.append(curr.strftime("%Y%m"))
            # Avançar para próximo mês
            if curr.month == 12:
                curr = curr.replace(year=curr.year + 1, month=1)
            else:
                curr = curr.replace(month=curr.month + 1)
                
        for month_str in meses_unicos:
            cache_file = RAW_DIR / f"inpe_pa_{month_str}.csv.gz"
            
            if cache_file.exists():
                df_month = pd.read_csv(cache_file, compression="gzip")
            else:
                url = INPE_MENSAL_URL.format(month_str=month_str)
                try:
                    print(f"  • Obtendo mês {month_str} do INPE...")
                    cols = ["id", "lat", "lon", "data_hora_gmt", "satelite", "municipio", "estado", "estado_id", "bioma", "frp"]
                    df_raw = pd.read_csv(url, usecols=lambda c: c in cols)
                    df_month = df_raw[(df_raw["estado_id"] == estado_id) | (df_raw["estado"].str.contains("PAR", na=False))].copy()
                    df_month.to_csv(cache_file, compression="gzip", index=False)
                except Exception as e:
                    print(f"  ! Aviso: Mês {month_str} não encontrado no dataserver do INPE ({e}).")
                    df_month = pd.DataFrame()
                    
            if not df_month.empty:
                dfs_coletados.append(df_month)
                
    if not dfs_coletados:
        print("! Nenhum foco retornado para o período selecionado.")
        return gpd.GeoDataFrame(columns=["geometry", "data_hora_gmt", "satelite", "municipio"], crs=CRS_GEOGRAFICO)
        
    df_total = pd.concat(dfs_coletados, ignore_index=True)
    
    # Normalizar datas e filtrar estritamente entre data_inicio e data_fim
    df_total["dt_parsed"] = pd.to_datetime(df_total["data_hora_gmt"], errors="coerce")
    df_total["data_apenas"] = df_total["dt_parsed"].dt.date
    
    mask_intervalo = (df_total["data_apenas"] >= dt_start) & (df_total["data_apenas"] <= dt_end)
    df_filtrado = df_total[mask_intervalo].copy()
    
    if df_filtrado.empty:
        return gpd.GeoDataFrame(columns=["geometry", "data_hora_gmt", "satelite", "municipio"], crs=CRS_GEOGRAFICO)
        
    # Converter para GeoDataFrame
    geoms = [Point(xy) for xy in zip(df_filtrado["lon"], df_filtrado["lat"])]
    gdf = gpd.GeoDataFrame(df_filtrado, geometry=geoms, crs=CRS_GEOGRAFICO)
    
    print(f"[OK] Total de focos extraídos no Pará no período: {len(gdf)}")
    return gdf


def load_focos_from_gee(
    asset_path: str,
    filter_geometry: Optional[ee.Geometry] = None
) -> gpd.GeoDataFrame:
    """
    Carrega focos de incêndio a partir de um Asset FeatureCollection do Earth Engine (fallback).
    """
    fc = ee.FeatureCollection(asset_path)
    if filter_geometry:
        fc = fc.filterBounds(filter_geometry)
        
    info = fc.getInfo()
    features = info.get("features", [])
    
    if not features:
        return gpd.GeoDataFrame(
            columns=["geometry", "data_hora", "data", "satelite", "municipio"],
            crs=CRS_GEOGRAFICO
        )
        
    records = []
    geometries = []
    
    for f in features:
        props = f.get("properties", {})
        coords = f.get("geometry", {}).get("coordinates", [])
        if len(coords) >= 2:
            lon, lat = coords[0], coords[1]
            geometries.append(Point(lon, lat))
            records.append(props)
            
    gdf = gpd.GeoDataFrame(records, geometry=geometries, crs=CRS_WGS84)
    if gdf.crs != CRS_GEOGRAFICO:
        gdf = gdf.to_crs(CRS_GEOGRAFICO)
        
    return _standardize_focos_columns(gdf)


def load_focos_from_file(file_path: Union[str, Path]) -> gpd.GeoDataFrame:
    """
    Carrega focos a partir de arquivo local (.geojson, .shp, .gpkg, .csv).
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Arquivo de focos não encontrado: {path}")
        
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path)
        lat_col = next((c for c in df.columns if c.lower() in ["lat", "latitude"]), None)
        lon_col = next((c for c in df.columns if c.lower() in ["lon", "long", "longitude"]), None)
        if not lat_col or not lon_col:
            raise ValueError(f"Colunas de latitude/longitude não identificadas no CSV: {df.columns.tolist()}")
        geoms = [Point(xy) for xy in zip(df[lon_col], df[lat_col])]
        gdf = gpd.GeoDataFrame(df, geometry=geoms, crs=CRS_WGS84)
    else:
        gdf = gpd.read_file(path)
        
    if gdf.crs != CRS_GEOGRAFICO:
        gdf = gdf.to_crs(CRS_GEOGRAFICO)
        
    return _standardize_focos_columns(gdf)


def _standardize_focos_columns(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Normaliza campos de data, satélite e município independente da fonte."""
    if gdf.empty:
        return gdf
        
    dt_col = next((c for c in gdf.columns if any(k in c.lower() for k in ["datahora", "data_hora", "acq_date", "date"])), None)
    
    if dt_col:
        gdf["dt_parsed"] = pd.to_datetime(gdf[dt_col], errors="coerce")
        gdf["data_apenas"] = gdf["dt_parsed"].dt.date
    else:
        gdf["dt_parsed"] = pd.Timestamp.now()
        gdf["data_apenas"] = date.today()
        
    return gdf


def classify_focos_by_date(
    gdf: gpd.GeoDataFrame,
    data_referencia: Optional[Union[str, date]] = None
) -> Tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, Dict[str, Any]]:
    """
    Classifica os focos em duas categorias:
    1. Focos do dia atual da análise ou última observação detectada
    2. Focos dos dias anteriores
    """
    if gdf.empty:
        metricas = {
            "total": 0,
            "recentes": 0,
            "anteriores": 0,
            "data_ultima_observacao": "Sem focos",
            "satelites": []
        }
        return gdf.copy(), gdf.copy(), metricas
        
    if data_referencia is not None:
        if isinstance(data_referencia, str):
            ref_date = datetime.strptime(data_referencia, "%Y-%m-%d").date()
        else:
            ref_date = data_referencia
    else:
        ref_date = gdf["data_apenas"].dropna().max()
        
    mask_recente = gdf["data_apenas"] == ref_date
    gdf_recentes = gdf[mask_recente].copy()
    gdf_anteriores = gdf[~mask_recente].copy()
    
    gdf_recentes["cor_fill"] = FOCOS_RECENTES_FILL
    gdf_recentes["cor_stroke"] = FOCOS_RECENTES_STROKE
    gdf_recentes["categoria"] = "Última Observação"
    
    gdf_anteriores["cor_fill"] = FOCOS_ANTERIORES_FILL
    gdf_anteriores["cor_stroke"] = FOCOS_ANTERIORES_STROKE
    gdf_anteriores["categoria"] = "Dias Anteriores"
    
    sat_col = next((c for c in gdf.columns if "sat" in c.lower()), None)
    satelites = gdf[sat_col].dropna().unique().tolist() if sat_col else ["Diversos (INPE/BDQueimadas)"]
    
    metricas = {
        "total": len(gdf),
        "recentes": len(gdf_recentes),
        "anteriores": len(gdf_anteriores),
        "data_ultima_observacao": ref_date.strftime("%d/%m/%Y") if ref_date else "N/D",
        "satelites": satelites
    }
    
    return gdf_anteriores, gdf_recentes, metricas


def filter_focos_by_polygon(
    gdf_focos: gpd.GeoDataFrame,
    polygon_geom,
    buffer_meters: float = 0.0
) -> gpd.GeoDataFrame:
    """Filtra os focos que interceptam o polígono da Unidade de Conservação."""
    if gdf_focos.empty:
        return gdf_focos
        
    if buffer_meters > 0:
        poly_series = gpd.GeoSeries([polygon_geom], crs=CRS_GEOGRAFICO).to_crs(CRS_WGS84)
        buffered = poly_series.buffer(buffer_meters / 111320.0).iloc[0]
        return gdf_focos[gdf_focos.intersects(buffered)].copy()
        
    return gdf_focos[gdf_focos.intersects(polygon_geom)].copy()
