"""
Módulo de Triagem Rápida e Alerta de Queimadas nas UCs Estaduais do Pará
========================================================================
Núcleo de Geotecnologias (NGEO / IDEFLOR-Bio)

Varre os dados oficiais do BDQueimadas/INPE para todo o Estado do Pará,
realiza a interseção espacial com as 29 Unidades de Conservação Estaduais
e gera um quadro tático de inteligência com:
1. Ranqueamento de emergência (Crítico, Alerta, Atenção, Normal);
2. Tabela consolidada com contagem, FRP máximo e municípios atingidos;
3. Planilha executiva em Excel (.xlsx) com auto-filtro e focos detalhados;
4. Pacote KML estadual para Google Earth com polígonos coloridos por alerta;
5. Lista de UCs prioritárias pronta para alimentar o gerador cartográfico.
"""

from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, Any, Tuple, Optional, List, Union
import xml.sax.saxutils as saxutils

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, Polygon, MultiPolygon

from src.config import (
    FILE_UCS_ESTADUAIS, FILE_MUNICIPIOS, RAW_DIR, OUTPUTS_DIR,
    CRS_GEOGRAFICO, CRS_WGS84,
    FOCOS_ANTERIORES_FILL, FOCOS_ANTERIORES_STROKE,
    FOCOS_RECENTES_FILL, FOCOS_RECENTES_STROKE
)
from src.bdqueimadas import fetch_bdqueimadas_inpe


def _escape_xml(text: str) -> str:
    """Escapa caracteres especiais para XML."""
    return saxutils.escape(str(text if text is not None else ""))


def _polygon_to_kml_coordinates(geom) -> str:
    """Converte polígono ou multipolígono Shapely para blocos KML de coordenadas."""
    if geom is None or geom.is_empty:
        return ""
        
    def _single_poly_kml(poly: Polygon) -> str:
        parts = []
        ext_coords = " ".join(f"{pt[0]:.6f},{pt[1]:.6f},0" for pt in poly.exterior.coords)
        parts.append(
            f"<outerBoundaryIs><LinearRing><tessellate>1</tessellate>"
            f"<coordinates>{ext_coords}</coordinates></LinearRing></outerBoundaryIs>"
        )
        for interior in poly.interiors:
            int_coords = " ".join(f"{pt[0]:.6f},{pt[1]:.6f},0" for pt in interior.coords)
            parts.append(
                f"<innerBoundaryIs><LinearRing><tessellate>1</tessellate>"
                f"<coordinates>{int_coords}</coordinates></LinearRing></innerBoundaryIs>"
            )
        return f"<Polygon><tessellate>1</tessellate>{''.join(parts)}</Polygon>"

    if isinstance(geom, Polygon):
        return _single_poly_kml(geom)
    elif isinstance(geom, MultiPolygon):
        polys_str = "".join(_single_poly_kml(p) for p in geom.geoms)
        return f"<MultiGeometry>{polys_str}</MultiGeometry>"
    return ""


def classificar_alerta(total_focos: int) -> Tuple[str, str, str]:
    """
    Retorna o nível de alerta, badge e cor correspondente com base no total de focos.
    
    Returns
    -------
    Tuple[str, str, str]
        (nivel_texto, badge_emoji, cor_hex)
    """
    if total_focos >= 100:
        return "CRÍTICO", "🔴 CRÍTICO", "#D32F2F"
    elif total_focos >= 10:
        return "ALERTA", "🟠 ALERTA", "#F57C00"
    elif total_focos >= 1:
        return "ATENÇÃO", "🟡 ATENÇÃO", "#FBC02D"
    else:
        return "NORMAL", "🟢 NORMAL", "#388E3C"


def exportar_planilha_triagem(
    df_ranking: pd.DataFrame,
    gdf_focos_ucs: gpd.GeoDataFrame,
    output_path: Union[str, Path],
    periodo_str: str
) -> Path:
    """
    Exporta a planilha executiva de triagem em formato Excel (.xlsx).
    """
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    
    with pd.ExcelWriter(out_file, engine="openpyxl") as writer:
        # Aba 1: Resumo Executivo das UCs
        cols_resumo = [
            "Alerta", "Unidade de Conservação", "Categoria", "Grupo",
            "Total Focos", "Focos Recentes (< 48h)", "Focos Anteriores",
            "FRP Máximo (MW)", "FRP Médio (MW)", "Municípios Atingidos",
            "Última Detecção"
        ]
        df_export_resumo = df_ranking[[c for c in cols_resumo if c in df_ranking.columns]].copy()
        df_export_resumo.to_excel(writer, sheet_name="Resumo UCs", index=False)
        
        # Aba 2: Focos Detalhados em UCs
        if gdf_focos_ucs is not None and not gdf_focos_ucs.empty:
            cols_focos = [
                "id", "data_hora_gmt", "satelite", "Nome", "municipio",
                "lat", "lon", "frp", "bioma", "status_foco"
            ]
            df_export_focos = gdf_focos_ucs[[c for c in cols_focos if c in gdf_focos_ucs.columns]].copy()
            df_export_focos.rename(columns={"Nome": "Unidade de Conservação"}, inplace=True)
            df_export_focos.to_excel(writer, sheet_name="Focos Detalhados", index=False)
            
        # Formatação básica de colunas
        wb = writer.book
        for ws in wb.worksheets:
            ws.views.sheetView[0].showGridLines = True
            for col in ws.columns:
                max_len = max(len(str(cell.value or '')) for cell in col)
                col_letter = col[0].column_letter
                ws.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 45)
                
    return out_file


def exportar_kml_triagem(
    gdf_ucs_ranking: gpd.GeoDataFrame,
    gdf_focos_ucs: gpd.GeoDataFrame,
    output_path: Union[str, Path],
    periodo_str: str
) -> Path:
    """
    Exporta o mapa de triagem do Pará em formato KML com as 29 UCs estilizadas por severidade.
    """
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    
    ucs_wgs = gdf_ucs_ranking.to_crs(CRS_WGS84) if gdf_ucs_ranking.crs != CRS_WGS84 else gdf_ucs_ranking
    focos_wgs = gdf_focos_ucs.to_crs(CRS_WGS84) if (gdf_focos_ucs is not None and not gdf_focos_ucs.empty and gdf_focos_ucs.crs != CRS_WGS84) else gdf_focos_ucs
    
    kml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<kml xmlns="http://www.opengis.net/kml/2.2">',
        '<Document>',
        f'  <name>Triagem Geral de Focos em UCs – {periodo_str}</name>',
        f'  <description>Núcleo de Geotecnologias (NGEO / IDEFLOR-Bio) - Monitoramento de Focos de Calor</description>',
        '',
        '  <!-- Estilos por Nível de Alerta das UCs -->',
        '  <!-- Cores em KML: aabbggrr (Alpha, Blue, Green, Red) -->',
        '  <Style id="uc_critico">',
        '    <LineStyle><color>ff191180</color><width>2.5</width></LineStyle>',
        '    <PolyStyle><color>401911d3</color><fill>1</fill><outline>1</outline></PolyStyle>',
        '  </Style>',
        '  <Style id="uc_alerta">',
        '    <LineStyle><color>ff0055d8</color><width>2.2</width></LineStyle>',
        '    <PolyStyle><color>40007cf5</color><fill>1</fill><outline>1</outline></PolyStyle>',
        '  </Style>',
        '  <Style id="uc_atencao">',
        '    <LineStyle><color>ff15b3b3</color><width>2.0</width></LineStyle>',
        '    <PolyStyle><color>402dc0fb</color><fill>1</fill><outline>1</outline></PolyStyle>',
        '  </Style>',
        '  <Style id="uc_normal">',
        '    <LineStyle><color>ff208038</color><width>1.5</width></LineStyle>',
        '    <PolyStyle><color>20208038</color><fill>1</fill><outline>1</outline></PolyStyle>',
        '  </Style>',
        '',
        '  <!-- Estilos de Focos -->',
        '  <Style id="foco_recente">',
        '    <IconStyle>',
        '      <scale>0.9</scale>',
        '      <Icon><href>http://maps.google.com/mapfiles/kml/shapes/firedept.png</href></Icon>',
        '      <color>ff1911db</color>',
        '    </IconStyle>',
        '  </Style>',
        '  <Style id="foco_anterior">',
        '    <IconStyle>',
        '      <scale>0.7</scale>',
        '      <Icon><href>http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png</href></Icon>',
        '      <color>ff39fffa</color>',
        '    </IconStyle>',
        '  </Style>',
        ''
    ]
    
    # Pasta 1: Status das 29 UCs Estaduais
    kml_lines.append('  <Folder>')
    kml_lines.append('    <name>1. Status das 29 UCs Estaduais</name>')
    kml_lines.append('    <open>1</open>')
    
    for _, row in ucs_wgs.iterrows():
        nome_uc = _escape_xml(row.get("Nome", "UC"))
        alerta = row.get("nivel_alerta", "NORMAL")
        badge = row.get("Alerta", alerta)
        tot = int(row.get("Total Focos", 0))
        rec = int(row.get("Focos Recentes (< 48h)", 0))
        ant = int(row.get("Focos Anteriores", 0))
        frp_max = row.get("FRP Máximo (MW)", 0.0)
        mun = _escape_xml(row.get("Municípios Atingidos", "Nenhum"))
        cat = _escape_xml(row.get("Categoria", "UC Estadual"))
        
        style_map = {
            "CRÍTICO": "#uc_critico",
            "ALERTA": "#uc_alerta",
            "ATENÇÃO": "#uc_atencao",
            "NORMAL": "#uc_normal"
        }
        style_url = style_map.get(alerta, "#uc_normal")
        
        geom_kml = _polygon_to_kml_coordinates(row.geometry)
        if not geom_kml:
            continue
            
        balloon_html = (
            f"<h3>{badge} - {nome_uc}</h3>"
            f"<table border='1' cellpadding='4' cellspacing='0' style='font-family:Arial; font-size:12px; border-collapse:collapse;'>"
            f"<tr><td bgcolor='#f2f2f2'><b>Categoria:</b></td><td>{cat}</td></tr>"
            f"<tr><td bgcolor='#f2f2f2'><b>Total de Focos:</b></td><td><b>{tot}</b></td></tr>"
            f"<tr><td bgcolor='#f2f2f2'><b>Focos Ativos (&lt; 48h):</b></td><td><font color='red'><b>{rec}</b></font></td></tr>"
            f"<tr><td bgcolor='#f2f2f2'><b>Focos Anteriores:</b></td><td>{ant}</td></tr>"
            f"<tr><td bgcolor='#f2f2f2'><b>FRP Máximo:</b></td><td>{frp_max:.1f} MW</td></tr>"
            f"<tr><td bgcolor='#f2f2f2'><b>Municípios:</b></td><td>{mun}</td></tr>"
            f"</table>"
        )
        
        kml_lines.extend([
            '    <Placemark>',
            f'      <name>[{tot} focos] {nome_uc}</name>',
            f'      <styleUrl>{style_url}</styleUrl>',
            f'      <description><![CDATA[{balloon_html}]]></description>',
            f'      {geom_kml}',
            '    </Placemark>'
        ])
        
    kml_lines.append('  </Folder>')
    
    # Pasta 2: Focos Ativos (< 48h)
    if focos_wgs is not None and not focos_wgs.empty:
        focos_rec = focos_wgs[focos_wgs["status_foco"] == "Recente (< 48h)"]
        focos_ant = focos_wgs[focos_wgs["status_foco"] != "Recente (< 48h)"]
        
        kml_lines.append('  <Folder>')
        kml_lines.append(f'    <name>2. Focos Recentes (&lt; 48h) [{len(focos_rec)}]</name>')
        for _, row in focos_rec.iterrows():
            pt = row.geometry
            if not isinstance(pt, Point):
                continue
            dh = _escape_xml(row.get("data_hora_gmt", ""))
            sat = _escape_xml(row.get("satelite", ""))
            frp = float(row.get("frp", 0.0) or 0.0)
            uc_pt = _escape_xml(row.get("Nome", ""))
            mun_pt = _escape_xml(row.get("municipio", ""))
            
            kml_lines.extend([
                '    <Placemark>',
                f'      <name>Fogo Ativo ({sat} - {dh})</name>',
                '      <styleUrl>#foco_recente</styleUrl>',
                f'      <description><![CDATA[<b>UC:</b> {uc_pt}<br/><b>Município:</b> {mun_pt}<br/><b>Satélite:</b> {sat}<br/><b>Data/Hora (GMT):</b> {dh}<br/><b>FRP:</b> {frp:.1f} MW]]></description>',
                f'      <Point><coordinates>{pt.x:.6f},{pt.y:.6f},0</coordinates></Point>',
                '    </Placemark>'
            ])
        kml_lines.append('  </Folder>')
        
        kml_lines.append('  <Folder>')
        kml_lines.append(f'    <name>3. Focos Anteriores [{len(focos_ant)}]</name>')
        for _, row in focos_ant.iterrows():
            pt = row.geometry
            if not isinstance(pt, Point):
                continue
            dh = _escape_xml(row.get("data_hora_gmt", ""))
            sat = _escape_xml(row.get("satelite", ""))
            frp = float(row.get("frp", 0.0) or 0.0)
            uc_pt = _escape_xml(row.get("Nome", ""))
            mun_pt = _escape_xml(row.get("municipio", ""))
            
            kml_lines.extend([
                '    <Placemark>',
                f'      <name>Foco Pretérito ({sat} - {dh})</name>',
                '      <styleUrl>#foco_anterior</styleUrl>',
                f'      <description><![CDATA[<b>UC:</b> {uc_pt}<br/><b>Município:</b> {mun_pt}<br/><b>Satélite:</b> {sat}<br/><b>Data/Hora (GMT):</b> {dh}<br/><b>FRP:</b> {frp:.1f} MW]]></description>',
                f'      <Point><coordinates>{pt.x:.6f},{pt.y:.6f},0</coordinates></Point>',
                '    </Placemark>'
            ])
        kml_lines.append('  </Folder>')
        
    kml_lines.extend([
        '</Document>',
        '</kml>'
    ])
    
    with open(out_file, "w", encoding="utf-8") as f:
        f.write("\n".join(kml_lines))
        
    return out_file


def gerar_mapa_interativo_folium(
    gdf_ucs_ranking: gpd.GeoDataFrame,
    gdf_focos_ucs: Optional[gpd.GeoDataFrame] = None,
    output_html: Optional[Union[str, Path]] = None
):
    """
    Gera mapa interativo Folium para visualização das 29 UCs e dos focos de calor.
    """
    try:
        import folium
        from folium.plugins import MarkerCluster
    except ImportError:
        print("[!] Folium não instalado. Pulando geração do mapa HTML interativo.")
        return None

    # Assegurar WGS84 para renderização web
    ucs_wgs = gdf_ucs_ranking.to_crs(CRS_WGS84) if gdf_ucs_ranking.crs != CRS_WGS84 else gdf_ucs_ranking
    
    # Criar Mapa Base centrado no Pará
    m = folium.Map(
        location=[-3.7, -52.4],
        zoom_start=6,
        tiles="CartoDB positron",
        control_scale=True
    )
    
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Imagery",
        name="Satélite (Esri World Imagery)"
    ).add_to(m)
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(m)

    # Função de estilo dos polígonos das UCs
    def style_uc(feature):
        props = feature["properties"]
        alerta = props.get("nivel_alerta", "NORMAL")
        cores = {
            "CRÍTICO": "#D32F2F",
            "ALERTA": "#F57C00",
            "ATENÇÃO": "#FBC02D",
            "NORMAL": "#2E7D32"
        }
        cor = cores.get(alerta, "#2E7D32")
        opac = 0.45 if alerta in ["CRÍTICO", "ALERTA"] else 0.20
        return {
            "fillColor": cor,
            "color": cor,
            "weight": 2.2 if alerta == "CRÍTICO" else 1.5,
            "fillOpacity": opac
        }

    # Adicionar camada vetorial das 29 UCs
    ucs_geojson = folium.GeoJson(
        ucs_wgs,
        name="Status das 29 UCs Estaduais",
        style_function=style_uc,
        tooltip=folium.GeoJsonTooltip(
            fields=["Nome", "Alerta", "Total Focos", "Focos Recentes (< 48h)", "FRP Máximo (MW)"],
            aliases=["UC:", "Status:", "Total Focos:", "Ativos (< 48h):", "FRP Máx (MW):"],
            localize=True
        ),
        popup=folium.GeoJsonPopup(
            fields=["Nome", "Categoria", "Alerta", "Total Focos", "Focos Recentes (< 48h)", "FRP Máximo (MW)", "Municípios Atingidos"],
            aliases=["UC", "Categoria", "Alerta", "Total de Focos", "Focos Ativos (< 48h)", "FRP Máx (MW)", "Municípios"],
            labels=True
        )
    ).add_to(m)

    # Adicionar Focos de Calor se existirem
    if gdf_focos_ucs is not None and not gdf_focos_ucs.empty:
        focos_wgs = gdf_focos_ucs.to_crs(CRS_WGS84) if gdf_focos_ucs.crs != CRS_WGS84 else gdf_focos_ucs
        
        # Grupo de Focos Recentes (< 48h)
        focos_rec = focos_wgs[focos_wgs["status_foco"] == "Recente (< 48h)"]
        if not focos_rec.empty:
            cluster_rec = MarkerCluster(name=f"Focos Recentes (&lt; 48h) [{len(focos_rec)}]")
            for _, row in focos_rec.iterrows():
                pt = row.geometry
                if not isinstance(pt, Point):
                    continue
                dh = row.get("data_hora_gmt", "")
                sat = row.get("satelite", "")
                frp = float(row.get("frp", 0.0) or 0.0)
                uc_pt = row.get("Nome", "")
                mun_pt = row.get("municipio", "")
                
                popup_txt = f"<b>Fogo Ativo (&lt; 48h)</b><br/><b>UC:</b> {uc_pt}<br/><b>Mun:</b> {mun_pt}<br/><b>Sat:</b> {sat}<br/><b>Data/Hora:</b> {dh}<br/><b>FRP:</b> {frp:.1f} MW"
                folium.CircleMarker(
                    location=[pt.y, pt.x],
                    radius=5,
                    color="#801119",
                    weight=1.5,
                    fill=True,
                    fill_color="#DB1E2A",
                    fill_opacity=0.9,
                    popup=folium.Popup(popup_txt, max_width=300)
                ).add_to(cluster_rec)
            cluster_rec.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)

    if output_html:
        out_html_path = Path(output_html)
        out_html_path.parent.mkdir(parents=True, exist_ok=True)
        m.save(str(out_html_path))
        print(f"[+] Mapa interativo Folium salvo: {out_html_path.name}")

    return m


def executar_triagem_focos_ucs(
    dias: int = 2,
    data_inicio: Optional[str] = None,
    data_fim: Optional[str] = None,
    out_dir: Union[str, Path] = "outputs/triagem"
) -> Dict[str, Any]:
    """
    Executa a triagem rápida de focos de queimada em todas as 29 UCs Estaduais do Pará.
    
    Parameters
    ----------
    dias : int, default 2
        Janela de análise em dias retroativos a partir de hoje (se data_inicio não informada).
    data_inicio : str, optional
        Data inicial explícita 'AAAA-MM-DD'.
    data_fim : str, optional
        Data final explícita 'AAAA-MM-DD'.
    out_dir : Union[str, Path]
        Diretório para salvar os entregáveis da triagem.
        
    Returns
    -------
    Dict[str, Any]
        Dicionário com tabela de ranking, caminhos dos arquivos e lista de UCs críticas.
    """
    # 1. Definição do Período
    hoje = date.today()
    if not data_fim:
        data_fim = hoje.strftime("%Y-%m-%d")
    if not data_inicio:
        dt_start = hoje - timedelta(days=dias)
        data_inicio = dt_start.strftime("%Y-%m-%d")
        
    periodo_str = f"{data_inicio}_a_{data_fim}"
    print(f"\n" + "=" * 70)
    print(f" 🔥 TRIAGEM DE FOCOS DE QUEIMADA - 29 UCS ESTADUAIS DO PARÁ")
    print(f" 📅 Período analisado: {data_inicio} até {data_fim}")
    print("=" * 70)
    
    # 2. Carregar Camada Oficial das 29 UCs
    if not FILE_UCS_ESTADUAIS.exists():
        raise FileNotFoundError(f"Arquivo oficial das UCs não encontrado: {FILE_UCS_ESTADUAIS}")
        
    gdf_ucs = gpd.read_file(FILE_UCS_ESTADUAIS)
    col_nome_uc = [c for c in gdf_ucs.columns if c.lower() == "nome"][0]
    gdf_ucs.rename(columns={col_nome_uc: "Nome"}, inplace=True)
    
    # Assegurar CRS SIRGAS 2000
    if gdf_ucs.crs != CRS_GEOGRAFICO:
        gdf_ucs = gdf_ucs.to_crs(CRS_GEOGRAFICO)
        
    print(f"[*] Base de UCs carregada: {len(gdf_ucs)} Unidades de Conservação Estaduais.")
    
    # 3. Baixar Focos do Pará via BDQueimadas/INPE
    gdf_focos_pa = fetch_bdqueimadas_inpe(data_inicio, data_fim)
    
    gdf_focos_ucs = gpd.GeoDataFrame()
    stats_dict = {}
    
    if gdf_focos_pa is not None and not gdf_focos_pa.empty:
        # Garantir CRS SIRGAS 2000
        if gdf_focos_pa.crs != CRS_GEOGRAFICO:
            gdf_focos_pa = gdf_focos_pa.to_crs(CRS_GEOGRAFICO)
            
        print(f"[*] Focos totais no Estado do Pará no período: {len(gdf_focos_pa):,}")
        
        # 4. Interseção Espacial (Spatial Join)
        gdf_join = gpd.sjoin(
            gdf_focos_pa,
            gdf_ucs[["Nome", "Categoria", "Grupo", "geometry"]],
            how="inner",
            predicate="intersects"
        )
        
        if not gdf_join.empty:
            # Classificação temporal (recente < 48h vs pretérito)
            # Definir ponto de corte
            now = datetime.now()
            cutoff_48h = now - timedelta(hours=48)
            
            def _calc_status(row):
                dh_str = str(row.get("data_hora_gmt", ""))
                try:
                    dh = datetime.strptime(dh_str[:19], "%Y-%m-%d %H:%M:%S")
                    if dh >= cutoff_48h:
                        return "Recente (< 48h)"
                    return "Pretérito"
                except Exception:
                    return "Pretérito"
                    
            gdf_join["status_foco"] = gdf_join.apply(_calc_status, axis=1)
            gdf_focos_ucs = gdf_join.copy()
            
            # Agrupar estatísticas por UC
            for nome_uc, grp in gdf_join.groupby("Nome"):
                tot = len(grp)
                rec = len(grp[grp["status_foco"] == "Recente (< 48h)"])
                ant = tot - rec
                frp_max = float(grp["frp"].max()) if "frp" in grp.columns and pd.notna(grp["frp"].max()) else 0.0
                frp_med = float(grp["frp"].mean()) if "frp" in grp.columns and pd.notna(grp["frp"].mean()) else 0.0
                
                muns = sorted([m for m in grp["municipio"].dropna().unique() if str(m).strip()]) if "municipio" in grp.columns else []
                muns_str = ", ".join(muns) if muns else "Não identificado"
                
                sats = sorted([s for s in grp["satelite"].dropna().unique() if str(s).strip()]) if "satelite" in grp.columns else []
                sats_str = ", ".join(sats) if sats else "N/D"
                
                ult_det = str(grp["data_hora_gmt"].max()) if "data_hora_gmt" in grp.columns else "N/D"
                
                stats_dict[nome_uc] = {
                    "Total Focos": tot,
                    "Focos Recentes (< 48h)": rec,
                    "Focos Anteriores": ant,
                    "FRP Máximo (MW)": round(frp_max, 1),
                    "FRP Médio (MW)": round(frp_med, 1),
                    "Municípios Atingidos": muns_str,
                    "Satélites": sats_str,
                    "Última Detecção": ult_det
                }
    else:
        print("[!] Nenhum foco do BDQueimadas registrado para o Pará no período.")
        
    # 5. Consolidar com todas as 29 UCs
    linhas_ranking = []
    for _, uc_row in gdf_ucs.iterrows():
        nome_uc = uc_row["Nome"]
        st = stats_dict.get(nome_uc, {
            "Total Focos": 0,
            "Focos Recentes (< 48h)": 0,
            "Focos Anteriores": 0,
            "FRP Máximo (MW)": 0.0,
            "FRP Médio (MW)": 0.0,
            "Municípios Atingidos": "Nenhum",
            "Satélites": "-",
            "Última Detecção": "-"
        })
        
        tot = st["Total Focos"]
        alerta_txt, badge_txt, cor_hex = classificar_alerta(tot)
        
        linha = {
            "Alerta": badge_txt,
            "nivel_alerta": alerta_txt,
            "cor_alerta": cor_hex,
            "Unidade de Conservação": nome_uc,
            "Nome": nome_uc,
            "Categoria": uc_row.get("Categoria", "UC Estadual"),
            "Grupo": uc_row.get("Grupo", "N/D"),
            **st
        }
        linhas_ranking.append(linha)
        
    df_ranking = pd.DataFrame(linhas_ranking)
    
    # Ordenação por prioridade: Total de Focos decrescente, FRP Máximo decrescente
    ordem_alerta = {"CRÍTICO": 1, "ALERTA": 2, "ATENÇÃO": 3, "NORMAL": 4}
    df_ranking["prioridade"] = df_ranking["nivel_alerta"].map(ordem_alerta)
    df_ranking.sort_values(by=["prioridade", "Total Focos", "FRP Máximo (MW)"], ascending=[True, False, False], inplace=True)
    df_ranking.drop(columns=["prioridade"], inplace=True)
    df_ranking.reset_index(drop=True, inplace=True)
    
    # 6. Unir com Geometrias para Exportações
    gdf_ucs_ranking = gdf_ucs.merge(df_ranking, on="Nome", how="left")
    
    # 7. Criar Diretório de Saída
    out_dir_path = Path(out_dir)
    out_dir_path.mkdir(parents=True, exist_ok=True)
    
    # 8. Exportar Planilha Excel (.xlsx)
    xlsx_path = out_dir_path / f"triagem_focos_ucs_{periodo_str}.xlsx"
    exportar_planilha_triagem(df_ranking, gdf_focos_ucs, xlsx_path, periodo_str)
    print(f"[+] Planilha de triagem gerada: {xlsx_path.name}")
    
    # 9. Exportar KML Estadual (.kml)
    kml_path = out_dir_path / f"triagem_focos_ucs_{periodo_str}.kml"
    exportar_kml_triagem(gdf_ucs_ranking, gdf_focos_ucs, kml_path, periodo_str)
    print(f"[+] KML de triagem gerado: {kml_path.name}")
    
    # 10. Gerar Mapa Interativo HTML (Folium)
    html_path = out_dir_path / f"triagem_focos_ucs_{periodo_str}.html"
    mapa_folium = gerar_mapa_interativo_folium(gdf_ucs_ranking, gdf_focos_ucs, html_path)
    
    # 11. Resumo Executivo no Terminal / Notebook
    ucs_com_focos = df_ranking[df_ranking["Total Focos"] > 0]
    total_focos_ucs = int(df_ranking["Total Focos"].sum())
    
    print("\n" + "-" * 70)
    print(f" 📊 SÍNTESE DO MONITORAMENTO DE QUEIMADAS NAS UCS")
    print(f" • Total de Focos em UCs Estaduais: {total_focos_ucs:,}")
    print(f" • UCs com Incidência de Fogo: {len(ucs_com_focos)} de {len(df_ranking)}")
    print(f" • UCs em Nível CRÍTICO (>= 100): {len(df_ranking[df_ranking['nivel_alerta'] == 'CRÍTICO'])}")
    print(f" • UCs em Nível ALERTA (10-99): {len(df_ranking[df_ranking['nivel_alerta'] == 'ALERTA'])}")
    print(f" • UCs em Nível ATENÇÃO (1-9): {len(df_ranking[df_ranking['nivel_alerta'] == 'ATENÇÃO'])}")
    print("-" * 70)
    
    if not ucs_com_focos.empty:
        print("\n🏆 UCs PRIORITÁRIAS PARA GERAÇÃO DE RELATÓRIO E PRANCHAS CARTOGRÁFICAS:")
        for idx, row in ucs_com_focos.iterrows():
            print(f"  {row['Alerta']} | {row['Unidade de Conservação']} -> {row['Total Focos']} focos (Ativos: {row['Focos Recentes (< 48h)']}) | FRP Máx: {row['FRP Máximo (MW)']} MW")
    else:
        print("\n✅ Nenhuma Unidade de Conservação Estadual apresentou focos no período analisado.")
        
    lista_ucs_prioritarias = ucs_com_focos["Unidade de Conservação"].tolist()
    
    return {
        "periodo": (data_inicio, data_fim),
        "total_focos_pa": len(gdf_focos_pa) if gdf_focos_pa is not None else 0,
        "total_focos_ucs": total_focos_ucs,
        "ucs_com_focos": lista_ucs_prioritarias,
        "df_ranking": df_ranking,
        "gdf_focos_ucs": gdf_focos_ucs,
        "gdf_ucs_ranking": gdf_ucs_ranking,
        "planilha_path": xlsx_path,
        "kml_path": kml_path,
        "html_path": html_path,
        "mapa_folium": mapa_folium
    }
