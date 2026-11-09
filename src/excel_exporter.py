"""
Módulo de Exportação de Focos para Planilha Eletrônica Excel (.xlsx)
===================================================================
Gera planilhas estruturadas, elegantes e totalmente auditáveis contendo
a relação completa de focos de calor com metadados georreferenciados,
formatadas no padrão institucional do NGEO/IDEFLOR-Bio.
"""

from pathlib import Path
from typing import Union, Optional
import pandas as pd
import geopandas as gpd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter


def export_focos_to_excel(
    gdf_focos: gpd.GeoDataFrame,
    nome_uc: str,
    periodo_str: str,
    output_path: Union[str, Path],
    metricas: Optional[dict] = None
) -> Path:
    """
    Exporta a totalidade dos focos de calor para uma planilha Excel (.xlsx)
    com formatação profissional, tabela detalhada e aba de resumo por município.
    
    Parameters
    ----------
    gdf_focos : gpd.GeoDataFrame
        GeoDataFrame contendo os focos interceptados na UC.
    nome_uc : str
        Nome oficial da Unidade de Conservação.
    periodo_str : str
        Intervalo de datas do monitoramento.
    output_path : Union[str, Path]
        Caminho de saída para salvar o arquivo .xlsx.
    metricas : dict, optional
        Dicionário com métricas de classificação temporal.
        
    Returns
    -------
    Path
        Caminho do arquivo Excel gerado.
    """
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    
    wb = Workbook()
    
    # -------------------------------------------------------------
    # 1. ABA 1: Relação Individualizada de Focos
    # -------------------------------------------------------------
    ws_focos = wb.active
    ws_focos.title = "Focos_Detalhado"
    ws_focos.views.sheetView[0].showGridLines = True
    
    # Estilos Visuais Institucionais
    cor_cabecalho_fundo = "1B4F72"   # Azul institucional profundo
    cor_texto_cabecalho = "FFFFFF"
    cor_titulo_bloco = "EAEDED"      # Cinza suave
    
    font_titulo = Font(name="Arial", size=13, bold=True, color="1B2631")
    font_subtitulo = Font(name="Arial", size=9.5, italic=True, color="566573")
    font_header = Font(name="Arial", size=9.5, bold=True, color=cor_texto_cabecalho)
    font_data = Font(name="Arial", size=9, color="212F3D")
    
    fill_header = PatternFill(start_color=cor_cabecalho_fundo, end_color=cor_cabecalho_fundo, fill_type="solid")
    fill_zebra_par = PatternFill(start_color="F8F9F9", end_color="F8F9F9", fill_type="solid")
    fill_zebra_impar = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
    fill_alerta = PatternFill(start_color="FADBD8", end_color="FADBD8", fill_type="solid") # Vermelho suave para foco ativo
    
    border_thin = Border(
        left=Side(style="thin", color="D5D8DC"),
        right=Side(style="thin", color="D5D8DC"),
        top=Side(style="thin", color="D5D8DC"),
        bottom=Side(style="thin", color="D5D8DC")
    )
    
    align_center = Alignment(horizontal="center", vertical="center")
    align_left = Alignment(horizontal="left", vertical="center")
    align_right = Alignment(horizontal="right", vertical="center")
    
    # Cabeçalho Institucional Superior
    ws_focos.merge_cells("A1:K1")
    ws_focos["A1"] = f"MONITORAMENTO DE FOCOS DE CALOR E INCÊNDIO – {nome_uc.upper()}"
    ws_focos["A1"].font = font_titulo
    ws_focos["A1"].alignment = align_left
    
    ws_focos.merge_cells("A2:K2")
    total_count = len(gdf_focos) if gdf_focos is not None else 0
    ws_focos["A2"] = (
        f"Fonte Oficial: BDQueimadas / INPE | Período Avaliado: {periodo_str} | "
        f"Total de Ocorrências: {total_count} focos | Sistema Geodésico: SIRGAS 2000 (EPSG:4674)"
    )
    ws_focos["A2"].font = font_subtitulo
    ws_focos["A2"].alignment = align_left
    
    # Colunas de Dados
    headers = [
        "Nº", "Data/Hora (GMT)", "Data", "Hora (GMT)", "Latitude", "Longitude",
        "Satélite Detector", "FRP (MW)", "Município", "Bioma", "Status Operacional"
    ]
    
    row_header = 4
    for col_idx, h_text in enumerate(headers, start=1):
        cell = ws_focos.cell(row=row_header, column=col_idx, value=h_text)
        cell.font = font_header
        cell.fill = fill_header
        cell.alignment = align_center
        cell.border = border_thin
    
    ws_focos.row_dimensions[row_header].height = 24
    
    # Povoar Dados
    if gdf_focos is not None and not gdf_focos.empty:
        df_ord = gdf_focos.copy()
        if "data_hora_gmt" in df_ord.columns:
            df_ord["dt_sort"] = pd.to_datetime(df_ord["data_hora_gmt"], errors="coerce")
            df_ord = df_ord.sort_values(by="dt_sort", ascending=False)
            
        current_row = 5
        for idx, (_, row_data) in enumerate(df_ord.iterrows(), start=1):
            dh_raw = str(row_data.get("data_hora_gmt", ""))
            try:
                dt_obj = pd.to_datetime(dh_raw)
                data_str = dt_obj.strftime("%d/%m/%Y")
                hora_str = dt_obj.strftime("%H:%M")
                dh_full = dt_obj.strftime("%d/%m/%Y %H:%M")
            except Exception:
                data_str = dh_raw[:10] if len(dh_raw) >= 10 else dh_raw
                hora_str = dh_raw[11:16] if len(dh_raw) >= 16 else ""
                dh_full = dh_raw
                
            lat_val = row_data.geometry.y if hasattr(row_data, "geometry") and row_data.geometry else row_data.get("lat", 0.0)
            lon_val = row_data.geometry.x if hasattr(row_data, "geometry") and row_data.geometry else row_data.get("lon", 0.0)
            sat_val = str(row_data.get("satelite", "-"))
            
            frp_val = row_data.get("frp", None)
            try:
                frp_num = float(frp_val) if pd.notnull(frp_val) and float(frp_val) > 0 else None
            except Exception:
                frp_num = None
                
            muni_val = str(row_data.get("municipio", "-")).title()
            bioma_val = str(row_data.get("bioma", "Amazônia")).title()
            
            # Categoria
            cat_val = str(row_data.get("categoria", "Foco Pretérito"))
            is_ativo = "recente" in cat_val.lower() or "ativo" in cat_val.lower()
            
            row_vals = [
                idx,
                dh_full,
                data_str,
                hora_str,
                round(lat_val, 5),
                round(lon_val, 5),
                sat_val,
                round(frp_num, 1) if frp_num is not None else "-",
                muni_val,
                bioma_val,
                cat_val
            ]
            
            fill_row = fill_alerta if is_ativo else (fill_zebra_par if idx % 2 == 0 else fill_zebra_impar)
            
            for col_idx, val in enumerate(row_vals, start=1):
                cell = ws_focos.cell(row=current_row, column=col_idx, value=val)
                cell.font = font_data
                cell.fill = fill_row
                cell.border = border_thin
                
                # Alinhamento por tipo de dado
                if col_idx in [1, 3, 4, 7, 8, 10, 11]:
                    cell.alignment = align_center
                elif col_idx in [5, 6]:
                    cell.alignment = align_right
                    cell.number_format = "0.00000"
                else:
                    cell.alignment = align_left
                    
            ws_focos.row_dimensions[current_row].height = 19
            current_row += 1
            
        # Habilitar Auto-Filtro na tabela
        ws_focos.auto_filter.ref = f"A{row_header}:K{current_row - 1}"
    
    # Autoajuste de Largura das Colunas
    for col in ws_focos.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws_focos.column_dimensions[col_letter].width = max(max_len + 3, 11)
    
    ws_focos.column_dimensions["A"].width = 6
    ws_focos.column_dimensions["B"].width = 18
    ws_focos.column_dimensions["E"].width = 13
    ws_focos.column_dimensions["F"].width = 13
    ws_focos.column_dimensions["I"].width = 20
    ws_focos.column_dimensions["K"].width = 24
    
    # -------------------------------------------------------------
    # 2. ABA 2: Síntese Estatística por Município e Satélite
    # -------------------------------------------------------------
    if gdf_focos is not None and not gdf_focos.empty and "municipio" in gdf_focos.columns:
        ws_resumo = wb.create_sheet(title="Resumo_Municipios")
        ws_resumo.views.sheetView[0].showGridLines = True
        
        ws_resumo.merge_cells("A1:F1")
        ws_resumo["A1"] = f"SÍNTESE DE FOCOS POR MUNICÍPIO – {nome_uc.upper()}"
        ws_resumo["A1"].font = font_titulo
        ws_resumo["A1"].alignment = align_left
        
        headers_resumo = ["Município", "Qtd. Focos", "Representatividade (%)", "FRP Médio (MW)", "FRP Máximo (MW)", "Primeiro Registro", "Último Registro"]
        for col_idx, h_text in enumerate(headers_resumo, start=1):
            cell = ws_resumo.cell(row=3, column=col_idx, value=h_text)
            cell.font = font_header
            cell.fill = PatternFill(start_color="1E8449", end_color="1E8449", fill_type="solid") # Verde institucional
            cell.alignment = align_center
            cell.border = border_thin
            
        ws_resumo.row_dimensions[3].height = 22
        
        # Agrupamento com tratamento seguro de FRP
        df_group = gdf_focos.copy()
        df_group["municipio_clean"] = df_group["municipio"].astype(str).str.title()
        df_group["frp_num"] = pd.to_numeric(df_group.get("frp", None), errors="coerce")
        df_group["dt_parsed"] = pd.to_datetime(df_group.get("data_hora_gmt", None), errors="coerce")
        
        grp = df_group.groupby("municipio_clean").agg(
            qtd=("geometry", "count"),
            frp_mean=("frp_num", "mean"),
            frp_max=("frp_num", "max"),
            dt_min=("dt_parsed", "min"),
            dt_max=("dt_parsed", "max")
        ).reset_index().sort_values(by="qtd", ascending=False)
        
        tot_geral = len(df_group)
        r_idx = 4
        for _, g_row in grp.iterrows():
            m_pct = (g_row["qtd"] / tot_geral * 100.0) if tot_geral > 0 else 0.0
            frp_m = f"{g_row['frp_mean']:.1f}" if pd.notnull(g_row["frp_mean"]) else "-"
            frp_x = f"{g_row['frp_max']:.1f}" if pd.notnull(g_row["frp_max"]) else "-"
            d_min = g_row["dt_min"].strftime("%d/%m/%Y") if pd.notnull(g_row["dt_min"]) else "-"
            d_max = g_row["dt_max"].strftime("%d/%m/%Y") if pd.notnull(g_row["dt_max"]) else "-"
            
            vals_g = [
                g_row["municipio_clean"],
                g_row["qtd"],
                f"{m_pct:.1f}%",
                frp_m,
                frp_x,
                d_min,
                d_max
            ]
            
            fill_g = fill_zebra_par if (r_idx % 2 == 0) else fill_zebra_impar
            for col_idx, val in enumerate(vals_g, start=1):
                cell = ws_resumo.cell(row=r_idx, column=col_idx, value=val)
                cell.font = font_data
                cell.fill = fill_g
                cell.border = border_thin
                cell.alignment = align_left if col_idx == 1 else align_center
                
            ws_resumo.row_dimensions[r_idx].height = 19
            r_idx += 1
            
        # Linha Totalizadora
        cell_tot_lbl = ws_resumo.cell(row=r_idx, column=1, value="TOTAL GERAL")
        cell_tot_lbl.font = Font(name="Arial", size=9.5, bold=True, color="1B2631")
        cell_tot_lbl.fill = PatternFill(start_color="D5D8DC", end_color="D5D8DC", fill_type="solid")
        cell_tot_lbl.border = border_thin
        
        cell_tot_val = ws_resumo.cell(row=r_idx, column=2, value=tot_geral)
        cell_tot_val.font = Font(name="Arial", size=9.5, bold=True, color="1B2631")
        cell_tot_val.fill = PatternFill(start_color="D5D8DC", end_color="D5D8DC", fill_type="solid")
        cell_tot_val.alignment = align_center
        cell_tot_val.border = border_thin
        
        cell_tot_pct = ws_resumo.cell(row=r_idx, column=3, value="100.0%")
        cell_tot_pct.font = Font(name="Arial", size=9.5, bold=True, color="1B2631")
        cell_tot_pct.fill = PatternFill(start_color="D5D8DC", end_color="D5D8DC", fill_type="solid")
        cell_tot_pct.alignment = align_center
        cell_tot_pct.border = border_thin
        
        for c in range(4, 8):
            cell_blank = ws_resumo.cell(row=r_idx, column=c, value="")
            cell_blank.fill = PatternFill(start_color="D5D8DC", end_color="D5D8DC", fill_type="solid")
            cell_blank.border = border_thin
            
        ws_resumo.row_dimensions[r_idx].height = 20
        
        for col in ws_resumo.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            col_letter = get_column_letter(col[0].column)
            ws_resumo.column_dimensions[col_letter].width = max(max_len + 4, 15)
            
    wb.save(out_file)
    print(f"[OK] Planilha Excel estruturada de focos gerada com sucesso: {out_file}")
    return out_file
