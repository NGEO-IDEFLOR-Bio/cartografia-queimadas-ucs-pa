"""
Pipeline de Processamento Sentinel-2 e Google Earth Engine (GEE)
===============================================================
Implementa a ingestão da coleção Sentinel-2 Harmonized, aplicação de máscaras
espectrais rigorosas (SCL, QA60 e saturação de brilho B2), cálculo de NBR,
composição mediana e cálculo dinâmico da extensão para preenchimento de 100%
da área visível do mapa.
"""

import math
import io
import requests
from typing import Dict, Any, Tuple, Optional
import numpy as np
from PIL import Image

import ee
from src.config import GEE_S2_COLLECTION, DEFAULT_GEE_PROJECT, VIS_CONFIGS


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
        print(f"✓ Google Earth Engine inicializado com sucesso no projeto: {target_project}")
        return True
    except Exception as e:
        print(f"! Falha na inicialização direta do GEE ({e}).")
        print("Tentando autenticação interativa no ambiente...")
        try:
            ee.Authenticate()
            ee.Initialize(project=target_project)
            print(f"✓ GEE autenticado e inicializado com sucesso no projeto: {target_project}")
            return True
        except Exception as auth_err:
            print(f"✗ Erro definitivo ao autenticar GEE: {auth_err}")
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
    data_fim: str
) -> Dict[str, Any]:
    """
    Cria os mosaicos Sentinel-2 medianos e o NBR cobrindo a extensão visível total.
    
    Returns
    -------
    dict com:
        'mosaico': ee.Image mediana limpa
        'nbr': ee.Image NBR calculado
        'extent': Tuple[float, float, float, float]
        'geometry': ee.Geometry.Rectangle
        'count': ee.Number com contagem de imagens
    """
    xmin, ymin, xmax, ymax = extent_bbox
    region = ee.Geometry.Rectangle([xmin, ymin, xmax, ymax], proj="EPSG:4326", geodesic=False)
    
    s2_col = (ee.ImageCollection(GEE_S2_COLLECTION)
                .filterBounds(region)
                .filterDate(data_inicio, data_fim)
                .map(clean_mask))
    
    mosaico = s2_col.median().clip(region)
    
    # Cálculo do Normalized Burn Ratio: (B8 - B12) / (B8 + B12)
    nbr = mosaico.normalizedDifference(["B8", "B12"]).rename("NBR")
    
    return {
        "mosaico": mosaico,
        "nbr": nbr,
        "extent": (xmin, ymin, xmax, ymax),
        "geometry": region,
        "collection": s2_col,
    }


def fetch_rendered_basemap(
    image: ee.Image,
    extent_bbox: Tuple[float, float, float, float],
    vis_params: Dict[str, Any],
    dimensions: Tuple[int, int] = (1280, 1024)
) -> np.ndarray:
    """
    Renderiza e baixa o basemap como array RGB NumPy pronto para plotagem no Matplotlib.
    """
    xmin, ymin, xmax, ymax = extent_bbox
    region = ee.Geometry.Rectangle([xmin, ymin, xmax, ymax], proj="EPSG:4326", geodesic=False)
    
    vis_img = image.visualize(**vis_params)
    
    url = vis_img.getThumbURL({
        "region": region,
        "dimensions": f"{dimensions[0]}x{dimensions[1]}",
        "format": "png"
    })
    
    response = requests.get(url, timeout=45)
    response.raise_for_status()
    
    pil_img = Image.open(io.BytesIO(response.content)).convert("RGB")
    return np.array(pil_img)
