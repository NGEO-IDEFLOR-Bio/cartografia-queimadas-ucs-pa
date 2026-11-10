"""
Módulo de Exportação Cartográfica em Formato Google Earth (KML)
==============================================================
Gera pacote espacial KML (.kml) estruturado e estilizado com simbologia
oficial para visualização imediata no Google Earth, Avenza Maps e GPS:
1. Pasta 'Focos de Calor': Pontos com marcadores diferenciados (ativos < 48h vs pretéritos)
   e balões descritivos completos (data/hora, satélite, FRP, coordenadas, município);
2. Pasta 'Limite da UC': Polígono/linha vetorial destacada em verde florestal institucional;
3. Pasta 'Limites Municipais': Contorno dos municípios interceptados para contexto tático.
"""

from pathlib import Path
from typing import Union, Optional
import xml.sax.saxutils as saxutils
import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon, MultiPolygon

from src.config import FILE_MUNICIPIOS, CRS_GEOGRAFICO, CRS_WGS84


def _escape_xml(text: str) -> str:
    """Escapa caracteres especiais para XML."""
    return saxutils.escape(str(text))


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


def export_focos_to_kml(
    gdf_focos: gpd.GeoDataFrame,
    gdf_uc: gpd.GeoDataFrame,
    nome_uc: str,
    output_path: Union[str, Path],
    metricas: Optional[dict] = None
) -> Path:
    """
    Gera o pacote espacial KML completo contendo os focos, o perímetro da UC
    e as divisas municipais de apoio à fiscalização e campo.
    
    Parameters
    ----------
    gdf_focos : gpd.GeoDataFrame
        GeoDataFrame com os focos na UC.
    gdf_uc : gpd.GeoDataFrame
        GeoDataFrame com a geometria da UC.
    nome_uc : str
        Nome da Unidade de Conservação.
    output_path : Union[str, Path]
        Caminho para o arquivo .kml.
    metricas : dict, optional
        Métricas temporais e de classificação.
        
    Returns
    -------
    Path
        Caminho do arquivo KML gerado.
    """
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Garantir CRS em WGS84 para exportação padrão do Google Earth
    focos_wgs = gdf_focos.to_crs(CRS_WGS84) if (gdf_focos is not None and not gdf_focos.empty and gdf_focos.crs != CRS_WGS84) else gdf_focos
    uc_wgs = gdf_uc.to_crs(CRS_WGS84) if (gdf_uc is not None and not gdf_uc.empty and gdf_uc.crs != CRS_WGS84) else gdf_uc
    
    total_focos = len(focos_wgs) if focos_wgs is not None else 0
    safe_name = _escape_xml(nome_uc)
    
    # Início do Documento KML com Paleta de Estilos Oficiais
    kml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<kml xmlns="http://www.opengis.net/kml/2.2">',
        '<Document>',
        f'  <name>Monitoramento de Queimadas – {safe_name}</name>',
        f'  <description>Núcleo de Geotecnologias (NGEO / IDEFLOR-Bio) - Focos de Calor e Contexto Espacial</description>',
        '  <open>1</open>',
        '',
        '  <!-- ESTILOS: Focos Ativos (< 48h) - Alerta Vermelho -->',
        '  <Style id="style_foco_recente">',
        '    <IconStyle>',
        '      <scale>1.15</scale>',
        '      <Icon>',
        '        <href>http://maps.google.com/mapfiles/kml/shapes/firedept.png</href>',
        '      </Icon>',
        '      <hotSpot x="0.5" y="0.5" xunits="fraction" yunits="fraction"/>',
        '    </IconStyle>',
        '    <LabelStyle><scale>0</scale></LabelStyle>',
        '  </Style>',
        '',
        '  <!-- ESTILOS: Focos Pretéritos no Período - Âmbar/Laranja -->',
        '  <Style id="style_foco_anterior">',
        '    <IconStyle>',
        '      <scale>0.90</scale>',
        '      <Icon>',
        '        <href>http://maps.google.com/mapfiles/kml/pushpin/ylw-pushpin.png</href>',
        '      </Icon>',
        '      <hotSpot x="20" y="2" xunits="pixels" yunits="pixels"/>',
        '    </IconStyle>',
        '    <LabelStyle><scale>0</scale></LabelStyle>',
        '  </Style>',
        '',
        '  <!-- ESTILO: Limite Oficial da UC (Linha Verde Florestal, Preenchimento Translúcido) -->',
        '  <Style id="style_uc_limite">',
        '    <LineStyle>',
        '      <color>ff49841e</color> <!-- Formato aabbggrr: Verde #1E8449 -->',
        '      <width>3.0</width>',
        '    </LineStyle>',
        '    <PolyStyle>',
        '      <color>2849841e</color> <!-- 16% de opacidade para não encobrir imagem de satélite -->',
        '      <fill>1</fill>',
        '      <outline>1</outline>',
        '    </PolyStyle>',
        '    <LabelStyle><scale>0</scale></LabelStyle>',
        '  </Style>',
        '',
        '  <!-- ESTILO: Limites Municipais (Linha Fina Cinza/Azulada) -->',
        '  <Style id="style_municipios">',
        '    <LineStyle>',
        '      <color>ff888888</color>',
        '      <width>1.2</width>',
        '    </LineStyle>',
        '    <PolyStyle>',
        '      <fill>0</fill>',
        '      <outline>1</outline>',
        '    </PolyStyle>',
        '    <LabelStyle><scale>0</scale></LabelStyle>',
        '  </Style>',
        '  </Style>',
        ''
    ]
    
    # -------------------------------------------------------------
    # 1. PASTA 1: FOCOS DE CALOR
    # -------------------------------------------------------------
    kml_lines.append(f'  <Folder>')
    kml_lines.append(f'    <name>1. Focos de Calor ({total_focos} ocorrências)</name>')
    kml_lines.append(f'    <open>1</open>')
    
    if focos_wgs is not None and not focos_wgs.empty:
        df_ord = focos_wgs.copy()
        if "data_hora_gmt" in df_ord.columns:
            df_ord["dt_sort"] = pd.to_datetime(df_ord["data_hora_gmt"], errors="coerce")
            df_ord = df_ord.sort_values(by="dt_sort", ascending=False)
            
        for idx, (_, row_f) in enumerate(df_ord.iterrows(), start=1):
            dh_raw = str(row_f.get("data_hora_gmt", ""))
            try:
                dt_obj = pd.to_datetime(dh_raw)
                dh_fmt = dt_obj.strftime("%d/%m/%Y %H:%M")
            except Exception:
                dh_fmt = dh_raw
                
            lat = row_f.geometry.y if hasattr(row_f, "geometry") and row_f.geometry else row_f.get("lat", 0.0)
            lon = row_f.geometry.x if hasattr(row_f, "geometry") and row_f.geometry else row_f.get("lon", 0.0)
            sat = str(row_f.get("satelite", "-"))
            muni = str(row_f.get("municipio", "-")).title()
            
            frp_raw = row_f.get("frp", None)
            try:
                frp_fmt = f"{float(frp_raw):.1f} MW" if pd.notnull(frp_raw) and float(frp_raw) > 0 else "N/D"
            except Exception:
                frp_fmt = "N/D"
                
            cat_val = str(row_f.get("categoria", "Foco Pretérito"))
            is_recente = "recente" in cat_val.lower() or "ativo" in cat_val.lower()
            style_id = "#style_foco_recente" if is_recente else "#style_foco_anterior"
            status_cor = "#C0392B" if is_recente else "#D35400"
            status_label = "Foco Ativo / Recente (&lt; 48h)" if is_recente else "Foco Pretérito no Período"
            
            p_name = _escape_xml(f"#{idx} | {sat} | {dh_fmt}")
            
            description_html = f"""
            <div style="font-family: Arial, sans-serif; font-size: 12px; color: #1B2631; min-width: 250px;">
              <h4 style="margin: 0 0 6px 0; color: #154360; border-bottom: 2px solid #2980B9; padding-bottom: 4px;">
                Foco de Calor #{idx} – {sat}
              </h4>
              <p style="margin: 0 0 8px 0; font-weight: bold; color: {status_cor};">{status_label}</p>
              <table style="width: 100%; border-collapse: collapse; font-size: 11px;">
                <tr style="background-color: #F2F4F4;">
                  <td style="padding: 4px 6px; font-weight: bold; border: 1px solid #D5D8DC;">Data/Hora (GMT):</td>
                  <td style="padding: 4px 6px; border: 1px solid #D5D8DC;">{_escape_xml(dh_fmt)}</td>
                </tr>
                <tr>
                  <td style="padding: 4px 6px; font-weight: bold; border: 1px solid #D5D8DC;">Satélite:</td>
                  <td style="padding: 4px 6px; border: 1px solid #D5D8DC;">{_escape_xml(sat)}</td>
                </tr>
                <tr style="background-color: #F2F4F4;">
                  <td style="padding: 4px 6px; font-weight: bold; border: 1px solid #D5D8DC;">Município:</td>
                  <td style="padding: 4px 6px; border: 1px solid #D5D8DC;">{_escape_xml(muni)}</td>
                </tr>
                <tr>
                  <td style="padding: 4px 6px; font-weight: bold; border: 1px solid #D5D8DC;">Latitude:</td>
                  <td style="padding: 4px 6px; border: 1px solid #D5D8DC;">{lat:.5f}°</td>
                </tr>
                <tr style="background-color: #F2F4F4;">
                  <td style="padding: 4px 6px; font-weight: bold; border: 1px solid #D5D8DC;">Longitude:</td>
                  <td style="padding: 4px 6px; border: 1px solid #D5D8DC;">{lon:.5f}°</td>
                </tr>
                <tr>
                  <td style="padding: 4px 6px; font-weight: bold; border: 1px solid #D5D8DC;">Potência (FRP):</td>
                  <td style="padding: 4px 6px; border: 1px solid #D5D8DC;">{_escape_xml(frp_fmt)}</td>
                </tr>
              </table>
              <p style="margin: 6px 0 0 0; font-size: 9.5px; color: #7F8C8D; font-style: italic;">
                Fonte: BDQueimadas/INPE | Datum: SIRGAS 2000
              </p>
            </div>
            """
            
            kml_lines.append(f'    <Placemark>')
            kml_lines.append(f'      <name>{p_name}</name>')
            kml_lines.append(f'      <styleUrl>{style_id}</styleUrl>')
            kml_lines.append(f'      <description><![CDATA[{description_html}]]></description>')
            kml_lines.append(f'      <Point>')
            kml_lines.append(f'        <coordinates>{lon:.6f},{lat:.6f},0</coordinates>')
            kml_lines.append(f'      </Point>')
            kml_lines.append(f'    </Placemark>')
            
    kml_lines.append(f'  </Folder>')
    
    # -------------------------------------------------------------
    # 2. PASTA 2: LIMITE OFICIAL DA UNIDADE DE CONSERVAÇÃO
    # -------------------------------------------------------------
    kml_lines.append(f'  <Folder>')
    kml_lines.append(f'    <name>2. Limite da UC – {safe_name}</name>')
    kml_lines.append(f'    <open>1</open>')
    
    if uc_wgs is not None and not uc_wgs.empty:
        for _, row_uc in uc_wgs.iterrows():
            geom_kml = _polygon_to_kml_coordinates(row_uc.geometry)
            if geom_kml:
                kml_lines.append(f'    <Placemark>')
                kml_lines.append(f'      <name>{safe_name}</name>')
                kml_lines.append(f'      <styleUrl>#style_uc_limite</styleUrl>')
                kml_lines.append(f'      {geom_kml}')
                kml_lines.append(f'    </Placemark>')
                
    kml_lines.append(f'  </Folder>')
    
    # -------------------------------------------------------------
    # 3. PASTA 3: LIMITES MUNICIPAIS INTERCEPTADOS
    # -------------------------------------------------------------
    kml_lines.append(f'  <Folder>')
    kml_lines.append(f'    <name>3. Divisas Municipais</name>')
    kml_lines.append(f'    <open>0</open>')
    
    if FILE_MUNICIPIOS.exists() and uc_wgs is not None and not uc_wgs.empty:
        try:
            gdf_muni = gpd.read_file(FILE_MUNICIPIOS)
            if gdf_muni.crs != CRS_WGS84:
                gdf_muni = gdf_muni.to_crs(CRS_WGS84)
                
            uc_union = uc_wgs.unary_union
            muni_intersect = gdf_muni[gdf_muni.intersects(uc_union)].copy()
            
            col_muni_nome = next((c for c in muni_intersect.columns if any(k in c.lower() for k in ["municipio", "nome"])), "MUNICÍPIO")
            
            for _, row_m in muni_intersect.iterrows():
                m_nome = _escape_xml(str(row_m.get(col_muni_nome, "Município")).title())
                geom_m_kml = _polygon_to_kml_coordinates(row_m.geometry)
                if geom_m_kml:
                    kml_lines.append(f'    <Placemark>')
                    kml_lines.append(f'      <name>{m_nome}</name>')
                    kml_lines.append(f'      <styleUrl>#style_municipios</styleUrl>')
                    kml_lines.append(f'      {geom_m_kml}')
                    kml_lines.append(f'    </Placemark>')
        except Exception as e:
            print(f"! Aviso: Não foi possível incluir municípios no KML ({e})")
            
    kml_lines.append(f'  </Folder>')
    
    # Fechamento do KML
    kml_lines.append('</Document>')
    kml_lines.append('</kml>')
    
    with open(out_file, "w", encoding="utf-8") as f:
        f.write("\n".join(kml_lines))
        
    print(f"[OK] Pacote espacial KML gerado com sucesso: {out_file}")
    return out_file
