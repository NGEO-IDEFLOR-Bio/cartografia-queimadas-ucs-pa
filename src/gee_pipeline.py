"""
Pipeline de Processamento Sentinel-2 e Google Earth Engine (GEE)
===============================================================
Implementa a ingestão da coleção Sentinel-2 Harmonized, aplicação de máscaras
espectrais rigorosas (SCL, QA60 e saturação de brilho B2), cálculo de NBR,
composição mediana e cálculo dinâmico da extensão para preenchimento de 100%
da área visível do mapa.
"""

from datetime import datetime, timedelta
import math
import io
import requests
from typing import Dict, Any, Tuple, Optional
import numpy as np
from PIL import Image

import ee
from src.config import (
    GEE_S2_COLLECTION, DEFAULT_GEE_PROJECT, VIS_CONFIGS,
    MAPBIOMAS_C11_ASSET, MAPBIOMAS_YEAR_DEFAULT
)


def init_gee(project_id: Optional[str] = DEFAULT_GEE_PROJECT) -> bool:
    """
    Inicializa o Google Earth Engine de forma resiliente no ambiente local ou Google Colab.
    
    Parameters
    ----------
    project_id : str, optional
        ID do projeto no Google Cloud Platform associado ao Earth Engine.
        Padrão: 'ee-samuelsantosambientalcourse' (altere para o seu projeto institucional).
    """
    target_project = project_id or DEFAULT_GEE_PROJECT
    try:
        ee.Initialize(project=target_project)
        print(f"[OK] Google Earth Engine inicializado com sucesso no projeto: {target_project}")
        return True
    except Exception as e:
        print(f"! Falha na inicialização direta do GEE ({e}).")
        print("Tentando autenticação interativa no ambiente...")
        try:
            ee.Authenticate()
            ee.Initialize(project=target_project)
            print(f"[OK] GEE autenticado e inicializado com sucesso no projeto: {target_project}")
            return True
        except Exception as auth_err:
            print(f"[!] Erro definitivo ao autenticar GEE: {auth_err}")
            return False


def clean_mask(img: ee.Image) -> ee.Image:
    """
    Aplica máscara espectral de nuvens, sombras e brilho excessivo na coleção Sentinel-2:
    - SCL (Scene Classification): Mantém classes 4 (Vegetação), 5 (Solo) e 6 (Água)
    - QA60: Elimina nuvens opacas (bit 10) e cirrus (bit 11)
    - Banda B2: Filtra pixels com refletância >= 2000 (brilho saturado de nuvem residual)
    - Divide por 10.000 para escala de refletância de superfície (0 a 1)
    """
    scl = img.select("SCL")
    qa = img.select("QA60")
    
    # 4 = vegetation, 5 = bare soils / unclassified, 6 = water
    mask_scl = scl.eq(4).Or(scl.eq(5)).Or(scl.eq(6))
    
    # QA60 bits 10 and 11
    mask_qa = qa.bitwiseAnd(1 << 10).eq(0).And(qa.bitwiseAnd(1 << 11).eq(0))
    
    # B2 brightness filter (< 2000)
    mask_bright = img.select("B2").lt(2000)
    
    return (img.updateMask(mask_scl)
               .updateMask(mask_qa)
               .updateMask(mask_bright)
               .divide(10000.0)
               .copyProperties(img, ["system:time_start"]))


def calculate_visible_extent(
    xmin: float, ymin: float, xmax: float, ymax: float,
    aspect_ratio: float = 1.25,
    margin_pct: float = 0.05
) -> Tuple[float, float, float, float]:
    """
    Ajusta dinamicamente a extensão geográfica da área de interesse para coincidir
    com a proporção exata da moldura do mapa principal (155mm x 124mm -> 1.25).
    Adiciona margem de segurança para garantir 100% de cobertura orbital no enquadramento.
    """
    w = xmax - xmin
    h = ymax - ymin
    
    # Adicionar margem de segurança
    xmin -= w * margin_pct
    xmax += w * margin_pct
    ymin -= h * margin_pct
    ymax += h * margin_pct
    
    w_curr = xmax - xmin
    h_curr = ymax - ymin
    
    # Ajuste de proporção para aspect_ratio = w / h
    curr_ratio = w_curr / h_curr if h_curr != 0 else aspect_ratio
    
    if curr_ratio < aspect_ratio:
        # Muito alto: expandir largura horizontalmente
        needed_w = h_curr * aspect_ratio
        delta = (needed_w - w_curr) / 2.0
        xmin -= delta
        xmax += delta
    else:
        # Muito largo: expandir altura verticalmente
        needed_h = w_curr / aspect_ratio
        delta = (needed_h - h_curr) / 2.0
        ymin -= delta
        ymax += delta
        
    return (xmin, ymin, xmax, ymax)


def build_sentinel2_mosaics(
    extent_bbox: Tuple[float, float, float, float],
    data_inicio: str,
    data_fim: str,
    metodo_severidade: str = "DNBR",
    dias_pre_fogo: int = 45
) -> Dict[str, Any]:
    """
    Cria os mosaicos Sentinel-2 medianos e a camada de severidade de queimada
    cobringo a extensão visível total com suporte a duas abordagens robustas:
    1. 'DNBR' (Padrão): Análise Bi-temporal (dNBR = NBR_pré - NBR_pós), imune a falsos positivos em campos/savana.
    2. 'MAPBIOMAS': Mascaramento fenológico baseado na Coleção 11 do MapBiomas (classes 11, 12, 15, 21).
    3. 'NBR': NBR unitemporal calibrado clássico.
    
    Returns
    -------
    dict com:
        'mosaico': ee.Image mediana limpa do período analisado
        'nbr': ee.Image da camada de severidade calculada
        'severidade_layer': ee.Image da camada de severidade
        'tipo_severidade': chave da camada ('dnbr', 'nbr_mapbiomas' ou 'nbr')
        'water_mask': máscara refinada de água (NDWI/SCL)
        'extent': Tuple[float, float, float, float]
        'geometry': ee.Geometry.Rectangle
        'collection': ee.ImageCollection
    """
    xmin, ymin, xmax, ymax = extent_bbox
    region = ee.Geometry.Rectangle([xmin, ymin, xmax, ymax], proj="EPSG:4326", geodesic=False)
    
    # 1. Mosaico Pós-Fogo (Período Analisado)
    s2_col = (ee.ImageCollection(GEE_S2_COLLECTION)
                .filterBounds(region)
                .filterDate(data_inicio, data_fim)
                .map(clean_mask))
    
    mosaico = s2_col.median().clip(region)
    
    # Detecção refinada de corpos d'água (NDWI > 0 ou SCL == 6) para evitar coloração espúria de queimada na água
    ndwi = mosaico.normalizedDifference(["B3", "B8"]).rename("NDWI")
    is_water = ndwi.gt(0.0).Or(mosaico.select("SCL").round().eq(6))
    
    metodo_clean = str(metodo_severidade).strip().upper()
    
    if any(k in metodo_clean for k in ["DNBR", "BITEMPORAL", "BI-TEMPORAL"]):
        # -------------------------------------------------------------
        # ABORDAGEM 1: dNBR Bi-temporal (Pré-Fogo vs Pós-Fogo)
        # -------------------------------------------------------------
        dt_start = datetime.strptime(data_inicio, "%Y-%m-%d").date()
        dt_end = datetime.strptime(data_fim, "%Y-%m-%d").date()
        intervalo_dias = max((dt_end - dt_start).days, dias_pre_fogo)
        
        dt_pre_end = dt_start
        dt_pre_start = dt_start - timedelta(days=intervalo_dias)
        
        date_pre_end_str = dt_pre_end.strftime("%Y-%m-%d")
        date_pre_start_str = dt_pre_start.strftime("%Y-%m-%d")
        
        print(f"  • [GEE] Calculando dNBR Bi-temporal: Pré ({date_pre_start_str} a {date_pre_end_str}) vs Pós ({data_inicio} a {data_fim})...")
        
        s2_pre = (ee.ImageCollection(GEE_S2_COLLECTION)
                    .filterBounds(region)
                    .filterDate(date_pre_start_str, date_pre_end_str)
                    .map(clean_mask))
        mosaico_pre = s2_pre.median().clip(region)
        
        nbr_pre = mosaico_pre.normalizedDifference(["B8", "B12"]).rename("NBR_PRE")
        nbr_pos = mosaico.normalizedDifference(["B8", "B12"]).rename("NBR_POS")
        
        layer_severidade = nbr_pre.subtract(nbr_pos).rename("dNBR")
        tipo_severidade = "dnbr"
        
    elif any(k in metodo_clean for k in ["MAPBIOMAS", "C11"]):
        # -------------------------------------------------------------
        # ABORDAGEM 2: NBR com Mascaramento Fenológico MapBiomas Coleção 11
        # -------------------------------------------------------------
        print(f"  • [GEE] Aplicando mascaramento fenológico com MapBiomas Coleção 11 ({MAPBIOMAS_YEAR_DEFAULT})...")
        nbr_raw = mosaico.normalizedDifference(["B8", "B12"]).rename("NBR")
        
        try:
            mb_img = ee.Image(MAPBIOMAS_C11_ASSET).select(f"classification_{MAPBIOMAS_YEAR_DEFAULT}").clip(region)
            # Classes não florestais do MapBiomas que sofrem senescência estacional no Pará:
            # 11 = Campo Alagável e Área Pantanosa (Marajó)
            # 12 = Formação Campestre (Savanas/Cerrado)
            # 15 = Pastagem
            # 21 = Mosaico de Usos
            is_campo = mb_img.eq(11).Or(mb_img.eq(12)).Or(mb_img.eq(15)).Or(mb_img.eq(21))
            
            # Mascaramento inteligente: em campo natural/savana, se o NBR estiver na faixa
            # de senescência natural (>= -0.22), normaliza para patamar neutro (0.05).
            # Apenas se NBR < -0.22 (cinza e carvão profundo de queima real) aparece como fogo!
            layer_severidade = nbr_raw.where(is_campo.And(nbr_raw.gte(-0.22)), ee.Image.constant(0.05)).rename("NBR_MAPBIOMAS")
        except Exception as e:
            print(f"  ! Aviso: Falha ao carregar MapBiomas C11 ({e}). Usando NBR calibrado.")
            layer_severidade = nbr_raw
            
        tipo_severidade = "nbr_mapbiomas"
        
    else:
        # NBR Clássico Unitemporal
        layer_severidade = mosaico.normalizedDifference(["B8", "B12"]).rename("NBR")
        tipo_severidade = "nbr"
    
    return {
        "mosaico": mosaico,
        "nbr": layer_severidade,
        "severidade_layer": layer_severidade,
        "tipo_severidade": tipo_severidade,
        "water_mask": is_water,
        "extent": (xmin, ymin, xmax, ymax),
        "geometry": region,
        "collection": s2_col,
    }


def fetch_rendered_basemap(
    image: ee.Image,
    extent_bbox: Tuple[float, float, float, float],
    vis_params: Dict[str, Any],
    dimensions: Tuple[int, int] = (1280, 1024),
    water_mask: Optional[ee.Image] = None
) -> np.ndarray:
    """
    Renderiza e baixa o basemap como array RGB NumPy pronto para plotagem no Matplotlib.
    Se fornecida máscara de água, preserva rios e lagos com tonalidade azul hídrica.
    """
    xmin, ymin, xmax, ymax = extent_bbox
    region = ee.Geometry.Rectangle([xmin, ymin, xmax, ymax], proj="EPSG:4326", geodesic=False)
    
    # Filtrar apenas parâmetros aceitos por ee.Image.visualize()
    valid_vis_keys = {"bands", "gain", "bias", "min", "max", "gamma", "palette", "opacity", "forceRgbOutput"}
    clean_vis = {k: v for k, v in vis_params.items() if k in valid_vis_keys}
    
    vis_img = image.visualize(**clean_vis)
    
    if water_mask is not None:
        # Azul hídrico institucional (#1F618D -> [31, 97, 141])
        water_rgb = ee.Image.constant([31, 97, 141]).toByte()
        vis_img = vis_img.where(water_mask.eq(1), water_rgb)
    
    url = vis_img.getThumbURL({
        "region": region,
        "dimensions": f"{dimensions[0]}x{dimensions[1]}",
        "format": "png"
    })
    
    response = requests.get(url, timeout=45)
    response.raise_for_status()
    
    pil_img = Image.open(io.BytesIO(response.content)).convert("RGB")
    return np.array(pil_img)
