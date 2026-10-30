# Diretrizes de Projeto: Cartografia de Focos de Queimadas e Severidade em UCs do Pará

## 1. Visão Geral e Objetivo
Desenvolver um pipeline automatizado, modular e reprodutível para monitoramento, detecção e cartografia institucional de **focos de calor e incêndio (BDQueimadas/INPE)** e **análise de cicatrizes e severidade (Sentinel-2 Harmonized / GEE)** em Unidades de Conservação (UCs) sob gestão do **IDEFLOR-Bio** no Estado do Pará.

O projeto unifica o padrão cartográfico de pranchas A4 Paisagem ($297 \times 210\text{ mm}$) com hierarquia de 3 mapas do repositório `qgis-layout-engine` com a arquitetura modular e orquestração em Google Colab estruturada em `cartografia-alertas-deter-pa`.

---

## 2. Padrão de Integração e Arquitetura

O projeto adota uma estrita separação entre a **biblioteca lógica de produção (`src/`)** e o **ambiente de execução do usuário (Google Colab em `notebooks/colab_runner.ipynb`)**:

```text
cartografia-queimadas-ucs-pa/
├── data/
│   ├── raw/                 # Dados brutos de focos baixados (BDQueimadas/INPE, FIRMS)
│   └── processed/           # Camadas oficiais de referência (UCs, Estado PA, Municípios, Brasil)
├── assets/
│   └── img/                 # Logomarcas oficiais (Brasão PA, IDEFLOR-Bio, NGEO)
├── src/
│   ├── __init__.py
│   ├── config.py            # CRS, cores hexadecimais, parâmetros de bandas S2 e layout mm
│   ├── gee_pipeline.py      # Autenticação GEE, Sentinel-2 Harmonized, máscaras e cálculo NBR
│   ├── bdqueimadas.py       # Ingestão de focos, filtro espacial por UC e classificação temporal
│   ├── layout_engine.py     # Motor cartográfico A4 Paisagem (297x210 mm) em Python puro
│   └── exporter.py          # Renderização e exportação das 3 variantes (Falsa Cor, RGB, NBR)
├── notebooks/
│   └── colab_runner.ipynb   # Notebook orquestrador enxuto para execução no Google Colab
├── outputs/                 # Pranchas geradas em PNG (300 DPI) e PDF vetorial
├── layout_elements.json     # Especificação paramétrica dos elementos milimétricos
├── requirements.txt         # Dependências Python para execução local e no Colab
├── diretriz.md              # Este documento de diretrizes técnicas
└── README.md                # Apresentação do repositório e guia operacional
```

### Regras de Separação de Papéis
* **Módulos Python (`/src`):** Devem conter exclusivamente funções parametrizadas, desacopladas e testáveis. Nenhum caminho de arquivo absoluto (*hardcoded*) é permitido. Todos os caminhos derivam do diretório raiz do projeto.
* **Notebook Colab (`notebooks/colab_runner.ipynb`):** Atua unicamente como orquestrador. Responsável por:
  1. Instalação e verificação de dependências (`earthengine-api`, `geopandas`, `rasterio`, etc.).
  2. Autenticação interativa nativa do Google Earth Engine (`ee.Authenticate()` e `ee.Initialize()`).
  3. Parametrização via formulário (UC alvo, período da análise, projeto GEE).
  4. Execução do pipeline chamando `src.exporter.gerar_todas_as_pranchas(...)`.
  5. Exibição das pré-visualizações na célula e persistência em `outputs/` ou Google Drive.

---

## 3. Convenções Cartográficas e Simbologia Obrigatória

### 3.1. Simbologia dos Focos de Queimada (BDQueimadas)
A representação espacial dos focos segue a tipologia de triângulos (`▲`):
* **Focos dos dias anteriores:**
  - Preenchimento (Fill): `#FAFF39` (Amarelo brilhante)
  - Contorno (Stroke/Edge): `#B35C15` (Bronze queimado)
  - Linewidth: `1.2 pt`, Tamanho: `65 pt`
* **Dia atual da análise ou última observação:**
  - Preenchimento (Fill): `#DB1E2A` (Vermelho alerta intenso)
  - Contorno (Stroke/Edge): `#801119` (Bordô escuro)
  - Linewidth: `1.5 pt`, Tamanho: `85 pt`

### 3.2. Mosaicos de Basemap Sentinel-2 (GEE)
Os basemaps orbitais são derivados da coleção `COPERNICUS/S2_SR_HARMONIZED` aplicando a função de limpeza padronizada:
* **Filtros de Máscara:**
  - `SCL` (Scene Classification Layer): classes 4 (Vegetação), 5 (Solo exposto) e 6 (Água).
  - `QA60`: bits 10 (nuvens opacas) e 11 (cirrus) iguais a 0.
  - `B2` (Banda Azul): refletância $< 2000$ (elimina saturação/brilho excessivo).
  - Normalização: divisão por `10000.0`.
* **Composição Temporal:** Mediana da coleção no período especificado.
* **Cálculo da Extensão Visível:** O mosaico é recortado com base no **envelope retangular exato da área visível do mapa principal** (com margem de segurança de $5\%$), garantindo preenchimento de $100\%$ do quadro cartográfico sem margens vazias.
* **Variantes de Mapa Geradas (3 versões):**
  1. **Falsa Cor (Realce Queimadas):** Bandas `['B12', 'B8', 'B4']`, `min: 0.05`, `max: 0.40`, `gamma: 1.1`. Destaca cicatrizes de queima em tons avermelhados/cobre e vegetação saudável em tons verdes.
  2. **Cor Natural (RGB):** Bandas `['B4', 'B3', 'B2']`, `min: 0.02`, `max: 0.20`, `gamma: 1.2`. Visão fidedigna do relevo e cobertura vegetal.
  3. **NBR (Normalized Burn Ratio):** $\frac{\text{B8} - \text{B12}}{\text{B8} + \text{B12}}$, `min: -0.20`, `max: 0.50`, paleta: `['black', 'red', 'orange', 'yellow', 'white']`. Evidencia o grau de severidade e queima recente.

---

## 4. Hierarquia Cartográfica em Folha A4 Paisagem

O layout obedece à especificação milimétrica oficial do NGEO/IDEFLOR-Bio:

1. **Mapa Principal de Detalhe ($155 \times 124\text{ mm}$ - Esquerda):**
   - Enquadramento da UC com $100\%$ de cobertura do mosaico Sentinel-2.
   - Camada de focos com a simbologia bicolor de triângulos.
   - Grade uniforme com supressão de rótulos em quinas ($< 3{,}5\%$ da borda).
   - Eixo Y com coordenadas no sentido vertical ascendente ($90^\circ$).
   - Spines/molduras com `zorder=100` para garantir sobreposição nítida sobre o raster.

2. **Mapa Intermediário ($102 \times 75\text{ mm}$ - Superior Direito):**
   - Limite integral da UC em verde florestal com contexto municipal e hidrográfico.
   - Localização das queimadas na escala da unidade.
   - Grade uniforme simétrica ($0{,}10^\circ$).

3. **Mapa Macro ($102 \times 75\text{ mm}$ - Inferior Direito):**
   - Estado do Pará em destaque (#D5F5E3 / #1E8449) sobre o contexto do Brasil e América do Sul.
   - Posição geográfica da UC com marcador e halo circular.
   - Grade uniforme simétrica ($4{,}0^\circ$).

4. **Painéis Institucionais e Técnicos:**
   - Faixa de Título no topo ($y = 5{,}411$ a $17{,}713\text{ mm}$) com tipografia Segoe UI / Arial Black.
   - Caixa de Legenda contendo convenções de focos (dia atual vs anteriores) e limites.
   - Caixa de Metadados: Datum SIRGAS 2000 (EPSG:4674), satélites sensores e autoria NGEO.
   - Bloco de Escala gráfica calculada, Seta Norte vetorial e Logos (NGEO, IDEFLOR-Bio e Pará).

---

## 5. Instruções Operacionais para Agentes de Código / IA

1. **Autenticação GEE Resiliente:** Sempre suporte a inicialização via `ee.Initialize(project=...)` com fallback para `ee.Authenticate()`.
2. **Sistema de Coordenadas:** Todos os cálculos de distância, escalas e buffers devem ser processados em projeção métrica (SIRGAS 2000 / Policonica `EPSG:5880` ou UTM correspondente à zona da UC) antes da renderização geográfica (`EPSG:4674`).
3. **Resolução de Saída:** As pranchas exportadas devem ter rigorosamente $300\text{ DPI}$ em formato raster (PNG) e suporte a exportação vetorial limpa em PDF.
