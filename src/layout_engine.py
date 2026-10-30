"""
Motor Cartográfico A4 Paisagem (Padrão NGEO/IDEFLOR-Bio)
======================================================
Gera pranchas cartográficas institucionais no formato A4 Paisagem (297 x 210 mm)
com precisão milimétrica, hierarquia de três mapas articulados (Macro, Intermediário e Detalhe),
simbologia de triângulos para focos de queimada, grades com rotação a 90° e logotipos oficiais.
"""

import math
from pathlib import Path
from typing import Dict, Any, Tuple, Optional, List
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
from matplotlib.ticker import MultipleLocator, FormatStrFormatter
import numpy as np
import geopandas as gpd
from PIL import Image

from src.config import (
    PAGE_WIDTH_MM, PAGE_HEIGHT_MM, DPI_EXPORT,
    LAYOUT_ITEMS, mm_to_mpl_rect,
    FOCOS_ANTERIORES_FILL, FOCOS_ANTERIORES_STROKE, FOCOS_ANTERIORES_SIZE, FOCOS_ANTERIORES_LW,
    FOCOS_RECENTES_FILL, FOCOS_RECENTES_STROKE, FOCOS_RECENTES_SIZE, FOCOS_RECENTES_LW,
    FILE_UCS_ESTADUAIS, FILE_ESTADO_PA, FILE_MUNICIPIOS,
    FILE_BRASIL_UFS, FILE_AMERICA_SUL,
    FILE_BRASAO_PARA, FILE_LOGO_IDEFLOR, FILE_LOGO_NGEO,
    CRS_GEOGRAFICO
)


def format_coord_dms(val: float, is_lat: bool = True) -> str:
    """Formata coordenadas decimais para graus e minutos (ex: 01°30'S)."""
    hem = ("S" if val < 0 else "N") if is_lat else ("W" if val < 0 else "E")
    v = abs(val)
    d = int(v)
    m = int(round((v - d) * 60))
    if m == 60:
        d += 1
        m = 0
    return f"{d:02d}°{m:02d}'{hem}"


def draw_north_arrow(ax, center_x: float = 0.5, center_y: float = 0.75, size: float = 0.25):
    """Desenha uma rosa dos ventos / seta norte clássica e estilizada."""
    w = size * 0.4
    h = size
    
    # Metade esquerda preta
    poly_left = plt.Polygon(
        [[center_x, center_y + h/2], [center_x - w/2, center_y - h/2], [center_x, center_y - h/4]],
        facecolor="black", edgecolor="black", transform=ax.transAxes, zorder=50
    )
    # Metade direita branca
    poly_right = plt.Polygon(
        [[center_x, center_y + h/2], [center_x + w/2, center_y - h/2], [center_x, center_y - h/4]],
        facecolor="white", edgecolor="black", transform=ax.transAxes, zorder=50
    )
    ax.add_patch(poly_left)
    ax.add_patch(poly_right)
    ax.text(
        center_x, center_y + h/2 + 0.08, "N",
        transform=ax.transAxes, ha="center", va="bottom",
        fontsize=10, fontweight="bold", color="black"
    )


def calculate_scalebar_params(extent_bbox: Tuple[float, float, float, float]) -> Tuple[float, str]:
    """Calcula um valor elegante e arredondado para a barra de escala gráfica."""
    xmin, ymin, xmax, ymax = extent_bbox
    mean_lat = (ymin + ymax) / 2.0
    # Comprimento de 1 grau de longitude na latitude média em km
    km_per_deg = 111.320 * math.cos(math.radians(mean_lat))
    total_km = (xmax - xmin) * km_per_deg
    
    target_km = total_km * 0.18  # Escala deve ocupar ~18% da largura do mapa
    
    candidate_steps = [1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500]
    best_step = candidate_steps[0]
    min_diff = float("inf")
    for step in candidate_steps:
        diff = abs(step - target_km)
        if diff < min_diff:
            min_diff = diff
            best_step = step
            
    return float(best_step), f"{int(best_step)} km"


def render_mapa_prancha(
    nome_uc: str,
    gdf_uc: gpd.GeoDataFrame,
    gdf_anteriores: gpd.GeoDataFrame,
    gdf_recentes: gpd.GeoDataFrame,
    basemap_img: Optional[np.ndarray],
    basemap_extent: Tuple[float, float, float, float],
    tipo_basemap: str = "falsa_cor",
    periodo_str: str = "Agosto a Dezembro/2025",
    metricas: Optional[Dict[str, Any]] = None,
    output_path: Optional[Path] = None
) -> plt.Figure:
    """
    Renderiza a prancha cartográfica completa A4 Paisagem (297 x 210 mm) em alta resolução.
    """
    # 1. Configurar Figura A4 Paisagem
    fig_w_in = PAGE_WIDTH_MM / 25.4
    fig_h_in = PAGE_HEIGHT_MM / 25.4
    fig = plt.figure(figsize=(fig_w_in, fig_h_in), dpi=DPI_EXPORT, facecolor="white")
    
    # 2. Caixa de Moldura Externa do Layout
    # Borda fina delimitando a folha institucional
    rect_folha = plt.Rectangle(
        (3.0 / PAGE_WIDTH_MM, 3.0 / PAGE_HEIGHT_MM),
        (PAGE_WIDTH_MM - 6.0) / PAGE_WIDTH_MM,
        (PAGE_HEIGHT_MM - 6.0) / PAGE_HEIGHT_MM,
        transform=fig.transFigure,
        fill=False, edgecolor="#333333", linewidth=0.8, zorder=1
    )
    fig.patches.append(rect_folha)
    
    # 3. Faixa de Cabeçalho / Título Principal
    t_rect = LAYOUT_ITEMS["titulo"]
    mpl_t = mm_to_mpl_rect(t_rect["x"], t_rect["y"], t_rect["w"], t_rect["h"])
    ax_titulo = fig.add_axes(mpl_t)
    ax_titulo.axis("off")
    
    titulo_mapa = f"MONITORAMENTO DE FOCOS DE CALOR E INCÊNDIO – {nome_uc.upper()}"
    ax_titulo.text(
        0.5, 0.70, titulo_mapa,
        transform=ax_titulo.transAxes, ha="center", va="center",
        fontsize=13, fontweight="bold", fontfamily="sans-serif", color="#0B2F1B"
    )
    subtitulo = f"Insumo Orbital: Sentinel-2 Harmonized ({tipo_basemap.upper()}) | BDQueimadas/INPE | Período: {periodo_str}"
    ax_titulo.text(
        0.5, 0.22, subtitulo,
        transform=ax_titulo.transAxes, ha="center", va="center",
        fontsize=9, fontfamily="sans-serif", color="#444444"
    )
    
    # 4. Viewport do Mapa Principal (Detalhe)
    m_rect = LAYOUT_ITEMS["mapa_geral"]
    mpl_m = mm_to_mpl_rect(m_rect["x"], m_rect["y"], m_rect["w"], m_rect["h"])
    ax_main = fig.add_axes(mpl_m)
    ax_main.set_axisbelow(False)
    
    xmin, ymin, xmax, ymax = basemap_extent
    ax_main.set_xlim(xmin, xmax)
    ax_main.set_ylim(ymin, ymax)
    
    # 4.1. Plotar Imagem Orbital Sentinel-2 (Preenchimento 100%)
    if basemap_img is not None:
        ax_main.imshow(basemap_img, extent=[xmin, xmax, ymin, ymax], origin="upper", zorder=5)
    else:
        # Fundo suave caso basemap não esteja carregado
        ax_main.set_facecolor("#EDF2F4")
        
    # 4.2. Plotar Limite da UC
    if not gdf_uc.empty:
        gdf_uc.boundary.plot(ax=ax_main, edgecolor="#00FF66", linewidth=2.0, zorder=20)
        gdf_uc.boundary.plot(ax=ax_main, edgecolor="#004D20", linewidth=3.2, alpha=0.6, zorder=19)
        
    # 4.3. Plotar Focos de Queimadas (Triângulos)
    # Focos anteriores: Amarelo com borda bronze
    if not gdf_anteriores.empty:
        gdf_anteriores.plot(
            ax=ax_main, marker="^",
            color=FOCOS_ANTERIORES_FILL, edgecolor=FOCOS_ANTERIORES_STROKE,
            linewidth=FOCOS_ANTERIORES_LW, markersize=FOCOS_ANTERIORES_SIZE,
            zorder=30
        )
    # Focos recentes / última observação: Vermelho com borda bordô
    if not gdf_recentes.empty:
        gdf_recentes.plot(
            ax=ax_main, marker="^",
            color=FOCOS_RECENTES_FILL, edgecolor=FOCOS_RECENTES_STROKE,
            linewidth=FOCOS_RECENTES_LW, markersize=FOCOS_RECENTES_SIZE,
            zorder=35
        )
        
    # 4.4. Grade de Coordenadas e Eixo Y Rotacionado a 90°
    grid_step = max(0.05, round((xmax - xmin) / 4.0, 2))
    ax_main.xaxis.set_major_locator(MultipleLocator(grid_step))
    ax_main.yaxis.set_major_locator(MultipleLocator(grid_step))
    
    # Formatação DMS
    x_ticks = [x for x in ax_main.get_xticks() if xmin <= x <= xmax]
    y_ticks = [y for y in ax_main.get_yticks() if ymin <= y <= ymax]
    
    ax_main.set_xticks(x_ticks)
    ax_main.set_yticks(y_ticks)
    ax_main.set_xticklabels([format_coord_dms(x, is_lat=False) for x in x_ticks], fontsize=7, fontweight="semibold")
    ax_main.set_yticklabels([format_coord_dms(y, is_lat=True) for y in y_ticks], fontsize=7, fontweight="semibold", rotation=90, va="center")
    
    ax_main.grid(True, linestyle="--", alpha=0.5, color="white", linewidth=0.6, zorder=25)
    
    # Moldura no topo (zorder=100)
    for spine in ax_main.spines.values():
        spine.set_edgecolor("#111111")
        spine.set_linewidth(1.2)
        spine.set_zorder(100)
        
    # 5. Painel Lateral Direito: Moldura de Contenção
    p_rect = LAYOUT_ITEMS["rec_localizacao"]
    mpl_p = mm_to_mpl_rect(p_rect["x"], p_rect["y"], p_rect["w"], p_rect["h"])
    ax_painel = fig.add_axes(mpl_p)
    ax_painel.axis("off")
    rect_painel = plt.Rectangle((0, 0), 1, 1, transform=ax_painel.transAxes, fill=False, edgecolor="#333333", linewidth=1.0)
    ax_painel.add_patch(rect_painel)
    
    # 6. Inset Superior: Localização Intermediária (Contexto na Região / Municípios)
    i_rect = LAYOUT_ITEMS["mapa_intermediario"]
    mpl_i = mm_to_mpl_rect(i_rect["x"], i_rect["y"], i_rect["w"], i_rect["h"])
    ax_interm = fig.add_axes(mpl_i)
    ax_interm.set_facecolor("#E8F4F8")
    
    # Carregar e plotar contexto municipal
    if FILE_MUNICIPIOS.exists():
        try:
            gdf_muni = gpd.read_file(FILE_MUNICIPIOS)
            gdf_muni.plot(ax=ax_interm, facecolor="#F8F9FA", edgecolor="#BDC3C7", linewidth=0.5, zorder=2)
        except Exception:
            pass
            
    if not gdf_uc.empty:
        gdf_uc.plot(ax=ax_interm, facecolor="#D4EFDF", edgecolor="#1E8449", linewidth=1.5, zorder=5)
        # Bounding box no mapa intermediário
        uc_bounds = gdf_uc.total_bounds
        buf_x = (uc_bounds[2] - uc_bounds[0]) * 0.4
        buf_y = (uc_bounds[3] - uc_bounds[1]) * 0.4
        ax_interm.set_xlim(uc_bounds[0] - buf_x, uc_bounds[2] + buf_x)
        ax_interm.set_ylim(uc_bounds[1] - buf_y, uc_bounds[3] + buf_y)
        
        # Plotar os focos na escala da UC
        if not gdf_anteriores.empty:
            gdf_anteriores.plot(ax=ax_interm, marker="^", color=FOCOS_ANTERIORES_FILL, edgecolor=FOCOS_ANTERIORES_STROKE, markersize=25, linewidth=0.8, zorder=8)
        if not gdf_recentes.empty:
            gdf_recentes.plot(ax=ax_interm, marker="^", color=FOCOS_RECENTES_FILL, edgecolor=FOCOS_RECENTES_STROKE, markersize=35, linewidth=1.0, zorder=9)
            
    ax_interm.tick_params(labelsize=6)
    for spine in ax_interm.spines.values():
        spine.set_edgecolor("#222222")
        spine.set_linewidth(1.0)
        spine.set_zorder(100)
    ax_interm.set_title("Contexto Regional da Unidade", fontsize=7.5, fontweight="bold", pad=3)
    
    # 7. Inset Inferior: Localização Macro Estadual (Pará no Brasil)
    u_rect = LAYOUT_ITEMS["mapa_macro"]
    mpl_u = mm_to_mpl_rect(u_rect["x"], u_rect["y"], u_rect["w"], u_rect["h"])
    ax_macro = fig.add_axes(mpl_u)
    ax_macro.set_facecolor("#EBF5FB")
    
    if FILE_BRASIL_UFS.exists():
        try:
            gdf_brasil = gpd.read_file(FILE_BRASIL_UFS)
            gdf_brasil.plot(ax=ax_macro, facecolor="#EAEDED", edgecolor="#BDC3C7", linewidth=0.4, zorder=2)
        except Exception:
            pass
            
    if FILE_ESTADO_PA.exists():
        try:
            gdf_pa = gpd.read_file(FILE_ESTADO_PA)
            gdf_pa.plot(ax=ax_macro, facecolor="#D5F5E3", edgecolor="#1E8449", linewidth=1.2, zorder=4)
        except Exception:
            pass
            
    # Centroide da UC com marcador e halo circular
    if not gdf_uc.empty:
        c = gdf_uc.geometry.centroid.iloc[0]
        ax_macro.plot(c.x, c.y, marker="o", markersize=9, color="#E74C3C", alpha=0.4, zorder=10)
        ax_macro.plot(c.x, c.y, marker="o", markersize=5, color="#C0392B", zorder=11)
        
    ax_macro.set_xlim(-60.0, -44.0)
    ax_macro.set_ylim(-10.5, 3.5)
    ax_macro.tick_params(labelsize=6)
    for spine in ax_macro.spines.values():
        spine.set_edgecolor("#222222")
        spine.set_linewidth(1.0)
        spine.set_zorder(100)
    ax_macro.set_title("Localização no Estado do Pará", fontsize=7.5, fontweight="bold", pad=3)
    
    # 8. Caixa de Legenda
    leg_rect = LAYOUT_ITEMS["rec_legenda"]
    mpl_leg = mm_to_mpl_rect(leg_rect["x"], leg_rect["y"], leg_rect["w"], leg_rect["h"])
    ax_leg = fig.add_axes(mpl_leg)
    ax_leg.axis("off")
    rect_leg_box = plt.Rectangle((0, 0), 1, 1, transform=ax_leg.transAxes, fill=False, edgecolor="#333333", linewidth=1.0)
    ax_leg.add_patch(rect_leg_box)
    
    ax_leg.text(0.04, 0.85, "LEGENDA CONVENCIONADA", fontsize=8, fontweight="bold", color="#111111", transform=ax_leg.transAxes)
    
    # Elementos da legenda
    n_recentes = len(gdf_recentes)
    n_anteriores = len(gdf_anteriores)
    data_rec = metricas.get("data_ultima_observacao", "Último dia") if metricas else "Dia Atual"
    
    legend_elements = [
        Line2D([0], [0], marker="^", color="w", label=f"Foco Atual / Última Obs. ({data_rec}): {n_recentes}",
               markerfacecolor=FOCOS_RECENTES_FILL, markeredgecolor=FOCOS_RECENTES_STROKE, markersize=8, markeredgewidth=1.2),
        Line2D([0], [0], marker="^", color="w", label=f"Focos Dias Anteriores: {n_anteriores}",
               markerfacecolor=FOCOS_ANTERIORES_FILL, markeredgecolor=FOCOS_ANTERIORES_STROKE, markersize=7, markeredgewidth=1.0),
        mpatches.Patch(edgecolor="#00FF66", facecolor="none", linewidth=2.0, label=f"Limite Oficial da {nome_uc}"),
    ]
    ax_leg.legend(
        handles=legend_elements, loc="center left", bbox_to_anchor=(0.03, 0.42),
        frameon=False, fontsize=7.2, handletextpad=0.6, labelspacing=0.5
    )
    
    # 9. Caixa de Metadados e Fontes Cartográficas
    f_rect = LAYOUT_ITEMS["rec_fonte"]
    mpl_f = mm_to_mpl_rect(f_rect["x"], f_rect["y"], f_rect["w"], f_rect["h"])
    ax_fonte = fig.add_axes(mpl_f)
    ax_fonte.axis("off")
    rect_f_box = plt.Rectangle((0, 0), 1, 1, transform=ax_fonte.transAxes, fill=False, edgecolor="#333333", linewidth=1.0)
    ax_fonte.add_patch(rect_f_box)
    
    texto_fonte = (
        "Elaboração: Núcleo de Geotecnologias (NGEO / IDEFLOR-Bio)\n"
        "Datum: SIRGAS 2000 (EPSG:4674) | Projeção Cartográfica Geográfica\n"
        "Fontes: BDQueimadas/INPE; Imagens orbitais Sentinel-2/Copernicus (GEE); Limites DGMUC/IDEFLOR-Bio."
    )
    ax_fonte.text(
        0.04, 0.50, texto_fonte,
        transform=ax_fonte.transAxes, ha="left", va="center",
        fontsize=6.5, fontfamily="sans-serif", color="#222222", linespacing=1.35
    )
    
    # 10. Bloco Técnico: Escala, Rosa dos Ventos e Logotipos
    tec_rect = LAYOUT_ITEMS["rec_tecnico"]
    mpl_tec = mm_to_mpl_rect(tec_rect["x"], tec_rect["y"], tec_rect["w"], tec_rect["h"])
    ax_tec = fig.add_axes(mpl_tec)
    ax_tec.axis("off")
    rect_tec_box = plt.Rectangle((0, 0), 1, 1, transform=ax_tec.transAxes, fill=False, edgecolor="#333333", linewidth=1.0)
    ax_tec.add_patch(rect_tec_box)
    
    # 10.1. Rosa dos Ventos
    draw_north_arrow(ax_tec, center_x=0.5, center_y=0.78, size=0.22)
    
    # 10.2. Escala Gráfica
    step_val, step_label = calculate_scalebar_params(basemap_extent)
    ax_tec.plot([0.22, 0.78], [0.55, 0.55], color="black", linewidth=2.0, transform=ax_tec.transAxes)
    ax_tec.plot([0.22, 0.22], [0.52, 0.58], color="black", linewidth=1.5, transform=ax_tec.transAxes)
    ax_tec.plot([0.78, 0.78], [0.52, 0.58], color="black", linewidth=1.5, transform=ax_tec.transAxes)
    ax_tec.text(0.22, 0.44, "0", transform=ax_tec.transAxes, ha="center", fontsize=6.5, fontweight="bold")
    ax_tec.text(0.78, 0.44, step_label, transform=ax_tec.transAxes, ha="center", fontsize=6.5, fontweight="bold")
    
    # 10.3. Logotipos Institucionais (NGEO, IDEFLOR-Bio, Brasão Pará)
    logo_files = [FILE_LOGO_NGEO, FILE_LOGO_IDEFLOR, FILE_BRASAO_PARA]
    x_positions = [0.18, 0.50, 0.82]
    
    for l_path, x_pos in zip(logo_files, x_positions):
        if l_path.exists():
            try:
                img_logo = Image.open(l_path)
                ax_img = fig.add_axes([
                    mpl_tec[0] + (x_pos - 0.12) * mpl_tec[2],
                    mpl_tec[1] + 0.04 * mpl_tec[3],
                    0.24 * mpl_tec[2],
                    0.28 * mpl_tec[3]
                ])
                ax_img.imshow(img_logo)
                ax_img.axis("off")
            except Exception:
                pass
                
    # Salvar saída se solicitado
    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=DPI_EXPORT, bbox_inches="tight", pad_inches=0.02)
        print(f"✓ Prancha cartográfica salva: {output_path}")
        
    return fig
