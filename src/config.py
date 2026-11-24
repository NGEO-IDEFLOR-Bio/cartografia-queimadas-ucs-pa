"""
Módulo de Configuração Cartográfica e Parâmetros Operacionais
===========================================================
Define caminhos, CRS oficiais, dimensões milimétricas do layout A4 Paisagem
e convenções de cores da simbologia dos focos e dos basemaps orbitais.
"""

from pathlib import Path
from typing import Tuple

# Diretórios do Projeto
SRC_DIR = Path(__file__).resolve().parent
ROOT_DIR = SRC_DIR.parent
DATA_DIR = ROOT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
ASSETS_DIR = ROOT_DIR / "assets"
IMG_DIR = ASSETS_DIR / "img"
OUTPUTS_DIR = ROOT_DIR / "outputs"

# Garantir existência dos diretórios operacionais
for _dir in [DATA_DIR, RAW_DIR, PROCESSED_DIR, ASSETS_DIR, IMG_DIR, OUTPUTS_DIR]:
    _dir.mkdir(parents=True, exist_ok=True)

# Arquivos Geoespaciais Padrão
FILE_UCS_ESTADUAIS = PROCESSED_DIR / "ucs_estaduais.geojson"
FILE_ESTADO_PA = PROCESSED_DIR / "estado.geojson"
FILE_MUNICIPIOS = PROCESSED_DIR / "municipios.geojson"
FILE_BRASIL_UFS = PROCESSED_DIR / "brasil_ufs_simplificado.geojson"
FILE_AMERICA_SUL = PROCESSED_DIR / "america_do_sul_simplificado.geojson"

# Logotipos e Templates Institucionais
FILE_BRASAO_PARA = IMG_DIR / "brasao-para.png"
FILE_LOGO_IDEFLOR = IMG_DIR / "logo-ideflor-bio.png"
FILE_LOGO_NGEO = IMG_DIR / "logo-ngeo.png"
FILE_TEMPLATE_RELATORIO = ASSETS_DIR / "templates" / "relatorio.docx"

# Sistemas de Referência Espacial (CRS)
CRS_GEOGRAFICO = "EPSG:4674"      # SIRGAS 2000 Geográfico
CRS_WGS84 = "EPSG:4326"           # WGS 84
CRS_METRICO_PA = "EPSG:5880"      # SIRGAS 2000 / Brasil Policonica

# Convenção de Cores da Simbologia dos Focos de Queimada (Triângulos)
FOCOS_ANTERIORES_FILL = "#FAFF39"    # Amarelo intenso
FOCOS_ANTERIORES_STROKE = "#B35C15"  # Contorno bronze queimado
FOCOS_ANTERIORES_SIZE = 70           # Tamanho do marcador em pt²
FOCOS_ANTERIORES_LW = 1.2            # Espessura do traço

FOCOS_RECENTES_FILL = "#DB1E2A"      # Vermelho alerta intenso
FOCOS_RECENTES_STROKE = "#801119"    # Contorno bordô escuro
FOCOS_RECENTES_SIZE = 95             # Tamanho do marcador em pt²
FOCOS_RECENTES_LW = 1.6              # Espessura do traço

# Parâmetros da Coleção Sentinel-2 Harmonized (Google Earth Engine)
GEE_S2_COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"
DEFAULT_GEE_PROJECT = "ee-samuelsantosambientalcourse"

# Assets Oficiais MapBiomas Brasil (Coleção 11 - LULC 1985-2024)
MAPBIOMAS_C11_ASSET = "projects/mapbiomas-public/assets/brazil/lulc/collection11/mapbiomas_brazil_collection11_coverage_v3"
MAPBIOMAS_YEAR_DEFAULT = 2024

# Classificação Integrada de Severidade + Cobertura da Terra (MapBiomas C11)
# A legenda separa explicitamente o que é CICATRIZ DE QUEIMA (tons quentes/saturados)
# do que é COBERTURA DA TERRA (tons frios/mudos: verde, oliva e cinza).
# Classes 1..8 (a água é aplicada separadamente pela máscara NDWI em azul institucional).
SEVERIDADE_CLASSES = [
    ("#67000D", "Queimada Severa (dNBR > 0,66)"),
    ("#A50F15", "Queimada Alta (0,44 a 0,66)"),
    ("#EF6548", "Queimada Moderada (0,27 a 0,44)"),
    ("#FDBB84", "Queimada Leve (limiar local a 0,27)"),
    ("#1B5E20", "Floresta"),
    ("#9E9D24", "Campo / Savana"),
    ("#7CB342", "Pastagem / Mosaico"),
    ("#BDBDBD", "Outros usos / Solo exposto"),
]
SEVERIDADE_PALETTE = [cor for cor, _ in SEVERIDADE_CLASSES]

# Limiares mínimos de dNBR para disparar cicatriz de queima, por cobertura da terra.
# Campos e savanas exigem perda de biomassa maior para não confundir senescência sazonal.
LIMIAR_DNBR_FLORESTA = 0.10
LIMIAR_DNBR_CAMPO = 0.18
LIMIAR_DNBR_PASTAGEM = 0.15
LIMIAR_DNBR_OUTROS = 0.12

# Mapa intermediário: acima deste número de focos a plotagem individual é
# substituída por um mapa de calor (KDE), evitando a saturação visual dos símbolos.
HEATMAP_MIN_FOCOS = 250
HEATMAP_CMAP = ["#FFF7BC", "#FEC44F", "#F03B20", "#BD0026", "#67000D"]
HEATMAP_PESO_PRETERITO = 0.45  # Focos antigos pesam menos que os recentes (< 48h)

# Enquadramento do mapa principal: zoom na OCORRÊNCIA (e não no limite integral da UC)
OCORRENCIA_MARGIN_PCT = 0.15        # Margem de contexto ao redor das ocorrências
OCORRENCIA_MIN_SPAN_DEG = 0.06      # Janela mínima (~6,6 km) para focos muito agrupados
OCORRENCIA_FALLBACK_UC_MARGIN = 0.06  # Margem usada quando não há focos no período

# Escalonamento dinâmico dos triângulos quando há grande volume de focos
FOCOS_ESCALA = [
    # (limite_total, tam_ant, tam_rec, lw_ant, lw_rec, alpha_ant, alpha_rec)
    (400, FOCOS_ANTERIORES_SIZE, FOCOS_RECENTES_SIZE, FOCOS_ANTERIORES_LW, FOCOS_RECENTES_LW, 1.0, 1.0),
    (1500, 46, 62, 0.8, 1.0, 0.95, 1.0),
    (5000, 28, 40, 0.6, 0.8, 0.82, 0.95),
    (10000, 16, 26, 0.45, 0.6, 0.62, 0.88),
    (float("inf"), 12, 20, 0.4, 0.55, 0.55, 0.82),
]

# Visualizações Orbitais
VIS_CONFIGS = {
    "falsa_cor": {
        "nome": "Falsa Cor (Realce Queimadas)",
        "subtitulo": "Composição SWIR-NIR-Red (B12, B8, B4)",
        "bands": ["B12", "B8", "B4"],
        "min": 0.05,
        "max": 0.40,
        "gamma": 1.1,
    },
    "cor_natural": {
        "nome": "Cor Natural (RGB)",
        "subtitulo": "Composição Red-Green-Blue (B4, B3, B2)",
        "bands": ["B4", "B3", "B2"],
        "min": 0.02,
        "max": 0.20,
        "gamma": 1.2,
    },
    "dnbr": {
        "nome": "Severidade do Fogo (dNBR Bi-temporal)",
        "subtitulo": "Delta NBR (Pré vs Pós) — Padrão USGS/MTBS/Copernicus",
        "min": -0.10,
        "max": 0.66,
        "palette": [
            "#1A9641",  # <= -0.10: Rebrota vegetal / Aumento de vigor
            "#A6D96A",  #  0.00: Vegetação estável / sem cicatriz (Campos/Florestas)
            "#FEE08B",  #  0.10: Severidade baixa / Queima leve
            "#FDAE61",  #  0.27: Severidade moderada-baixa
            "#D73027",  #  0.44: Severidade moderada-alta
            "#7F0000",  # >= 0.66: Severidade alta / Queima profunda da biomassa
        ],
    },
    "nbr_mapbiomas": {
        "nome": "Severidade do Fogo (MapBiomas C11)",
        "subtitulo": "Cicatriz de Queima (dNBR) + Cobertura da Terra (MapBiomas C11)",
        "min": 1,
        "max": len(SEVERIDADE_CLASSES),
        "categorical": True,
        "classes": SEVERIDADE_CLASSES,
        "palette": SEVERIDADE_PALETTE,
    },
    "nbr": {
        "nome": "NBR Clássico (Unitemporal)",
        "subtitulo": "Normalized Burn Ratio (B8 - B12) / (B8 + B12)",
        "min": -0.30,
        "max": 0.70,
        # Tons frios/mudos para cobertura da terra; tons quentes apenas para cicatriz.
        "palette": [
            "#67000D",  # -0.30: Queimada Severa (cinzas profundas / solo calcinado)
            "#A50F15",  # -0.15: Queimada Alta / Cicatriz recente
            "#EF6548",  # -0.08: Queimada Moderada
            "#FDBB84",  #  0.02: Queima leve
            "#9E9D24",  #  0.15: Campos Naturais / Savanas / Cerrado seco sazonal
            "#7CB342",  #  0.28: Pastagem / Vegetação herbácea
            "#2E7D32",  #  0.45: Floresta conservada
            "#1B5E20",  #  0.60: Floresta densa
            "#0B3D0B",  #  0.70: Floresta tropical densa
        ],
    }
}

# Dimensões da Prancha em Milímetros (A4 Paisagem: 297 x 210 mm)
PAGE_WIDTH_MM = 297.0
PAGE_HEIGHT_MM = 210.0
DPI_EXPORT = 300

# Especificações dos Eixos (Origem superior-esquerda convertida para Matplotlib)
# No QGIS (0,0) é top-left. No Matplotlib (0,0) é bottom-left.
def mm_to_mpl_rect(x_mm, y_mm, w_mm, h_mm, page_w=PAGE_WIDTH_MM, page_h=PAGE_HEIGHT_MM):
    """Converte coordenadas milimétricas do QGIS em frações de figura para Matplotlib [left, bottom, width, height]."""
    left = x_mm / page_w
    bottom = (page_h - y_mm - h_mm) / page_h
    width = w_mm / page_w
    height = h_mm / page_h
    return [left, bottom, width, height]


def calculate_visible_extent(
    xmin: float, ymin: float, xmax: float, ymax: float,
    aspect_ratio: float = 1.25,
    margin_pct: float = 0.05
) -> Tuple[float, float, float, float]:
    """
    Ajusta dinamicamente a extensão geográfica da área de interesse para coincidir
    com a proporção exata da moldura do mapa (aspect_ratio = w / h).
    """
    w = xmax - xmin
    h = ymax - ymin
    
    xmin -= w * margin_pct
    xmax += w * margin_pct
    ymin -= h * margin_pct
    ymax += h * margin_pct
    
    w_curr = xmax - xmin
    h_curr = ymax - ymin
    
    curr_ratio = w_curr / h_curr if h_curr != 0 else aspect_ratio
    
    if curr_ratio < aspect_ratio:
        needed_w = h_curr * aspect_ratio
        delta = (needed_w - w_curr) / 2.0
        xmin -= delta
        xmax += delta
    else:
        needed_h = w_curr / aspect_ratio
        delta = (needed_h - h_curr) / 2.0
        ymin -= delta
        ymax += delta
        
    return (xmin, ymin, xmax, ymax)

# Coordenadas extraídas de layout_elements.json
LAYOUT_ITEMS = {
    # Faixa de Título
    "titulo": {
        "x": 8.0, "y": 5.411, "w": 278.85, "h": 12.302
    },
    # Moldura Externa Mapa Geral
    "rec_mapa": {
        "x": 8.15, "y": 18.50, "w": 167.106, "h": 132.751
    },
    # Viewport Mapa Geral (Principal)
    "mapa_geral": {
        "x": 14.15, "y": 22.50, "w": 155.0, "h": 124.0
    },
    # Painel Direito Localização
    "rec_localizacao": {
        "x": 175.254, "y": 18.50, "w": 111.466, "h": 180.010
    },
    # Inset Superior: Contexto Regional da UC
    "mapa_intermediario": {
        "x": 180.0, "y": 25.50, "w": 102.0, "h": 75.0
    },
    # Inset Inferior: Contexto Macro Estadual (Pará no Brasil)
    "mapa_macro": {
        "x": 180.0, "y": 110.50, "w": 102.0, "h": 75.0
    },
    # Bloco de Legenda
    "rec_legenda": {
        "x": 8.15, "y": 151.251, "w": 108.543, "h": 32.883
    },
    # Bloco de Fonte e Notas SIRGAS 2000
    "rec_fonte": {
        "x": 8.15, "y": 184.135, "w": 108.543, "h": 14.375
    },
    # Bloco Técnico: Escala, Norte e Logos
    "rec_tecnico": {
        "x": 116.697, "y": 151.251, "w": 58.559, "h": 47.259
    }
}
