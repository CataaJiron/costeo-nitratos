import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import anthropic
from pathlib import Path
import datetime

st.set_page_config(page_title="Costeo Nitratos 2026", layout="wide")

MESES = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']
COLORES = ['#7F77DD','#1D9E75','#D85A30','#BA7517','#185FA5','#D4537E','#888780','#639922','#E8A838']

COSTOS = [
    ('1.1 TRANSPORTE DE SALES',           'TRANSPORTE DE SALES',                    'Tpte Sales'),
    ('1.2 Operación Pozas (NV+CS+PV+PB)', 'Operación Pozas (NV+CS+PV+PB)',          'Op. Pozas'),
    ('1.3 CRISTALIZACION',                'Total Cristalización (NPT II/IV/NPT III)','Cristalización'),
    ('1.4 KCl',                           'KCl',                                    'KCl'),
    ('1.5 Terminado+Tpte Interm',         'Terminado+Tpte Interm',                  'Terminados + Tpte interm'),
    ('1.6 Transporte y Puerto',           'Transporte y Puerto',                    'Tpte + Puerto'),
    ('1.7 Perdidas F/E',                  'Perdidas F/E',                           'Pérdidas FE'),
    ('1.8 Distributivos + Depreciación',  'Distributivos + Depreciación',           'Distributivos'),
    ('1.9 OTROS',                         'OTROS',                                  'Otros'),
]
NOMBRES = [c[2] for c in COSTOS]

# ── HELPERS ────────────────────────────────────────────────────────────────────
def cargar_api_key():
    p = Path("C:/CosteoNitratos/api_key.txt")
    return p.read_text().strip() if p.exists() else None

@st.cache_data
def cargar_datos(archivo):
    df = pd.read_excel(archivo, sheet_name='Tabla_maestra')
    df.columns = [c.strip() for c in df.columns]
    def fix(v):
        if isinstance(v, datetime.datetime): return datetime.datetime(v.year, v.month, 1)
        if isinstance(v, datetime.time): return datetime.datetime(2026, 1, 1)
        return v
    df['Fecha'] = df['Fecha'].apply(fix)
    df['GASTO/COSTO'] = pd.to_numeric(df['GASTO/COSTO'], errors='coerce')
    for c in ['AREA','SUBAREA','CONCEPTO','Medida','Tipo','Tipo_2']:
        df[c] = df[c].astype(str).str.strip()
    return df

def gv(df, area, subarea, concepto, mes, tipo='Puntual', tipo2='PPTO', medida=None):
    fechas = sorted(df['Fecha'].unique())
    if mes >= len(fechas): return 0
    mask = (
        (df['Fecha'] == fechas[mes]) &
        (df['AREA'] == area) &
        (df['SUBAREA'] == subarea) &
        (df['CONCEPTO'] == concepto) &
        (df['Tipo'] == tipo) &
        (df['Tipo_2'] == tipo2)
    )
    if medida: mask = mask & (df['Medida'] == medida)
    r = df[mask]
    return r['GASTO/COSTO'].values[0] if not r.empty else 0

def gs(df, area, subarea, concepto, tipo='Puntual', tipo2='PPTO', medida=None):
    return [gv(df, area, subarea, concepto, i, tipo, tipo2, medida) for i in range(12)]

def total_serie(df, tipo='Puntual', tipo2='PPTO'):
    return [sum(gv(df, 'COSTO TOTAL', sa, c, i, tipo, tipo2) for sa, c, _ in COSTOS) for i in range(12)]

def real_proy(tipo2_mes):
    """Returns REAL for early months, PROY for later — combined as 'real+proy'"""
    return tipo2_mes  # handled per month in real_proy_val

def rp_val(df, area, subarea, concepto, mes, tipo='Puntual', medida=None):
    """Get Real+Proy value: REAL if exists, else PROY"""
    v = gv(df, area, subarea, concepto, mes, tipo, 'REAL', medida)
    if v != 0: return v
    return gv(df, area, subarea, concepto, mes, tipo, 'PROY', medida)

def rp_serie(df, area, subarea, concepto, tipo='Puntual', medida=None):
    return [rp_val(df, area, subarea, concepto, i, tipo, medida) for i in range(12)]

def total_rp_serie(df, tipo='Puntual'):
    return [sum(rp_val(df, 'COSTO TOTAL', sa, c, i, tipo) for sa, c, _ in COSTOS) for i in range(12)]

def botones_mes(key):
    if f'm_{key}' not in st.session_state: st.session_state[f'm_{key}'] = 0
    cols = st.columns(12)
    for i, (col, mes) in enumerate(zip(cols, MESES)):
        with col:
            if st.button(mes, key=f'{key}_{i}',
                         type='primary' if i == st.session_state[f'm_{key}'] else 'secondary',
                         use_container_width=True):
                st.session_state[f'm_{key}'] = i
                st.rerun()
    return st.session_state[f'm_{key}']

def kpis_row(df, mes, tipo):
    ppto_s = total_serie(df, tipo, 'PPTO')
    rp_s   = total_rp_serie(df, tipo)

    ppto_m    = ppto_s[mes]
    rp_m      = rp_s[mes]

    # Acumulado del mes seleccionado
    ppto_acum_s = total_serie(df, 'Acumulado', 'PPTO')
    rp_acum_s   = total_rp_serie(df, 'Acumulado')
    ppto_acum = ppto_acum_s[mes]
    rp_acum   = rp_acum_s[mes]

    # Acumulado diciembre — siempre fijo en mes 11, ignora filtros
    ppto_dic = total_serie(df, 'Acumulado', 'PPTO')[11]
    rp_dic   = total_rp_serie(df, 'Acumulado')[11]

    k1, k2, k3, k4 = st.columns(4)
    k1.metric(f"PPTO {MESES[mes]} ({tipo})", f"${ppto_m:.1f}/T",
              delta=f"Real/Proy: ${rp_m:.1f}/T  ({rp_m-ppto_m:+.1f})", delta_color="inverse")
    k2.metric(f"Acumulado Ene-{MESES[mes]} PPTO", f"${ppto_acum:.1f}/T",
              delta=f"R+P: ${rp_acum:.1f}/T  ({rp_acum-ppto_acum:+.1f})", delta_color="inverse")
    k3.metric("Acumulado Ene-Dic PPTO", f"${ppto_dic:.1f}/T",
              delta=f"R+P: ${rp_dic:.1f}/T  ({rp_dic-ppto_dic:+.1f})", delta_color="inverse")

# ── SIDEBAR ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("Costeo Nitratos 2026")
    st.divider()
    archivo = st.file_uploader("Cargar Planilla costeo 2026.xlsx", type=["xlsx"])
    st.divider()
    pagina = st.radio("", ["Dashboard", "Analisis mensual", "Sensibilidad"],
                      label_visibility="collapsed")

if not archivo:
    st.info("Carga el archivo Planilla costeo 2026.xlsx desde el panel izquierdo.")
    st.stop()

df = cargar_datos(archivo)


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
if pagina == "Dashboard":
    st.title("Dashboard — Costo Total 2026")

    col_v, _ = st.columns([2,6])
    with col_v:
        modo = st.radio("Vista", ["Puntual","Acumulado"], horizontal=True, label_visibility="collapsed")
    tipo = "Puntual" if modo == "Puntual" else "Acumulado"

    mes = botones_mes("dash")
    st.divider()
    kpis_row(df, mes, tipo)
    st.divider()

    # Grafico PPTO vs Real+Proy — barras agrupadas con delta encima
    ppto_s = total_serie(df, tipo, 'PPTO')
    rp_s   = total_rp_serie(df, tipo)

    deltas = [rp - ppto for rp, ppto in zip(rp_s, ppto_s)]

    fig = go.Figure()

    fig.add_trace(go.Bar(
        name="PPTO",
        x=MESES, y=ppto_s,
        marker_color='#152578',
        text=[f"${v:.0f}" for v in ppto_s],
        textposition="outside",
        textfont_size=10,
    ))

    fig.add_trace(go.Bar(
        name="Real + Proyección",
        x=MESES, y=rp_s,
        marker_color='#80BC00',
        text=[f"${v:.0f}" for v in rp_s],
        textposition="outside",
        textfont_size=10,
    ))

    # Anotaciones de delta encima de cada par de barras
    annotations = []
    for i, (mes_label, delta) in enumerate(zip(MESES, deltas)):
        color  = "#D83030" if delta > 0 else "#80BC00"
        symbol = "▲" if delta > 0 else "▼"
        annotations.append(dict(
            x=mes_label,
            y=max(ppto_s[i], rp_s[i]) * 1.13,  # un poco arriba de la barra más alta
            text=f"{symbol} {delta:+.1f}",
            showarrow=False,
            font=dict(size=11, color=color, family="Arial Black"),
            xanchor="center",
        ))

    fig.update_layout(
        barmode="group",
        title=f"PPTO vs Real + Proyección — {modo} US$/T",
        height=400,
        legend=dict(orientation="h", y=1.12),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=60, b=20),
        annotations=annotations,
    )
    fig.update_yaxes(gridcolor="#f0f0f0")
    st.plotly_chart(fig, use_container_width=True)

    # Barras apiladas composición
    st.subheader("Composición del costo")
    col_tab1, col_tab2 = st.columns(2)

    with col_tab1:
        st.caption("PPTO")
        fig2 = go.Figure()
        totales_ppto = [0] * len(MESES)
        for (sa, c, nombre), color in zip(COSTOS, COLORES):
            s = gs(df, 'COSTO TOTAL', sa, c, tipo, 'PPTO')
            totales_ppto = [t + v for t, v in zip(totales_ppto, s)]
            fig2.add_trace(go.Bar(name=nombre, x=MESES, y=s, marker_color=color))

        fig2.update_layout(
            barmode="stack", height=320,
            legend=dict(orientation="h", y=-0.35, font_size=10),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(t=30, b=10),
            annotations=[dict(
                x=mes, y=total * 1.02,
                text=f"${total:.0f}",
                showarrow=False,
                font=dict(size=10, color="white"),
                xanchor="center", yanchor="bottom"
            ) for mes, total in zip(MESES, totales_ppto)]
        )
        fig2.update_yaxes(gridcolor="#f0f0f0")
        st.plotly_chart(fig2, use_container_width=True)

    with col_tab2:
        st.caption("Real + Proyección")
        fig3 = go.Figure()
        totales_rp = [0] * len(MESES)
        for (sa, c, nombre), color in zip(COSTOS, COLORES):
            s = rp_serie(df, 'COSTO TOTAL', sa, c, tipo)
            totales_rp = [t + v for t, v in zip(totales_rp, s)]
            fig3.add_trace(go.Bar(name=nombre, x=MESES, y=s, marker_color=color))

        fig3.update_layout(
            barmode="stack", height=320,
            legend=dict(orientation="h", y=-0.35, font_size=10),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(t=30, b=10),
            annotations=[dict(
                x=mes, y=total * 1.02,
                text=f"${total:.0f}",
                showarrow=False,
                font=dict(size=10, color="white"),
                xanchor="center", yanchor="bottom"
            ) for mes, total in zip(MESES, totales_rp)]
        )
        fig3.update_yaxes(gridcolor="#f0f0f0")
        st.plotly_chart(fig3, use_container_width=True)
# ══════════════════════════════════════════════════════════════════════════════
# ANALISIS MENSUAL
# ══════════════════════════════════════════════════════════════════════════════
elif pagina == "Analisis mensual":
    st.title("Análisis mensual")

    col_v, _ = st.columns([2,6])
    with col_v:
        modo = st.radio("Vista", ["Puntual","Acumulado"], horizontal=True, label_visibility="collapsed")
    tipo = "Puntual" if modo == "Puntual" else "Acumulado"

    mes = botones_mes("anal")
    st.divider()
    kpis_row(df, mes, tipo)
    st.divider()

    # Barras PPTO vs Real+Proy por componente para el mes seleccionado
    st.subheader(f"PPTO vs Real+Proyección por componente — {MESES[mes]}")
    vals_ppto = [gv(df, 'COSTO TOTAL', sa, c, mes, tipo, 'PPTO') for sa, c, _ in COSTOS]
    vals_rp   = [rp_val(df, 'COSTO TOTAL', sa, c, mes, tipo) for sa, c, _ in COSTOS]

    deltas = [rp - ppto for rp, ppto in zip(vals_rp, vals_ppto)]

    fig4 = go.Figure()
    fig4.add_trace(go.Bar(name="PPTO", x=NOMBRES, y=vals_ppto, marker_color='#152578',
                          text=[f"${v:.1f}" for v in vals_ppto], textposition="outside", textfont_size=10))
    fig4.add_trace(go.Bar(name="Real+Proy", x=NOMBRES, y=vals_rp,
                          marker_color=['#80BC00' if r <= p else '#D83030' for r, p in zip(vals_rp, vals_ppto)],
                          text=[f"${v:.1f}" for v in vals_rp], textposition="outside", textfont_size=10))

    # Delta encima de cada par de barras
    annotations = []
    for i, (nombre, delta) in enumerate(zip(NOMBRES, deltas)):
        color  = "#D85A30" if delta > 0 else "#2ECC71"
        symbol = "▲" if delta > 0 else "▼"
        annotations.append(dict(
            x=nombre,
            y=max(vals_ppto[i], vals_rp[i]) * 1.15,
            text=f"{symbol} {delta:+.1f}",
            showarrow=False,
            font=dict(size=11, color=color, family="Arial Black"),
            xanchor="center",
        ))

    fig4.update_layout(
        barmode="group", height=380, xaxis_tickangle=-20,
        legend=dict(orientation="h", y=1.1),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=50, b=60),
        annotations=annotations,
    )
    fig4.update_yaxes(gridcolor="#f0f0f0")
    st.plotly_chart(fig4, use_container_width=True)

    # Evolución anual componente seleccionado
    st.subheader("Evolución anual por componente")
    comp_idx = st.selectbox("Componente:", range(len(NOMBRES)), format_func=lambda i: NOMBRES[i])
    sa, c, nombre = COSTOS[comp_idx]
    s_ppto = gs(df, 'COSTO TOTAL', sa, c, tipo, 'PPTO')
    s_rp   = rp_serie(df, 'COSTO TOTAL', sa, c, tipo)

    deltas = [rp - ppto for rp, ppto in zip(s_rp, s_ppto)]

    fig5 = go.Figure()

    # Barras agrupadas PPTO vs Real+Proy
    fig5.add_trace(go.Bar(
        name="PPTO", x=MESES, y=s_ppto,
        marker_color='#152578',
        text=[f"${v:.1f}" for v in s_ppto],
        textposition="outside", textfont_size=10,
    ))
    fig5.add_trace(go.Bar(
        name="Real+Proy", x=MESES, y=s_rp,
        marker_color=['#80BC00' if r <= p else '#D83030' for r, p in zip(s_rp, s_ppto)],
        text=[f"${v:.1f}" for v in s_rp],
        textposition="outside", textfont_size=10,
    ))

    # Delta encima de cada par
    annotations = []
    for i, (mes_label, delta) in enumerate(zip(MESES, deltas)):
        color  = "#D85A30" if delta > 0 else "#2ECC71"
        symbol = "▲" if delta > 0 else "▼"
        annotations.append(dict(
            x=mes_label,
            y=max(s_ppto[i], s_rp[i]) * 1.15,
            text=f"{symbol} {delta:+.1f}",
            showarrow=False,
            font=dict(size=11, color=color, family="Arial Black"),
            xanchor="center",
        ))

    fig5.update_layout(
        barmode="group",
        title=f"{nombre} — {modo}", height=380,
        legend=dict(orientation="h", y=1.1),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=50, b=20),
        annotations=annotations,
    )
    fig5.update_yaxes(gridcolor="#f0f0f0")
    st.plotly_chart(fig5, use_container_width=True)

    # Tabla comparativa anual
    st.subheader("Comparativa anual — todos los componentes")
    rows = []
    for sa, c, nombre in COSTOS:
        s_p = gs(df, 'COSTO TOTAL', sa, c, tipo, 'PPTO')
        s_r = rp_serie(df, 'COSTO TOTAL', sa, c, tipo)
        row = {"Componente": nombre, "Tipo": "PPTO"}
        for i, m in enumerate(MESES): row[m] = round(s_p[i], 1)
        row["Acum Dic"] = round(sum(s_p) / 12, 1)
        rows.append(row)
        row2 = {"Componente": nombre, "Tipo": "R+P"}
        for i, m in enumerate(MESES): row2[m] = round(s_r[i], 1)
        row2["Acum Dic"] = round(sum(s_r) / 12, 1)
        rows.append(row2)

    # Total rows
    for tipo2, label, fn in [('PPTO','TOTAL PPTO', lambda sa,c,i: gv(df,'COSTO TOTAL',sa,c,i,tipo,'PPTO')),
                              ('RP',  'TOTAL R+P',  lambda sa,c,i: rp_val(df,'COSTO TOTAL',sa,c,i,tipo))]:
        row_t = {"Componente": label, "Tipo": ""}
        for i, m in enumerate(MESES):
            row_t[m] = round(sum(fn(sa,c,i) for sa,c,_ in COSTOS), 1)
        row_t["Acum Dic"] = round(sum(row_t[m] for m in MESES) / 12, 1)
        rows.append(row_t)

    df_tabla = pd.DataFrame(rows)

    # Columnas numéricas
    cols_num = MESES + ["Acum Dic"]

    def highlight(row):
        styles = [''] * len(row)
        if row['Tipo'] == 'R+P':
            for i, col in enumerate(df_tabla.columns):
                if col in MESES or col == 'Acum Dic':
                    try:
                        ppto_row = df_tabla[(df_tabla['Componente']==row['Componente']) & (df_tabla['Tipo']=='PPTO')]
                        if not ppto_row.empty:
                            ppto_val = ppto_row[col].values[0]
                            if isinstance(row[col], float) and row[col] > ppto_val:
                                styles[i] = 'color: red'
                            elif isinstance(row[col], float) and row[col] < ppto_val:
                                styles[i] = 'color: green'
                    except: pass
        return styles

    st.dataframe(
        df_tabla.style
            .apply(highlight, axis=1)
            .format({col: "{:.1f}" for col in cols_num}),
        use_container_width=True, hide_index=True, height=500
    )

# ══════════════════════════════════════════════════════════════════════════════
# SENSIBILIDAD — Simulador de insumos mes puntual
# ══════════════════════════════════════════════════════════════════════════════
elif pagina == "Sensibilidad":
    import copy
 
    st.title("Simulador de Sensibilidad — Costo Total US$/T")
 
    mes = botones_mes("sens")
    st.divider()
 
    fechas_sorted = sorted(df['Fecha'].unique())
    if mes >= len(fechas_sorted):
        st.warning("Mes fuera de rango.")
        st.stop()
    fecha = fechas_sorted[mes]
 
    # ── helper de lectura ────────────────────────────────────────────────────
    def _r(area, subarea, concepto, medida=None, nth=0):
        """Lee valor PPTO Puntual del mes seleccionado."""
        mask = (
            (df['Fecha']    == fecha) &
            (df['AREA']     == area)  &
            (df['SUBAREA']  == subarea) &
            (df['CONCEPTO'] == concepto) &
            (df['Tipo']     == 'Puntual') &
            (df['Tipo_2']   == 'PPTO')
        )
        if medida:
            mask = mask & (df['Medida'] == medida)
        r = df[mask]['GASTO/COSTO']
        if r.empty:
            return 0.0
        return float(r.values[nth]) if len(r) > nth else 0.0
 
    def _area_val(area):
        """Lee valor para áreas sin subarea/concepto (ej. Distributivos Nitratos)."""
        mask = (
            (df['Fecha']   == fecha) &
            (df['AREA']    == area)  &
            (df['Tipo']    == 'Puntual') &
            (df['Tipo_2']  == 'PPTO')
        )
        r = df[mask]['GASTO/COSTO']
        return float(r.values[0]) if not r.empty else 0.0
 
    # ── Leer valores PPTO base ───────────────────────────────────────────────
    BASE = {
        # --- Producción NPT3 ---
        'KNO3_T_NPT3':   _r('PRODUCCION','NPT3','- KNO3 T NPT III'),
        'KNO3_R_NPT3':   _r('PRODUCCION','NPT3','- KNO3 R NPT III'),
        # --- Producción NPT4 ---
        'KNO3_L_NPT4':   _r('PRODUCCION','NPT4','- KNO3 L NPT II/IV'),
        'CSSI_NPT4':     _r('PRODUCCION','NPT4','- CSSI NPT II/IV'),
        'CSSR_NPT4':     _r('PRODUCCION','NPT4','- CSSR NPT II/IV'),
        # --- Producción Terminados ---
        'PRIL_DTP':      _r('PRODUCCION','TERMINADOS','PRILADO + DTP'),
        'SECADO':        _r('PRODUCCION','TERMINADOS','SECADO'),
        # --- Gastos Pozas (KUS) ---
        'G_POZAS_NV':    _r('GASTO','Operación Pozas (NV+CS+PV+PB)','Gasto Operación Pozas NV'),
        'G_POZAS_CS':    _r('GASTO','Operación Pozas (NV+CS+PV+PB)','Gasto Operación Pozas CS'),
        'G_POZAS_PB':    _r('GASTO','Operación Pozas (NV+CS+PV+PB)','Gasto Operación Pozas PB'),
        # --- Gastos Plantas (KUS) ---
        'G_PRIL':        _r('GASTO','TERMINADOS','Gasto Planta Prilado CS'),
        'G_DTP':         _r('GASTO','TERMINADOS','Gasto Planta DTP'),
        'G_SECADO':      _r('GASTO','TERMINADOS','Gasto Planta Secado KNO3'),
        'G_NPT3':        _r('GASTO','CRISTALIZACION','Gasto NPT III + Korda'),
        'G_NPT4':        _r('GASTO','CRISTALIZACION','Gasto NPT IV'),
        # --- Gastos Puerto (KUS / US$/T según tabla) ---
        'G_EMBARQUE_KUS':  _r('Embarque Granel Trimestral','EMBARQUE','Embarque Granel + Demurrage','KUS'),
        'TON_EMBARQUE':    _r('Embarque Granel Trimestral','EMBARQUE','Embarque Granel + Demurrage','Kton', nth=0),
        'G_ALMACENAJE_KUS':_r('Almacenaje Trimestral','ALMACENAJE','Almacenaje Trimestral','KUS'),
        'TON_ALMACENAJE':  _r('Almacenaje Trimestral','ALMACENAJE','Almacenaje Trimestral','Kton'),
        'G_DIST_T_KUS':    _r('Distributivos Trimestral','DISTRIBUTIVOS','Distributivos Trimestral','KUS'),
        'TON_DIST_T':      _r('Distributivos Trimestral','DISTRIBUTIVOS','Despacho Camiones y contenedores','Kton'),
        # --- Transporte camiones (US$/T) ---
        'TPTE_CAM_USDPT': _r('Tpte Camiones Terminados','TRANSPORTE','Tpte Camiones Terminados','US$/T'),
        # --- FC KCl (factor consumo, adimensional) ---
        'FC_MOP90_NPT3':  _r('KCl','Fc KCl NPT3','MOP 90', nth=0),
        'FC_MOP70_NPT3':  _r('KCl','CONSUMO NPT3','MOP 70', nth=0),
        'FC_SS_NPT3':     _r('KCl','CONSUMO NPT3','SS', nth=0),
        'FC_MOP90_NPT4':  _r('KCl','Fc KCl NPT4','MOP 90', nth=0),
        'FC_MOP70_NPT4':  _r('KCl','Fc KCl NPT4','MOP 70', nth=0),
        'FC_SS_NPT4':     _r('KCl','CONSUMO NPT4','SS', nth=0) if _r('KCl','CONSUMO NPT4','SS', nth=0) else 0.0,
        # --- Precio KCl (US$/T) ---
        'P_MOP90':        _r('KCl','Costo Promedio KCl','MOP 90'),
        'P_MOP70':        _r('KCl','Costo Promedio KCl','MOP 70'),
        'P_SS':           _r('KCl','Costo Promedio KCl','SS'),
        # --- FC NaNO3 (sales) ---
        'FC_SALES':       _r('TRANSPORTE DE SALES','- Factor Consumo de Sales','- Factor Consumo de Sales'),
        'P_TPTE_SALES':   _r('TRANSPORTE DE SALES','Total Transporte de Sales (promedio)','Total Transporte de Sales (promedio)'),
        # --- Depreciaciones fijas (no editables) ---
        'DEPR_POZAS_CS':  _r('GASTO','Operación Pozas (NV+CS+PV+PB)','Depreciación Pozas CS'),
        'DEPR_PRIL':      _r('GASTO','TERMINADOS','Depreciación Planta Prilado CS'),
        'DEPR_DTP':       _r('GASTO','TERMINADOS','Depreciación Planta DTP'),
        'DEPR_SECADO':    _r('GASTO','TERMINADOS','Depreciación Planta Secado KNO3'),
        'DEPR_NPT3':      _r('GASTO','CRISTALIZACION','Depreciación NPT III'),
        'DEPR_NPT4':      _r('GASTO','CRISTALIZACION','Depreciación NPT IV'),
        'DEPR_PUERTO':    _r('DEPRECIACION','PUERTO','Depreciacion Puerto','US$/T'),
        'G_TPTE_INT':     _r('GASTO','TERMINADOS','Gasto Transporte Intermedios '),
        'DIST_NITRATOS':  _area_val('Distributivos Nitratos'),
        'DEPR_COM':       _area_val('Depreciación Costo Comun'),
        # --- Perdidas FE fijas ---
        'PERD_FE':        _r('Perdidas F/E','Perdidas F/E','Perdidas F/E'),
        'PERD_PUERTO':    _r('- Perdidas y FE (Puerto/Cancha)',
                             '- Perdidas y FE (Puerto/Cancha)',
                             '- Perdidas y FE (Puerto/Cancha)'),
        # --- OTROS ---
        'OTROS':          gv(df,'COSTO TOTAL','1.9 OTROS','OTROS', mes,'Puntual','PPTO'),
    }
 
    # ── Función de recálculo ─────────────────────────────────────────────────
    def recalcular(v):
        # Producción
        npt3  = v['KNO3_T_NPT3'] + v['KNO3_R_NPT3']
        npt4  = v['KNO3_L_NPT4'] + v['CSSI_NPT4'] + v['CSSR_NPT4']
        prod_total = npt3 + npt4
        prod_term  = v['PRIL_DTP'] + v['SECADO']
 
        # 1.1 Tpte Sales
        c11 = v['P_TPTE_SALES'] * v['FC_SALES']
 
        # 1.2 Pozas
        gasto_pozas = v['G_POZAS_NV'] + v['G_POZAS_CS'] + v['G_POZAS_PB'] + v['DEPR_POZAS_CS']
        c12 = gasto_pozas / prod_total if prod_total > 0 else 0.0
 
        # 1.3 Cristalización
        gasto_crist = v['G_NPT3'] + v['G_NPT4'] + v['DEPR_NPT3'] + v['DEPR_NPT4']
        c13 = gasto_crist / prod_total if prod_total > 0 else 0.0
 
        # 1.4 KCl
        cons_mop90 = v['FC_MOP90_NPT3']*npt3 + v['FC_MOP90_NPT4']*npt4
        cons_mop70 = v['FC_MOP70_NPT3']*npt3 + v['FC_MOP70_NPT4']*npt4
        cons_ss    = v['FC_SS_NPT3']*npt3    + v['FC_SS_NPT4']*npt4
        cons_total = cons_mop90 + cons_mop70 + cons_ss
        costo_prom_kcl = (
            v['P_MOP90']*cons_mop90 + v['P_MOP70']*cons_mop70 + v['P_SS']*cons_ss
        ) / cons_total if cons_total > 0 else 0.0
        fc_kcl_total = cons_total / prod_total if prod_total > 0 else 0.0
        c14 = fc_kcl_total * costo_prom_kcl
 
        # 1.5 Terminados
        gasto_term = (v['G_PRIL'] + v['G_DTP'] + v['G_SECADO'] + v['G_TPTE_INT']
                      + v['DEPR_PRIL'] + v['DEPR_DTP'] + v['DEPR_SECADO'])
        c15 = gasto_term / prod_term if prod_term > 0 else 0.0
 
        # 1.6 Tpte + Puerto
        emb_usdT  = v['G_EMBARQUE_KUS']  / v['TON_EMBARQUE']   if v['TON_EMBARQUE']  > 0 else 0.0
        alm_usdT  = v['G_ALMACENAJE_KUS']/ v['TON_ALMACENAJE'] if v['TON_ALMACENAJE']> 0 else 0.0
        # Distributivos trimestral: volumen total = embarque + despacho camiones
        vol_dist  = v['TON_EMBARQUE'] + v['TON_DIST_T']
        dist_usdT = v['G_DIST_T_KUS'] / vol_dist if vol_dist > 0 else 0.0
        c16 = v['TPTE_CAM_USDPT'] + emb_usdT + alm_usdT + dist_usdT + v['DEPR_PUERTO']
 
        # 1.7 Perdidas FE (fijas)
        c17 = v['PERD_FE'] + v['PERD_PUERTO']
 
        # 1.8 Distributivos + Depreciación
        c18 = (v['DIST_NITRATOS'] + v['DEPR_COM']) / prod_total if prod_total > 0 else 0.0
 
        # 1.9 Otros
        c19 = v['OTROS']
 
        componentes = {
            '1.1 Tpte Sales':   c11,
            '1.2 Op. Pozas':    c12,
            '1.3 Cristalización': c13,
            '1.4 KCl':          c14,
            '1.5 Terminados':   c15,
            '1.6 Tpte+Puerto':  c16,
            '1.7 Pérdidas F/E': c17,
            '1.8 Distributivos':c18,
            '1.9 Otros':        c19,
        }
        total = sum(componentes.values())
        return total, componentes
 
    # ── Inicializar session_state con valores base ───────────────────────────
    if 'sens_vals' not in st.session_state or st.session_state.get('sens_mes') != mes:
        st.session_state['sens_vals'] = copy.deepcopy(BASE)
        st.session_state['sens_mes']  = mes
 
    V = st.session_state['sens_vals']
 
    # ── Layout: inputs izquierda | resultado derecha ─────────────────────────
    col_inp, col_res = st.columns([3, 2], gap="large")
 
    with col_inp:
        # ── PRODUCCIÓN ──────────────────────────────────────────────────────
        st.markdown("#### 🏭 Producción (Kton)")
        c1, c2 = st.columns(2)
        with c1:
            st.caption("NPT3")
            V['KNO3_T_NPT3'] = st.number_input("T NPT3",   value=float(f"{V['KNO3_T_NPT3']:.3f}"), step=0.1, format="%.3f", key="p_t3")
            V['KNO3_R_NPT3'] = st.number_input("R NPT3",   value=float(f"{V['KNO3_R_NPT3']:.3f}"), step=0.1, format="%.3f", key="p_r3")
            npt3_calc = V['KNO3_T_NPT3'] + V['KNO3_R_NPT3']
            st.metric("TOTAL NPT3", f"{npt3_calc:.3f} Kton")
        with c2:
            st.caption("NPT4")
            V['KNO3_L_NPT4'] = st.number_input("L NPT4",   value=float(f"{V['KNO3_L_NPT4']:.3f}"), step=0.1, format="%.3f", key="p_l4")
            V['CSSI_NPT4']   = st.number_input("CSSI NPT4",value=float(f"{V['CSSI_NPT4']:.3f}"),   step=0.1, format="%.3f", key="p_cssi")
            V['CSSR_NPT4']   = st.number_input("CSSR NPT4",value=float(f"{V['CSSR_NPT4']:.3f}"),   step=0.1, format="%.3f", key="p_cssr")
            npt4_calc = V['KNO3_L_NPT4'] + V['CSSI_NPT4'] + V['CSSR_NPT4']
            st.metric("TOTAL NPT4", f"{npt4_calc:.3f} Kton")
 
        c3, c4 = st.columns(2)
        with c3:
            st.caption("Terminados")
            V['PRIL_DTP'] = st.number_input("PRILADO + DTP", value=float(f"{V['PRIL_DTP']:.3f}"), step=0.1, format="%.3f", key="p_pril")
            V['SECADO']   = st.number_input("SECADO",        value=float(f"{V['SECADO']:.3f}"),   step=0.1, format="%.3f", key="p_sec")
        with c4:
            st.caption("")
            st.metric("Total Terminados", f"{V['PRIL_DTP']+V['SECADO']:.3f} Kton", label_visibility="visible")
            st.metric("Total NPT3+NPT4",  f"{npt3_calc+npt4_calc:.3f} Kton")
 
        st.divider()
 
        # ── GASTOS ──────────────────────────────────────────────────────────
        st.markdown("#### 💰 Gastos (KUS)")
 
        st.caption("Pozas")
        cp1, cp2, cp3 = st.columns(3)
        with cp1: V['G_POZAS_NV'] = st.number_input("NV", value=round(V['G_POZAS_NV'],1), step=10.0, format="%.1f", key="g_nv")
        with cp2: V['G_POZAS_CS'] = st.number_input("CS", value=round(V['G_POZAS_CS'],1), step=10.0, format="%.1f", key="g_cs")
        with cp3: V['G_POZAS_PB'] = st.number_input("PB", value=round(V['G_POZAS_PB'],1), step=10.0, format="%.1f", key="g_pb")
 
        st.caption("Plantas")
        cp4, cp5, cp6, cp7, cp8 = st.columns(5)
        with cp4: V['G_PRIL']  = st.number_input("Prilado", value=round(V['G_PRIL'],1),  step=10.0, format="%.1f", key="g_pril")
        with cp5: V['G_DTP']   = st.number_input("DTP",     value=round(V['G_DTP'],1),   step=10.0, format="%.1f", key="g_dtp")
        with cp6: V['G_SECADO']= st.number_input("Secado",  value=round(V['G_SECADO'],1),step=10.0, format="%.1f", key="g_sec")
        with cp7: V['G_NPT3']  = st.number_input("NPT3",    value=round(V['G_NPT3'],1),  step=10.0, format="%.1f", key="g_npt3")
        with cp8: V['G_NPT4']  = st.number_input("NPT4",    value=round(V['G_NPT4'],1),  step=10.0, format="%.1f", key="g_npt4")
 
        st.caption("Puerto")
        cp9, cp10, cp11 = st.columns(3)
        with cp9:  V['G_EMBARQUE_KUS']   = st.number_input("Embarque (KUS)",    value=round(V['G_EMBARQUE_KUS'],1),   step=10.0, format="%.1f", key="g_emb")
        with cp10: V['G_ALMACENAJE_KUS'] = st.number_input("Almacenaje (KUS)",  value=round(V['G_ALMACENAJE_KUS'],1), step=10.0, format="%.1f", key="g_alm")
        with cp11: V['G_DIST_T_KUS']     = st.number_input("Distributivos (KUS)",value=round(V['G_DIST_T_KUS'],1),   step=10.0, format="%.1f", key="g_dist")
 
        st.caption("Transporte")
        V['TPTE_CAM_USDPT'] = st.number_input("Tpte Camiones (US$/T)", value=round(V['TPTE_CAM_USDPT'],4), step=0.1, format="%.4f", key="g_tpte")
 
        st.divider()
 
        # ── FC KCl ──────────────────────────────────────────────────────────
        st.markdown("#### ⚗️ Factor Consumo KCl")
        st.caption("NPT3 (KTon KCl / Kton prod)")
        fk1, fk2, fk3 = st.columns(3)
        with fk1: V['FC_MOP90_NPT3'] = st.number_input("MOP90 NPT3", value=float(f"{V['FC_MOP90_NPT3']:.6f}"), step=0.001, format="%.6f", key="fc90_3")
        with fk2: V['FC_MOP70_NPT3'] = st.number_input("MOP70 NPT3", value=float(f"{V['FC_MOP70_NPT3']:.6f}"), step=0.001, format="%.6f", key="fc70_3")
        with fk3: V['FC_SS_NPT3']    = st.number_input("SS NPT3",    value=float(f"{V['FC_SS_NPT3']:.6f}"),    step=0.001, format="%.6f", key="fcss_3")
 
        st.caption("NPT4 (KTon KCl / Kton prod)")
        fk4, fk5, fk6 = st.columns(3)
        with fk4: V['FC_MOP90_NPT4'] = st.number_input("MOP90 NPT4", value=float(f"{V['FC_MOP90_NPT4']:.6f}"), step=0.001, format="%.6f", key="fc90_4")
        with fk5: V['FC_MOP70_NPT4'] = st.number_input("MOP70 NPT4", value=float(f"{V['FC_MOP70_NPT4']:.6f}"), step=0.001, format="%.6f", key="fc70_4")
        with fk6: V['FC_SS_NPT4']    = st.number_input("SS NPT4",    value=float(f"{V['FC_SS_NPT4']:.6f}"),    step=0.001, format="%.6f", key="fcss_4")
 
        st.caption("Precio KCl (US$/T)")
        pk1, pk2, pk3 = st.columns(3)
        with pk1: V['P_MOP90'] = st.number_input("MOP 90", value=round(V['P_MOP90'],2), step=1.0, format="%.2f", key="p90")
        with pk2: V['P_MOP70'] = st.number_input("MOP 70", value=round(V['P_MOP70'],2), step=1.0, format="%.2f", key="p70")
        with pk3: V['P_SS']    = st.number_input("SS",     value=round(V['P_SS'],2),    step=1.0, format="%.2f", key="pss")
 
        st.divider()
 
        # ── FC NaNO3 / Transporte Sales ─────────────────────────────────────
        st.markdown("#### 🧂 Transporte de Sales")
        fs1, fs2 = st.columns(2)
        with fs1: V['P_TPTE_SALES'] = st.number_input("Precio Tpte Sales (USD/TNitr)", value=round(V['P_TPTE_SALES'],4), step=0.1, format="%.4f", key="p_tsales")
        with fs2: V['FC_SALES']     = st.number_input("FC Consumo Sales (NaNO3/Ton)",  value=float(f"{V['FC_SALES']:.6f}"), step=0.001, format="%.6f", key="fc_sales")
 
        st.divider()
 
        # ── Botón reset ──────────────────────────────────────────────────────
        if st.button("🔄 Restablecer valores PPTO", use_container_width=True):
            st.session_state['sens_vals'] = copy.deepcopy(BASE)
            st.rerun()
 
    # ── PANEL DE RESULTADOS ──────────────────────────────────────────────────
    with col_res:
        costo_base, comp_base = recalcular(BASE)
        costo_sim,  comp_sim  = recalcular(V)
        delta_total = costo_sim - costo_base
 
        st.markdown("#### 📊 Resultado")
 
        color_delta = "#D83030" if delta_total > 0 else "#2ECC71"
        signo = "▲" if delta_total > 0 else "▼"
 
        st.metric(
            label=f"Costo Total PPTO — {MESES[mes]}",
            value=f"${costo_base:.2f} / T",
        )
        st.metric(
            label="Costo Total Simulado",
            value=f"${costo_sim:.2f} / T",
            delta=f"{signo} {delta_total:+.2f} US$/T",
            delta_color="inverse",
        )
 
        st.divider()
        st.markdown("**Detalle por componente**")
 
        rows_det = []
        for comp in comp_base:
            b = comp_base[comp]
            s = comp_sim[comp]
            d = s - b
            rows_det.append({
                "Componente": comp,
                "PPTO":       round(b, 2),
                "Simulado":   round(s, 2),
                "Δ US$/T":    round(d, 2),
            })
        df_det = pd.DataFrame(rows_det)
 
        def _style(row):
            styles = ['', '', '', '']
            d = row["Δ US$/T"]
            if d > 0:   styles[3] = 'color:#D83030; font-weight:bold'
            elif d < 0: styles[3] = 'color:#2ECC71; font-weight:bold'
            return styles
 
        st.dataframe(
            df_det.style.apply(_style, axis=1).format({
                "PPTO":    "{:.2f}",
                "Simulado":"{:.2f}",
                "Δ US$/T": "{:+.2f}",
            }),
            use_container_width=True,
            hide_index=True,
            height=380,
        )
 
        st.divider()
        st.markdown("**Composición del costo simulado**")
 
        fig_pie = go.Figure(go.Bar(
            x=list(comp_sim.values()),
            y=list(comp_sim.keys()),
            orientation='h',
            marker_color=[
                '#D83030' if comp_sim[k] > comp_base[k]
                else ('#2ECC71' if comp_sim[k] < comp_base[k] else '#7F77DD')
                for k in comp_sim
            ],
            text=[f"${v:.1f}" for v in comp_sim.values()],
            textposition='outside',
            textfont_size=10,
        ))
        fig_pie.update_layout(
            height=320,
            margin=dict(l=120, r=60, t=10, b=10),
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            xaxis=dict(gridcolor='#333333'),
            yaxis=dict(autorange='reversed'),
        )
        st.plotly_chart(fig_pie, use_container_width=True)
 
