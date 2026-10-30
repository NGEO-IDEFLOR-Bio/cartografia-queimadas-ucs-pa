"""
Motor Cartográfico A4 Paisagem (Padrão Oficial NGEO/IDEFLOR-Bio)
==============================================================
Reproduz rigorosamente a diagramação milimétrica da prancha A4 Paisagem (297 x 210 mm)
em 3 escalas articuladas (Macro, Intermediário e Detalhe), conforme as convenções
cartográficas oficiais do Núcleo de Geotecnologias (NGEO/IDEFLOR-Bio).
"""

import re
import math
from pathlib import Path
from typing import Dict, Any, Tuple, Optional, List
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
from matplotlib.ticker import MultipleLocator
import numpy as np
import pandas as pd
import geopandas as gpd
from PIL import Image

from src.config import (
    PAGE_WIDTH_MM, PAGE_HEIGHT_MM, DPI_EXPORT,
    LAYOUT_ITEMS, mm_to_mpl_rect, calculate_visible_extent,
    FOCOS_ANTERIORES_FILL, FOCOS_ANTERIORES_STROKE, FOCOS_ANTERIORES_SIZE, FOCOS_ANTERIORES_LW,
    FOCOS_RECENTES_FILL, FOCOS_RECENTES_STROKE, FOCOS_RECENTES_SIZE, FOCOS_RECENTES_LW,
    FILE_UCS_ESTADUAIS, FILE_ESTADO_PA, FILE_MUNICIPIOS,
    FILE_BRASIL_UFS, FILE_AMERICA_SUL,
    FILE_BRASAO_PARA, FILE_LOGO_IDEFLOR, FILE_LOGO_NGEO,
    CRS_GEOGRAFICO, CRS_METRICO_PA
)


def get_short_uc_name(name: str) -> str:
    """Abrevia categorias de UCs para títulos e rótulos cartográficos concisos."""
    s = name.strip()
    replacements = [
        ("Reserva de Desenvolvimento Sustentável", "RDS"),
        ("Área de Proteção Ambiental", "APA"),
        ("Floresta Estadual", "FLOTA"),
        ("Parque Estadual", "PES"),
        ("Reserva Biológica", "REBIO"),
        ("Estação Ecológica", "ESEC"),
        ("Refúgio de Vida Silvestre", "REVIS"),
        ("Monumento Natural", "MONA"),
    ]
    for old, new in replacements:
        if old.lower() in s.lower():
            s = re.sub(re.escape(old), new, s, flags=re.IGNORECASE)
            break
    s = re.sub(r"\s*[\(\-]?\s*(RDS|APA|FLOTA|PES|REBIO|ESEC|REVIS|MONA)\s*[\)]?$", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*-\s*$", "", s).strip()
    return s


def format_coord_deg(val: float, is_lat: bool = True) -> str:
    """Formata coordenadas no padrão de graus decimais com indicador hemisférico (ex: 0.40°S, 50.38°W)."""
    hem = ("S" if val < 0 else "N") if is_lat else ("W" if val < 0 else "E")
    v = abs(val)
    return f"{v:.2f}°{hem}"


def format_coord_dms(val: float, is_lat: bool = True) -> str:
    """Formata coordenadas em graus e minutos (ex: 02°45'S, 51°56'W)."""
    hem = ("S" if val < 0 else "N") if is_lat else ("W" if val < 0 else "E")
    v = abs(val)
    d = int(v)
    m = int(round((v - d) * 60))
    if m >= 60:
        d += 1
        m = 0
    return f"{d:02d}°{m:02d}'{hem}"


def draw_north_arrow(ax, center_x: float = 0.5, center_y: float = 0.72, size: float = 0.22):
    """Desenha a rosa dos ventos clássica preta e branca com o N estilizado."""
    w = size * 0.42
    h = size
    
    # Metade esquerda preta
    poly_left = plt.Polygon(
        [[center_x, center_y + h/2], [center_x - w/2, center_y - h/2], [center_x, center_y - h/4]],
        facecolor="#111111", edgecolor="#111111", linewidth=0.8,
        transform=ax.transAxes, zorder=50
    )
    # Metade direita branca
    poly_right = plt.Polygon(
        [[center_x, center_y + h/2], [center_x + w/2, center_y - h/2], [center_x, center_y - h/4]],
        facecolor="#FFFFFF", edgecolor="#111111", linewidth=0.8,
        transform=ax.transAxes, zorder=50
    )
    ax.add_patch(poly_left)
    ax.add_patch(poly_right)
    ax.text(
        center_x, center_y + h/2 + 0.05, "N",
        transform=ax.transAxes, ha="center", va="bottom",
        fontsize=9, fontweight="bold", fontfamily="sans-serif", color="#111111"
    )


def calculate_scale_and_bar(extent_bbox: Tuple[float, float, float, float]) -> Tuple[float, str, str]:
    """
    Calcula a escala gráfica e numérica representativa (ex: 1 : 50.000).
    """
    xmin, ymin, xmax, ymax = extent_bbox
    mean_lat = (ymin + ymax) / 2.0
    km_per_deg = 111.320 * math.cos(math.radians(mean_lat))
    total_km = (xmax - xmin) * km_per_deg
    
    # Largura do mapa em metros no papel: 155mm = 0.155m
    # Largura no terreno: total_km * 1000 m
    ground_m = total_km * 1000.0
    raw_scale = ground_m / 0.155
    
    # Arredondar escala numérica para valor padrão
    round_bases = [10000, 25000, 50000, 75000, 100000, 150000, 200000, 250000, 500000, 1000000]
    best_scale = round_bases[0]
    min_scale_diff = float("inf")
    for base in round_bases:
        diff = abs(base - raw_scale)
        if diff < min_scale_diff:
            min_scale_diff = diff
            best_scale = base
    escala_num_str = f"Escala 1 : {best_scale:,}".replace(",", ".")
    
    # Barra gráfica (~20% da largura do mapa)
    target_bar_km = total_km * 0.20
    candidate_steps = [0.5, 1, 2, 5, 10, 20, 25, 50, 100, 200]
    best_step = candidate_steps[0]
    min_diff = float("inf")
    for s in candidate_steps:
        diff = abs(s - target_bar_km)
        if diff < min_diff:
            min_diff = diff
            best_step = s
            
    bar_label = f"{int(best_step) if best_step >= 1 else best_step} km"
    return float(best_step), bar_label, escala_num_str


def render_mapa_prancha(
    nome_uc: str,
    gdf_uc: gpd.GeoDataFrame,
    gdf_anteriores: gpd.GeoDataFrame,
    gdf_recentes: gpd.GeoDataFrame,
    basemap_img: Optional[np.ndarray],
    basemap_extent: Tuple[float, float, float, float],
    tipo_basemap: str = "Falsa Cor (Realce Queimadas)",
    periodo_str: str = "Últimos 30 dias",
    metricas: Optional[Dict[str, Any]] = None,
    output_path: Optional[Path] = None
) -> plt.Figure:
    """
    Renderiza a prancha cartográfica completa A4 Paisagem (297 x 210 mm) com precisão milimétrica.
    """
    # 1. Configurar Figura A4 Paisagem
    fig_w_in = PAGE_WIDTH_MM / 25.4
    fig_h_in = PAGE_HEIGHT_MM / 25.4
    fig = plt.figure(figsize=(fig_w_in, fig_h_in), dpi=DPI_EXPORT, facecolor="white")
    
    # 2. Borda Dupla Externa do Layout Institucional (como no mapa_exemplo.png)
    # Borda 1 (Externa): 3.5 mm de margem
    rect_out1 = plt.Rectangle(
        (3.5 / PAGE_WIDTH_MM, 3.5 / PAGE_HEIGHT_MM),
        (PAGE_WIDTH_MM - 7.0) / PAGE_WIDTH_MM,
        (PAGE_HEIGHT_MM - 7.0) / PAGE_HEIGHT_MM,
        transform=fig.transFigure,
        fill=False, edgecolor="#111111", linewidth=1.0, zorder=1
    )
    # Borda 2 (Interna): 4.5 mm de margem
    rect_out2 = plt.Rectangle(
        (4.5 / PAGE_WIDTH_MM, 4.5 / PAGE_HEIGHT_MM),
        (PAGE_WIDTH_MM - 9.0) / PAGE_WIDTH_MM,
        (PAGE_HEIGHT_MM - 9.0) / PAGE_HEIGHT_MM,
        transform=fig.transFigure,
        fill=False, edgecolor="#111111", linewidth=0.5, zorder=2
    )
    fig.patches.extend([rect_out1, rect_out2])
    
    # 3. Faixa de Cabeçalho / Título Principal (txt_titulo)
    # Caixa retangular contínua que cobre da extremidade esquerda à direita sobre os mapas
    t_rect = LAYOUT_ITEMS["titulo"]
    mpl_t = mm_to_mpl_rect(t_rect["x"], t_rect["y"], t_rect["w"], t_rect["h"])
    ax_titulo = fig.add_axes(mpl_t)
    ax_titulo.axis("off")
    
    rect_t_box = plt.Rectangle((0, 0), 1, 1, transform=ax_titulo.transAxes,
                               fill=True, facecolor="#F8F9F9", edgecolor="#2C3E50", linewidth=1.0)
    ax_titulo.add_patch(rect_t_box)
    
    short_uc_name = get_short_uc_name(nome_uc)
    titulo_mapa = f"MAPA DE MONITORAMENTO DE FOCOS DE CALOR E INCÊNDIO – {short_uc_name.upper()}"
    ax_titulo.text(
        0.5, 0.65, titulo_mapa,
        transform=ax_titulo.transAxes, ha="center", va="center",
        fontsize=10.5, fontweight="bold", fontfamily="sans-serif", color="#1B2631"
    )
    subtitulo = f"Insumo Orbital: Sentinel-2 Harmonized ({tipo_basemap}) | BDQueimadas/INPE | Período: {periodo_str}"
    ax_titulo.text(
        0.5, 0.25, subtitulo,
        transform=ax_titulo.transAxes, ha="center", va="center",
        fontsize=7.0, fontfamily="sans-serif", color="#2C3E50"
    )
    
    # 4. Coluna Esquerda: Moldura Externa de Contenção (rec_mapa)
    rec_m = LAYOUT_ITEMS["rec_mapa"]
    mpl_rec_m = mm_to_mpl_rect(rec_m["x"], rec_m["y"], rec_m["w"], rec_m["h"])
    ax_rec_m = fig.add_axes(mpl_rec_m)
    ax_rec_m.axis("off")
    rect_m_box = plt.Rectangle((0, 0), 1, 1, transform=ax_rec_m.transAxes, fill=False, edgecolor="#111111", linewidth=0.8)
    ax_rec_m.add_patch(rect_m_box)
    
    # 4.1. Viewport do Mapa Principal (mapa_geral: 155 x 124 mm)
    m_rect = LAYOUT_ITEMS["mapa_geral"]
    mpl_m = mm_to_mpl_rect(m_rect["x"], m_rect["y"], m_rect["w"], m_rect["h"])
    ax_main = fig.add_axes(mpl_m)
    ax_main.set_axisbelow(False)
    
    # Limpeza absoluta de títulos nos eixos (elimina 'Geodetic longitude [degree]')
    ax_main.set_xlabel(None)
    ax_main.set_ylabel(None)
    ax_main.xaxis.label.set_visible(False)
    ax_main.yaxis.label.set_visible(False)
    
    xmin, ymin, xmax, ymax = basemap_extent
    ax_main.set_xlim(xmin, xmax)
    ax_main.set_ylim(ymin, ymax)
    
    # Imagem orbital Sentinel-2 (Preenchimento 100% sem margens vazias)
    if basemap_img is not None:
        ax_main.imshow(basemap_img, extent=[xmin, xmax, ymin, ymax], origin="upper", zorder=5)
    else:
        ax_main.set_facecolor("#EDF2F4")
        
    # Limite da UC no mapa principal (verde neon com halo florestal escuro)
    if not gdf_uc.empty:
        gdf_uc.boundary.plot(ax=ax_main, edgecolor="#00FF66", linewidth=2.0, zorder=20)
        gdf_uc.boundary.plot(ax=ax_main, edgecolor="#004D20", linewidth=3.2, alpha=0.7, zorder=19)
        
    # Focos de Queimadas (Triângulos)
    if not gdf_anteriores.empty:
        gdf_anteriores.plot(
            ax=ax_main, marker="^",
            color=FOCOS_ANTERIORES_FILL, edgecolor=FOCOS_ANTERIORES_STROKE,
            linewidth=FOCOS_ANTERIORES_LW, markersize=FOCOS_ANTERIORES_SIZE,
            zorder=30
        )
    if not gdf_recentes.empty:
        gdf_recentes.plot(
            ax=ax_main, marker="^",
            color=FOCOS_RECENTES_FILL, edgecolor=FOCOS_RECENTES_STROKE,
            linewidth=FOCOS_RECENTES_LW, markersize=FOCOS_RECENTES_SIZE,
            zorder=35
        )
        
    # Grade de Coordenadas do Mapa Principal
    span_x = xmax - xmin
    grid_step = 0.05 if span_x < 0.25 else (0.10 if span_x < 0.6 else (0.20 if span_x < 1.2 else 0.50))
    ax_main.xaxis.set_major_locator(MultipleLocator(grid_step))
    ax_main.yaxis.set_major_locator(MultipleLocator(grid_step))
    
    x_ticks = [x for x in ax_main.get_xticks() if (xmin + 0.01 * span_x) <= x <= (xmax - 0.01 * span_x)]
    y_ticks = [y for y in ax_main.get_yticks() if (ymin + 0.01 * span_x) <= y <= (ymax - 0.01 * span_x)]
    
    ax_main.set_xticks(x_ticks)
    ax_main.set_yticks(y_ticks)
    ax_main.set_xticklabels([format_coord_deg(x, is_lat=False) for x in x_ticks], fontsize=7.5, fontweight="semibold")
    ax_main.set_yticklabels([format_coord_deg(y, is_lat=True) for y in y_ticks], fontsize=7.5, fontweight="semibold", rotation=90, va="center")
    
    ax_main.grid(True, linestyle="--", alpha=0.45, color="white", linewidth=0.6, zorder=25)
    
    # 4.2. Legenda Cartográfica Flutuante de Severidade do Fogo (NBR)
    if "nbr" in tipo_basemap.lower() or "severidade" in tipo_basemap.lower():
        rec_nbr_leg = mpatches.FancyBboxPatch(
            (0.68, 0.70), 0.305, 0.28,
            boxstyle="square,pad=0.01",
            transform=ax_main.transAxes,
            facecolor="#FFFFFF", edgecolor="#2C3E50",
            linewidth=0.8, alpha=0.92, zorder=50
        )
        ax_main.add_patch(rec_nbr_leg)
        
        ax_main.text(0.832, 0.958, "Severidade do Fogo (NBR)",
                     transform=ax_main.transAxes, ha="center", va="top",
                     fontsize=6.8, fontweight="bold", color="#1B2631", zorder=51)
                     
        nbr_classes = [
            ("#7F0000", "Queimada Severa (< -0.15)"),
            ("#F46D43", "Queimada Moderada (-0.15 a 0.05)"),
            ("#FEE08B", "Solo / Baixa Veg. (0.05 a 0.25)"),
            ("#1A9641", "Floresta Preservada (> 0.25)"),
            ("#1F618D", "Corpos d'Água (Rios / Lagos)"),
        ]
        y_swatch_start = 0.895
        for i, (cor, label_cls) in enumerate(nbr_classes):
            y_cls = y_swatch_start - (i * 0.040)
            patch_cls = mpatches.Rectangle(
                (0.695, y_cls - 0.013), 0.026, 0.026,
                transform=ax_main.transAxes,
                facecolor=cor, edgecolor="#333333", linewidth=0.5, zorder=51
            )
            ax_main.add_patch(patch_cls)
            ax_main.text(0.732, y_cls, label_cls,
                         transform=ax_main.transAxes, ha="left", va="center",
                         fontsize=5.6, fontweight="semibold", color="#2C3E50", zorder=51)

    # Moldura no topo (zorder=100)
    for spine in ax_main.spines.values():
        spine.set_edgecolor("#111111")
        spine.set_linewidth(1.0)
        spine.set_zorder(100)
        
    # 5. Coluna Direita: Painel de Enquadramento Regional e Macro (rec_localizacao)
    p_rect = LAYOUT_ITEMS["rec_localizacao"]
    mpl_p = mm_to_mpl_rect(p_rect["x"], p_rect["y"], p_rect["w"], p_rect["h"])
    ax_painel = fig.add_axes(mpl_p)
    ax_painel.axis("off")
    rect_painel = plt.Rectangle((0, 0), 1, 1, transform=ax_painel.transAxes, fill=False, edgecolor="#111111", linewidth=0.8)
    ax_painel.add_patch(rect_painel)
    
    # 5.1. Título do Mapa Intermediário (Centralizado acima do mapa)
    ax_painel.text(
        0.5, 0.98, "LOCALIZAÇÃO DA OCORRÊNCIA NA UC",
        transform=ax_painel.transAxes, ha="center", va="top",
        fontsize=8.2, fontweight="bold", fontfamily="sans-serif", color="#111111"
    )
    
    # 5.2. Viewport do Mapa Intermediário (mapa_intermediario: 102 x 75 mm)
    i_rect = LAYOUT_ITEMS["mapa_intermediario"]
    mpl_i = mm_to_mpl_rect(i_rect["x"], i_rect["y"], i_rect["w"], i_rect["h"])
    ax_interm = fig.add_axes(mpl_i)
    ax_interm.set_facecolor("#E8F4F8")  # Fundo hídrico/baía
    ax_interm.set_axisbelow(False)
    
    # Limpeza de labels
    ax_interm.set_xlabel(None)
    ax_interm.set_ylabel(None)
    ax_interm.xaxis.label.set_visible(False)
    ax_interm.yaxis.label.set_visible(False)
    
    if FILE_MUNICIPIOS.exists():
        try:
            gdf_muni = gpd.read_file(FILE_MUNICIPIOS)
            gdf_muni.plot(ax=ax_interm, facecolor="#FFFFFF", edgecolor="#CBD5E1", linewidth=0.5, zorder=2)
        except Exception:
            pass
            
    if not gdf_uc.empty:
        # Enquadramento proporcional com aspect ratio fixo idêntico ao viewport (102.0 / 75.0 = 1.36)
        uc_bounds = gdf_uc.total_bounds
        xmin_i, ymin_i, xmax_i, ymax_i = calculate_visible_extent(
            uc_bounds[0], uc_bounds[1], uc_bounds[2], uc_bounds[3],
            aspect_ratio=(102.0 / 75.0),
            margin_pct=0.20
        )
        ax_interm.set_xlim(xmin_i, xmax_i)
        ax_interm.set_ylim(ymin_i, ymax_i)
        
        gdf_uc.plot(ax=ax_interm, facecolor="#D4EFDF", edgecolor="#1E8449", linewidth=1.5, zorder=5)
        
        # Rótulo com nome da UC em verde florestal (garantido dentro da geometria)
        rep_pt = gdf_uc.to_crs(CRS_METRICO_PA).geometry.representative_point().to_crs(CRS_GEOGRAFICO).iloc[0]
        ax_interm.text(
            rep_pt.x, rep_pt.y, short_uc_name,
            ha="center", va="center", fontsize=7.2, fontweight="bold",
            color="#1E8449", zorder=15,
            bbox=dict(boxstyle="square,pad=0.2", fc="#FFFFFF", ec="none", alpha=0.75)
        )
        
        # Focos no mapa intermediário (simbologia padrão conforme legenda)
        if not gdf_anteriores.empty:
            gdf_anteriores.plot(ax=ax_interm, marker="^", color=FOCOS_ANTERIORES_FILL, edgecolor=FOCOS_ANTERIORES_STROKE, markersize=25, linewidth=0.8, zorder=8)
        if not gdf_recentes.empty:
            gdf_recentes.plot(ax=ax_interm, marker="^", color=FOCOS_RECENTES_FILL, edgecolor=FOCOS_RECENTES_STROKE, markersize=35, linewidth=1.0, zorder=9)
            
    # Trava a geometria do eixo intermediário para dimensões físicas fixas (102 x 75 mm), sem estreitar pela UC
    ax_interm.set_aspect('equal', adjustable='datalim')
    
    # Ticks e coordenadas do mapa intermediário
    ax_interm.tick_params(axis="both", which="both", labelsize=5.0, length=2.0, color="#2C3E50", pad=1.2)
    for tick in ax_interm.get_yticklabels():
        tick.set_rotation(90)
        tick.set_va("center")
        
    for spine in ax_interm.spines.values():
        spine.set_edgecolor("#111111")
        spine.set_linewidth(0.8)
        spine.set_zorder(100)
        
    # 5.3. Título do Mapa Macro (Centralizado com folga milimétrica exata: 2.7mm após ticks e 2.6mm antes do mapa)
    ax_painel.text(
        0.5, 0.5094, f"LOCALIZAÇÃO DA UNIDADE – {short_uc_name.upper()}",
        transform=ax_painel.transAxes, ha="center", va="center",
        fontsize=7.5, fontweight="bold", fontfamily="sans-serif", color="#111111"
    )
    
    # 5.4. Viewport do Mapa Macro (mapa_macro: 102 x 75 mm)
    u_rect = LAYOUT_ITEMS["mapa_macro"]
    mpl_u = mm_to_mpl_rect(u_rect["x"], u_rect["y"], u_rect["w"], u_rect["h"])
    ax_macro = fig.add_axes(mpl_u)
    ax_macro.set_facecolor("#E8F4F8")  # Fundo oceano
    ax_macro.set_axisbelow(False)
    
    # Limpeza de labels
    ax_macro.set_xlabel(None)
    ax_macro.set_ylabel(None)
    ax_macro.xaxis.label.set_visible(False)
    ax_macro.yaxis.label.set_visible(False)
    
    # Países vizinhos da América do Sul
    if FILE_AMERICA_SUL.exists():
        try:
            gdf_sa = gpd.read_file(FILE_AMERICA_SUL)
            gdf_sa.plot(ax=ax_macro, facecolor="#EAEDED", edgecolor="#BDC3C7", linewidth=0.5, zorder=2)
        except Exception:
            pass
            
    # Estados Brasileiros vizinhos
    if FILE_BRASIL_UFS.exists():
        try:
            gdf_brasil = gpd.read_file(FILE_BRASIL_UFS)
            gdf_brasil.plot(ax=ax_macro, facecolor="#EAEDED", edgecolor="#BDC3C7", linewidth=0.5, zorder=3)
        except Exception:
            pass
            
    # Estado do Pará em destaque (#D5F5E3 com contorno verde escuro #1E8449)
    if FILE_ESTADO_PA.exists():
        try:
            gdf_pa = gpd.read_file(FILE_ESTADO_PA)
            gdf_pa.plot(ax=ax_macro, facecolor="#D5F5E3", edgecolor="#1E8449", linewidth=1.2, zorder=4)
        except Exception:
            pass
            
    # Textos de contexto regional no mapa macro (estilo mapa_exemplo.png)
    ax_macro.text(-56.5, 4.2, "SURINAME", fontsize=5.8, color="#7F8C8D", zorder=6)
    ax_macro.text(-53.2, 4.2, "GUIANA FRANCESA", fontsize=5.8, color="#7F8C8D", zorder=6)
    ax_macro.text(-47.5, 2.5, "OCEANO\nATLÂNTICO", fontsize=6.2, fontstyle="italic", color="#2980B9", ha="center", zorder=6)
    
    # Siglas dos estados vizinhos
    state_labels = [
        ("AP", -51.8, 1.4), ("RR", -61.5, 1.8), ("AM", -60.2, -4.2),
        ("MT", -55.5, -11.2), ("TO", -48.2, -8.2), ("MA", -45.5, -4.2)
    ]
    for sigla, lx, ly in state_labels:
        ax_macro.text(lx, ly, sigla, fontsize=6.5, fontweight="bold", color="#7F8C8D", ha="center", va="center", zorder=6)
        
    # Sigla PA centralizada no Pará
    ax_macro.text(-53.5, -4.0, "PA", fontsize=8.5, fontweight="bold", color="#1E8449", ha="center", va="center", zorder=6)
    
    # Posição da UC no mapa macro (com cálculo de centroide métrico sem warnings)
    if not gdf_uc.empty:
        c_macro = gdf_uc.to_crs(CRS_METRICO_PA).geometry.centroid.to_crs(CRS_GEOGRAFICO).iloc[0]
        # Ponto vermelho + halo circular concêntrico
        ax_macro.plot(c_macro.x, c_macro.y, marker="o", markersize=9, color="#E74C3C", alpha=0.35, zorder=10)
        ax_macro.plot(c_macro.x, c_macro.y, marker="o", markersize=4.5, color="#C0392B", zorder=11)
        
        # Callout box com nome da UC (estilo PES Charapucu do mapa_exemplo.png)
        call_uc_x = c_macro.x + 3.2 if c_macro.x < -50.0 else c_macro.x - 3.2
        call_uc_y = c_macro.y + 1.2
        ax_macro.annotate(
            short_uc_name,
            xy=(c_macro.x, c_macro.y), xytext=(call_uc_x, call_uc_y),
            ha="center", va="center", fontsize=6.5, fontweight="bold", color="#C0392B",
            arrowprops=dict(arrowstyle="->", color="#C0392B", lw=1.0),
            bbox=dict(boxstyle="square,pad=0.2", fc="#FFFFFF", ec="#C0392B", lw=0.8),
            zorder=20
        )
        
    ax_macro.set_xlim(-62.5, -43.5)
    ax_macro.set_ylim(-12.0, 5.0)
    ax_macro.set_aspect('equal', adjustable='datalim')
    
    # Grade de 4.0° uniforme no mapa macro
    ax_macro.xaxis.set_major_locator(MultipleLocator(4.0))
    ax_macro.yaxis.set_major_locator(MultipleLocator(4.0))
    ax_macro.tick_params(labelsize=6, direction="out", length=2.5)
    for tick in ax_macro.get_yticklabels():
        tick.set_rotation(90)
        tick.set_va("center")
        
    for spine in ax_macro.spines.values():
        spine.set_edgecolor("#111111")
        spine.set_linewidth(0.8)
        spine.set_zorder(100)
        
    # 6. Bloco Inferior Esquerdo: Caixa de Legenda (rec_legenda)
    leg_rect = LAYOUT_ITEMS["rec_legenda"]
    mpl_leg = mm_to_mpl_rect(leg_rect["x"], leg_rect["y"], leg_rect["w"], leg_rect["h"])
    ax_leg = fig.add_axes(mpl_leg)
    ax_leg.axis("off")
    rect_leg_box = plt.Rectangle((0, 0), 1, 1, transform=ax_leg.transAxes, fill=False, edgecolor="#111111", linewidth=0.8)
    ax_leg.add_patch(rect_leg_box)
    
    ax_leg.text(0.04, 0.88, "LEGENDA CONVENCIONADA", fontsize=7.8, fontweight="bold", color="#111111", transform=ax_leg.transAxes)
    
    n_recentes = len(gdf_recentes)
    n_anteriores = len(gdf_anteriores)
    data_rec = metricas.get("data_ultima_observacao", "Último dia") if metricas else "Dia Atual"
    
    # Handles estilizados da legenda
    h_rec = Line2D([0], [0], marker="^", color="w", label=f"Foco Atual / Última Obs. ({data_rec}) – {n_recentes} focos",
                   markerfacecolor=FOCOS_RECENTES_FILL, markeredgecolor=FOCOS_RECENTES_STROKE, markersize=8, markeredgewidth=1.2)
    h_ant = Line2D([0], [0], marker="^", color="w", label=f"Focos Dias Anteriores – {n_anteriores} focos",
                   markerfacecolor=FOCOS_ANTERIORES_FILL, markeredgecolor=FOCOS_ANTERIORES_STROKE, markersize=7, markeredgewidth=1.0)
    h_uc = Line2D([0, 1], [0, 0], color="#00FF66", linestyle="--", linewidth=2.0, label=f"Limite Oficial da {short_uc_name}")
    h_pa = mpatches.Patch(facecolor="#D5F5E3", edgecolor="#1E8449", linewidth=1.0, label="Limite do Estado do Pará (Contexto Regional)")
    
    ax_leg.legend(
        handles=[h_rec, h_ant, h_uc, h_pa],
        loc="center left", bbox_to_anchor=(0.02, 0.42),
        frameon=False, fontsize=6.8, handletextpad=0.8, labelspacing=0.4
    )
    
    # 7. Bloco Inferior Esquerdo: Metadados e Fontes Cartográficas (rec_fonte)
    f_rect = LAYOUT_ITEMS["rec_fonte"]
    mpl_f = mm_to_mpl_rect(f_rect["x"], f_rect["y"], f_rect["w"], f_rect["h"])
    ax_fonte = fig.add_axes(mpl_f)
    ax_fonte.axis("off")
    rect_f_box = plt.Rectangle((0, 0), 1, 1, transform=ax_fonte.transAxes, fill=False, edgecolor="#111111", linewidth=0.8)
    ax_fonte.add_patch(rect_f_box)
    
    texto_fonte = (
        "Elaboração: Núcleo de Geotecnologias (NGEO / IDEFLOR-Bio)\n"
        "Sistema Geodésico de Referência: SIRGAS 2000 (EPSG:4674) / Projeção Cartográfica Geográfica\n"
        "Fontes de Dados: INPE / BDQueimadas; Sentinel-2/Copernicus (GEE); Limites DGMUC/IDEFLOR-Bio.\n"
        "Nota: Mapeamento oficial de suporte à gestão e fiscalização ambiental."
    )
    ax_fonte.text(
        0.03, 0.50, texto_fonte,
        transform=ax_fonte.transAxes, ha="left", va="center",
        fontsize=6.0, fontfamily="sans-serif", color="#222222", linespacing=1.35
    )
    
    # 8. Bloco Técnico: Rosa dos Ventos, Escala Gráfica e Logotipos (rec_escala-icons-seta)
    tec_rect = LAYOUT_ITEMS["rec_tecnico"]
    mpl_tec = mm_to_mpl_rect(tec_rect["x"], tec_rect["y"], tec_rect["w"], tec_rect["h"])
    ax_tec = fig.add_axes(mpl_tec)
    ax_tec.axis("off")
    rect_tec_box = plt.Rectangle((0, 0), 1, 1, transform=ax_tec.transAxes, fill=False, edgecolor="#111111", linewidth=0.8)
    ax_tec.add_patch(rect_tec_box)
    
    # 8.1. Rosa dos Ventos
    draw_north_arrow(ax_tec, center_x=0.5, center_y=0.74, size=0.20)
    
    # 8.2. Escala Gráfica e Numérica
    step_val, step_label, escala_txt = calculate_scale_and_bar(basemap_extent)
    
    # Barra de escala em blocos alternados (estilo QGIS)
    x0, x1 = 0.18, 0.82
    y_bar = 0.52
    h_bar = 0.03
    mid = (x0 + x1) / 2.0
    
    # Bloco esquerdo preto, direito branco
    ax_tec.add_patch(plt.Rectangle((x0, y_bar), mid - x0, h_bar, transform=ax_tec.transAxes, facecolor="#111111", edgecolor="#111111"))
    ax_tec.add_patch(plt.Rectangle((mid, y_bar), x1 - mid, h_bar, transform=ax_tec.transAxes, facecolor="#FFFFFF", edgecolor="#111111"))
    
    # Ticks e textos da barra de escala
    ax_tec.text(x0, y_bar + h_bar + 0.02, "0", transform=ax_tec.transAxes, ha="center", fontsize=6.2, fontweight="bold")
    ax_tec.text(mid, y_bar + h_bar + 0.02, f"{int(step_val/2) if step_val>=2 else step_val/2}", transform=ax_tec.transAxes, ha="center", fontsize=6.2)
    ax_tec.text(x1, y_bar + h_bar + 0.02, step_label, transform=ax_tec.transAxes, ha="center", fontsize=6.2, fontweight="bold")
    
    # Escala Numérica
    ax_tec.text(0.5, y_bar - 0.08, escala_txt, transform=ax_tec.transAxes, ha="center", fontsize=6.5, fontfamily="sans-serif", color="#111111")
    
    # 8.3. Três Logotipos Oficiais (Perfeitamente dimensionados e sem sobreposição)
    # Posições horizontais dedicadas
    logos_config = [
        (FILE_LOGO_NGEO, 0.04, 0.28),
        (FILE_LOGO_IDEFLOR, 0.36, 0.28),
        (FILE_BRASAO_PARA, 0.68, 0.28)
    ]
    
    for l_path, lx_start, lw_box in logos_config:
        if l_path.exists():
            try:
                img_logo = Image.open(l_path)
                ax_img = fig.add_axes([
                    mpl_tec[0] + lx_start * mpl_tec[2],
                    mpl_tec[1] + 0.04 * mpl_tec[3],
                    lw_box * mpl_tec[2],
                    0.26 * mpl_tec[3]
                ])
                ax_img.imshow(img_logo)
                ax_img.axis("off")
            except Exception:
                pass
                
    # 9. Salvar saída se solicitado
    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=DPI_EXPORT, bbox_inches="tight", pad_inches=0.01)
        print(f"[OK] Prancha cartográfica salva: {output_path}")
        
    return fig
