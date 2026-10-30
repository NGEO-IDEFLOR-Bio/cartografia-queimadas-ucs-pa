"""
Módulo de Ingestão e Classificação de Focos de Queimada (BDQueimadas / INPE)
==========================================================================
Manipula conjuntos de dados de focos de incêndio a partir de FeatureCollections do GEE,
arquivos locais (GeoJSON/Shapefile/CSV) ou fontes públicas do INPE, aplicando
filtro espacial por Unidade de Conservação e classificação temporal estrita
(dias anteriores vs. dia atual da análise ou última observação).
"""

from datetime import datetime, date
from pathlib import Path
from typing import Dict, Any, Tuple, Optional, Union
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

import ee
from src.config import (
    CRS_GEOGRAFICO, CRS_WGS84,
    FOCOS_ANTERIORES_FILL, FOCOS_ANTERIORES_STROKE,
    FOCOS_RECENTES_FILL, FOCOS_RECENTES_STROKE
)


def load_focos_from_gee(
    asset_path: str,
    filter_geometry: Optional[ee.Geometry] = None
) -> gpd.GeoDataFrame:
    """
    Carrega focos de incêndio a partir de um Asset FeatureCollection do Earth Engine
    e converte para um GeoDataFrame em EPSG:4674.
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
    """
    Normaliza os campos de data, satélite e município independente da fonte (BDQueimadas/INPE ou FIRMS).
    """
    if gdf.empty:
        return gdf
        
    # Identificar coluna de data/hora
    dt_col = next((c for c in gdf.columns if any(k in c.lower() for k in ["datahora", "data_hora", "acq_date", "date"])), None)
    
    if dt_col:
        gdf["dt_parsed"] = pd.to_datetime(gdf[dt_col], errors="coerce")
        gdf["data_apenas"] = gdf["dt_parsed"].dt.date
    else:
        # Fallback para hoje
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
    
    Returns
    -------
    Tuple:
        gdf_anteriores (GeoDataFrame)
        gdf_recentes (GeoDataFrame)
        metricas (dict com contagens e metadados)
    """
    if gdf.empty:
        metricas = {
            "total": 0,
            "recentes": 0,
            "anteriores": 0,
            "data_ultima_observacao": None,
            "satelites": []
        }
        return gdf.copy(), gdf.copy(), metricas
        
    # Determinar a data de referência
    if data_referencia is not None:
        if isinstance(data_referencia, str):
            ref_date = datetime.strptime(data_referencia, "%Y-%m-%d").date()
        else:
            ref_date = data_referencia
    else:
        # Usar a maior data registrada no próprio conjunto (última observação)
        ref_date = gdf["data_apenas"].dropna().max()
        
    mask_recente = gdf["data_apenas"] == ref_date
    gdf_recentes = gdf[mask_recente].copy()
    gdf_anteriores = gdf[~mask_recente].copy()
    
    # Adicionar metadados de estilo para renderização
    gdf_recentes["cor_fill"] = FOCOS_RECENTES_FILL
    gdf_recentes["cor_stroke"] = FOCOS_RECENTES_STROKE
    gdf_recentes["categoria"] = "Última Observação"
    
    gdf_anteriores["cor_fill"] = FOCOS_ANTERIORES_FILL
    gdf_anteriores["cor_stroke"] = FOCOS_ANTERIORES_STROKE
    gdf_anteriores["categoria"] = "Dias Anteriores"
    
    # Extrair estatísticas
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
    """
    Filtra os focos que interceptam o polígono da Unidade de Conservação (com buffer opcional).
    """
    if gdf_focos.empty:
        return gdf_focos
        
    if buffer_meters > 0:
        # Reprojetar para CRS métrico para cálculo exato do buffer
        poly_series = gpd.GeoSeries([polygon_geom], crs=CRS_GEOGRAFICO).to_crs(CRS_WGS84)
        buffered = poly_series.buffer(buffer_meters / 111320.0).iloc[0]
        return gdf_focos[gdf_focos.intersects(buffered)].copy()
        
    return gdf_focos[gdf_focos.intersects(polygon_geom)].copy()
