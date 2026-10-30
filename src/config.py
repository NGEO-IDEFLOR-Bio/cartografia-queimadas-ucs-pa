"""
Módulo de Configuração Cartográfica e Parâmetros Operacionais
===========================================================
Define caminhos, CRS oficiais, dimensões milimétricas do layout A4 Paisagem
e convenções de cores da simbologia dos focos e dos basemaps orbitais.
"""

from pathlib import Path

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

# Logotipos Institucionais
FILE_BRASAO_PARA = IMG_DIR / "brasao-para.png"
FILE_LOGO_IDEFLOR = IMG_DIR / "logo-ideflor-bio.png"
FILE_LOGO_NGEO = IMG_DIR / "logo-ngeo.png"

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
    "nbr": {
        "nome": "NBR (Severidade do Fogo)",
        "subtitulo": "Normalized Burn Ratio (B8 - B12) / (B8 + B12)",
        "min": -0.20,
        "max": 0.50,
        "palette": ["#000000", "#db1e2a", "#ff8c00", "#ffff00", "#ffffff"],
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
