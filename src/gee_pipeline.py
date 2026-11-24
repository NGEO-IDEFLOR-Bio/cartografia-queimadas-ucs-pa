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
    MAPBIOMAS_C11_ASSET, MAPBIOMAS_YEAR_DEFAULT,
    SEVERIDADE_CLASSES,
    LIMIAR_DNBR_FLORESTA, LIMIAR_DNBR_CAMPO,
    LIMIAR_DNBR_PASTAGEM, LIMIAR_DNBR_OUTROS
)


# Bandas ópticas essenciais do Sentinel-2 para as pranchas e índices (economiza >75% de memória/tempo no GEE)
OPTICAL_BANDS = ["B2", "B3", "B4", "B8", "B12"]


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
        try:
            import IPython
            if IPython.get_ipython() is not None:
                print("Tentando autenticação interativa no ambiente...")
                ee.Authenticate()
                ee.Initialize(project=target_project)
                print(f"[OK] GEE autenticado e inicializado com sucesso no projeto: {target_project}")
                return True
        except Exception as auth_err:
            print(f"[!] Erro ao autenticar GEE: {auth_err}")
        return False


def clean_mask(img: ee.Image) -> ee.Image:
    """
    Aplica máscara espectral de nuvens, sombras e brilho excessivo na coleção Sentinel-2
    estritamente sobre as bandas ópticas essenciais (B2, B3, B4, B8, B12), reduzindo a carga
    de processamento do GEE em mais de 75%:
    - SCL (Scene Classification): Mantém classes 4 (Vegetação), 5 (Solo) e 6 (Água)
    - QA60: Elimina nuvens opacas (bit 10) e cirrus (bit 11)
    - Banda B2: Filtra pixels com refletância >= 2000 (brilho saturado de nuvem residual)
    - Divide apenas as bandas ópticas por 10.000 (escala 0 a 1)
    """
    scl = img.select("SCL")
    qa = img.select("QA60")
    
    # 4 = vegetação, 5 = solo exposto, 6 = água
    mask_scl = scl.eq(4).Or(scl.eq(5)).Or(scl.eq(6))
    
    # QA60 bits 10 (opaca) e 11 (cirrus)
    mask_qa = qa.bitwiseAnd(1 << 10).eq(0).And(qa.bitwiseAnd(1 << 11).eq(0))
    
    # Filtro de brilho saturado residual em B2 (< 2000)
    mask_bright = img.select("B2").lt(2000)
    
    # Combinação booleana consolidada em uma única operação de máscara
    combined_mask = mask_scl.And(mask_qa).And(mask_bright)
    
    return (img.select(OPTICAL_BANDS)
               .divide(10000.0)
               .updateMask(combined_mask)
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


def classify_severity_by_landcover(dnbr: ee.Image, region: ee.Geometry) -> ee.Image:
    """
    Combina a cicatriz de queima (dNBR bi-temporal) com a cobertura da terra do
    MapBiomas Coleção 11, produzindo uma imagem categórica 1..8.

    A lógica separa explicitamente manejo/uso (pastagem, mosaico) e vegetação
    natural sazonal (campo, savana) de cicatriz de queima real:

    - 1..4: cicatriz de queima (severa, alta, moderada, leve). O limiar mínimo
      de dNBR varia por cobertura: floresta 0,10; pastagem 0,15; campo/savana
      0,18. Assim, a seca sazonal do Marajó não é pintada como fogo.
    - 5..8: cobertura da terra (floresta, campo/savana, pastagem/mosaico,
      outros usos), em tons frios/mudos.
    """
    asset_img = ee.Image(MAPBIOMAS_C11_ASSET)
    banda_solicitada = f"classification_{MAPBIOMAS_YEAR_DEFAULT}"
    banda_alvo = banda_solicitada

    # Verificação explícita: o GEE é lazy e um select() de banda inexistente só
    # falharia ao renderizar. Assim o fallback do pipeline realmente funciona.
    bandas = asset_img.bandNames().getInfo()
    if banda_alvo not in bandas:
        candidatas = sorted(b for b in bandas if b.startswith("classification_"))
        if not candidatas:
            raise ValueError(f"Asset MapBiomas sem bandas 'classification_*': {bandas}")
        banda_alvo = candidatas[-1]
        print(f"  ! Aviso: banda {banda_solicitada} indisponível; usando a mais recente ({banda_alvo}).")

    mb = asset_img.select(banda_alvo).clip(region)

    # 3 Formação Florestal, 5 Mangue, 6 Floresta Alagável, 7 Restinga Arborizada
    is_floresta = mb.eq(3).Or(mb.eq(5)).Or(mb.eq(6)).Or(mb.eq(7))
    # 4 Formação Savânica, 11 Campo Alagável, 12 Formação Campestre, 13 Outra Formação Não Florestal
    is_campo = mb.eq(4).Or(mb.eq(11)).Or(mb.eq(12)).Or(mb.eq(13))
    # 14 Agropecuária, 15 Pastagem, 18/19/20 Lavouras, 21 Mosaico de Usos
    is_pastagem = (
        mb.eq(14).Or(mb.eq(15)).Or(mb.eq(18))
        .Or(mb.eq(19)).Or(mb.eq(20)).Or(mb.eq(21))
    )

    # Classe base = outros usos / solo exposto (8)
    classes = ee.Image.constant(8).rename("SEVERIDADE_CLASSES")
    classes = classes.where(is_pastagem, 7)
    classes = classes.where(is_campo, 6)
    classes = classes.where(is_floresta, 5)

    # Limiar local de dNBR para considerar cicatriz de queima
    limiar = ee.Image.constant(LIMIAR_DNBR_OUTROS)
    limiar = limiar.where(is_pastagem, LIMIAR_DNBR_PASTAGEM)
    limiar = limiar.where(is_campo, LIMIAR_DNBR_CAMPO)
    limiar = limiar.where(is_floresta, LIMIAR_DNBR_FLORESTA)

    # Sobrepõe as classes de queima (ordem crescente de severidade)
    classes = classes.where(dnbr.gte(limiar), 4)
    classes = classes.where(dnbr.gte(0.27), 3)
    classes = classes.where(dnbr.gte(0.44), 2)
    classes = classes.where(dnbr.gte(0.66), 1)

    # Preserva o footprint válido do mosaico (sem pintar no-data como "outros usos")
    return classes.updateMask(dnbr.mask())


def build_sentinel2_mosaics(
    extent_bbox: Tuple[float, float, float, float],
    data_inicio: str,
    data_fim: str,
    metodo_severidade: str = "DNBR",
    dias_pre_fogo: int = 45
) -> Dict[str, Any]:
    """
    Cria os mosaicos Sentinel-2 medianos e a camada de severidade de queimada
    cobrindo a extensão visível total com suporte a três abordagens:

    1. 'DNBR' (padrão): análise bi-temporal contínua (dNBR = NBR_pré - NBR_pós).
    2. 'MAPBIOMAS': classificação categórica de cicatriz de queima (dNBR) por
       cobertura da terra (MapBiomas C11), separando campos/savana/pastagem de
       queimada real.
    3. 'NBR': NBR unitemporal calibrado clássico.

    Returns
    -------
    dict com:
        'mosaico': ee.Image mediana limpa do período analisado
        'nbr': ee.Image da camada de severidade calculada
        'severidade_layer': ee.Image da camada de severidade
        'tipo_severidade': chave da camada ('dnbr', 'nbr_mapbiomas' ou 'nbr')
        'legenda_severidade': lista [(cor, rótulo)] quando a camada é categórica
        'legenda_titulo': título da legenda categórica
        'water_mask': máscara refinada de água (NDWI/SCL)
        'extent': Tuple[float, float, float, float]
        'geometry': ee.Geometry.Rectangle
        'collection': ee.ImageCollection
    """
    xmin, ymin, xmax, ymax = extent_bbox
    region = ee.Geometry.Rectangle([xmin, ymin, xmax, ymax], proj="EPSG:4326", geodesic=False)
    
    # 1. Mosaico Pós-Fogo (Período Analisado)
    # Pré-filtra cenas com nuvens < 80% para evitar o carregamento inútil de cenas opacas
    s2_col = (ee.ImageCollection(GEE_S2_COLLECTION)
                .filterBounds(region)
                .filterDate(data_inicio, data_fim)
                .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 80))
                .map(clean_mask))
    
    mosaico = s2_col.median().clip(region)
    
    # Detecção refinada de corpos d'água (NDWI > 0) para evitar coloração espúria de queimada em rios e lagos
    ndwi = mosaico.normalizedDifference(["B3", "B8"]).rename("NDWI")
    is_water = ndwi.gt(0.0)
    
    metodo_clean = str(metodo_severidade).strip().upper()

    usa_dnbr = any(k in metodo_clean for k in ["DNBR", "BITEMPORAL", "BI-TEMPORAL", "MAPBIOMAS", "C11"])

    dnbr = None
    if usa_dnbr:
        # -------------------------------------------------------------
        # Mosaico Pré-Fogo (base do dNBR bi-temporal)
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
                    .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 80))
                    .map(clean_mask))
        mosaico_pre = s2_pre.median().clip(region)

        nbr_pre = mosaico_pre.normalizedDifference(["B8", "B12"]).rename("NBR_PRE")
        nbr_pos = mosaico.normalizedDifference(["B8", "B12"]).rename("NBR_POS")

        dnbr = nbr_pre.subtract(nbr_pos).rename("dNBR")

    if any(k in metodo_clean for k in ["DNBR", "BITEMPORAL", "BI-TEMPORAL"]):
        # -------------------------------------------------------------
        # ABORDAGEM 1: dNBR Bi-temporal contínuo (Pré-Fogo vs Pós-Fogo)
        # -------------------------------------------------------------
        layer_severidade = dnbr
        tipo_severidade = "dnbr"

    elif any(k in metodo_clean for k in ["MAPBIOMAS", "C11"]):
        # -------------------------------------------------------------
        # ABORDAGEM 2: Classificação de Cicatriz por Cobertura da Terra
        # (dNBR + MapBiomas C11), com classes categóricas e legenda própria
        # -------------------------------------------------------------
        print(f"  • [GEE] Classificando cicatriz de queima por cobertura da terra (MapBiomas C11 {MAPBIOMAS_YEAR_DEFAULT})...")

        try:
            layer_severidade = classify_severity_by_landcover(dnbr, region)
        except Exception as e:
            print(f"  ! Aviso: Falha ao carregar MapBiomas C11 ({e}). Aplicando classificação por limiar global de dNBR.")
            layer_severidade = ee.Image.constant(8).rename("SEVERIDADE_CLASSES")
            layer_severidade = layer_severidade.where(dnbr.gte(LIMIAR_DNBR_OUTROS), 4)
            layer_severidade = layer_severidade.where(dnbr.gte(0.27), 3)
            layer_severidade = layer_severidade.where(dnbr.gte(0.44), 2)
            layer_severidade = layer_severidade.where(dnbr.gte(0.66), 1)

        tipo_severidade = "nbr_mapbiomas"

    else:
        # NBR Clássico Unitemporal (sem análise pré-fogo)
        layer_severidade = mosaico.normalizedDifference(["B8", "B12"]).rename("NBR")
        tipo_severidade = "nbr"

    return {
        "mosaico": mosaico,
        "nbr": layer_severidade,
        "severidade_layer": layer_severidade,
        "tipo_severidade": tipo_severidade,
        "legenda_severidade": SEVERIDADE_CLASSES if tipo_severidade == "nbr_mapbiomas" else None,
        "legenda_titulo": "Severidade e Cobertura (MapBiomas C11)" if tipo_severidade == "nbr_mapbiomas" else None,
        "water_mask": is_water,
        "extent": (xmin, ymin, xmax, ymax),
        "geometry": region,
        "collection": s2_col,
    }


def get_adaptive_dimensions(extent_bbox: Tuple[float, float, float, float]) -> Tuple[int, int]:
    """
    Calcula dimensões adaptativas para renderização de basemaps no GEE,
    evitando estouro de tempo/memória em UCs gigantescas (como Paru, Marajó e Grão-Pará).
    """
    xmin, ymin, xmax, ymax = extent_bbox
    span_deg = max(xmax - xmin, ymax - ymin)
    if span_deg > 2.0:
        # Mega-UCs (> 100.000 km² / > 1.000.000 ha): 1024x819
        return (1024, 819)
    elif span_deg > 1.0:
        # UCs grandes: 1152x922
        return (1152, 922)
    else:
        # UCs médias e compactas: 1280x1024
        return (1280, 1024)


def fetch_rendered_basemap(
    image: ee.Image,
    extent_bbox: Tuple[float, float, float, float],
    vis_params: Dict[str, Any],
    dimensions: Optional[Tuple[int, int]] = None,
    water_mask: Optional[ee.Image] = None,
    timeout_seconds: int = 120
) -> np.ndarray:
    """
    Renderiza e baixa o basemap como array RGB NumPy com retry resiliente
    e escalonamento dinâmico de resolução em caso de sobrecarga do servidor GEE.
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
    
    target_dim = dimensions or get_adaptive_dimensions(extent_bbox)
    
    # Estratégia de tentativas com redução gradual de resolução se houver lentidão no GEE
    tentativas = [
        (target_dim, timeout_seconds),
        ((max(target_dim[0] * 3 // 4, 768), max(target_dim[1] * 3 // 4, 614)), max(timeout_seconds - 30, 90)),
        ((768, 614), 75)
    ]
    
    ultimo_erro = None
    for i, (dim, t_out) in enumerate(tentativas, start=1):
        try:
            url = vis_img.getThumbURL({
                "region": region,
                "dimensions": f"{dim[0]}x{dim[1]}",
                "format": "png"
            })
            
            response = requests.get(url, timeout=t_out)
            response.raise_for_status()
            
            pil_img = Image.open(io.BytesIO(response.content)).convert("RGB")
            return np.array(pil_img)
            
        except Exception as e:
            ultimo_erro = e
            if i < len(tentativas):
                prox_dim = tentativas[i][0]
                print(f"  ! Aviso: Tentativa {i} ao obter basemap do GEE falhou ({e}). Tentando novamente com resolução otimizada ({prox_dim[0]}x{prox_dim[1]})...")
            else:
                print(f"  ! Falha definitiva após {len(tentativas)} tentativas ao baixar basemap do GEE: {e}")
                raise ultimo_erro
