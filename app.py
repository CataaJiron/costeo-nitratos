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
    k2.metric(f"REAL + PROY {MESES[mes]} ({tipo})", f"${rp_m:.1f}/T",
              delta=f"PPTO: ${ppto_m:.1f}/T  ({rp_m-ppto_m:+.1f})", delta_color="inverse")
    k3.metric(f"Acumulado Ene-{MESES[mes]} PPTO", f"${ppto_acum:.1f}/T",
              delta=f"R+P: ${rp_acum:.1f}/T  ({rp_acum-ppto_acum:+.1f})", delta_color="inverse")
    k4.metric("Acumulado Ene-Dic PPTO", f"${ppto_dic:.1f}/T",
              delta=f"R+P: ${rp_dic:.1f}/T  ({rp_dic-ppto_dic:+.1f})", delta_color="inverse")

    

# ── SIDEBAR ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("Costeo Nitratos 2026")
    st.divider()
    archivo = st.file_uploader("Cargar Planilla costeo 2026.xlsx", type=["xlsx"])
    st.divider()
    pagina = st.radio("", ["Dashboard", "Analisis mensual", "Sensibilidad PPTO", "Sensibilidad R+P", "Plan Industrial", "Asistente"], 
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

    mes = botones_mes("analisis")
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
        row["Acum Dic"] = round(gv(df, 'COSTO TOTAL', sa, c, 11, 'Acumulado', 'PPTO'), 1)
        rows.append(row)
        row2 = {"Componente": nombre, "Tipo": "R+P"}
        for i, m in enumerate(MESES): row2[m] = round(s_r[i], 1)
        row2["Acum Dic"] = round(rp_val(df, 'COSTO TOTAL', sa, c, 11, 'Acumulado'), 1)
        rows.append(row2)

    # Total rows
    for tipo2, label, fn, fn_dic in [
        ('PPTO','TOTAL PPTO', lambda sa,c,i: gv(df,'COSTO TOTAL',sa,c,i,tipo,'PPTO'),
                              lambda sa,c:   gv(df,'COSTO TOTAL',sa,c,11,'Acumulado','PPTO')),
        ('RP',  'TOTAL R+P',  lambda sa,c,i: rp_val(df,'COSTO TOTAL',sa,c,i,tipo),
                              lambda sa,c:   rp_val(df,'COSTO TOTAL',sa,c,11,'Acumulado'))
    ]:
        row_t = {"Componente": label, "Tipo": ""}
        for i, m in enumerate(MESES):
            row_t[m] = round(sum(fn(sa,c,i) for sa,c,_ in COSTOS), 1)
        row_t["Acum Dic"] = round(sum(fn_dic(sa,c) for sa,c,_ in COSTOS), 1)
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
# SENSIBILIDAD — Simulador insumos mes puntual
# Muestra USD y Ton por separado; recalcula USD/T en tiempo real
# ══════════════════════════════════════════════════════════════════════════════
elif pagina == "Sensibilidad PPTO":
    import copy

    st.title("Simulador de Sensibilidad — PPTO")

    col_v, _ = st.columns([2, 6])
    with col_v:
        modo_sens = st.radio("Vista", ["Puntual", "Acumulado"], horizontal=True,
                             label_visibility="collapsed", key="modo_sens_ppto")
    tipo_sens = "Puntual" if modo_sens == "Puntual" else "Acumulado"

    mes = botones_mes("sens_ppto")
    st.divider()

    fechas_sorted = sorted(df['Fecha'].unique())
    if mes >= len(fechas_sorted):
        st.warning("Mes fuera de rango.")
        st.stop()
    fecha = fechas_sorted[mes]

    # ── helpers ──────────────────────────────────────────────────────────────
    def _r(area, subarea, concepto, medida=None, nth=0):
        mask = (
            (df['Fecha']    == fecha) &
            (df['AREA']     == area)  &
            (df['SUBAREA']  == subarea) &
            (df['CONCEPTO'] == concepto) &
            (df['Tipo']     == tipo_sens) &
            (df['Tipo_2']   == 'PPTO')
        )
        if medida:
            mask = mask & (df['Medida'] == medida)
        r = df[mask]['GASTO/COSTO']
        return float(r.values[nth]) if len(r) > nth else 0.0
    def _area(area):
        mask = (df['Fecha']==fecha)&(df['AREA']==area)&(df['Tipo']==tipo_sens)&(df['Tipo_2']=='PPTO')
        r = df[mask]['GASTO/COSTO']
        return float(r.values[0]) if not r.empty else 0.0
 
    # ── Valores PPTO base ─────────────────────────────────────────────────────
    BASE = {
        # Producción NPT3 (Kton)
        'KNO3_T_NPT3':   _r('PRODUCCION','NPT3','- KNO3 T NPT III'),
        'KNO3_R_NPT3':   _r('PRODUCCION','NPT3','- KNO3 R NPT III'),
    
        # Producción NPT4 (Kton)
        'KNO3_L_NPT4':   _r('PRODUCCION','NPT4','- KNO3 L NPT II/IV'),
        'CSSI_NPT4':     _r('PRODUCCION','NPT4','- CSSI NPT II/IV'),
        'CSSR_NPT4':     _r('PRODUCCION','NPT4','- CSSR NPT II/IV'),
    
        # Producción Terminados (Kton)
        'PRIL_DTP':      _r('PRODUCCION','TERMINADOS','PRILADO + DTP'),
        'SECADO':        _r('PRODUCCION','TERMINADOS','SECADO'),
    
        # Gastos Pozas (KUS)
        'G_POZAS_NV':    _r('GASTO','Operación Pozas (NV+CS+PV+PB)','Gasto Operación Pozas NV'),
        'G_POZAS_CS':    _r('GASTO','Operación Pozas (NV+CS+PV+PB)','Gasto Operación Pozas CS'),
        'G_POZAS_PB':    _r('GASTO','Operación Pozas (NV+CS+PV+PB)','Gasto Operación Pozas PB'),
        'G_DEPRECIACION_CS':    _r('GASTO','Operación Pozas (NV+CS+PV+PB)','Gasto Depreciación CS'),
        'G_POZAS_TOTAL': _r('GASTO','Operación Pozas (NV+CS+PV+PB)','Operación Pozas (SV+CS+PV+PB)'),
    
        # Gastos Plantas (KUS)
        'G_PRIL':        _r('GASTO','TERMINADOS','Gasto Planta Prilado CS'),
        'G_DTP':         _r('GASTO','TERMINADOS','Gasto Planta DTP'),
        'G_SECADO':      _r('GASTO','TERMINADOS','Gasto Planta Secado KNO3'),
        'G_NPT3':        _r('GASTO','CRISTALIZACION','Gasto NPT III + Korda'),
        'G_NPT4':        _r('GASTO','CRISTALIZACION','Gasto NPT IV'),

        
        # Puerto — gastos (KUS) y toneladas (Kton) por separado
        'G_EMBARQUE':    _r('Embarque Granel Trimestral','EMBARQUE','Embarque Granel + Demurrage','KUS'),
        'TON_EMBARQUE_TOTAL':  _r('Embarque Granel Trimestral','EMBARQUE','Embarque total','Kton'),  # granel real
        'G_ALMACENAJE':  _r('Almacenaje Trimestral','ALMACENAJE','Almacenaje Trimestral','KUS'),
        'TON_ALMACENAJE':_r('Almacenaje Trimestral','ALMACENAJE','Almacenaje Trimestral','Kton'),
        'G_DIST_T':      _r('Distributivos Trimestral','DISTRIBUTIVOS','Distributivos Trimestral','KUS'),
        'TON_DESPACHO':  _r('Distributivos Trimestral','DISTRIBUTIVOS','Despacho Camiones y contenedores','Kton'),
        'TON_EMBARQUE_GRANEL':  _r('Embarque Granel Trimestral','EMBARQUE','Embarque Granel','Kton'),
        'TON_EMBARQUE_ENVASADO':  _r('Embarque Granel Trimestral','EMBARQUE','Embarque Granel','Kton'),


        # Transporte camiones — gasto (KUS) y toneladas por separado
        'G_TPTE_CAM':    _r('GASTO','TRANSPORTE','Tpte Camiones Terminados', 'KUS'),
        'TON_TPTE_CAM':  _r('TRANSPORTE','TRANSPORTE','Tpte Camiones Terminados','kTon'),
        'G_TPTE_NV':     _r('TRANSPORTE DE SALES','Total Transporte de Sales NV + PB','- Transporte Sales NV', 'KUS'),
        'TON_TPTE_NV':   _r('TRANSPORTE DE SALES','Total Transporte Sales (Promedio)','Transporte de Sales NV a CS (Cat 1 + Cat 3)', 'KTon NaNO3'),
        'G_TPTE_PB':     _r('TRANSPORTE DE SALES','Total Transporte de Sales NV + PB','- Transporte Sales PB', 'KUS'),
        'TON_TPTE_PB':   _r('TRANSPORTE DE SALES','Total Transporte Sales (Promedio)','Transporte de Sales PB a CS', 'KTon NaNO3'),
        'G_CAMINOS_NV':  _r('TRANSPORTE DE SALES','Total Transporte de Sales NV + PB','- Op Canchas + Caminos NV', 'KUS'),
        'TON_TPTE_CS':   _r('TRANSPORTE DE SALES','Total Transporte Sales (Promedio)','Transporte de Sales CS (Alimentación)', 'KTon NaNO3'),

        # FC KCl (adimensional: KTon KCl / Kton prod)
        'FC_MOP90_NPT3': _r('KCl','Fc KCl NPT3','MOP 90', nth=0),
        'FC_MOP70_NPT3': _r('KCl','CONSUMO NPT3','MOP 70', nth=0),
        'FC_SS_NPT3':    _r('KCl','CONSUMO NPT3','SS', nth=0),
        'FC_MOP90_NPT4': _r('KCl','Fc KCl NPT4','MOP 90', nth=0),
        'FC_MOP70_NPT4': _r('KCl','Fc KCl NPT4','MOP 70', nth=0),
        'FC_SS_NPT4':    _r('KCl','CONSUMO NPT4','SS', nth=0),
        
        # Precio KCl (US$/T)
        'P_MOP90':       _r('KCl','Costo Promedio KCl','MOP 90'),
        'P_MOP70':       _r('KCl','Costo Promedio KCl','MOP 70'),
        'P_SS':          _r('KCl','Costo Promedio KCl','SS'),
        
        # FC NaNO3 y precio transporte sales
        'FC_SALES':      _r('TRANSPORTE DE SALES','- Factor Consumo de Sales','- Factor Consumo de Sales'),
        'P_TPTE_SALES':  _r('TRANSPORTE DE SALES','Total Transporte de Sales (promedio)','Total Transporte de Sales (promedio)'),
        'NV cat 1':  _r('TRANSPORTE DE SALES','Consumo Total de Sales','- NV cat 1'),
        'PB':  _r('TRANSPORTE DE SALES','Consumo Total de Sales','- PB'),
        'CS':  _r('TRANSPORTE DE SALES','Consumo Total de Sales','- CS'),        


        # Depreciaciones (fijas, no editables)

        'DEP_POZAS_CS': _r('GASTO','Operación Pozas (NV+CS+PV+PB)','Gasto Depreciación CS'),
        'DEP_PRIL':        _r('GASTO','TERMINADOS','Gasto Depreciación Prilado CS'),
        'DEP_DTP':         _r('GASTO','TERMINADOS','Gasto Depreciación DTP'),
        'DEP_SECADO':      _r('GASTO','TERMINADOS','Gasto Depreciación Secado KNO3'),
        'DEP_NPT3':        _r('GASTO','CRISTALIZACION','Gasto Depreciación NPT III'),
        'DEP_NPT4':        _r('GASTO','CRISTALIZACION','Gasto Depreciación NPT IV'),
        'DEPR_PUERTO': _r('DEPRECIACION','PUERTO','Depreciacion Puerto','KUS'),
        'G_TPTE_INT':    _r('GASTO','TERMINADOS','Gasto Transporte Intermedios'),
        'DIST_NITRATOS': _area('Distributivos Nitratos'),
        'DEPR_COM':      _area('Depreciación Costo Comun'),


        # Perdidas FE (fijas)
        'GEN_FE':       _r('PERDIDAS','PERDIDAS','Generación Producto FE (Terminados)'),
        'GEN_Perdidas':       _r('PERDIDAS','PERDIDAS','Generación Perdidas / Costras (Terminados)'),
        'GEN_Perdidas_Puerto':   _r('PERDIDAS','PERDIDAS', 'Perdidas / FE puerto y cancha'),
        'GEN_Perdidas_Degradacion':   _r('Perdidas y degradaciones puerto y cancha','Perdidas y degradaciones puerto y cancha', 'Perdidas y degradaciones puerto y cancha'),
        'OTROS':         gv(df,'COSTO TOTAL','1.9 OTROS','OTROS', mes,tipo_sens,'PPTO'),
    }
 
    def recalcular(v):
        npt3       = v['KNO3_T_NPT3'] + v['KNO3_R_NPT3']
        npt4       = v['KNO3_L_NPT4'] + v['CSSI_NPT4']  + v['CSSR_NPT4']
        prod_total = npt3 + npt4
        prod_sin_Sod = npt3 + v['KNO3_L_NPT4']
        prod_term  = v['PRIL_DTP'] + v['SECADO']

        # 1.1 Tpte Sales
        # Precio por ruta = Gasto KUS / Ton por ruta

        Ton_total_trans = v['TON_TPTE_NV'] + v['TON_TPTE_PB'] + v['TON_TPTE_CS']
        precio_nv = v['G_TPTE_NV'] / Ton_total_trans if Ton_total_trans > 0 else 0.0
        precio_pb = v['G_TPTE_PB'] / Ton_total_trans if Ton_total_trans > 0 else 0.0
        precio_cs = v['G_CAMINOS_NV'] / Ton_total_trans if Ton_total_trans > 0 else 0.0
        precio_total_transporte = precio_cs + precio_nv + precio_pb

        # Precio promedio ponderado por consumo de sales
        consumo_nv = v['NV cat 1']
        consumo_pb = v['PB']
        consumo_cs = v['CS']
        consumo_total = consumo_nv + consumo_pb + consumo_cs

        #precio_prom = (precio_nv * consumo_nv + precio_pb * consumo_pb + precio_cs * consumo_cs) / consumo_total if consumo_total > 0 else 0.0
        fc_sales = consumo_total / prod_total if prod_total > 0 else 0.0
        c11 = precio_total_transporte * fc_sales

        # 1.2 Pozas: usar total directo de la tabla
        #pozas_editado = any(v[k] != BASE[k] for k in ['G_POZAS_NV','G_POZAS_CS','G_POZAS_PB'])
        Gasto_pozas_Total =  (v['G_POZAS_NV'] + v['G_POZAS_CS'] + v['G_POZAS_PB'] + v['G_DEPRECIACION_CS'])
        Pozas_NV = v['G_POZAS_NV'] / prod_total if prod_total > 0 else 0.0
        Pozas_PB = v['G_POZAS_PB'] / prod_total if prod_total > 0 else 0.0
        Pozas_CS = v['G_POZAS_CS'] / prod_total if prod_total > 0 else 0.0
        Dep_CS =  v['G_DEPRECIACION_CS'] / prod_total if prod_total > 0 else 0.0
        c12 = Pozas_NV + Pozas_PB + Pozas_CS + Dep_CS

        # 1.3 Cristalización
        c13 = (v['G_NPT3'] + v['G_NPT4'] + v['DEP_NPT3'] + v['DEP_NPT4']) / prod_total if prod_total > 0 else 0.0

        # 1.4 KCl
        cons_mop90 = (v['FC_MOP90_NPT3'] * npt3) + (v['FC_MOP90_NPT4'] * v['KNO3_L_NPT4'])
        cons_mop70 = (v['FC_MOP70_NPT3'] * npt3) + (v['FC_MOP70_NPT4'] * v['KNO3_L_NPT4'])
        cons_ss    = (v['FC_SS_NPT3'] * npt3)  + (v['FC_SS_NPT4'] * v['KNO3_L_NPT4'])
        cons_total = cons_mop90 + cons_mop70 + cons_ss
        costo_total_kcl = (v['P_MOP90'] * cons_mop90) + (v['P_MOP70'] * cons_mop70) + (v['P_SS'] * cons_ss)
        c14 = costo_total_kcl / prod_sin_Sod if prod_sin_Sod > 0 else 0.0

        # 1.5 Terminados
       # Gasto_Total_terminados = (v['G_PRIL'] + v['G_DTP'] + v['G_SECADO'] + v['G_TPTE_INT'] + v['DEP_PRIL'] + v['DEP_DTP'] + v['DEP_SECADO'])
        G_Prilado = v['G_PRIL'] / prod_term if prod_term > 0 else 0.0
        G_DTP = v['G_DTP'] / prod_term if prod_term > 0 else 0.0
        G_Sec = v['G_SECADO'] / prod_term if prod_term > 0 else 0.0
        Tpte_inter = v['G_TPTE_INT'] / prod_term if prod_term > 0 else 0.0
        G_Dep =  (v['DEP_PRIL'] + v['DEP_DTP'] + v['DEP_SECADO']) / prod_term if prod_term > 0 else 0.0
        c15 = G_Prilado + G_DTP + G_Sec + G_Dep + Tpte_inter

        # 1.6 Tpte + Puerto
        c_tpte     = v['G_TPTE_CAM']  / v['TON_TPTE_CAM']       if v['TON_TPTE_CAM'] > 0       else 0.0
        c_embarque = v['G_EMBARQUE']  / v[ 'TON_EMBARQUE_GRANEL']  if v[ 'TON_EMBARQUE_GRANEL'] > 0  else 0.0
        c_alm      = v['G_ALMACENAJE']/ v['TON_ALMACENAJE']      if v['TON_ALMACENAJE'] > 0      else 0.0
        vol_d      = v['TON_EMBARQUE_TOTAL'] + v['TON_DESPACHO']
        c_dist     = v['G_DIST_T']    / vol_d                    if vol_d > 0                    else 0.0
        dep_puerto = v['DEPR_PUERTO'] / vol_d                    if vol_d > 0                    else 0.0
        c16 = c_tpte + c_embarque + c_alm + c_dist + dep_puerto

        # 1.7 Perdidas FE
        Op_dep = c11 + c12 + c13 + c14
        Perd_FE_pct = (-(v["GEN_FE"] + v["GEN_Perdidas"])) / prod_term if prod_term > 0 else 0.0
        Perdidas_FE = Op_dep * Perd_FE_pct
        base_comun = (Op_dep + Perdidas_FE + c15)
        prod_con_perdidas =  prod_total + v['GEN_Perdidas_Puerto'] + v["GEN_FE"] + v["GEN_Perdidas"]
        Per_Deg_PTOC = -(v['GEN_Perdidas_Puerto'] / (prod_con_perdidas - v["GEN_FE"] - v["GEN_Perdidas"]))
        Perd_Puerto = Per_Deg_PTOC * base_comun
        c17 = Perdidas_FE + Perd_Puerto

        # 1.7 Perdidas FE
        #Op_dep      = c11 + c12 + c13 + c14
        
        #pct_fe      = (-(v["GEN_FE"] + v["GEN_Perdidas"])) / prod_term if prod_term > 0 else 0.0
        #Perdidas_FE = Op_dep * pct_fe
        #base_deg    = Op_dep + Perdidas_FE + c15
        #pct_deg     = -v['GEN_Perdidas_Puerto'] / (prod_total - v["GEN_FE"] - v["GEN_Perdidas"]) if (prod_total - v["GEN_FE"] - v["GEN_Perdidas"]) != 0 else 0.0
        #Perd_Puerto = pct_deg * base_deg
        #c17         = Perdidas_FE + Perd_Puerto        

        # 1.8 Distributivos
        c18 = (v['DIST_NITRATOS'] + v['DEPR_COM']) / prod_total if prod_total > 0 else 0.0

        c19 = v['OTROS']


        TOTAL_COSTO = c11 + c12 + c13 + c14 + c15 + c16 + c17 + c18 + c19

        comp = {
            '1.1 Tpte Sales':    c11,
            '1.2 Op. Pozas':     c12,
            '1.3 Cristalización':c13,
            '1.4 KCl':           c14,
            '1.5 Terminados':    c15,
            '1.6 Tpte+Puerto':   c16,
            '1.7 Pérdidas F/E':  c17,
            '1.8 Distributivos': c18,
            '1.9 Otros':         c19,
#            'TOTAL_COSTO': TOTAL_COSTO
        }
        return sum(comp.values()), comp

    # ── Session state ─────────────────────────────────────────────────────────
    if 'sv' not in st.session_state or st.session_state.get('sv_mes') != mes or st.session_state.get('sv_tipo') != tipo_sens:
        st.session_state['sv']      = copy.deepcopy(BASE)
        st.session_state['sv_mes']  = mes
        st.session_state['sv_tipo'] = tipo_sens
        st.session_state['ppto_rc'] = st.session_state.get('ppto_rc', 0) + 1
    if 'ppto_rc' not in st.session_state:
        st.session_state['ppto_rc'] = 0
    rc = st.session_state['ppto_rc']
    V = st.session_state['sv']
    for k, val in BASE.items():
        if k not in V:
            V[k] = val

    # ── UI: inputs + resultados ───────────────────────────────────────────────
    col_inp, col_res = st.columns([3, 2], gap="large")
    with col_inp:
 
        # helper para mostrar fila "USD | Ton | => USD/T"
        def fila_usdton(label_usd, key_usd, label_ton, key_ton, fmt_usd="%.1f", fmt_ton="%.3f", step_usd=10.0, step_ton=0.1, usdpt_label="=> USD/T"):
            c1, c2, c3 = st.columns([2, 2, 1])
            with c1:
                V[key_usd] = st.number_input(label_usd, value=round(V[key_usd], 1), step=step_usd, format=fmt_usd, key=f"ui_{key_usd}_{rc}")
            with c2:
                V[key_ton] = st.number_input(label_ton, value=round(V[key_ton], 3), step=step_ton, format=fmt_ton, key=f"ui_{key_ton}_{rc}")
            with c3:
                ratio = V[key_usd] / V[key_ton] if V[key_ton] != 0 else 0.0
                st.metric(usdpt_label, f"${ratio:.2f}")
 
        # ─── PRODUCCIÓN ───────────────────────────────────────────────────────
        st.markdown("#### 🏭 Producción (Kton)")
 
        pc1, pc2 = st.columns(2)
        with pc1:
            st.caption("NPT3")
            V['KNO3_T_NPT3'] = st.number_input("T NPT3", value=round(V['KNO3_T_NPT3'],3), step=0.1, format="%.3f", key=f"ui_T3_{rc}")
            V['KNO3_R_NPT3'] = st.number_input("R NPT3", value=round(V['KNO3_R_NPT3'],3), step=0.1, format="%.3f", key=f"ui_R3_{rc}")
            npt3_v = V['KNO3_T_NPT3'] + V['KNO3_R_NPT3']
            st.metric("TOTAL NPT3", f"{npt3_v:.3f} Kton",
                      delta=f"{npt3_v - (BASE['KNO3_T_NPT3']+BASE['KNO3_R_NPT3']):+.3f}",
                      delta_color="off")
        with pc2:
            st.caption("NPT4")
            V['KNO3_L_NPT4'] = st.number_input("L NPT4",    value=round(V['KNO3_L_NPT4'],3), step=0.1, format="%.3f", key=f"ui_L4_{rc}")
            V['CSSI_NPT4']   = st.number_input("CSSI NPT4", value=round(V['CSSI_NPT4'],3),   step=0.1, format="%.3f", key=f"ui_CSSI_{rc}")
            V['CSSR_NPT4']   = st.number_input("CSSR NPT4", value=round(V['CSSR_NPT4'],3),   step=0.1, format="%.3f", key=f"ui_CSSR_{rc}")
            npt4_v = V['KNO3_L_NPT4'] + V['CSSI_NPT4'] + V['CSSR_NPT4']
            st.metric("TOTAL NPT4", f"{npt4_v:.3f} Kton",
                      delta=f"{npt4_v - (BASE['KNO3_L_NPT4']+BASE['CSSI_NPT4']+BASE['CSSR_NPT4']):+.3f}",
                      delta_color="off")
 
        pt1, pt2 = st.columns(2)
        with pt1:
            st.caption("Terminados")
            V['PRIL_DTP'] = st.number_input("PRILADO + DTP", value=round(V['PRIL_DTP'],3), step=0.1, format="%.3f", key=f"ui_PRIL_{rc}")
            V['SECADO']   = st.number_input("SECADO",        value=round(V['SECADO'],3),   step=0.1, format="%.3f", key=f"ui_SEC_{rc}")
        with pt2:
            st.caption(" ")
            prod_term_v  = V['PRIL_DTP'] + V['SECADO']
            prod_total_v = (V['KNO3_T_NPT3']+V['KNO3_R_NPT3']) + (V['KNO3_L_NPT4']+V['CSSI_NPT4']+V['CSSR_NPT4'])
            st.metric("Total Terminados", f"{prod_term_v:.3f} Kton",
                      delta=f"{prod_term_v - (BASE['PRIL_DTP']+BASE['SECADO']):+.3f}", delta_color="off")
            st.metric("Total NPT3+NPT4",  f"{prod_total_v:.3f} Kton",
                      delta=f"{prod_total_v - (BASE['KNO3_T_NPT3']+BASE['KNO3_R_NPT3']+BASE['KNO3_L_NPT4']+BASE['CSSI_NPT4']+BASE['CSSR_NPT4']):+.3f}",
                      delta_color="off")
 
        st.divider()
 
 
        # ─── GASTOS POZAS ─────────────────────────────────────────────────────
        st.markdown("#### 💰 Gastos Pozas (KUS) → USD/T sobre NPT3+NPT4")
        st.caption("Gasto (KUS)  |  — denominador: prod total —  |  USD/T resultante")
 
        for lbl, key in [("NV", "G_POZAS_NV"), ("CS", "G_POZAS_CS"), ("PB", "G_POZAS_PB")]:
            c1, c2 = st.columns([3, 1])
            with c1:
                V[key] = st.number_input(f"Gasto Pozas {lbl} (KUS)", value=round(V[key],1), step=10.0, format="%.1f", key=f"ui_{key}_{rc}")
            with c2:
                st.metric("USD/T", f"${V[key]/prod_total_v:.2f}" if prod_total_v > 0 else "-")
 
        tot_pozas = V['G_POZAS_NV']+V['G_POZAS_CS']+V['G_POZAS_PB']+V['G_DEPRECIACION_CS']
        st.caption(f"📌 Total Pozas (incl. depr. CS ${V['G_DEPRECIACION_CS']:.0f} KUS fija): **${tot_pozas:.0f} KUS** → **${tot_pozas/prod_total_v:.2f} USD/T**" if prod_total_v > 0 else "")
 
        st.divider()
 
        # ─── GASTOS PLANTAS ───────────────────────────────────────────────────
        st.markdown("#### 🏗️ Gastos Plantas (KUS)")
 
        st.caption("Cristalización → USD/T sobre NPT3+NPT4")
        for lbl, key in [("NPT3 (+ Korda)", "G_NPT3"), ("NPT4", "G_NPT4")]:
            c1, c2 = st.columns([3, 1])
            with c1:
                V[key] = st.number_input(f"Gasto {lbl} (KUS)", value=round(V[key],1), step=10.0, format="%.1f", key=f"ui_{key}_{rc}")
            with c2:
                st.metric("USD/T", f"${V[key]/prod_total_v:.2f}" if prod_total_v > 0 else "-")
        tot_crist = V['G_NPT3']+V['G_NPT4']+V['DEP_NPT3']+V['DEP_NPT4']
        st.caption(f"📌 Total Crist (incl. depr. ${V['DEP_NPT3']+V['DEP_NPT4']:.0f} KUS fija): **${tot_crist:.0f} KUS** → **${tot_crist/prod_total_v:.2f} USD/T**" if prod_total_v > 0 else "")
 
        st.caption("Terminados → USD/T sobre Pril+DTP+Secado")
        for lbl, key in [("Prilado CS", "G_PRIL"), ("DTP", "G_DTP"), ("Secado KNO3", "G_SECADO")]:
            c1, c2 = st.columns([3, 1])
            with c1:
                V[key] = st.number_input(f"Gasto {lbl} (KUS)", value=round(V[key],1), step=10.0, format="%.1f", key=f"ui_{key}_{rc}")
            with c2:
                st.metric("USD/T", f"${V[key]/prod_term_v:.2f}" if prod_term_v > 0 else "-")
        tot_term = V['G_PRIL']+V['G_DTP']+V['G_SECADO']+V['G_TPTE_INT']+V['DEP_PRIL']+V['DEP_DTP']+V['DEP_SECADO']
        st.caption(f"📌 Total Terminados (incl. depr+tpte int. ${V['DEP_PRIL']+V['DEP_DTP']+V['DEP_SECADO']+V['G_TPTE_INT']:.0f} KUS fija): **${tot_term:.0f} KUS** → **${tot_term/prod_term_v:.2f} USD/T**" if prod_term_v > 0 else "")
 
        st.divider()
 
# ─── PUERTO ───────────────────────────────────────────────────────────
        st.markdown("#### 🚢 Puerto — Gasto (KUS) | Toneladas (Kton) | USD/T")

        # 1. Función local exclusiva para Puerto
        def fila_usdton_puerto(label_usd, key_usd, label_ton, key_ton, step_ton=0.1):
            c1, c2, c3 = st.columns([2, 2, 1])
            with c1:
                V[key_usd] = st.number_input(label_usd, value=round(V[key_usd], 1), step=10.0, format="%.1f", key=f"ui_puerto_{key_usd}_{rc}")
            with c2:
                V[key_ton] = st.number_input(label_ton, value=round(V[key_ton], 3), step=step_ton, format="%.3f", key=f"ui_puerto_{key_ton}_{rc}")
            with c3:
                ratio = V[key_usd] / V[key_ton] if V[key_ton] != 0 else 0.0
                st.metric("=> USD/T", f"${ratio:.2f}")

        # 2. Llamadas a las filas de la tabla
        fila_usdton_puerto("Embarque+Demurrage (KUS)", "G_EMBARQUE", 
                           "Embarque Granel (Kton)",    "TON_EMBARQUE_TOTAL", 
                           step_ton=0.1)
                    
        fila_usdton_puerto("Almacenaje (KUS)", "G_ALMACENAJE", 
                           "Almacenaje (Kton)", "TON_ALMACENAJE", 
                           step_ton=1.0)

        # 3. Inputs manuales y cálculo de Distributivos (CORREGIDO AQUÍ)
        c1, c2, c3 = st.columns([2, 2, 1])
        with c1:
            V['G_DIST_T'] = st.number_input("Distributivos (KUS)", value=round(V['G_DIST_T'],1), step=10.0, format="%.1f", key=f"ui_G_DIST_T_{rc}")
        with c2:
            V['TON_DESPACHO'] = st.number_input("Despacho Cam. (Kton)", value=round(V['TON_DESPACHO'],3), step=0.1, format="%.3f", key=f"ui_TON_DESPACHO_{rc}")
        with c3:
            # Calculamos las variables en el flujo global para que el caption de abajo las pueda leer
            vol_d = V['TON_EMBARQUE_TOTAL'] + V['TON_DESPACHO']
            ratio_d = V['G_DIST_T'] / vol_d if vol_d > 0 else 0.0
            st.metric("=> USD/T", f"${ratio_d:.2f}")
 
        # Ahora vol_d ya existe aquí afuera y no fallará
        st.caption(f"ℹ️ Distributivos: denominador = Embarque Total + Despacho Camiones = {vol_d:.2f} Kton")
 
    # ─── TRANSPORTE CAMIONES ──────────────────────────────────────────────
        st.markdown("#### 🚛 Transporte Terminados — KUS | Kton | USD/T")
        
        # CAMBIO DEFINITIVO: Creamos una función local exclusiva para camiones
        # Esto ignora cualquier problema de caché o duplicado en el código de arriba
        def fila_usdton_camiones(label_usd, key_usd, label_ton, key_ton, step_ton=0.1):
            c1, c2, c3 = st.columns([2, 2, 1])
            with c1:
                V[key_usd] = st.number_input(label_usd, value=round(V[key_usd], 1), step=10.0, format="%.1f", key=f"ui_camiones_{key_usd}_{rc}")
            with c2:
                V[key_ton] = st.number_input(label_ton, value=round(V[key_ton], 3), step=step_ton, format="%.3f", key=f"ui_camiones_{key_ton}_{rc}")
            with c3:
                ratio = V[key_usd] / V[key_ton] if V[key_ton] != 0 else 0.0
                st.metric("=> USD/T", f"${ratio:.2f}")

        # Ejecutamos la nueva función con tus llaves originales del diccionario
        fila_usdton_camiones("Tpte Camiones (KUS)", "G_TPTE_CAM",
                             "Tpte Camiones (Kton)", "TON_TPTE_CAM",
                             step_ton=0.1)
 
        st.divider()
        # ─── FC KCl ───────────────────────────────────────────────────────────
        st.markdown("#### ⚗️ Factor Consumo KCl (KTon KCl / Kton prod)")
 
        npt3_v2 = V['KNO3_T_NPT3'] + V['KNO3_R_NPT3']
        npt4_v2 = V['KNO3_L_NPT4'] + V['CSSI_NPT4'] + V['CSSR_NPT4']
 
        st.caption("NPT3")
        fck1, fck2, fck3 = st.columns(3)
        with fck1: V['FC_MOP90_NPT3'] = st.number_input("MOP 90 NPT3", value=float(f"{V['FC_MOP90_NPT3']:.6f}"), step=0.001, format="%.6f", key=f"ui_FC_MOP90_NPT3_{rc}")
        with fck2: V['FC_MOP70_NPT3'] = st.number_input("MOP 70 NPT3", value=float(f"{V['FC_MOP70_NPT3']:.6f}"), step=0.001, format="%.6f", key=f"ui_FC_MOP70_NPT3_{rc}")
        with fck3: V['FC_SS_NPT3']    = st.number_input("SS NPT3",     value=float(f"{V['FC_SS_NPT3']:.6f}"),    step=0.001, format="%.6f", key=f"ui_FC_SS_NPT3_{rc}")
 
        cons3 = (V['FC_MOP90_NPT3']+V['FC_MOP70_NPT3']+V['FC_SS_NPT3'])*npt3_v2
        st.caption(f"Consumo KCl NPT3: {cons3:.2f} KTon")
 
        st.caption("NPT4")
        fck4, fck5, fck6 = st.columns(3)
        with fck4: V['FC_MOP90_NPT4'] = st.number_input("MOP 90 NPT4", value=float(f"{V['FC_MOP90_NPT4']:.6f}"), step=0.001, format="%.6f", key=f"ui_FC_MOP90_NPT4_{rc}")
        with fck5: V['FC_MOP70_NPT4'] = st.number_input("MOP 70 NPT4", value=float(f"{V['FC_MOP70_NPT4']:.6f}"), step=0.001, format="%.6f", key=f"ui_FC_MOP70_NPT4_{rc}")
        with fck6: V['FC_SS_NPT4']    = st.number_input("SS NPT4",     value=float(f"{V['FC_SS_NPT4']:.6f}"),    step=0.001, format="%.6f", key=f"ui_FC_SS_NPT4_{rc}")
 
        cons4 = (V['FC_MOP90_NPT4']+V['FC_MOP70_NPT4']+V['FC_SS_NPT4'])*npt4_v2
        st.caption(f"Consumo KCl NPT4: {cons4:.2f} KTon")
 
        st.caption("Precio KCl (US$/T)")
        pk1, pk2, pk3 = st.columns(3)
        with pk1: V['P_MOP90'] = st.number_input("MOP 90", value=round(V['P_MOP90'],2), step=1.0, format="%.2f", key=f"ui_P_MOP90_{rc}")
        with pk2: V['P_MOP70'] = st.number_input("MOP 70", value=round(V['P_MOP70'],2), step=1.0, format="%.2f", key=f"ui_P_MOP70_{rc}")
        with pk3: V['P_SS']    = st.number_input("SS",     value=round(V['P_SS'],2),    step=1.0, format="%.2f", key=f"ui_P_SS_{rc}")
 
        st.divider()
        # ─── FC NaNO3────────────────────────────────────────────
        st.markdown("#### 🧂Consumo Sales por origen (KTon NaNO3) y FC NaNO3 ")
        cs1, cs2, cs3 = st.columns(3)
        with cs1: V['NV cat 1'] = st.number_input("NV cat 1", value=round(V['NV cat 1'],3), step=0.1, format="%.3f", key=f"ui_ts_NV_{rc}")
        with cs2: V['PB']       = st.number_input("PB",       value=round(V['PB'],3),       step=0.1, format="%.3f", key=f"ui_ts_PB_{rc}")
        with cs3: V['CS']       = st.number_input("CS",       value=round(V['CS'],3),       step=0.1, format="%.3f", key=f"ui_ts_CS_{rc}")

        consumo_tot_v = V['NV cat 1'] + V['PB'] + V['CS']
        prod_total_ts = (V['KNO3_T_NPT3']+V['KNO3_R_NPT3']) + (V['KNO3_L_NPT4']+V['CSSI_NPT4']+V['CSSR_NPT4'])
        fc_v          = consumo_tot_v / prod_total_ts if prod_total_ts > 0 else 0.0
        precio_nv_v   = V['G_TPTE_NV']    / V['TON_TPTE_NV']  if V['TON_TPTE_NV']  > 0 else 0.0
        precio_pb_v   = V['G_TPTE_PB']    / V['TON_TPTE_PB']  if V['TON_TPTE_PB']  > 0 else 0.0
        precio_cs_v   = V['G_CAMINOS_NV'] / V['TON_TPTE_CS']  if V['TON_TPTE_CS']  > 0 else 0.0
        precio_prom_v = (precio_nv_v*V['NV cat 1'] + precio_pb_v*V['PB'] + precio_cs_v*V['CS']) / consumo_tot_v if consumo_tot_v > 0 else 0.0
        c11_preview   = precio_prom_v * fc_v
        st.caption(f"FC: {fc_v:.4f} | Precio prom: ${precio_prom_v:.2f} | **=> 1.1 Tpte Sales = ${c11_preview:.2f} USD/T**")
        st.divider() 

        # ───Tpte Sales ────────────────────────────────────────────
        st.markdown("#### 🧂 Transporte de Sales")

        def fila_tpte(label, key_g, key_ton):
            c1, c2, c3 = st.columns([2, 2, 1])
            with c1:
                V[key_g]   = st.number_input(f"{label} (KUS)",  value=round(V[key_g], 1),   step=10.0, format="%.1f", key=f"ui_ts_{key_g}_{rc}")
            with c2:
                V[key_ton] = st.number_input(f"{label} (KTon)", value=round(V[key_ton], 3), step=0.1,  format="%.3f", key=f"ui_ts_{key_ton}_{rc}")
            with c3:
                ton_total = V['TON_TPTE_NV'] + V['TON_TPTE_PB'] + V['TON_TPTE_CS']
                ratio = V[key_g] / ton_total if ton_total > 0 else 0.0
                st.metric("USD/KTon", f"${ratio:.2f}")

        fila_tpte("NV → CS",    "G_TPTE_NV",    "TON_TPTE_NV")
        fila_tpte("PB → CS",    "G_TPTE_PB",    "TON_TPTE_PB")
        c1, c2 = st.columns([3, 1])
        with c1:
            V['G_CAMINOS_NV'] = st.number_input("Caminos NV (KUS)", value=round(V['G_CAMINOS_NV'],1), step=10.0, format="%.1f", key=f"ui_ts_G_CAMINOS_NV_{rc}")
        with c2:
            ton_total = V['TON_TPTE_NV'] + V['TON_TPTE_PB'] + V['TON_TPTE_CS']
            ratio_cam = V['G_CAMINOS_NV'] / ton_total if ton_total > 0 else 0.0
            st.metric("USD/KTon", f"${ratio_cam:.2f}")

        fs1, fs2 = st.columns(2)
        with fs1:
            V['P_TPTE_SALES'] = st.number_input("Precio Tpte Sales (USD/TNitr)", value=round(V['P_TPTE_SALES'],4), step=0.1, format="%.4f", key=f"ui_P_TPTE_SALES_{rc}")
        with fs2:
            V['FC_SALES'] = st.number_input("FC Consumo Sales (NaNO3/Ton)", value=float(f"{V['FC_SALES']:.6f}"), step=0.001, format="%.6f", key=f"ui_FC_SALES_{rc}")
        st.caption(f"=> 1.1 Tpte Sales = ${V['P_TPTE_SALES']:.4f} × {V['FC_SALES']:.4f} = **${V['P_TPTE_SALES']*V['FC_SALES']:.4f} USD/T**")
 
        st.divider()
        
        if st.button(f"🔄 Restablecer valores PPTO ({modo_sens})", use_container_width=True):
            # Borrar TODAS las keys del session state que sean de esta página
            keys_to_delete = [k for k in st.session_state.keys() 
                             if k.startswith("ui_") or k in ('sv', 'sv_mes', 'sv_tipo')]
            for k in keys_to_delete:
                del st.session_state[k]
            st.rerun()
 
    # ── PANEL RESULTADO ───────────────────────────────────────────────────────
    with col_res:
        costo_base, comp_base = recalcular(BASE)
        costo_sim,  comp_sim  = recalcular(V)
        delta_total = costo_sim - costo_base
 
        st.markdown(f"#### 📊 Resultado — {MESES[mes]}")
        st.metric("PPTO Base",       f"${costo_base:.2f} / T")
        st.metric("Simulado",        f"${costo_sim:.2f} / T",
                  delta=f"{delta_total:+.2f} USD/T", delta_color="inverse")
 
        st.divider()
        st.markdown("**Detalle por componente**")
 
        rows = []
        for k in comp_base:
            b, s = comp_base[k], comp_sim[k]
            rows.append({"Componente": k, "PPTO": round(b,2), "Sim": round(s,2), "Δ": round(s-b,2)})
        df_det = pd.DataFrame(rows)
 
        def _col_delta(val):
            if isinstance(val, float):
                if val > 0: return 'color:#D83030;font-weight:bold'
                if val < 0: return 'color:#80BC00;font-weight:bold'
            return ''
 
        st.dataframe(
            df_det.style
                .map(_col_delta, subset=["Δ"])
                .format({"PPTO":"{:.2f}", "Sim":"{:.2f}", "Δ":"{:+.2f}"}),
            use_container_width=True, hide_index=True, height=360,
        )
        st.divider()

        st.markdown("**PPTO vs Simulado**")
        fig = go.Figure()
        nombres = list(comp_base.keys())
        v_base  = [comp_base[k] for k in nombres]
        v_sim   = [comp_sim[k]  for k in nombres]
        fig.add_trace(go.Bar(name="PPTO",     x=v_base, y=nombres, orientation='h',
                             marker_color='#152578', text=[f"${v:.1f}" for v in v_base],
                             textposition='outside', textfont_size=9))
        fig.add_trace(go.Bar(name="Simulado", x=v_sim,  y=nombres, orientation='h',
                             marker_color=['#D83030' if s>b else '#80BC00' for b,s in zip(v_base,v_sim)],
                             text=[f"${v:.1f}" for v in v_sim],
                             textposition='outside', textfont_size=9))
        fig.update_layout(
            barmode='group', height=360,
            margin=dict(l=120, r=60, t=10, b=10),
            plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
            xaxis=dict(gridcolor='#333333'),
            yaxis=dict(autorange='reversed'),
            legend=dict(orientation='h', y=1.05),
        )
        st.plotly_chart(fig, use_container_width=True) 



# ══════════════════════════════════════════════════════════════════════════════
# SENSIBILIDAD R+P
# ══════════════════════════════════════════════════════════════════════════════
elif pagina == "Sensibilidad R+P":
    import copy

    st.title("Simulador de Sensibilidad — Real + Proyección")

    col_v, _ = st.columns([2, 6])
    with col_v:
        modo_sens = st.radio("Vista", ["Puntual", "Acumulado"], horizontal=True,
                             label_visibility="collapsed", key="modo_sens_rp")
    tipo_sens = "Puntual" if modo_sens == "Puntual" else "Acumulado"

    mes = botones_mes("sens_rp")
    st.divider()

    fechas_sorted = sorted(df['Fecha'].unique())
    if mes >= len(fechas_sorted):
        st.warning("Mes fuera de rango.")
        st.stop()
    fecha = fechas_sorted[mes]

    # ── helpers R+P ──────────────────────────────────────────────────────────
    def _r(area, subarea, concepto, medida=None, nth=0):
        # Intenta REAL primero, luego PROY
        for t2 in ['REAL', 'PROY']:
            mask = (
                (df['Fecha']    == fecha) &
                (df['AREA']     == area)  &
                (df['SUBAREA']  == subarea) &
                (df['CONCEPTO'] == concepto) &
                (df['Tipo']     == tipo_sens) &
                (df['Tipo_2']   == t2)
            )
            if medida:
                mask = mask & (df['Medida'] == medida)
            r = df[mask]['GASTO/COSTO']
            if len(r) > nth and r.values[nth] != 0:
                return float(r.values[nth])
        return 0.0

    def _area(area):
        for t2 in ['REAL', 'PROY']:
            mask = (df['Fecha']==fecha)&(df['AREA']==area)&(df['Tipo']==tipo_sens)&(df['Tipo_2']==t2)
            r = df[mask]['GASTO/COSTO']
            if not r.empty and r.values[0] != 0:
                return float(r.values[0])
        return 0.0

    # ── Valores R+P base ──────────────────────────────────────────────────────
    BASE = {
        'KNO3_T_NPT3':   _r('PRODUCCION','NPT3','- KNO3 T NPT III'),
        'KNO3_R_NPT3':   _r('PRODUCCION','NPT3','- KNO3 R NPT III'),
        'KNO3_L_NPT4':   _r('PRODUCCION','NPT4','- KNO3 L NPT II/IV'),
        'CSSI_NPT4':     _r('PRODUCCION','NPT4','- CSSI NPT II/IV'),
        'CSSR_NPT4':     _r('PRODUCCION','NPT4','- CSSR NPT II/IV'),
        'PRIL_DTP':      _r('PRODUCCION','TERMINADOS','PRILADO + DTP'),
        'SECADO':        _r('PRODUCCION','TERMINADOS','SECADO'),
        'G_POZAS_NV':    _r('GASTO','Operación Pozas (NV+CS+PV+PB)','Gasto Operación Pozas NV'),
        'G_POZAS_CS':    _r('GASTO','Operación Pozas (NV+CS+PV+PB)','Gasto Operación Pozas CS'),
        'G_POZAS_PB':    _r('GASTO','Operación Pozas (NV+CS+PV+PB)','Gasto Operación Pozas PB'),
        'G_DEPRECIACION_CS': _r('GASTO','Operación Pozas (NV+CS+PV+PB)','Gasto Depreciación CS'),
        'G_POZAS_TOTAL': _r('GASTO','Operación Pozas (NV+CS+PV+PB)','Operación Pozas (SV+CS+PV+PB)'),
        'G_PRIL':        _r('GASTO','TERMINADOS','Gasto Planta Prilado CS'),
        'G_DTP':         _r('GASTO','TERMINADOS','Gasto Planta DTP'),
        'G_SECADO':      _r('GASTO','TERMINADOS','Gasto Planta Secado KNO3'),
        'G_NPT3':        _r('GASTO','CRISTALIZACION','Gasto NPT III + Korda'),
        'G_NPT4':        _r('GASTO','CRISTALIZACION','Gasto NPT IV'),
        'G_EMBARQUE':    _r('Embarque Granel Trimestral','EMBARQUE','Embarque Granel + Demurrage','KUS'),
        'TON_EMBARQUE_TOTAL': _r('Embarque Granel Trimestral','EMBARQUE','Embarque total','Kton'),
        'G_ALMACENAJE':  _r('Almacenaje Trimestral','ALMACENAJE','Almacenaje Trimestral','KUS'),
        'TON_ALMACENAJE':_r('Almacenaje Trimestral','ALMACENAJE','Almacenaje Trimestral','Kton'),
        'G_DIST_T':      _r('Distributivos Trimestral','DISTRIBUTIVOS','Distributivos Trimestral','KUS'),
        'TON_DESPACHO':  _r('Distributivos Trimestral','DISTRIBUTIVOS','Despacho Camiones y contenedores','Kton'),
        'TON_EMBARQUE_GRANEL': _r('Embarque Granel Trimestral','EMBARQUE','Embarque Granel','Kton'),
        'G_TPTE_CAM':    _r('GASTO','TRANSPORTE','Tpte Camiones Terminados','KUS'),
        'TON_TPTE_CAM':  _r('TRANSPORTE','TRANSPORTE','Tpte Camiones Terminados','kTon'),
        'G_TPTE_NV':     _r('TRANSPORTE DE SALES','Total Transporte de Sales NV + PB','- Transporte Sales NV','KUS'),
        'TON_TPTE_NV':   _r('TRANSPORTE DE SALES','Total Transporte Sales (Promedio)','Transporte de Sales NV a CS (Cat 1 + Cat 3)','KTon NaNO3'),
        'G_TPTE_PB':     _r('TRANSPORTE DE SALES','Total Transporte de Sales NV + PB','- Transporte Sales PB','KUS'),
        'TON_TPTE_PB':   _r('TRANSPORTE DE SALES','Total Transporte Sales (Promedio)','Transporte de Sales PB a CS','KTon NaNO3'),
        'G_CAMINOS_NV':  _r('TRANSPORTE DE SALES','Total Transporte de Sales NV + PB','- Op Canchas + Caminos NV','KUS'),
        'TON_TPTE_CS':   _r('TRANSPORTE DE SALES','Total Transporte Sales (Promedio)','Transporte de Sales CS (Alimentación)','KTon NaNO3'),
        'FC_MOP90_NPT3': _r('KCl','Fc KCl NPT3','MOP 90',nth=0),
        'FC_MOP70_NPT3': _r('KCl','CONSUMO NPT3','MOP 70',nth=0),
        'FC_SS_NPT3':    _r('KCl','CONSUMO NPT3','SS',nth=0),
        'FC_MOP90_NPT4': _r('KCl','Fc KCl NPT4','MOP 90',nth=0),
        'FC_MOP70_NPT4': _r('KCl','Fc KCl NPT4','MOP 70',nth=0),
        'FC_SS_NPT4':    _r('KCl','Fc KCl NPT4','SS',nth=0),
        'P_MOP90':       _r('KCl','Costo Promedio KCl','MOP 90'),
        'P_MOP70':       _r('KCl','Costo Promedio KCl','MOP 70'),
        'P_SS':          _r('KCl','Costo Promedio KCl','SS'),
        'FC_SALES':      _r('TRANSPORTE DE SALES','- Factor Consumo de Sales','- Factor Consumo de Sales'),
        'P_TPTE_SALES':  _r('TRANSPORTE DE SALES','Total Transporte de Sales (promedio)','Total Transporte de Sales (promedio)'),
        'NV cat 1':      _r('TRANSPORTE DE SALES','Consumo Total de Sales','- NV cat 1'),
        'PB':            _r('TRANSPORTE DE SALES','Consumo Total de Sales','- PB'),
        'CS':            _r('TRANSPORTE DE SALES','Consumo Total de Sales','- CS'),
        'DEP_POZAS_CS':  _r('GASTO','Operación Pozas (NV+CS+PV+PB)','Gasto Depreciación CS'),
        'DEP_PRIL':      _r('GASTO','TERMINADOS','Gasto Depreciación Prilado CS'),
        'DEP_DTP':       _r('GASTO','TERMINADOS','Gasto Depreciación DTP'),
        'DEP_SECADO':    _r('GASTO','TERMINADOS','Gasto Depreciación Secado KNO3'),
        'DEP_NPT3':      _r('GASTO','CRISTALIZACION','Gasto Depreciación NPT III'),
        'DEP_NPT4':      _r('GASTO','CRISTALIZACION','Gasto Depreciación NPT IV'),
        'DEPR_PUERTO':   _r('DEPRECIACION','PUERTO','Depreciacion Puerto','KUS'),
        'G_TPTE_INT':    _r('GASTO','TERMINADOS','Gasto Transporte Intermedios'),
        'DIST_NITRATOS': _area('Distributivos Nitratos'),
        'DEPR_COM':      _area('Depreciación Costo Comun'),
        'GEN_FE':        _r('PERDIDAS','PERDIDAS','Generación Producto FE (Terminados)'),
        'GEN_Perdidas':  _r('PERDIDAS','PERDIDAS','Generación Perdidas / Costras (Terminados)'),
        'GEN_Perdidas_Puerto': _r('PERDIDAS','PERDIDAS','Perdidas / FE puerto y cancha'),
        'GEN_Perdidas_Degradacion': _r('Perdidas y degradaciones puerto y cancha','Perdidas y degradaciones puerto y cancha','Perdidas y degradaciones puerto y cancha'),
        'OTROS': rp_val(df,'COSTO TOTAL','1.9 OTROS','OTROS', mes, tipo_sens),
    }

   
 
    def recalcular(v):
        npt3       = v['KNO3_T_NPT3'] + v['KNO3_R_NPT3']
        npt4       = v['KNO3_L_NPT4'] + v['CSSI_NPT4']  + v['CSSR_NPT4']
        prod_total = npt3 + npt4
        prod_sin_Sod = npt3 + v['KNO3_L_NPT4']
        prod_term  = v['PRIL_DTP'] + v['SECADO']


        # 1.1 Tpte Sales
        # Precio por ruta = Gasto KUS / Ton por ruta

        Ton_total_trans = v['TON_TPTE_NV'] + v['TON_TPTE_PB'] + v['TON_TPTE_CS']
        precio_nv = v['G_TPTE_NV'] / Ton_total_trans if Ton_total_trans > 0 else 0.0
        precio_pb = v['G_TPTE_PB'] / Ton_total_trans if Ton_total_trans > 0 else 0.0
        precio_cs = v['G_CAMINOS_NV'] / Ton_total_trans if Ton_total_trans > 0 else 0.0
        precio_total_transporte = precio_cs + precio_nv + precio_pb

        # Precio promedio ponderado por consumo de sales
        consumo_nv = v['NV cat 1']
        consumo_pb = v['PB']
        consumo_cs = v['CS']
        consumo_total = consumo_nv + consumo_pb + consumo_cs

        #precio_prom = (precio_nv * consumo_nv + precio_pb * consumo_pb + precio_cs * consumo_cs) / consumo_total if consumo_total > 0 else 0.0
        fc_sales = consumo_total / prod_total if prod_total > 0 else 0.0
        c11 = precio_total_transporte * fc_sales

        # 1.2 Pozas: usar total directo de la tabla
        #pozas_editado = any(v[k] != BASE[k] for k in ['G_POZAS_NV','G_POZAS_CS','G_POZAS_PB'])
        Gasto_pozas_Total =  (v['G_POZAS_NV'] + v['G_POZAS_CS'] + v['G_POZAS_PB'] + v['G_DEPRECIACION_CS'])
        Pozas_NV = v['G_POZAS_NV'] / prod_total if prod_total > 0 else 0.0
        Pozas_PB = v['G_POZAS_PB'] / prod_total if prod_total > 0 else 0.0
        Pozas_CS = v['G_POZAS_CS'] / prod_total if prod_total > 0 else 0.0
        Dep_CS =  v['G_DEPRECIACION_CS'] / prod_total if prod_total > 0 else 0.0
        c12 = Pozas_NV + Pozas_PB + Pozas_CS + Dep_CS

        # 1.3 Cristalización
        c13 = (v['G_NPT3'] + v['G_NPT4'] + v['DEP_NPT3'] + v['DEP_NPT4']) / prod_total if prod_total > 0 else 0.0

        # 1.4 KCl
        cons_mop90 = (v['FC_MOP90_NPT3'] * npt3) + (v['FC_MOP90_NPT4'] * v['KNO3_L_NPT4'])
        cons_mop70 = (v['FC_MOP70_NPT3'] * npt3) + (v['FC_MOP70_NPT4'] * v['KNO3_L_NPT4'])
        cons_ss    = (v['FC_SS_NPT3'] * npt3)  + (v['FC_SS_NPT4'] * v['KNO3_L_NPT4'])
        cons_total = cons_mop90 + cons_mop70 + cons_ss
        costo_total_kcl = (v['P_MOP90'] * cons_mop90) + (v['P_MOP70'] * cons_mop70) + (v['P_SS'] * cons_ss)
        c14 = costo_total_kcl / prod_sin_Sod if prod_sin_Sod > 0 else 0.0

        # 1.5 Terminados
       # Gasto_Total_terminados = (v['G_PRIL'] + v['G_DTP'] + v['G_SECADO'] + v['G_TPTE_INT'] + v['DEP_PRIL'] + v['DEP_DTP'] + v['DEP_SECADO'])
        G_Prilado = v['G_PRIL'] / prod_term if prod_term > 0 else 0.0
        G_DTP = v['G_DTP'] / prod_term if prod_term > 0 else 0.0
        G_Sec = v['G_SECADO'] / prod_term if prod_term > 0 else 0.0
        Tpte_inter = v['G_TPTE_INT'] / prod_term if prod_term > 0 else 0.0
        G_Dep =  (v['DEP_PRIL'] + v['DEP_DTP'] + v['DEP_SECADO']) / prod_term if prod_term > 0 else 0.0
        c15 = G_Prilado + G_DTP + G_Sec + G_Dep + Tpte_inter

        # 1.6 Tpte + Puerto
        c_tpte     = v['G_TPTE_CAM']  / v['TON_TPTE_CAM']       if v['TON_TPTE_CAM'] > 0       else 0.0
        c_embarque = v['G_EMBARQUE']  / v[ 'TON_EMBARQUE_GRANEL']  if v[ 'TON_EMBARQUE_GRANEL'] > 0  else 0.0
        c_alm      = v['G_ALMACENAJE']/ v['TON_ALMACENAJE']      if v['TON_ALMACENAJE'] > 0      else 0.0
        vol_d      = v['TON_EMBARQUE_TOTAL'] + v['TON_DESPACHO']
        c_dist     = v['G_DIST_T']    / vol_d                    if vol_d > 0                    else 0.0
        dep_puerto = v['DEPR_PUERTO'] / vol_d                    if vol_d > 0                    else 0.0
        c16 = c_tpte + c_embarque + c_alm + c_dist + dep_puerto

        # 1.7 Perdidas FE
        Op_dep = c11 + c12 + c13 + c14
        Perd_FE_pct = (-(v["GEN_FE"] + v["GEN_Perdidas"])) / prod_term if prod_term > 0 else 0.0
        Perdidas_FE = Op_dep * Perd_FE_pct
        base_comun = (Op_dep + Perdidas_FE + c15)
        prod_con_perdidas =  prod_total + v['GEN_Perdidas_Puerto'] + v["GEN_FE"] + v["GEN_Perdidas"]
        Per_Deg_PTOC = -(v['GEN_Perdidas_Puerto'] / (prod_con_perdidas - v["GEN_FE"] - v["GEN_Perdidas"]))
        Perd_Puerto = Per_Deg_PTOC * base_comun
        c17 = Perdidas_FE + Perd_Puerto

        # 1.7 Perdidas FE
        #Op_dep      = c11 + c12 + c13 + c14
        
        #pct_fe      = (-(v["GEN_FE"] + v["GEN_Perdidas"])) / prod_term if prod_term > 0 else 0.0
        #Perdidas_FE = Op_dep * pct_fe
        #base_deg    = Op_dep + Perdidas_FE + c15
        #pct_deg     = -v['GEN_Perdidas_Puerto'] / (prod_total - v["GEN_FE"] - v["GEN_Perdidas"]) if (prod_total - v["GEN_FE"] - v["GEN_Perdidas"]) != 0 else 0.0
        #Perd_Puerto = pct_deg * base_deg
        #c17         = Perdidas_FE + Perd_Puerto        

        # 1.8 Distributivos
        c18 = (v['DIST_NITRATOS'] + v['DEPR_COM']) / prod_total if prod_total > 0 else 0.0

        c19 = v['OTROS']


        TOTAL_COSTO = c11 + c12 + c13 + c14 + c15 + c16 + c17 + c18 + c19

        comp = {
            '1.1 Tpte Sales':    c11,
            '1.2 Op. Pozas':     c12,
            '1.3 Cristalización':c13,
            '1.4 KCl':           c14,
            '1.5 Terminados':    c15,
            '1.6 Tpte+Puerto':   c16,
            '1.7 Pérdidas F/E':  c17,
            '1.8 Distributivos': c18,
            '1.9 Otros':         c19,
#            'TOTAL_COSTO': TOTAL_COSTO
        }
        return sum(comp.values()), comp

    # ── Session state ─────────────────────────────────────────────────────────
    sv_key = 'sv_rp'
    if sv_key not in st.session_state or st.session_state.get('sv_rp_mes') != mes or st.session_state.get('sv_rp_tipo') != tipo_sens:
        st.session_state[sv_key]        = copy.deepcopy(BASE)
        st.session_state['sv_rp_mes']   = mes
        st.session_state['sv_rp_tipo']  = tipo_sens
        st.session_state['rp_rc']       = st.session_state.get('rp_rc', 0) + 1
    if 'rp_rc' not in st.session_state:
        st.session_state['rp_rc'] = 0
    rp_rc = st.session_state['rp_rc']
    V = st.session_state[sv_key]
    for k, val in BASE.items():
        if k not in V:
            V[k] = val

    # ── UI: inputs + resultados ───────────────────────────────────────────────
    col_inp, col_res = st.columns([3, 2], gap="large")
    with col_inp:
 
        # helper para mostrar fila "USD | Ton | => USD/T"
        def fila_usdton(label_usd, key_usd, label_ton, key_ton, fmt_usd="%.1f", fmt_ton="%.3f", step_usd=10.0, step_ton=0.1, usdpt_label="=> USD/T"):
            c1, c2, c3 = st.columns([2, 2, 1])
            with c1:
                V[key_usd] = st.number_input(label_usd, value=round(V[key_usd], 1), step=step_usd, format=fmt_usd, key=f"ui_{key_usd}_{rp_rc}")
            with c2:
                V[key_ton] = st.number_input(label_ton, value=round(V[key_ton], 3), step=step_ton, format=fmt_ton, key=f"ui_{key_ton}_{rp_rc}")
            with c3:
                ratio = V[key_usd] / V[key_ton] if V[key_ton] != 0 else 0.0
                st.metric(usdpt_label, f"${ratio:.2f}")

        # ─── PRODUCCIÓN ─────────────────────────────────────────────────────── 
        st.markdown("#### 🏭 Producción (Kton)")
 
        pc1, pc2 = st.columns(2)
        with pc1:
            st.caption("NPT3")
            V['KNO3_T_NPT3'] = st.number_input("T NPT3", value=round(V['KNO3_T_NPT3'],3), step=0.1, format="%.3f", key=f"ui_T3_{rp_rc}")
            V['KNO3_R_NPT3'] = st.number_input("R NPT3", value=round(V['KNO3_R_NPT3'],3), step=0.1, format="%.3f", key=f"ui_R3_{rp_rc}")
            npt3_v = V['KNO3_T_NPT3'] + V['KNO3_R_NPT3']
            st.metric("TOTAL NPT3", f"{npt3_v:.3f} Kton",
                      delta=f"{npt3_v - (BASE['KNO3_T_NPT3']+BASE['KNO3_R_NPT3']):+.3f}",
                      delta_color="off")
        with pc2:
            st.caption("NPT4")
            V['KNO3_L_NPT4'] = st.number_input("L NPT4",    value=round(V['KNO3_L_NPT4'],3), step=0.1, format="%.3f", key=f"ui_L4_{rp_rc}")
            V['CSSI_NPT4']   = st.number_input("CSSI NPT4", value=round(V['CSSI_NPT4'],3),   step=0.1, format="%.3f", key=f"ui_CSSI_{rp_rc}")
            V['CSSR_NPT4']   = st.number_input("CSSR NPT4", value=round(V['CSSR_NPT4'],3),   step=0.1, format="%.3f", key=f"ui_CSSR_{rp_rc}")
            npt4_v = V['KNO3_L_NPT4'] + V['CSSI_NPT4'] + V['CSSR_NPT4']
            st.metric("TOTAL NPT4", f"{npt4_v:.3f} Kton",
                      delta=f"{npt4_v - (BASE['KNO3_L_NPT4']+BASE['CSSI_NPT4']+BASE['CSSR_NPT4']):+.3f}",
                      delta_color="off")
 
        pt1, pt2 = st.columns(2)
        with pt1:
            st.caption("Terminados")
            V['PRIL_DTP'] = st.number_input("PRILADO + DTP", value=round(V['PRIL_DTP'],3), step=0.1, format="%.3f", key=f"ui_PRIL_{rp_rc}")
            V['SECADO']   = st.number_input("SECADO",        value=round(V['SECADO'],3),   step=0.1, format="%.3f", key=f"ui_SEC_{rp_rc}")
        with pt2:
            st.caption(" ")
            prod_term_v  = V['PRIL_DTP'] + V['SECADO']
            prod_total_v = (V['KNO3_T_NPT3']+V['KNO3_R_NPT3']) + (V['KNO3_L_NPT4']+V['CSSI_NPT4']+V['CSSR_NPT4'])
            st.metric("Total Terminados", f"{prod_term_v:.3f} Kton",
                      delta=f"{prod_term_v - (BASE['PRIL_DTP']+BASE['SECADO']):+.3f}", delta_color="off")
            st.metric("Total NPT3+NPT4",  f"{prod_total_v:.3f} Kton",
                      delta=f"{prod_total_v - (BASE['KNO3_T_NPT3']+BASE['KNO3_R_NPT3']+BASE['KNO3_L_NPT4']+BASE['CSSI_NPT4']+BASE['CSSR_NPT4']):+.3f}",
                      delta_color="off")
 
        st.divider()
 
 
        
        # ─── GASTOS POZAS ─────────────────────────────────────────────────────
        st.markdown("#### 💰 Gastos Pozas (KUS) → USD/T sobre NPT3+NPT4")
        st.caption("Gasto (KUS)  |  — denominador: prod total —  |  USD/T resultante")
 
        for lbl, key in [("NV", "G_POZAS_NV"), ("CS", "G_POZAS_CS"), ("PB", "G_POZAS_PB")]:
            c1, c2 = st.columns([3, 1])
            with c1:
                V[key] = st.number_input(f"Gasto Pozas {lbl} (KUS)", value=round(V[key],1), step=10.0, format="%.1f", key=f"ui_{key}_{rp_rc}")
            with c2:
                st.metric("USD/T", f"${V[key]/prod_total_v:.2f}" if prod_total_v > 0 else "-")
 
        tot_pozas = V['G_POZAS_NV']+V['G_POZAS_CS']+V['G_POZAS_PB']+V['G_DEPRECIACION_CS']
        st.caption(f"📌 Total Pozas (incl. depr. CS ${V['G_DEPRECIACION_CS']:.0f} KUS fija): **${tot_pozas:.0f} KUS** → **${tot_pozas/prod_total_v:.2f} USD/T**" if prod_total_v > 0 else "")
 
        st.divider()
 
        # ─── GASTOS PLANTAS ───────────────────────────────────────────────────  

        st.markdown("#### 🏗️ Gastos Plantas (KUS)")
 
        st.caption("Cristalización → USD/T sobre NPT3+NPT4")
        for lbl, key in [("NPT3 (+ Korda)", "G_NPT3"), ("NPT4", "G_NPT4")]:
            c1, c2 = st.columns([3, 1])
            with c1:
                V[key] = st.number_input(f"Gasto {lbl} (KUS)", value=round(V[key],1), step=10.0, format="%.1f", key=f"ui_{key}_{rp_rc}")
            with c2:
                st.metric("USD/T", f"${V[key]/prod_total_v:.2f}" if prod_total_v > 0 else "-")
        tot_crist = V['G_NPT3']+V['G_NPT4']+V['DEP_NPT3']+V['DEP_NPT4']
        st.caption(f"📌 Total Crist (incl. depr. ${V['DEP_NPT3']+V['DEP_NPT4']:.0f} KUS fija): **${tot_crist:.0f} KUS** → **${tot_crist/prod_total_v:.2f} USD/T**" if prod_total_v > 0 else "")
 
        st.caption("Terminados → USD/T sobre Pril+DTP+Secado")
        for lbl, key in [("Prilado CS", "G_PRIL"), ("DTP", "G_DTP"), ("Secado KNO3", "G_SECADO")]:
            c1, c2 = st.columns([3, 1])
            with c1:
                V[key] = st.number_input(f"Gasto {lbl} (KUS)", value=round(V[key],1), step=10.0, format="%.1f", key=f"ui_{key}_{rp_rc}")
            with c2:
                st.metric("USD/T", f"${V[key]/prod_term_v:.2f}" if prod_term_v > 0 else "-")
        tot_term = V['G_PRIL']+V['G_DTP']+V['G_SECADO']+V['G_TPTE_INT']+V['DEP_PRIL']+V['DEP_DTP']+V['DEP_SECADO']
        st.caption(f"📌 Total Terminados (incl. depr+tpte int. ${V['DEP_PRIL']+V['DEP_DTP']+V['DEP_SECADO']+V['G_TPTE_INT']:.0f} KUS fija): **${tot_term:.0f} KUS** → **${tot_term/prod_term_v:.2f} USD/T**" if prod_term_v > 0 else "")
 
        st.divider()



# ─── PUERTO ───────────────────────────────────────────────────────────
        st.markdown("#### 🚢 Puerto — Gasto (KUS) | Toneladas (Kton) | USD/T")

        # 1. Función local exclusiva para Puerto
        def fila_usdton_puerto(label_usd, key_usd, label_ton, key_ton, step_ton=0.1):
            c1, c2, c3 = st.columns([2, 2, 1])
            with c1:
                V[key_usd] = st.number_input(label_usd, value=round(V[key_usd], 1), step=10.0, format="%.1f", key=f"ui_puerto_{key_usd}_{rp_rc}")
            with c2:
                V[key_ton] = st.number_input(label_ton, value=round(V[key_ton], 3), step=step_ton, format="%.3f", key=f"ui_puerto_{key_ton}_{rp_rc}")
            with c3:
                ratio = V[key_usd] / V[key_ton] if V[key_ton] != 0 else 0.0
                st.metric("=> USD/T", f"${ratio:.2f}")

        # 2. Llamadas a las filas de la tabla
        fila_usdton_puerto("Embarque+Demurrage (KUS)", "G_EMBARQUE", 
                           "Embarque Granel (Kton)",    "TON_EMBARQUE_TOTAL", 
                           step_ton=0.1)
                    
        fila_usdton_puerto("Almacenaje (KUS)", "G_ALMACENAJE", 
                           "Almacenaje (Kton)", "TON_ALMACENAJE", 
                           step_ton=1.0)

        # 3. Inputs manuales y cálculo de Distributivos (CORREGIDO AQUÍ)
        c1, c2, c3 = st.columns([2, 2, 1])
        with c1:
            V['G_DIST_T'] = st.number_input("Distributivos (KUS)", value=round(V['G_DIST_T'],1), step=10.0, format="%.1f", key=f"ui_G_DIST_T_{rp_rc}")
        with c2:
            V['TON_DESPACHO'] = st.number_input("Despacho Cam. (Kton)", value=round(V['TON_DESPACHO'],3), step=0.1, format="%.3f", key=f"ui_TON_DESPACHO_{rp_rc}")
        with c3:
            # Calculamos las variables en el flujo global para que el caption de abajo las pueda leer
            vol_d = V['TON_EMBARQUE_TOTAL'] + V['TON_DESPACHO']
            ratio_d = V['G_DIST_T'] / vol_d if vol_d > 0 else 0.0
            st.metric("=> USD/T", f"${ratio_d:.2f}")
 
        # Ahora vol_d ya existe aquí afuera y no fallará
        st.caption(f"ℹ️ Distributivos: denominador = Embarque Total + Despacho Camiones = {vol_d:.2f} Kton")
 
    # ─── TRANSPORTE CAMIONES ──────────────────────────────────────────────
        st.markdown("#### 🚛 Transporte Terminados — KUS | Kton | USD/T")
        
        # CAMBIO DEFINITIVO: Creamos una función local exclusiva para camiones
        # Esto ignora cualquier problema de caché o duplicado en el código de arriba
        def fila_usdton_camiones(label_usd, key_usd, label_ton, key_ton, step_ton=0.1):
            c1, c2, c3 = st.columns([2, 2, 1])
            with c1:
                V[key_usd] = st.number_input(label_usd, value=round(V[key_usd], 1), step=10.0, format="%.1f", key=f"ui_camiones_{key_usd}_{rp_rc}")
            with c2:
                V[key_ton] = st.number_input(label_ton, value=round(V[key_ton], 3), step=step_ton, format="%.3f", key=f"ui_camiones_{key_ton}_{rp_rc}")
            with c3:
                ratio = V[key_usd] / V[key_ton] if V[key_ton] != 0 else 0.0
                st.metric("=> USD/T", f"${ratio:.2f}")

        # Ejecutamos la nueva función con tus llaves originales del diccionario
        fila_usdton_camiones("Tpte Camiones (KUS)", "G_TPTE_CAM",
                             "Tpte Camiones (Kton)", "TON_TPTE_CAM",
                             step_ton=0.1)
 
        st.divider()

        # ─── FC KCl ───────────────────────────────────────────────────────────
        st.markdown("#### ⚗️ Factor Consumo KCl (KTon KCl / Kton prod)")
 
        npt3_v2 = V['KNO3_T_NPT3'] + V['KNO3_R_NPT3']
        npt4_v2 = V['KNO3_L_NPT4'] + V['CSSI_NPT4'] + V['CSSR_NPT4']
 
        st.caption("NPT3")
        fck1, fck2, fck3 = st.columns(3)
        with fck1: V['FC_MOP90_NPT3'] = st.number_input("MOP 90 NPT3", value=float(f"{V['FC_MOP90_NPT3']:.6f}"), step=0.001, format="%.6f", key=f"ui_FC_MOP90_NPT3_{rp_rc}")
        with fck2: V['FC_MOP70_NPT3'] = st.number_input("MOP 70 NPT3", value=float(f"{V['FC_MOP70_NPT3']:.6f}"), step=0.001, format="%.6f", key=f"ui_FC_MOP70_NPT3_{rp_rc}")
        with fck3: V['FC_SS_NPT3']    = st.number_input("SS NPT3",     value=float(f"{V['FC_SS_NPT3']:.6f}"),    step=0.001, format="%.6f", key=f"ui_FC_SS_NPT3_{rp_rc}")
 
        cons3 = (V['FC_MOP90_NPT3']+V['FC_MOP70_NPT3']+V['FC_SS_NPT3'])*npt3_v2
        st.caption(f"Consumo KCl NPT3: {cons3:.2f} KTon")
 
        st.caption("NPT4")
        fck4, fck5, fck6 = st.columns(3)
        with fck4: V['FC_MOP90_NPT4'] = st.number_input("MOP 90 NPT4", value=float(f"{V['FC_MOP90_NPT4']:.6f}"), step=0.001, format="%.6f", key=f"ui_FC_MOP90_NPT4_{rp_rc}")
        with fck5: V['FC_MOP70_NPT4'] = st.number_input("MOP 70 NPT4", value=float(f"{V['FC_MOP70_NPT4']:.6f}"), step=0.001, format="%.6f", key=f"ui_FC_MOP70_NPT4_{rp_rc}")
        with fck6: V['FC_SS_NPT4']    = st.number_input("SS NPT4",     value=float(f"{V['FC_SS_NPT4']:.6f}"),    step=0.001, format="%.6f", key=f"ui_FC_SS_NPT4_{rp_rc}")
 
        cons4 = (V['FC_MOP90_NPT4']+V['FC_MOP70_NPT4']+V['FC_SS_NPT4'])*npt4_v2
        st.caption(f"Consumo KCl NPT4: {cons4:.2f} KTon")
 
        st.caption("Precio KCl (US$/T)")
        pk1, pk2, pk3 = st.columns(3)
        with pk1: V['P_MOP90'] = st.number_input("MOP 90", value=round(V['P_MOP90'],2), step=1.0, format="%.2f", key=f"ui_P_MOP90_{rp_rc}")
        with pk2: V['P_MOP70'] = st.number_input("MOP 70", value=round(V['P_MOP70'],2), step=1.0, format="%.2f", key=f"ui_P_MOP70_{rp_rc}")
        with pk3: V['P_SS']    = st.number_input("SS",     value=round(V['P_SS'],2),    step=1.0, format="%.2f", key=f"ui_P_SS_{rp_rc}")
 
        st.divider()
        # ─── FC NaNO3────────────────────────────────────────────
        st.markdown("#### 🧂Consumo Sales por origen (KTon NaNO3) y FC NaNO3 ")
        cs1, cs2, cs3 = st.columns(3)
        with cs1: V['NV cat 1'] = st.number_input("NV cat 1", value=round(V['NV cat 1'],3), step=0.1, format="%.3f", key=f"ui_ts_NV_{rp_rc}")
        with cs2: V['PB']       = st.number_input("PB",       value=round(V['PB'],3),       step=0.1, format="%.3f", key=f"ui_ts_PB_{rp_rc}")
        with cs3: V['CS']       = st.number_input("CS",       value=round(V['CS'],3),       step=0.1, format="%.3f", key=f"ui_ts_CS_{rp_rc}")

        consumo_tot_v = V['NV cat 1'] + V['PB'] + V['CS']
        prod_total_ts = (V['KNO3_T_NPT3']+V['KNO3_R_NPT3']) + (V['KNO3_L_NPT4']+V['CSSI_NPT4']+V['CSSR_NPT4'])
        fc_v          = consumo_tot_v / prod_total_ts if prod_total_ts > 0 else 0.0
        precio_nv_v   = V['G_TPTE_NV']    / V['TON_TPTE_NV']  if V['TON_TPTE_NV']  > 0 else 0.0
        precio_pb_v   = V['G_TPTE_PB']    / V['TON_TPTE_PB']  if V['TON_TPTE_PB']  > 0 else 0.0
        precio_cs_v   = V['G_CAMINOS_NV'] / V['TON_TPTE_CS']  if V['TON_TPTE_CS']  > 0 else 0.0
        precio_prom_v = (precio_nv_v*V['NV cat 1'] + precio_pb_v*V['PB'] + precio_cs_v*V['CS']) / consumo_tot_v if consumo_tot_v > 0 else 0.0
        c11_preview   = precio_prom_v * fc_v
        st.caption(f"FC: {fc_v:.4f} | Precio prom: ${precio_prom_v:.2f} | **=> 1.1 Tpte Sales = ${c11_preview:.2f} USD/T**")
        st.divider() 

        # ───Tpte Sales ────────────────────────────────────────────
        st.markdown("#### 🧂 Transporte de Sales")

        def fila_tpte(label, key_g, key_ton):
            c1, c2, c3 = st.columns([2, 2, 1])
            with c1:
                V[key_g]   = st.number_input(f"{label} (KUS)",  value=round(V[key_g], 1),   step=10.0, format="%.1f", key=f"ui_ts_{key_g}_{rp_rc}")
            with c2:
                V[key_ton] = st.number_input(f"{label} (KTon)", value=round(V[key_ton], 3), step=0.1,  format="%.3f", key=f"ui_ts_{key_ton}_{rp_rc}")
            with c3:
                ton_total = V['TON_TPTE_NV'] + V['TON_TPTE_PB'] + V['TON_TPTE_CS']
                ratio = V[key_g] / ton_total if ton_total > 0 else 0.0
                st.metric("USD/KTon", f"${ratio:.2f}")

        fila_tpte("NV → CS",    "G_TPTE_NV",    "TON_TPTE_NV")
        fila_tpte("PB → CS",    "G_TPTE_PB",    "TON_TPTE_PB")
        c1, c2 = st.columns([3, 1])
        with c1:
            V['G_CAMINOS_NV'] = st.number_input("Caminos NV (KUS)", value=round(V['G_CAMINOS_NV'],1), step=10.0, format="%.1f", key=f"ui_ts_G_CAMINOS_NV_{rp_rc}")
        with c2:
            ton_total = V['TON_TPTE_NV'] + V['TON_TPTE_PB'] + V['TON_TPTE_CS']
            ratio_cam = V['G_CAMINOS_NV'] / ton_total if ton_total > 0 else 0.0
            st.metric("USD/KTon", f"${ratio_cam:.2f}")

        fs1, fs2 = st.columns(2)
        with fs1:
            V['P_TPTE_SALES'] = st.number_input("Precio Tpte Sales (USD/TNitr)", value=round(V['P_TPTE_SALES'],4), step=0.1, format="%.4f", key=f"ui_P_TPTE_SALES_{rp_rc}")
        with fs2:
            V['FC_SALES'] = st.number_input("FC Consumo Sales (NaNO3/Ton)", value=float(f"{V['FC_SALES']:.6f}"), step=0.001, format="%.6f", key=f"ui_FC_SALES_{rp_rc}")
        st.caption(f"=> 1.1 Tpte Sales = ${V['P_TPTE_SALES']:.4f} × {V['FC_SALES']:.4f} = **${V['P_TPTE_SALES']*V['FC_SALES']:.4f} USD/T**")
        st.divider()

        
        if st.button(f"🔄 Restablecer valores REAL+PROY ({modo_sens})", use_container_width=True):
            st.session_state['rp_rc']      = st.session_state.get('rp_rc', 0) + 1
            st.session_state[sv_key]       = copy.deepcopy(BASE)
            st.session_state['sv_rp_mes']  = mes
            st.session_state['sv_rp_tipo'] = tipo_sens
            st.rerun()

    # ── PANEL RESULTADO ───────────────────────────────────────────────────────
    with col_res:
        costo_base, comp_base = recalcular(BASE)
        costo_sim,  comp_sim  = recalcular(V)
        delta_total = costo_sim - costo_base
 
        st.markdown(f"#### 📊 Resultado — {MESES[mes]}")
        st.metric("REAL + PROY BASE",       f"${costo_base:.2f} / T")
        st.metric("Simulado",        f"${costo_sim:.2f} / T",
                  delta=f"{delta_total:+.2f} USD/T", delta_color="inverse")
 
        st.divider()
        
        st.markdown("**Detalle por componente**")
 
        rows = []
        for k in comp_base:
            b, s = comp_base[k], comp_sim[k]
            rows.append({"Componente": k, "REAL+PROY": round(b,2), "Sim": round(s,2), "Δ": round(s-b,2)})
        df_det = pd.DataFrame(rows)
 
        def _col_delta(val):
            if isinstance(val, float):
                if val > 0: return 'color:#D83030;font-weight:bold'
                if val < 0: return 'color:#80BC00;font-weight:bold'
            return ''
 
        st.dataframe(
            df_det.style
                .map(_col_delta, subset=["Δ"])
                .format({"REAL+PROY":"{:.2f}", "Sim":"{:.2f}", "Δ":"{:+.2f}"}),
            use_container_width=True, hide_index=True, height=360,
        )
        st.divider()
        
        st.markdown("**R+P vs Simulado**")
        fig = go.Figure()
        nombres = list(comp_base.keys())
        v_base  = [comp_base[k] for k in nombres]
        v_sim   = [comp_sim[k]  for k in nombres]
        fig.add_trace(go.Bar(name="REAL + PROY",     x=v_base, y=nombres, orientation='h',
                             marker_color='#152578', text=[f"${v:.1f}" for v in v_base],
                             textposition='outside', textfont_size=9))
        fig.add_trace(go.Bar(name="Simulado", x=v_sim,  y=nombres, orientation='h',
                             marker_color=['#D83030' if s>b else '#80BC00' for b,s in zip(v_base,v_sim)],
                             text=[f"${v:.1f}" for v in v_sim],
                             textposition='outside', textfont_size=9))
        fig.update_layout(
            barmode='group', height=360,
            margin=dict(l=120, r=60, t=10, b=10),
            plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
            xaxis=dict(gridcolor='#333333'),
            yaxis=dict(autorange='reversed'),
            legend=dict(orientation='h', y=1.05),
        )
        st.plotly_chart(fig, use_container_width=True)

        # ══════════════════════════════════════════════════════════════════════════════
# ASISTENTE
# ══════════════════════════════════════════════════════════════════════════════
elif pagina == "Asistente":
    st.title("🤖 Asistente de Costeo Nitratos")
    st.caption("Pregunta sobre costos, producción o cualquier dato de la planilla 2026")

    def build_context():
        lines = ["# Datos Costeo Nitratos 2026\n"]
        for tipo in ["Puntual", "Acumulado"]:
            lines.append(f"\n## {tipo}")
            ppto = total_serie(df, tipo, 'PPTO')
            rp   = total_rp_serie(df, tipo)
            lines.append("### Costo Total USD/T")
            lines.append("Mes | PPTO | Real+Proy")
            lines.append("---|---|---")
            for i, m in enumerate(MESES):
                lines.append(f"{m} | {ppto[i]:.1f} | {rp[i]:.1f}")
            lines.append(f"\n### Por componente ({tipo})")
            for sa, c, nombre in COSTOS:
                s_p = gs(df, 'COSTO TOTAL', sa, c, tipo, 'PPTO')
                s_r = rp_serie(df, 'COSTO TOTAL', sa, c, tipo)
                lines.append(f"\n**{nombre}** (USD/T)")
                lines.append("Mes | PPTO | R+P")
                lines.append("---|---|---")
                for i, m in enumerate(MESES):
                    lines.append(f"{m} | {s_p[i]:.1f} | {s_r[i]:.1f}")
        return "\n".join(lines)

    context = build_context()

    if "messages" not in st.session_state:
        st.session_state["messages"] = []

    for msg in st.session_state["messages"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("Pregunta algo sobre los datos..."):
        st.session_state["messages"].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Analizando..."):
                try:
                    api_key = cargar_api_key() or st.secrets.get("ANTHROPIC_API_KEY", "")
                    client = anthropic.Anthropic(api_key=api_key)
                    response = client.messages.create(
                        model="claude-sonnet-4-20250514",
                        max_tokens=1024,
                        system=f"""Eres un asistente experto en costos de producción de nitratos.
Tienes acceso a todos los datos de la planilla de costeo 2026.
Responde en español, de forma clara y concisa.
Cuando menciones números usa siempre la unidad (USD/T, Kton, KUS).

DATOS DISPONIBLES:
{context}""",
                        messages=[
                            {"role": m["role"], "content": m["content"]}
                            for m in st.session_state["messages"]
                        ]
                    )
                    answer = response.content[0].text
                except Exception as e:
                    answer = f"Error al conectar con el asistente: {e}"

                st.markdown(answer)
                st.session_state["messages"].append({"role": "assistant", "content": answer})

    if st.session_state["messages"]:
        if st.button("🗑️ Limpiar conversación"):
            st.session_state["messages"] = []
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# PLAN INDUSTRIAL
# ══════════════════════════════════════════════════════════════════════════════

elif pagina == "Plan Industrial":
    from plan_industrial import render
    render(df)
    """
plan_industrial.py
ââââââââââââââââââ
P¡gina "Plan Industrial" para app.py de Costeo Nitratos.
 
INTEGRACIÃN (3 pasos):
1. En app.py sidebar agrega "Plan Industrial" a la lista del radio:
       pagina = st.radio("", ["Dashboard","Analisis mensual","Sensibilidad PPTO",
                              "Sensibilidad R+P","Plan Industrial","Asistente"], ...)
2. Al final de app.py, antes del elif "Asistente":
       elif pagina == "Plan Industrial":
           from plan_industrial import render
           render(df)
3. Este archivo va en la misma carpeta que app.py.
 
STANDALONE (prueba sin app.py):
       streamlit run plan_industrial.py
"""
 
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
 
# ââ Paleta dark âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
BG_DARK  = "#0d1117"
BG_CARD  = "#161b22"
BG_CARD2 = "#1c2128"
BORDER   = "#30363d"
TEXT_PRI = "#e6edf3"
TEXT_SEC = "#8b949e"
C_BLUE   = "#378ADD"
C_GREEN  = "#80BC00"
C_RED    = "#D83030"
C_ORANGE = "#D85A30"
 
COLORES_COMP = [
    "#5c85d6","#1D9E75","#7F77DD","#E8A838",
    "#639922","#5DCAA5","#D85A30","#D4537E",
    "#888780","#B4B2A9",
]
 
# ââ Datos embebidos del plan âââââââââââââââââââââââââââââââââââââââââââââââââââ
PERIODOS   = ["2026 (PPTO)","2026 R+P","2027","2028","2029","2030","2031","2032"]
PERIODOS_S = ["PP'26","Des'26","2027","2028","2029","2030","2031","2032"]
BASE_IDX   = 0
 
PLAN_COSTOS = {
    "Transporte":          [32.72,29.46,30.53,28.24,27.83,27.83,31.14,31.14],
    "Pozas":               [65.93,57.84,60.99,60.91,60.87,60.90,62.15,62.15],
    "CristalizaciÃ³n":      [121.08,109.36,112.01,112.24,112.24,112.24,113.77,113.77],
    "KCl":                 [178.76,173.63,183.56,191.10,196.81,199.67,199.49,199.49],
    "Terminados":          [59.81,54.84,56.15,55.85,55.34,55.28,54.40,54.40],
    "Tpte CS-TOC":         [11.56,11.09,11.09,11.09,11.09,11.09,11.09,11.09],
    "Puerto":              [22.59,18.09,19.19,19.07,18.85,18.82,18.45,18.45],
    "PÃ©rd. y FE":          [13.30,11.25,12.67,12.78,12.80,12.87,12.89,12.89],
    "Distributivos":       [83.16,77.84,82.37,82.63,82.63,82.63,84.55,84.55],
    "Ajuste otros gastos": [50.00,50.00,50.00,50.00,50.00,50.00,50.00,50.00],
}
 
PLAN_PROD = {
    "NPT III":   [474341,499846,477556,477556,477556,477556,460660,456300],
    "NPT II-IV": [227610,249353,230390,228190,228190,228190,229030,229030],
    "Terminados":[666480,725733,669011,674495,684329,685441,702910,732071],
}
 
PLAN_GASTOS = {
    "Total Tpte Sales":      [22652,22084,22084,22084,22084,22084,22084,22084],
    "OperaciÃ³n Pozas":       [46281,43333,43177,42987,42957,42980,42866,42866],
    "CristalizaciÃ³n":        [84995,81929,79298,79211,79211,79211,78463,78463],
    "NPT IV":                [28828,27441,26120,26033,26033,26033,26067,26067],
    "NPT III + Korda":       [39692,38472,37161,37161,37161,37161,36380,36380],
    "Terminados":            [39864,39799,37564,37674,37870,37893,38240,38240],
    "Trilado CS":            [5109,12849,11071,11084,11097,11109,11123,11123],
    "DTP":                   [1710,3718,3429,3430,3431,3432,3433,3433],
    "Secado KNO3":           [1603,13281,13113,13209,13391,13401,13734,13734],
    "Puerto + Tpte":         [27415,26506,25938,25999,26108,26120,26314,26314],
    "Distributivos + Depr.": [58372,58315,58315,58315,58315,58315,58315,58315],
}
 
PLAN_FC_NANO3 = {
    "Fc NaNO3 NPT3":       [1.333,1.319,1.333,1.332,1.332,1.332,1.352,1.371],
    "Fc NaNO3 cat 1 NPT3": [1.183,1.161,1.173,1.302,1.332,1.332,1.193,1.183],
    "Fc CS NPT3":          [0.050,0.099,0.100,0.030,0.000,0.000,0.150,0.170],
    "Fc PB NPT3":          [0.099,0.059,0.059,0.000,0.000,0.000,0.009,0.019],
    "Fc NaNO3 NPT4 LDTP":  [1.918,1.837,1.900,1.900,1.900,1.900,1.900,1.900],
    "Fc CS NPT4":          [1.198,1.157,1.200,1.200,1.200,1.200,1.200,1.200],
    "Fc Purga NPT4":       [0.719,0.680,0.700,0.700,0.700,0.700,0.700,0.700],
    "Fc consumo sales":    [1.294,1.271,1.292,1.242,1.241,1.241,1.274,1.274],
}
 
PLAN_FC_KCL = {
    "Fc KCl global NPT3":  [0.000,0.000,0.000,0.000,0.000,0.000,0.000,0.000],
    "Fc KCl fresco NPT3":  [0.871,0.859,0.860,0.860,0.860,0.860,0.860,0.860],
    "MOP-90":              [0.558,0.538,0.540,0.540,0.540,0.540,0.540,0.540],
    "MOP-70":              [0.228,0.273,0.240,0.240,0.240,0.240,0.240,0.240],
    "SS":                  [0.085,0.048,0.080,0.080,0.080,0.080,0.080,0.080],
    "Fc KCl global NPT4":  [0.000,0.000,0.000,0.000,0.000,0.000,0.000,0.000],
    "Fc KCl fresco NPT4":  [0.289,0.286,0.400,0.600,0.700,0.750,0.700,0.550],
    "MOP-90 NPT4":         [0.000,0.000,0.000,0.000,0.000,0.000,0.000,0.000],
    "MOP-70 NPT4":         [0.289,0.272,0.400,0.600,0.700,0.750,0.700,0.550],
    "SS NPT4":             [0.000,0.014,0.000,0.000,0.000,0.000,0.000,0.000],
}
 
PLAN_COSECHAS = {
    "Cosecha productiva":   [1791288,2036045,2036045,2036045,1944676,1543981,1558467],
    "Pozas SV":             [1133015,1486739,1486739,1571694,1484216,1129171,1149942],
    "Pozas PB":             [118804,85925,85925,0,0,0,0],
    "Pozas CS":             [539470,463381,463381,451193,460459,414810,408525],
    "Transporte salar a CS":[550000,550000,550000,550000,550000,550000,550000],
}
 
PLAN_PROD_TERM = {
    "ProducciÃ³n terminados":[669011,674495,684329,685441,702910,732071],
    "ProducciÃ³n Trilado":   [189824,190446,191083,191698,192361,193059],
    "ProducciÃ³n DTP":       [143209,143817,144428,145042,145659,146278],
    "ProducciÃ³n Secado":    [479187,484049,493246,493743,510549,539012],
}
 
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# CSS DARK
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
DARK_CSS = f"""
<style>
section.main > div {{background:{BG_DARK} !important}}
.stApp {{background:{BG_DARK} !important}}
.stTabs [data-baseweb="tab-list"] {{background:{BG_CARD};border-radius:8px;gap:2px}}
.stTabs [data-baseweb="tab"] {{color:{TEXT_SEC};padding:8px 18px;border-radius:6px}}
.stTabs [aria-selected="true"] {{background:{BG_CARD2};color:{TEXT_PRI} !important}}
.stExpander {{background:{BG_CARD} !important;border:1px solid {BORDER} !important;border-radius:8px}}
.stSelectbox > div > div {{background:{BG_CARD2} !important;color:{TEXT_PRI} !important;border-color:{BORDER} !important}}
.stNumberInput input {{background:{BG_CARD2} !important;color:{TEXT_PRI} !important;border-color:{BORDER} !important}}
.stSlider .st-bd {{background:{BORDER}}}
div[data-testid="metric-container"] {{background:{BG_CARD};border:1px solid {BORDER};border-radius:8px;padding:8px 14px}}
div[data-testid="metric-container"] label {{color:{TEXT_SEC} !important}}
div[data-testid="metric-container"] [data-testid="stMetricValue"] {{color:{TEXT_PRI} !important}}
.plan-tbl {{width:100%;border-collapse:collapse;font-size:11px;font-family:'Courier New',monospace}}
.plan-tbl th {{background:#1f2937;color:{TEXT_SEC};padding:4px 7px;border-bottom:1px solid {BORDER};white-space:nowrap;text-align:right}}
.plan-tbl th:first-child {{text-align:left}}
.plan-tbl td {{padding:3px 7px;border-bottom:1px solid #21262d;color:{TEXT_PRI};white-space:nowrap;text-align:right}}
.plan-tbl td:first-child {{text-align:left}}
.plan-tbl tr:hover td {{background:#1c2128}}
.plan-tbl .bold {{font-weight:700}}
.plan-tbl .neu {{color:{TEXT_SEC}}}
.pos {{color:{C_GREEN} !important;font-weight:600}}
.neg {{color:{C_RED} !important;font-weight:600}}
.neu {{color:{TEXT_SEC} !important}}
</style>
"""
 
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# HELPERS
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
def total_costo(costos, idx):
    return sum(v[idx] for v in costos.values() if idx < len(v))
 
 
def fmt_delta(val, decimals=1, invert=False):
    """Retorna (texto, clase_css)."""
    if abs(val) < 0.005:
        return "â", "neu"
    sign = "+" if val > 0 else ""
    txt  = f"{sign}{val:.{decimals}f}"
    worse = val > 0 if not invert else val < 0
    return txt, ("neg" if worse else "pos")
 
 
def kpi_card(label, value, delta_txt="", delta_cls="neu"):
    color_map = {"pos": C_GREEN, "neg": C_RED, "neu": TEXT_SEC}
    dc = color_map.get(delta_cls, TEXT_SEC)
    delta_html = f'<div style="font-size:11px;color:{dc};margin-top:2px">{delta_txt}</div>' if delta_txt else ""
    return f"""
    <div style="background:{BG_CARD};border:1px solid {BORDER};border-radius:10px;
         padding:10px 14px;text-align:center">
      <div style="font-size:10px;color:{TEXT_SEC};margin-bottom:4px;font-weight:600">{label}</div>
      <div style="font-size:19px;font-weight:700;color:{TEXT_PRI}">{value}</div>
      {delta_html}
    </div>"""
 
 
def tabla_plan_html(data, unidad, decimals=1, bold_rows=None, invert_delta=False,
                    periodos_mostrar=None):
    """HTML de tabla con Î vs PPTO 2026."""
    cols = periodos_mostrar or PERIODOS[1:]
    ths  = "<th>Concepto</th><th>Und</th>"
    ths += "".join(f"<th>{p}</th><th>Î</th>" for p in cols)
 
    rows_html = ""
    for nombre, vals in data.items():
        is_b  = bold_rows and nombre in bold_rows
        bcls  = " bold" if is_b else ""
        base_v = vals[BASE_IDX] if BASE_IDX < len(vals) else 0
        tds    = f'<td class="{bcls}">{nombre}</td><td class="neu">{unidad}</td>'
        for p in cols:
            pidx = PERIODOS.index(p) if p in PERIODOS else -1
            if pidx < 0 or pidx >= len(vals):
                tds += "<td>â</td><td>â</td>"
                continue
            val   = vals[pidx]
            delta = val - base_v
            vstr  = f"{val:,.{decimals}f}"
            dt, dc = fmt_delta(delta, decimals, invert=invert_delta)
            tds += f'<td class="{bcls}">{vstr}</td><td class="{dc}" style="font-size:10px">{dt}</td>'
        rows_html += f"<tr>{tds}</tr>"
 
    return (f'<div style="overflow-x:auto">'
            f'<table class="plan-tbl"><thead><tr>{ths}</tr></thead>'
            f'<tbody>{rows_html}</tbody></table></div>')
 
 
def mini_panel_detalle(titulo, comp_base, comp_sim):
    """Mini tabla de componentes para la cuadrÃ­cula del simulador."""
    filas = ""
    for k in comp_base:
        b  = comp_base[k]
        s  = comp_sim.get(k, b)
        dt, dc = fmt_delta(s - b)
        filas += (f'<tr><td style="color:{TEXT_PRI}">{k}</td>'
                  f'<td style="text-align:right;color:{TEXT_SEC}">{b:.2f}</td>'
                  f'<td style="text-align:right;color:{TEXT_PRI}">{s:.2f}</td>'
                  f'<td style="text-align:right" class="{dc}">{dt}</td></tr>')
    total_b = sum(comp_base.values())
    total_s = sum(comp_sim.values())
    dt_t, dc_t = fmt_delta(total_s - total_b)
    color_title = {"pos": C_GREEN, "neg": C_RED, "neu": TEXT_SEC}[dc_t]
    return f"""
    <div style="background:{BG_CARD};border:1px solid {BORDER};border-radius:7px;
         padding:8px;margin-bottom:6px;overflow-x:auto">
      <div style="font-size:11px;font-weight:700;color:{TEXT_PRI};margin-bottom:5px">
        {titulo}
        <span style="float:right;font-size:10px;color:{color_title}">Î {dt_t}</span>
      </div>
      <table style="width:100%;border-collapse:collapse;font-size:10px">
        <thead><tr>
          <th style="color:{TEXT_SEC};text-align:left;padding:2px 4px">Componente</th>
          <th style="color:{TEXT_SEC};text-align:right;padding:2px 4px">Plan</th>
          <th style="color:{TEXT_SEC};text-align:right;padding:2px 4px">Sim</th>
          <th style="color:{TEXT_SEC};text-align:right;padding:2px 4px">Î</th>
        </tr></thead>
        <tbody>{filas}</tbody>
      </table>
    </div>"""
 
 
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# GRÃFICOS
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
LAYOUT_DARK = dict(
    plot_bgcolor=BG_CARD, paper_bgcolor=BG_CARD,
    font=dict(color=TEXT_PRI, size=11),
    xaxis=dict(gridcolor="#21262d", tickfont=dict(color=TEXT_SEC)),
    yaxis=dict(gridcolor="#21262d", tickfont=dict(color=TEXT_SEC)),
    legend=dict(font=dict(color=TEXT_SEC), bgcolor=BG_CARD, bordercolor=BORDER),
    margin=dict(t=40, b=30, l=50, r=20),
)
 
 
def fig_linea_costo(sim_vals=None):
    n    = len(PERIODOS_S)
    plan = [total_costo(PLAN_COSTOS, i) for i in range(n)]
    fig  = go.Figure()
    fig.add_hline(y=plan[0], line_dash="dot", line_color=TEXT_SEC, line_width=1)
    fig.add_trace(go.Scatter(
        x=PERIODOS_S, y=plan, name="Plan",
        mode="lines+markers",
        line=dict(color=C_BLUE, width=2), marker=dict(size=6),
    ))
    if sim_vals:
        fig.add_trace(go.Scatter(
            x=PERIODOS_S, y=sim_vals, name="Simulado",
            mode="lines+markers",
            line=dict(color=C_ORANGE, width=2, dash="dash"),
            marker=dict(size=6, symbol="diamond"),
        ))
    ymin = min(min(plan), min(sim_vals) if sim_vals else min(plan)) * 0.97
    ymax = max(max(plan), max(sim_vals) if sim_vals else max(plan)) * 1.03
    fig.update_layout(
        title=dict(text="COSTO TOTAL US$/T â EVOLUCIÃN POR AÃO",
                   font=dict(color=TEXT_SEC, size=11)),
        height=280, **LAYOUT_DARK,
        yaxis=dict(gridcolor="#21262d", tickfont=dict(color=TEXT_SEC),
                   tickprefix="$", range=[ymin, ymax]),
    )
    return fig
 
 
def fig_desglose_bar(periodo_idx, sim_costos=None):
    data    = sim_costos or PLAN_COSTOS
    nombres = list(data.keys())
    vals    = [data[k][periodo_idx] if periodo_idx < len(data[k]) else 0 for k in nombres]
    fig = go.Figure(go.Bar(
        x=vals, y=nombres, orientation="h",
        marker_color=COLORES_COMP,
        text=[f"${v:.1f}" for v in vals],
        textposition="outside", textfont=dict(size=9, color=TEXT_SEC),
    ))
    fig.update_layout(
        title=dict(text="DESGLOSE DE COSTOS â AÃO SELECCIONADO",
                   font=dict(color=TEXT_SEC, size=11)),
        height=280, **LAYOUT_DARK,
        xaxis=dict(gridcolor="#21262d", tickfont=dict(color=TEXT_SEC), tickprefix="$"),
        yaxis=dict(gridcolor="rgba(0,0,0,0)", tickfont=dict(color=TEXT_PRI),
                   autorange="reversed"),
    )
    return fig
 
 
def fig_waterfall(ano_label, ano_idx, sim_costos=None):
    data   = sim_costos or PLAN_COSTOS
    base   = total_costo(data, BASE_IDX)
    deltas = {k: data[k][ano_idx] - data[k][BASE_IDX]
              for k in data if ano_idx < len(data[k])}
    total  = total_costo(data, ano_idx)
    xs     = ["PPTO 2026"] + list(deltas.keys()) + [ano_label]
    ys     = [base] + list(deltas.values()) + [total]
    fig = go.Figure(go.Waterfall(
        orientation="v",
        measure=["absolute"] + ["relative"] * len(deltas) + ["total"],
        x=xs, y=ys,
        text=[f"${v:.1f}" for v in ys],
        textposition="outside", textfont=dict(size=9, color=TEXT_SEC),
        connector=dict(line=dict(color=BORDER, width=0.5)),
        decreasing=dict(marker_color=C_GREEN),
        increasing=dict(marker_color=C_RED),
        totals=dict(marker_color=C_BLUE),
    ))
    fig.update_layout(
        title=dict(text=f"Puente PPTO 2026 â {ano_label}",
                   font=dict(color=TEXT_SEC, size=11)),
        height=340, **LAYOUT_DARK,
        xaxis=dict(gridcolor="#21262d", tickfont=dict(color=TEXT_SEC), tickangle=-25),
        yaxis=dict(gridcolor="#21262d", tickfont=dict(color=TEXT_SEC), tickprefix="$"),
    )
    return fig
 
 
def fig_comp_h(comp_base, comp_sim, titulo=""):
    nombres = list(comp_base.keys())
    vb = [comp_base[k] for k in nombres]
    vs = [comp_sim.get(k, comp_base[k]) for k in nombres]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Real+PROY / Plan", x=vb, y=nombres, orientation="h",
        marker_color=C_BLUE,
        text=[f"${v:.1f}" for v in vb], textposition="outside",
        textfont=dict(size=9, color=TEXT_SEC),
    ))
    fig.add_trace(go.Bar(
        name="Simulado", x=vs, y=nombres, orientation="h",
        marker_color=[C_RED if s > b else C_GREEN for b, s in zip(vb, vs)],
        text=[f"${v:.1f}" for v in vs], textposition="outside",
        textfont=dict(size=9, color=TEXT_SEC),
    ))
    fig.update_layout(
        title=dict(text=titulo, font=dict(color=TEXT_SEC, size=11)),
        barmode="group", height=340,
        **LAYOUT_DARK,
        margin=dict(l=130, r=70, t=35, b=10),
        xaxis=dict(gridcolor="#21262d", tickfont=dict(color=TEXT_SEC), tickprefix="$"),
        yaxis=dict(autorange="reversed", tickfont=dict(color=TEXT_PRI)),
        legend=dict(orientation="h", y=1.08),
    )
    return fig
 
 
def fig_tornado(pct):
    rows = [(k, -vals[BASE_IDX]*pct, vals[BASE_IDX]*pct)
            for k, vals in PLAN_COSTOS.items()]
    rows.sort(key=lambda x: x[2])
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name=f"-{pct*100:.0f}%", x=[r[1] for r in rows], y=[r[0] for r in rows],
        orientation="h", marker_color=C_GREEN,
        text=[f"{r[1]:+.1f}" for r in rows],
        textposition="outside", textfont=dict(size=9, color=TEXT_SEC),
    ))
    fig.add_trace(go.Bar(
        name=f"+{pct*100:.0f}%", x=[r[2] for r in rows], y=[r[0] for r in rows],
        orientation="h", marker_color=C_RED,
        text=[f"+{r[2]:.1f}" for r in rows],
        textposition="outside", textfont=dict(size=9, color=TEXT_SEC),
    ))
    fig.update_layout(
        title=dict(text=f"Sensibilidad Â±{pct*100:.0f}% â Î US$/T",
                   font=dict(color=TEXT_SEC, size=11)),
        barmode="overlay", height=380,
        **LAYOUT_DARK,
        margin=dict(l=150, r=70, t=40, b=20),
        xaxis=dict(gridcolor="#21262d", tickfont=dict(color=TEXT_SEC),
                   zeroline=True, zerolinecolor=TEXT_SEC),
        yaxis=dict(tickfont=dict(color=TEXT_PRI)),
    )
    return fig
 
 
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# RENDER PRINCIPAL
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
def render(df=None):
    st.html(DARK_CSS)
 
    # TÃ­tulo
    st.html(f"""
    <div style="background:{BG_CARD};border-left:4px solid {C_BLUE};
         padding:14px 20px;margin-bottom:16px;border-radius:0 8px 8px 0">
      <span style="color:{TEXT_PRI};font-size:26px;font-weight:800;letter-spacing:1px">
        PLAN INDUSTRIAL
      </span>
      <span style="color:{TEXT_SEC};font-size:12px;margin-left:16px">
        Nitratos 2026â2032 Â· deltas vs PPTO 2026
      </span>
    </div>""")
 
    tab_dash, tab_sim, tab_tablas, tab_sens = st.tabs([
        "ð Dashboard",
        "ð§ Simulador",
        "ð Tablas completas",
        "ð Sensibilidad",
    ])
 
    # âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    # TAB 1 ââ DASHBOARD
    # âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    with tab_dash:
        # Selector de perÃ­odo como botones
        st.html(f'<div style="font-size:10px;color:{TEXT_SEC};font-weight:700;'
                f'letter-spacing:.08em;margin-bottom:6px">PERIODO</div>')
 
        if "dash_per" not in st.session_state:
            st.session_state["dash_per"] = 0
 
        btn_cols = st.columns(len(PERIODOS))
        for i, (col, per) in enumerate(zip(btn_cols, PERIODOS)):
            with col:
                if st.button(per, key=f"dp_{i}",
                             type="primary" if i == st.session_state["dash_per"] else "secondary",
                             use_container_width=True):
                    st.session_state["dash_per"] = i
                    st.rerun()
 
        per_idx    = st.session_state["dash_per"]
        c_sel      = total_costo(PLAN_COSTOS, per_idx)
        c_base     = total_costo(PLAN_COSTOS, BASE_IDX)
        dc_t, dcl  = fmt_delta(c_sel - c_base)
        npt3_v     = PLAN_PROD["NPT III"][per_idx]
        npt4_v     = PLAN_PROD["NPT II-IV"][per_idx]
        term_v     = PLAN_PROD["Terminados"][per_idx]
        dn3, dcn3  = fmt_delta(npt3_v - PLAN_PROD["NPT III"][BASE_IDX], 0, invert=True)
        dn4, dcn4  = fmt_delta(npt4_v - PLAN_PROD["NPT II-IV"][BASE_IDX], 0, invert=True)
        dt_, dct_  = fmt_delta(term_v - PLAN_PROD["Terminados"][BASE_IDX], 0, invert=True)
 
        st.html('<div style="height:8px"></div>')
        kpi_cols = st.columns(5)
        kpis = [
            ("PERIODO",         PERIODOS[per_idx], "", "neu"),
            ("COSTO USD/TON",   f"${c_sel:.0f}",   f"{dc_t} vs PPTO", dcl),
            ("PROD NPT3",       f"{npt3_v:,} t",   f"{dn3} vs PPTO",  dcn3),
            ("PROD NPT4",       f"{npt4_v:,} t",   f"{dn4} vs PPTO",  dcn4),
            ("PROD TERMINADOS", f"{term_v:,} t",   f"{dt_} vs PPTO",  dct_),
        ]
        for col, (lbl, val, dtext, dcls) in zip(kpi_cols, kpis):
            with col:
                st.html(kpi_card(lbl, val, dtext, dcls))
 
        st.html('<div style="height:10px"></div>')
 
        g1, g2 = st.columns(2)
        with g1:
            st.plotly_chart(fig_linea_costo(), use_container_width=True)
        with g2:
            c2a, c2b = st.columns([3, 1])
            with c2a:
                st.html(f'<div style="font-size:11px;color:{TEXT_SEC};'
                        f'font-weight:600;margin-bottom:4px">DESGLOSE DE COSTOS â AÃO SELECCIONADO</div>')
            with c2b:
                yr_pick = st.selectbox("AÃ±o:", PERIODOS, index=per_idx,
                                       key="dash_yr_bar", label_visibility="collapsed")
            st.plotly_chart(fig_desglose_bar(PERIODOS.index(yr_pick)),
                            use_container_width=True)
 
        # Tabla delta rÃ¡pida
        st.html(f'<div style="font-size:11px;color:{TEXT_SEC};font-weight:600;'
                f'margin:8px 0 4px">Indicadores US$/T â Î vs PPTO 2026</div>')
        cols_mostrar = [p for p in PERIODOS if p != "2026 (PPTO)"]
        st.html(tabla_plan_html(PLAN_COSTOS, "US$/T", decimals=1,
                                periodos_mostrar=cols_mostrar))
 
    # âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    # TAB 2 ââ SIMULADOR
    # âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    with tab_sim:
        st.html(f"""
        <div style="background:{BG_CARD};border-left:4px solid {C_ORANGE};
             padding:10px 16px;margin-bottom:12px;border-radius:0 8px 8px 0">
          <span style="font-size:15px;font-weight:700;color:{TEXT_PRI}">
            SIMULADOR DE SENSIBILIDAD - PLAN INDUSTRIAL
          </span>
          <span style="font-size:11px;color:{TEXT_SEC};margin-left:10px">
            Edita cualquier valor Â· los paneles recalculan en tiempo real Â· Î vs PPTO 2026
          </span>
        </div>""")
 
        hc1, hc2 = st.columns([2, 2])
        with hc1:
            ano_sim = st.selectbox("AÃ±o a simular",
                                   [p for p in PERIODOS if p != "2026 (PPTO)"],
                                   key="sim_ano_sel")
        with hc2:
            comp_ref = st.radio("Î comparar contra",
                                ["PPTO 2026", "AÃ±o anterior"],
                                horizontal=True, key="sim_ref")
 
        ano_idx      = PERIODOS.index(ano_sim)
        comp_ref_idx = BASE_IDX if comp_ref == "PPTO 2026" else max(0, ano_idx - 1)
 
        # Session state â copias editables
        sk = f"simC_{ano_sim}"
        sp = f"simP_{ano_sim}"
        if sk not in st.session_state:
            st.session_state[sk] = {k: list(v) for k, v in PLAN_COSTOS.items()}
        if sp not in st.session_state:
            st.session_state[sp] = {k: list(v) for k, v in PLAN_PROD.items()}
        simC = st.session_state[sk]
        simP = st.session_state[sp]
 
        # ââ Layout: tabla left | cuadrÃ­cula paneles right ââââââââââââââââââââ
        col_tabla, col_paneles = st.columns([3, 4], gap="medium")
 
        with col_tabla:
            st.html(f'<div style="font-size:11px;color:{TEXT_SEC};font-weight:700;'
                    f'margin-bottom:4px">FC NaNO3</div>')
            st.html(tabla_plan_html(PLAN_FC_NANO3, "NaNO3/T", decimals=2,
                                    periodos_mostrar=PERIODOS[2:]))
            st.html('<div style="height:6px"></div>')
            st.html(f'<div style="font-size:11px;color:{TEXT_SEC};font-weight:700;'
                    f'margin-bottom:4px">FC KCl</div>')
            st.html(tabla_plan_html(PLAN_FC_KCL, "KCl/KNO3", decimals=2,
                                    periodos_mostrar=PERIODOS[2:]))
            st.html('<div style="height:6px"></div>')
            st.html(f'<div style="font-size:11px;color:{TEXT_SEC};font-weight:700;'
                    f'margin-bottom:4px">Cosechas productivas (ton)</div>')
            st.html(tabla_plan_html(PLAN_COSECHAS, "ton", decimals=0,
                                    invert_delta=True, periodos_mostrar=PERIODOS[2:7]))
            st.html('<div style="height:6px"></div>')
            st.html(f'<div style="font-size:11px;color:{TEXT_SEC};font-weight:700;'
                    f'margin-bottom:4px">ProducciÃ³n terminados (ton)</div>')
            st.html(tabla_plan_html(PLAN_PROD_TERM, "ton", decimals=0,
                                    invert_delta=True, periodos_mostrar=PERIODOS[2:8]))
 
        with col_paneles:
            # 6 mini paneles 2Ã3 con costos de cada aÃ±o
            anos_paneles = ["2027","2028","2029","2030","2031","2032"]
            r1 = st.columns(3)
            r2 = st.columns(3)
            panel_grid = [*r1, *r2]
            for pc, ap in zip(panel_grid, anos_paneles):
                with pc:
                    aidx = PERIODOS.index(ap) if ap in PERIODOS else -1
                    if aidx < 0:
                        continue
                    # comp_b = plan base del aÃ±o; comp_s = simulado si es el aÃ±o editado
                    cb = {k: PLAN_COSTOS[k][aidx] for k in PLAN_COSTOS}
                    cs = ({k: simC[k][aidx] for k in simC}
                          if ap == ano_sim else cb)
                    st.html(mini_panel_detalle(ap, cb, cs))
 
            st.html('<div style="height:8px"></div>')
            # ââ Inputs de simulaciÃ³n ââââââââââââââââââââââââââââââââââââââââ
            st.html(f'<div style="font-size:12px;font-weight:700;color:{TEXT_PRI};'
                    f'margin-bottom:8px">Editar costos â {ano_sim} (US$/T)</div>')
 
            for nombre in PLAN_COSTOS:
                ref_v  = PLAN_COSTOS[nombre][comp_ref_idx]
                plan_v = PLAN_COSTOS[nombre][ano_idx]
                cur_v  = simC[nombre][ano_idx]
 
                ic1, ic2, ic3 = st.columns([3, 1, 1])
                with ic1:
                    nuevo = st.number_input(
                        nombre, value=float(f"{cur_v:.2f}"),
                        step=0.5, format="%.2f",
                        key=f"si_c_{nombre}_{ano_sim}",
                    )
                    simC[nombre][ano_idx] = nuevo
                with ic2:
                    dv, dc = fmt_delta(nuevo - ref_v)
                    col_d = C_GREEN if dc == "pos" else (C_RED if dc == "neg" else TEXT_SEC)
                    st.html(f'<p style="margin-top:28px;color:{col_d};font-size:12px;'
                            f'font-weight:700">{dv}</p>')
                with ic3:
                    st.html(f'<p style="margin-top:28px;color:{TEXT_SEC};font-size:10px">'
                            f'Plan:<br>{plan_v:.1f}</p>')
 
            st.html(f'<div style="font-size:12px;font-weight:700;color:{TEXT_PRI};'
                    f'margin:10px 0 6px">Editar producciÃ³n â {ano_sim} (ton)</div>')
            for grp in ["NPT III","NPT II-IV","Terminados"]:
                ref_pv = PLAN_PROD[grp][comp_ref_idx]
                cur_pv = simP[grp][ano_idx]
                pc1, pc2 = st.columns([3, 1])
                with pc1:
                    np_ = st.number_input(grp, value=float(f"{cur_pv:.0f}"),
                                          step=1000.0, format="%.0f",
                                          key=f"si_p_{grp}_{ano_sim}")
                    simP[grp][ano_idx] = np_
                with pc2:
                    dv, dc = fmt_delta(np_ - ref_pv, 0, invert=True)
                    col_d = C_GREEN if dc == "pos" else (C_RED if dc == "neg" else TEXT_SEC)
                    st.html(f'<p style="margin-top:28px;color:{col_d};font-size:12px;'
                            f'font-weight:700">{dv}</p>')
 
            if st.button("ð Restablecer", key="reset_sim", use_container_width=True):
                for k_del in [sk, sp]:
                    if k_del in st.session_state:
                        del st.session_state[k_del]
                st.rerun()
 
        # ââ GrÃ¡fico lÃ­nea temporal + comparativo âââââââââââââââââââââââââââââ
        sim_line = [total_costo(simC, i) for i in range(len(PERIODOS))]
        st.plotly_chart(fig_linea_costo(sim_vals=sim_line), use_container_width=True)
 
        wf1, wf2 = st.columns(2)
        with wf1:
            st.plotly_chart(fig_waterfall(ano_sim, ano_idx, simC),
                            use_container_width=True)
        with wf2:
            cb = {k: PLAN_COSTOS[k][comp_ref_idx] for k in PLAN_COSTOS}
            cs = {k: simC[k][ano_idx] for k in simC}
            st.plotly_chart(fig_comp_h(cb, cs, f"Plan vs Simulado â {ano_sim}"),
                            use_container_width=True)
 
    # âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    # TAB 3 ââ TABLAS COMPLETAS
    # âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    with tab_tablas:
        secciones = [
            ("Indicadores de costo (US$/T)", PLAN_COSTOS, "US$/T", 1, False),
            ("Producciones (ton)", PLAN_PROD, "ton", 0, True),
            ("FC NaNO3", PLAN_FC_NANO3, "NaNO3/T", 3, False),
            ("FC KCl", PLAN_FC_KCL, "KCl/KNO3", 3, False),
            ("Gasto total estimado (KUS)", PLAN_GASTOS, "KUS", 0, False),
            ("Cosechas productivas (ton)", PLAN_COSECHAS, "ton", 0, True),
            ("ProducciÃ³n terminados (ton)", PLAN_PROD_TERM, "ton", 0, True),
        ]
        cols_all = [p for p in PERIODOS if p != "2026 (PPTO)"]
        for titulo, data, unidad, decs, inv in secciones:
            with st.expander(f"â¶  {titulo}", expanded=True):
                st.html(tabla_plan_html(data, unidad, decimals=decs,
                                        invert_delta=inv,
                                        periodos_mostrar=cols_all))
 
    # âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    # TAB 4 ââ SENSIBILIDAD
    # âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    with tab_sens:
        pc, _ = st.columns([2, 6])
        with pc:
            pct = st.slider("VariaciÃ³n Â±%", 1, 30, 10, key="sens_pct_pi") / 100
 
        st.plotly_chart(fig_tornado(pct), use_container_width=True)
 
        # Heatmap delta
        st.html(f'<div style="font-size:13px;font-weight:600;color:{TEXT_PRI};'
                f'margin:12px 0 6px">Î US$/T por componente vs PPTO 2026</div>')
        anos_hm = PERIODOS[1:]
        matrix  = [
            [PLAN_COSTOS[k][i] - PLAN_COSTOS[k][BASE_IDX]
             for i in range(1, len(PERIODOS))]
            for k in PLAN_COSTOS
        ]
        fig_hm = go.Figure(go.Heatmap(
            z=matrix, x=anos_hm, y=list(PLAN_COSTOS.keys()),
            colorscale=[[0, C_GREEN],[0.5, BG_CARD2],[1, C_RED]],
            zmid=0,
            text=[[f"{v:+.1f}" for v in row] for row in matrix],
            texttemplate="%{text}", textfont=dict(size=10, color=TEXT_PRI),
            colorbar=dict(title="Î US$/T", tickfont=dict(color=TEXT_SEC)),
        ))
        fig_hm.update_layout(
            height=360, **LAYOUT_DARK,
            margin=dict(l=160, r=40, t=30, b=40),
            xaxis=dict(side="top", tickfont=dict(color=TEXT_SEC)),
            yaxis=dict(tickfont=dict(color=TEXT_PRI)),
        )
        st.plotly_chart(fig_hm, use_container_width=True)
 
        # Waterfall interactivo
        st.html(f'<div style="font-size:13px;font-weight:600;color:{TEXT_PRI};'
                f'margin:12px 0 6px">Puente de costo por aÃ±o seleccionado</div>')
        wf_ano = st.selectbox("AÃ±o destino (vs PPTO 2026)",
                              PERIODOS[1:], key="wf_ano_sens")
        wf_idx = PERIODOS.index(wf_ano)
        st.plotly_chart(fig_waterfall(wf_ano, wf_idx), use_container_width=True)
 
 
# ââ Standalone ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
if __name__ == "__main__":
    st.set_page_config(
        page_title="Plan Industrial â Nitratos",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    render()
 