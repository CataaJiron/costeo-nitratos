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
    pagina = st.radio("", ["Dashboard", "Analisis mensual", "Sensibilidad PPTO", "Sensibilidad R+P", "Sim. Gastos PPTO", "Gastos por Área", "Asistente","Simulacion 2"],
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
        #NPT3
        'FC_MOP90_NPT3': _r('KCl','Fc KCl NPT3','MOP 90', nth=0),
        'FC_MOP70_NPT3': _r('KCl','Fc KCl NPT3','MOP 70', nth=0),
        'FC_SS_NPT3':    _r('KCl','Fc KCl NPT3','SS', nth=0),
        #NPT4
        'FC_MOP90_NPT4': _r('KCl','Fc KCl NPT4','MOP 90', nth=0),
        'FC_MOP70_NPT4': _r('KCl','Fc KCl NPT4','MOP 70', nth=0),
        'FC_SS_NPT4':    _r('KCl','Fc KCl NPT4','SS', nth=0),
        
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
        #NPT3
        'FC_NaNO3_CAT1_NPT3': _r('FC NaNO3','NPT3','CAT1'),
        'FC_NaNO3_CS_NPT3': _r('FC NaNO3','NPT3','CS'),        
        'FC_NaNO3_PB_NPT3': _r('FC NaNO3','NPT3','PB'),
        #NPT4
        'FC_NaNO3_CS_NPT4': _r('FC NaNO3','NPT4','CS'),
        'FC_NaNO3_PB_NPT4': _r('FC NaNO3','NPT4','PB'),        
        'FC_NaNO3_PB_CSSI_NPT4': _r('FC NaNO3','NPT4','PB CSSI'),
        'FC_NaNO3_CAT1_CSSI_NPT4': _r('FC NaNO3','NPT4','CAT1 CSSI'),        
        'FC_NaNO3_CAT1_CSSR_NPT4': _r('FC NaNO3','NPT4','CAT1 CSSR'),
        'FC_NaNO3_PURGA_NPT4': _r('FC NaNO3','NPT4','FC PURGA'),        


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
        CAT1_NPT3 = npt3 * v['FC_NaNO3_CAT1_NPT3']
        CAT1_CSSR = v['FC_NaNO3_CAT1_CSSR_NPT4'] * v['CSSR_NPT4']
        CAT1_CSSI = v['CSSI_NPT4'] * v['FC_NaNO3_CAT1_CSSI_NPT4']
        PB_NPT3 = npt3 * v['FC_NaNO3_PB_NPT3']
        PB_CSSI = v['CSSI_NPT4'] * v['FC_NaNO3_PB_CSSI_NPT4']
        PB_NPT4 = v['KNO3_L_NPT4'] * v['FC_NaNO3_PB_NPT4']
        CS_NPT3 = npt3 * v['FC_NaNO3_CS_NPT3'] 
        CS_NPT4 = v['KNO3_L_NPT4'] * v['FC_NaNO3_CS_NPT4']

        consumo_nv = CAT1_NPT3 + CAT1_CSSI + CAT1_CSSR 
        consumo_pb = PB_NPT3 + PB_NPT4 + PB_CSSI
        consumo_cs = CS_NPT3 + CS_NPT4
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
        MOP90_NPT3 = (v['FC_MOP90_NPT3'] * npt3)
        MOP90_NPT4 = (v['FC_MOP90_NPT4'] * v['KNO3_L_NPT4'])
        MOP70_NPT3 = (v['FC_MOP70_NPT3'] * npt3)
        MOP70_NPT4 = (v['FC_MOP70_NPT4'] * v['KNO3_L_NPT4'])
        SS_NPT3 = (v['FC_SS_NPT3'] * npt3) 
        SS_NPT4 = (v['FC_SS_NPT4'] * v['KNO3_L_NPT4'])

        #CONSUMO
        cons_mop90 = MOP90_NPT3 + MOP90_NPT4
        cons_mop70 = MOP70_NPT3 + MOP70_NPT4
        cons_ss    = SS_NPT3 + SS_NPT4
        
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
        st.markdown("#### Producción (Kton)")
 
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
        st.markdown("#### Gastos Pozas (KUS) → USD/T sobre NPT3+NPT4")
        st.caption("Gasto (KUS)  |  — denominador: prod total —  |  USD/T resultante")
 
        for lbl, key in [("NV", "G_POZAS_NV"), ("CS", "G_POZAS_CS"), ("PB", "G_POZAS_PB")]:
            c1, c2 = st.columns([3, 1])
            with c1:
                V[key] = st.number_input(f"Gasto Pozas {lbl} (KUS)", value=round(V[key],2), step=10.0, format="%.2f", key=f"ui_{key}_{rc}")
            with c2:
                st.metric("USD/T", f"${V[key]/prod_total_v:.2f}" if prod_total_v > 0 else "-")
 
        tot_pozas = V['G_POZAS_NV']+V['G_POZAS_CS']+V['G_POZAS_PB']+V['G_DEPRECIACION_CS']
        st.caption(f"📌 Total Pozas (incl. depr. CS ${V['G_DEPRECIACION_CS']:.0f} KUS fija): **${tot_pozas:.1f} KUS** → **${tot_pozas/prod_total_v:.2f} USD/T**" if prod_total_v > 0 else "")
 
        st.divider()
 
        # ─── GASTOS PLANTAS ───────────────────────────────────────────────────
        st.markdown("#### Gastos Plantas (KUS)")
 
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
        st.markdown("#### Puerto — Gasto (KUS) | Toneladas (Kton) | USD/T")

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
        st.markdown("#### Transporte Terminados — KUS | Kton | USD/T")
        
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
        st.markdown("#### Factor Consumo KCl (KTon KCl / Kton prod)")
 
        npt3_v2 = V['KNO3_T_NPT3'] + V['KNO3_R_NPT3']
        npt4_v2 = V['KNO3_L_NPT4'] + V['CSSI_NPT4'] + V['CSSR_NPT4']
 
        st.caption("NPT3")
        fck1, fck2, fck3 = st.columns(3)
        with fck1: V['FC_MOP90_NPT3'] = st.number_input("MOP 90 NPT3", value=float(f"{V['FC_MOP90_NPT3']:.6f}"), step=0.001, format="%.6f", key=f"ui_FC_MOP90_NPT3_{rc}")
        with fck2: V['FC_MOP70_NPT3'] = st.number_input("MOP 70 NPT3", value=float(f"{V['FC_MOP70_NPT3']:.6f}"), step=0.001, format="%.6f", key=f"ui_FC_MOP70_NPT3_{rc}")
        with fck3: V['FC_SS_NPT3']    = st.number_input("SS NPT3",     value=float(f"{V['FC_SS_NPT3']:.6f}"),    step=0.001, format="%.6f", key=f"ui_FC_SS_NPT3_{rc}")
 
        cons3 = (V['FC_MOP90_NPT3']+V['FC_MOP70_NPT3']+V['FC_SS_NPT3'])
        st.caption(f"KCl fresco NPT3: {cons3:.2f} KTon")
 
        st.caption("NPT4")
        fck4, fck5, fck6 = st.columns(3)
        with fck4: V['FC_MOP90_NPT4'] = st.number_input("MOP 90 NPT4", value=float(f"{V['FC_MOP90_NPT4']:.6f}"), step=0.001, format="%.6f", key=f"ui_FC_MOP90_NPT4_{rc}")
        with fck5: V['FC_MOP70_NPT4'] = st.number_input("MOP 70 NPT4", value=float(f"{V['FC_MOP70_NPT4']:.6f}"), step=0.001, format="%.6f", key=f"ui_FC_MOP70_NPT4_{rc}")
        with fck6: V['FC_SS_NPT4']    = st.number_input("SS NPT4",     value=float(f"{V['FC_SS_NPT4']:.6f}"),    step=0.001, format="%.6f", key=f"ui_FC_SS_NPT4_{rc}")
 
        cons4 = (V['FC_MOP90_NPT4']+V['FC_MOP70_NPT4']+V['FC_SS_NPT4'])
        st.caption(f"KCl fresco NPT4: {cons4:.2f} KTon")
 
        st.caption("Precio KCl (US$/T)")
        pk1, pk2, pk3 = st.columns(3)
        with pk1: V['P_MOP90'] = st.number_input("MOP 90", value=round(V['P_MOP90'],2), step=1.0, format="%.2f", key=f"ui_P_MOP90_{rc}")
        with pk2: V['P_MOP70'] = st.number_input("MOP 70", value=round(V['P_MOP70'],2), step=1.0, format="%.2f", key=f"ui_P_MOP70_{rc}")
        with pk3: V['P_SS']    = st.number_input("SS",     value=round(V['P_SS'],2),    step=1.0, format="%.2f", key=f"ui_P_SS_{rc}")
 
        st.divider()
 
        # ─── FC NaNO3 ────────────────────────────────────────────
        st.markdown("#### FC NaNO3")

        st.caption("NPT3")
        fn1, fn2, fn3 = st.columns(3)
        with fn1: V['FC_NaNO3_CAT1_NPT3']      = st.number_input("CAT1",    value=float(f"{V['FC_NaNO3_CAT1_NPT3']:.4f}"),      step=0.01, format="%.4f", key=f"ui_fc_cat1_npt3_{rc}")
        with fn2: V['FC_NaNO3_PB_NPT3']        = st.number_input("PB",      value=float(f"{V['FC_NaNO3_PB_NPT3']:.4f}"),        step=0.01, format="%.4f", key=f"ui_fc_pb_npt3_{rc}")
        with fn3: V['FC_NaNO3_CS_NPT3']        = st.number_input("CS",      value=float(f"{V['FC_NaNO3_CS_NPT3']:.4f}"),        step=0.01, format="%.4f", key=f"ui_fc_cs_npt3_{rc}")

        st.caption("NPT4")
        fn4, fn5, fn6, fn7, fn8 = st.columns(5)
        with fn4: V['FC_NaNO3_CS_NPT4']        = st.number_input("CS",          value=float(f"{V['FC_NaNO3_CS_NPT4']:.4f}"),        step=0.01, format="%.4f", key=f"ui_fc_cs_npt4_{rc}")
        with fn5: V['FC_NaNO3_PB_CSSI_NPT4']   = st.number_input("PB CSSI",     value=float(f"{V['FC_NaNO3_PB_CSSI_NPT4']:.4f}"),   step=0.01, format="%.4f", key=f"ui_fc_pb_cssi_{rc}")
        with fn6: V['FC_NaNO3_CAT1_CSSI_NPT4'] = st.number_input("CAT1 CSSI",   value=float(f"{V['FC_NaNO3_CAT1_CSSI_NPT4']:.4f}"), step=0.01, format="%.4f", key=f"ui_fc_cat1_cssi_{rc}")
        with fn7: V['FC_NaNO3_CAT1_CSSR_NPT4'] = st.number_input("CAT1 CSSR",   value=float(f"{V['FC_NaNO3_CAT1_CSSR_NPT4']:.4f}"), step=0.01, format="%.4f", key=f"ui_fc_cat1_cssr_{rc}")
        with fn8: V['FC_NaNO3_PURGA_NPT4']     = st.number_input("FC Purga",    value=float(f"{V['FC_NaNO3_PURGA_NPT4']:.4f}"),     step=0.01, format="%.4f", key=f"ui_fc_purga_{rc}")

        npt3_fc = V['KNO3_T_NPT3'] + V['KNO3_R_NPT3']
        consumo_nv_v = (npt3_fc * V['FC_NaNO3_CAT1_NPT3']
                        + V['CSSR_NPT4'] * V['FC_NaNO3_CAT1_CSSR_NPT4']
                        + V['CSSI_NPT4'] * V['FC_NaNO3_CAT1_CSSI_NPT4'])
        consumo_pb_v = (npt3_fc * V['FC_NaNO3_PB_NPT3']
                        + V['CSSI_NPT4'] * V['FC_NaNO3_PB_CSSI_NPT4'])
        consumo_cs_v = V['KNO3_L_NPT4'] * V['FC_NaNO3_CS_NPT4']
        consumo_tot_v = consumo_nv_v + consumo_pb_v + consumo_cs_v
        prod_total_ts = (V['KNO3_T_NPT3']+V['KNO3_R_NPT3']) + (V['KNO3_L_NPT4']+V['CSSI_NPT4']+V['CSSR_NPT4'])
        fc_v = consumo_tot_v / prod_total_ts if prod_total_ts > 0 else 0.0

        ton_trans = V['TON_TPTE_NV'] + V['TON_TPTE_PB'] + V['TON_TPTE_CS']
        precio_tot_v = (V['G_TPTE_NV'] + V['G_TPTE_PB'] + V['G_CAMINOS_NV']) / ton_trans if ton_trans > 0 else 0.0
        c11_preview = precio_tot_v * fc_v
        st.caption(f"Consumo NV: {consumo_nv_v:.3f} | PB: {consumo_pb_v:.3f} | CS: {consumo_cs_v:.3f} Kton")
        #st.caption(f"FC total: {fc_v:.4f} | Precio tpte: ${precio_tot_v:.2f} | **=> 1.1 Tpte Sales = ${c11_preview:.2f} USD/T**")


        # ───Tpte Sales ────────────────────────────────────────────
        st.markdown("#### Transporte de Sales")

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

        #fs1 = st.columns(2)
        #with fs1:
        #    V['P_TPTE_SALES'] = st.number_input("Precio Tpte Sales (USD/TNitr)", value=round(V['P_TPTE_SALES'],4), step=0.1, format="%.4f", key=f"ui_P_TPTE_SALES_{rc}")
        #with fs2:
        #    V['FC_SALES'] = st.number_input("FC Consumo Sales (NaNO3/Ton)", value=float(f"{V['FC_SALES']:.6f}"), step=0.001, format="%.6f", key=f"ui_FC_SALES_{rc}")
        #st.caption(f"=> 1.1 Tpte Sales = ${V['P_TPTE_SALES']:.4f} × {V['FC_SALES']:.4f} = **${V['P_TPTE_SALES']*V['FC_SALES']:.4f} USD/T**")
 
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
        delta_display = 0.0 if abs(delta_total) < 0.005 else round(delta_total, 1)
        delta_str = "0.00 USD/T" if delta_display == 0.0 else f"{delta_display:+.1f} USD/T"

        st.markdown(f"#### 📊 Resultado — {MESES[mes]}")
        st.metric("PPTO Base",   f"${costo_base:.1f} / T")
        st.metric("Simulado",    f"${costo_sim:.1f} / T",
                  delta=delta_str, delta_color="inverse")
 
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
        # FC KCl (adimensional: KTon KCl / Kton prod)
        'FC_MOP90_NPT3': _r('KCl','Fc KCl NPT3','MOP 90', nth=0),
        'FC_MOP70_NPT3': _r('KCl','Fc KCl NPT3','MOP 70', nth=0),
        'FC_SS_NPT3':    _r('KCl','Fc KCl NPT3','SS', nth=0),
        'FC_MOP90_NPT4': _r('KCl','Fc KCl NPT4','MOP 90', nth=0),
        'FC_MOP70_NPT4': _r('KCl','Fc KCl NPT4','MOP 70', nth=0),
        'FC_SS_NPT4':    _r('KCl','Fc KCl NPT4','SS', nth=0),

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
        #NPT3
        'FC_NaNO3_CAT1_NPT3': _r('FC NaNO3','NPT3','CAT1'),
        'FC_NaNO3_CS_NPT3': _r('FC NaNO3','NPT3','CS'),        
        'FC_NaNO3_PB_NPT3': _r('FC NaNO3','NPT3','PB'),
        #NPT4
        'FC_NaNO3_CS_NPT4': _r('FC NaNO3','NPT4','CS'),
        'FC_NaNO3_PB_NPT4': _r('FC NaNO3','NPT4','PB'),        
        'FC_NaNO3_PB_CSSI_NPT4': _r('FC NaNO3','NPT4','PB CSSI'),
        'FC_NaNO3_CAT1_CSSI_NPT4': _r('FC NaNO3','NPT4','CAT1 CSSI'),        
        'FC_NaNO3_CAT1_CSSR_NPT4': _r('FC NaNO3','NPT4','CAT1 CSSR'),
        'FC_NaNO3_PURGA_NPT4': _r('FC NaNO3','NPT4','FC PURGA'),
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
        CAT1_NPT3 = npt3 * v['FC_NaNO3_CAT1_NPT3']
        CAT1_CSSR = v['FC_NaNO3_CAT1_CSSR_NPT4'] * v['CSSR_NPT4']
        CAT1_CSSI = v['CSSI_NPT4'] * v['FC_NaNO3_CAT1_CSSI_NPT4']
        PB_NPT3 = npt3 * v['FC_NaNO3_PB_NPT3']
        PB_CSSI = v['CSSI_NPT4'] * v['FC_NaNO3_PB_CSSI_NPT4']
        PB_NPT4 = v['KNO3_L_NPT4'] * v['FC_NaNO3_PB_NPT4']
        CS_NPT3 = npt3 * v['FC_NaNO3_CS_NPT3'] 
        CS_NPT4 = v['KNO3_L_NPT4'] * v['FC_NaNO3_CS_NPT4']

        consumo_nv = CAT1_NPT3 + CAT1_CSSI + CAT1_CSSR 
        consumo_pb = PB_NPT3 + PB_NPT4 + PB_CSSI
        consumo_cs = CS_NPT3 + CS_NPT4
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
        MOP90_NPT3 = (v['FC_MOP90_NPT3'] * npt3)
        MOP90_NPT4 = (v['FC_MOP90_NPT4'] * v['KNO3_L_NPT4'])
        MOP70_NPT3 = (v['FC_MOP70_NPT3'] * npt3)
        MOP70_NPT4 = (v['FC_MOP70_NPT4'] * v['KNO3_L_NPT4'])
        SS_NPT3 = (v['FC_SS_NPT3'] * npt3) 
        SS_NPT4 = (v['FC_SS_NPT4'] * v['KNO3_L_NPT4'])

        #CONSUMO
        cons_mop90 = MOP90_NPT3 + MOP90_NPT4
        cons_mop70 = MOP70_NPT3 + MOP70_NPT4
        cons_ss    = SS_NPT3 + SS_NPT4
        
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
        st.markdown("#### Producción (Kton)")
 
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
        st.markdown("#### Gastos Pozas (KUS) → USD/T sobre NPT3+NPT4")
        st.caption("Gasto (KUS)  |  — denominador: prod total —  |  USD/T resultante")
 
        for lbl, key in [("NV", "G_POZAS_NV"), ("CS", "G_POZAS_CS"), ("PB", "G_POZAS_PB")]:
            c1, c2 = st.columns([3, 1])
            with c1:
                V[key] = st.number_input(f"Gasto Pozas {lbl} (KUS)", value=round(V[key],2), step=10.0, format="%.2f", key=f"ui_{key}_{rp_rc}")
            with c2:
                st.metric("USD/T", f"${V[key]/prod_total_v:.2f}" if prod_total_v > 0 else "-")
 
        tot_pozas = V['G_POZAS_NV']+V['G_POZAS_CS']+V['G_POZAS_PB']+V['G_DEPRECIACION_CS']
        st.caption(f"📌 Total Pozas (incl. depr. CS ${V['G_DEPRECIACION_CS']:.0f} KUS fija): **${tot_pozas:.1f} KUS** → **${tot_pozas/prod_total_v:.2f} USD/T**" if prod_total_v > 0 else "")
 
        st.divider()
 
        # ─── GASTOS PLANTAS ───────────────────────────────────────────────────  

        st.markdown("#### Gastos Plantas (KUS)")
 
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
        st.markdown("#### Puerto — Gasto (KUS) | Toneladas (Kton) | USD/T")

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
        st.markdown("#### Transporte Terminados — KUS | Kton | USD/T")
        
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
        st.markdown("#### Factor Consumo KCl (KTon KCl / Kton prod)")
 
        npt3_v2 = V['KNO3_T_NPT3'] + V['KNO3_R_NPT3']
        npt4_v2 = V['KNO3_L_NPT4'] + V['CSSI_NPT4'] + V['CSSR_NPT4']
 
        st.caption("NPT3")
        fck1, fck2, fck3 = st.columns(3)
        with fck1: V['FC_MOP90_NPT3'] = st.number_input("MOP 90 NPT3", value=float(f"{V['FC_MOP90_NPT3']:.6f}"), step=0.001, format="%.6f", key=f"ui_FC_MOP90_NPT3_{rp_rc}")
        with fck2: V['FC_MOP70_NPT3'] = st.number_input("MOP 70 NPT3", value=float(f"{V['FC_MOP70_NPT3']:.6f}"), step=0.001, format="%.6f", key=f"ui_FC_MOP70_NPT3_{rp_rc}")
        with fck3: V['FC_SS_NPT3']    = st.number_input("SS NPT3",     value=float(f"{V['FC_SS_NPT3']:.6f}"),    step=0.001, format="%.6f", key=f"ui_FC_SS_NPT3_{rp_rc}")
 
        cons3 = (V['FC_MOP90_NPT3']+V['FC_MOP70_NPT3']+V['FC_SS_NPT3'])
        st.caption(f"KCl fresco NPT3: {cons3:.2f} KTon")
 
        st.caption("NPT4")
        fck4, fck5, fck6 = st.columns(3)
        with fck4: V['FC_MOP90_NPT4'] = st.number_input("MOP 90 NPT4", value=float(f"{V['FC_MOP90_NPT4']:.6f}"), step=0.001, format="%.6f", key=f"ui_FC_MOP90_NPT4_{rp_rc}")
        with fck5: V['FC_MOP70_NPT4'] = st.number_input("MOP 70 NPT4", value=float(f"{V['FC_MOP70_NPT4']:.6f}"), step=0.001, format="%.6f", key=f"ui_FC_MOP70_NPT4_{rp_rc}")
        with fck6: V['FC_SS_NPT4']    = st.number_input("SS NPT4",     value=float(f"{V['FC_SS_NPT4']:.6f}"),    step=0.001, format="%.6f", key=f"ui_FC_SS_NPT4_{rp_rc}")
 
        cons4 = (V['FC_MOP90_NPT4']+V['FC_MOP70_NPT4']+V['FC_SS_NPT4'])
        st.caption(f"KCl fresco NPT4: {cons4:.2f} KTon")

         
        st.caption("Precio KCl (US$/T)")
        pk1, pk2, pk3 = st.columns(3)
        with pk1: V['P_MOP90'] = st.number_input("MOP 90", value=round(V['P_MOP90'],2), step=1.0, format="%.2f", key=f"ui_P_MOP90_{rp_rc}")
        with pk2: V['P_MOP70'] = st.number_input("MOP 70", value=round(V['P_MOP70'],2), step=1.0, format="%.2f", key=f"ui_P_MOP70_{rp_rc}")
        with pk3: V['P_SS']    = st.number_input("SS",     value=round(V['P_SS'],2),    step=1.0, format="%.2f", key=f"ui_P_SS_{rp_rc}")
        
       
        st.divider()

        # ─── FC NaNO3 ────────────────────────────────────────────
        st.markdown("#### FC NaNO3")

        st.caption("NPT3")
        fn1, fn2, fn3 = st.columns(3)
        with fn1: V['FC_NaNO3_CAT1_NPT3']      = st.number_input("CAT1",      value=float(f"{V['FC_NaNO3_CAT1_NPT3']:.4f}"),      step=0.01, format="%.4f", key=f"ui_fc_cat1_npt3_{rp_rc}")
        with fn2: V['FC_NaNO3_PB_NPT3']        = st.number_input("PB",        value=float(f"{V['FC_NaNO3_PB_NPT3']:.4f}"),        step=0.01, format="%.4f", key=f"ui_fc_pb_npt3_{rp_rc}")
        with fn3: V['FC_NaNO3_CS_NPT3']        = st.number_input("CS",        value=float(f"{V['FC_NaNO3_CS_NPT3']:.4f}"),        step=0.01, format="%.4f", key=f"ui_fc_cs_npt3_{rp_rc}")

        st.caption("NPT4")
        fn4, fn5, fn6, fn7, fn8 = st.columns(5)
        with fn4: V['FC_NaNO3_CS_NPT4']        = st.number_input("CS",          value=float(f"{V['FC_NaNO3_CS_NPT4']:.4f}"),        step=0.01, format="%.4f", key=f"ui_fc_cs_npt4_{rp_rc}")
        with fn5: V['FC_NaNO3_PB_CSSI_NPT4']   = st.number_input("PB CSSI",     value=float(f"{V['FC_NaNO3_PB_CSSI_NPT4']:.4f}"),   step=0.01, format="%.4f", key=f"ui_fc_pb_cssi_{rp_rc}")
        with fn6: V['FC_NaNO3_CAT1_CSSI_NPT4'] = st.number_input("CAT1 CSSI",   value=float(f"{V['FC_NaNO3_CAT1_CSSI_NPT4']:.4f}"), step=0.01, format="%.4f", key=f"ui_fc_cat1_cssi_{rp_rc}")
        with fn7: V['FC_NaNO3_CAT1_CSSR_NPT4'] = st.number_input("CAT1 CSSR",   value=float(f"{V['FC_NaNO3_CAT1_CSSR_NPT4']:.4f}"), step=0.01, format="%.4f", key=f"ui_fc_cat1_cssr_{rp_rc}")
        with fn8: V['FC_NaNO3_PURGA_NPT4']     = st.number_input("FC Purga",    value=float(f"{V['FC_NaNO3_PURGA_NPT4']:.4f}"),     step=0.01, format="%.4f", key=f"ui_fc_purga_{rp_rc}")

        npt3_fc = V['KNO3_T_NPT3'] + V['KNO3_R_NPT3']
        consumo_nv_v = (npt3_fc * V['FC_NaNO3_CAT1_NPT3']
                        + V['CSSR_NPT4'] * V['FC_NaNO3_CAT1_CSSR_NPT4']
                        + V['CSSI_NPT4'] * V['FC_NaNO3_CAT1_CSSI_NPT4'])
        consumo_pb_v = (npt3_fc * V['FC_NaNO3_PB_NPT3']
                        + V['CSSI_NPT4'] * V['FC_NaNO3_PB_CSSI_NPT4'])
        consumo_cs_v = V['KNO3_L_NPT4'] * V['FC_NaNO3_CS_NPT4']
        consumo_tot_v = consumo_nv_v + consumo_pb_v + consumo_cs_v
        prod_total_ts = (V['KNO3_T_NPT3']+V['KNO3_R_NPT3']) + (V['KNO3_L_NPT4']+V['CSSI_NPT4']+V['CSSR_NPT4'])
        fc_v = consumo_tot_v / prod_total_ts if prod_total_ts > 0 else 0.0
        ton_trans = V['TON_TPTE_NV'] + V['TON_TPTE_PB'] + V['TON_TPTE_CS']
        precio_tot_v = (V['G_TPTE_NV'] + V['G_TPTE_PB'] + V['G_CAMINOS_NV']) / ton_trans if ton_trans > 0 else 0.0
        c11_preview = precio_tot_v * fc_v
        st.caption(f"Consumo NV: {consumo_nv_v:.3f} | PB: {consumo_pb_v:.3f} | CS: {consumo_cs_v:.3f} Kton")
        st.caption(f"FC total: {fc_v:.4f} | Precio tpte: ${precio_tot_v:.2f} | **=> 1.1 Tpte Sales = ${c11_preview:.2f} USD/T**")
        st.divider()

        # ───Tpte Sales ────────────────────────────────────────────
        st.markdown("#### Transporte de Sales")

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

        #fs1, fs2 = st.columns(2)
        #with fs1:
        #    V['P_TPTE_SALES'] = st.number_input("Precio Tpte Sales (USD/TNitr)", value=round(V['P_TPTE_SALES'],4), step=0.1, format="%.4f", key=f"ui_P_TPTE_SALES_{rp_rc}")
        #with fs2:
        #    V['FC_SALES'] = st.number_input("FC Consumo Sales (NaNO3/Ton)", value=float(f"{V['FC_SALES']:.6f}"), step=0.001, format="%.6f", key=f"ui_FC_SALES_{rp_rc}")
        #st.caption(f"=> 1.1 Tpte Sales = ${V['P_TPTE_SALES']:.4f} × {V['FC_SALES']:.4f} = **${V['P_TPTE_SALES']*V['FC_SALES']:.4f} USD/T**")
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
 
        st.markdown(f"#### Resultado — {MESES[mes]}")
        st.metric("REAL + PROY BASE",       f"${costo_base:.1f} / T")
        st.metric("Simulado",        f"${costo_sim:.1f} / T",
                  delta=f"{delta_total:+.1f} USD/T", delta_color="inverse")
 
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



# GASTOS POR ÁREA
# ══════════════════════════════════════════════════════════════════════════════
elif pagina == "Gastos por Área":
    st.title("Gastos por Área")
 
    col_v, _ = st.columns([2, 6])
    with col_v:
        modo = st.radio("Vista", ["Puntual", "Acumulado"], horizontal=True,
                        label_visibility="collapsed", key="modo_gastos")
    tipo = "Puntual" if modo == "Puntual" else "Acumulado"
    mes  = botones_mes("gastos")
    st.divider()
 
    # ── Áreas principales ─────────────────────────────────────────────────────
    AREAS_PRINCIPAL = [
        ('Pozas NV',    'GASTO', 'Operación Pozas (NV+CS+PV+PB)', 'Gasto Operación Pozas NV'),
        ('Pozas PB',    'GASTO', 'Operación Pozas (NV+CS+PV+PB)', 'Gasto Operación Pozas PB'),
        ('Pozas CS',    'GASTO', 'Operación Pozas (NV+CS+PV+PB)', 'Gasto Operación Pozas CS'),
        ('Tpte NV-PB',  'TRANSPORTE DE SALES', 'Total Transporte de Sales NV + PB', 'Total Transporte de Sales NV + PB'),
        ('NPT3',        'GASTO', 'CRISTALIZACION', 'Gasto NPT III + Korda'),
        ('NPT4',        'GASTO', 'CRISTALIZACION', 'Gasto NPT IV'),
        ('Prilado',     'GASTO', 'TERMINADOS',     'Gasto Planta Prilado CS'),
        ('DTP',         'GASTO', 'TERMINADOS',     'Gasto Planta DTP'),
        ('Secado',      'GASTO', 'TERMINADOS',     'Gasto Planta Secado KNO3'),
        ('Tpte CS-TOC', 'GASTO', 'TRANSPORTE',     'Tpte Camiones Terminados'),
        ('Puerto',      'Embarque Granel Trimestral', 'EMBARQUE', 'Embarque Granel + Demurrage'),
    ]
 
    # ── Detalle con subgrupos ─────────────────────────────────────────────────
    # Formato: lista de (nombre_grupo, [lista de conceptos])
    # Cada concepto: (label, area, subarea, concepto)
    DETALLE_AREAS = {
        'Pozas NV': [
            ('Gasto Pozas SV', [
                ('Remuneración',        'GASTO POZAS', 'POZAS NV', 'REMUNERACION'),
                ('Energía',             'GASTO POZAS', 'POZAS NV', 'ENERGIA'),
                ('Arrdo y Servicios',   'GASTO POZAS', 'POZAS NV', 'Arrdo y Servicios'),
                ('Otros',               'GASTO POZAS', 'POZAS NV', 'Otros'),
                ('Mantención',          'GASTO POZAS', 'POZAS NV', 'Manteción'),
                ('Mant. Directos',      'GASTO POZAS', 'POZAS NV', 'Mant. Pozas-Directos'),
                ('Mant. Dist Mant.',    'GASTO POZAS', 'POZAS NV', 'Mant. Pozas-Dist Mantenedores'),
            ]),
            ('Cosecha Preconcentrado', [
                ('Arrdo y Servicios',   'GASTO POZAS', 'POZAS NV', 'Arrdo y Servicios Preco'),
                ('Otros',               'GASTO POZAS', 'POZAS NV', 'Otros Preco'),
            ]),
            ('Cosecha Producción', [
                ('Arrdo y Servicios',   'GASTO POZAS', 'POZAS NV', 'Arrdo y Servicios Produ'),
                ('Otros',               'GASTO POZAS', 'POZAS NV', 'Otros Produ'),
            ]),
        ],
        'Pozas PB': [
            ('Gasto Total Pozas PB', [
                ('Remuneración',        'GASTO POZAS', 'POZAS PB', 'REMUNERACION'),
                ('Mat. y Repuestos',    'GASTO POZAS', 'POZAS PB', 'Materiales y repuestos'),
                ('Combustibles',        'GASTO POZAS', 'POZAS PB', 'Combustibles'),
                ('Arriendo y Servicios','GASTO POZAS', 'POZAS PB', 'Arrdo y Servicios'),
                ('Mantención',          'GASTO POZAS', 'POZAS PB', 'Manteción'),
                ('Mant. Directos',      'GASTO POZAS', 'POZAS PB', 'Mant. Pozas-Directos'),
                ('Mant. Dist Mant.',    'GASTO POZAS', 'POZAS PB', 'Mant. Pozas-Dist Mantenedores'),
                ('Otros',               'GASTO POZAS', 'POZAS PB', 'Otros'),
                ('Dist. Gen. EE',       'GASTO POZAS', 'POZAS PB', 'Dist. Generación EE'),
            ]),
            ('Cosecha Preconcentrado', [
                ('Arrdo y Servicios',   'GASTO POZAS', 'POZAS PB', 'Arrdo y Servicios Preco'),
                ('Energía y Comb.',     'GASTO POZAS', 'POZAS PB', 'Otros Preco'),
            ]),
            ('Cosecha Producción', [
                ('Arrdo y Servicios',   'GASTO POZAS', 'POZAS PB', 'Arrdo y Servicios Produ'),
                ('Otros',               'GASTO POZAS', 'POZAS PB', 'Otros Produ'),
            ]),
        ],
        'Pozas CS': [
            ('Gasto Total Pozas CS', [
                ('Remuneración',        'GASTO POZAS', 'POZAS CS', 'REMUNERACION'),
                ('Mat. y Repuestos',    'GASTO POZAS', 'POZAS CS', 'Materiales y repuestos'),
                ('Energía y Comb.',     'GASTO POZAS', 'POZAS CS', 'Energia y Combustibles'),
                ('Arriendo y Servicios','GASTO POZAS', 'POZAS CS', 'Arriendo y Servicios'),
                ('Agua',                'GASTO POZAS', 'POZAS CS', 'Agua'),
                ('Mantención',          'GASTO POZAS', 'POZAS CS', 'Mantención'),
                ('Mant. Directos',      'GASTO POZAS', 'POZAS CS', 'Mant. Pozas-Directos'),
                ('Mant. Dist Mant.',    'GASTO POZAS', 'POZAS CS', 'Mant. Pozas-Dist Mantenedores'),
                ('Otros',               'GASTO POZAS', 'POZAS CS', 'Otros'),
            ]),
            ('Cosecha Preconcentrado', [
                ('Energía y Comb.',     'GASTO POZAS', 'POZAS CS', 'Arrdo y Servicios Preco'),
                ('Arrdo y Servicios',   'GASTO POZAS', 'POZAS CS', 'Otros Preco'),
            ]),
            ('Cosecha Producción', [
                ('Arrdo y Servicios',   'GASTO POZAS', 'POZAS CS', 'Arrdo y Servicios Produ'),
                ('Otros',               'GASTO POZAS', 'POZAS CS', 'Otros Produ'),
            ]),
        ],
        'Tpte NV-PB': [
            ('Transporte Sales', [
                ('Tpte Sales NV',       'TRANSPORTE DE SALES', 'Total Transporte de Sales NV + PB', '- Transporte Sales NV'),
                ('Op Canchas+Caminos',  'TRANSPORTE DE SALES', 'Total Transporte de Sales NV + PB', '- Op Canchas + Caminos NV'),
                ('Tpte Sales PB',       'TRANSPORTE DE SALES', 'Total Transporte de Sales NV + PB', '- Transporte Sales PB'),
            ]),
        ],
        'NPT3': [
            ('Gastos en NPT III', [
                ('Remuneración',        'CRISTALIZACIÓN', 'NPT3', 'REMUNERACION'),
                ('Energía',             'CRISTALIZACIÓN', 'NPT3', 'Energía'),
                ('Petroleo/Gas',        'CRISTALIZACIÓN', 'NPT3', 'Petroleo/Gas'),
                ('Maq. Pesada',         'CRISTALIZACIÓN', 'NPT3', 'MAQ. PESADA'),
                ('Aguas',               'CRISTALIZACIÓN', 'NPT3', 'AGUAS'),
                ('Mat. y Repuestos',    'CRISTALIZACIÓN', 'NPT3', 'Materiales y Repuestos'),
                ('Arriendo y Servicios','CRISTALIZACIÓN', 'NPT3', 'Arriendo y Servicios'),
                ('Ceniza de Soda',      'CRISTALIZACIÓN', 'NPT3', 'Ceniza de Soda'),
                ('Otros',               'CRISTALIZACIÓN', 'NPT3', 'Otros'),
                ('Mantención',          'CRISTALIZACIÓN', 'NPT3', 'Mantención'),
                ('Mant. Directos',      'CRISTALIZACIÓN', 'NPT3', 'Mant. NPT III-Directos'),
                ('Mant. Dist Mant.',    'CRISTALIZACIÓN', 'NPT3', 'Mant. NPT III-Dist Mantenedores'),
                ('De Korda',            'CRISTALIZACIÓN', 'NPT3', 'De Korda'),
            ]),
        ],
        'NPT4': [
            ('Gastos NPT II S/Ceniza Soda', [
                ('Remuneraciones',      'CRISTALIZACIÓN', 'NPT4', 'REMUNERACIONES'),
                ('Energía',             'CRISTALIZACIÓN', 'NPT4', 'ENERGÍA'),
                ('Petroleo/Gas',        'CRISTALIZACIÓN', 'NPT4', 'PETROLEO/GAS'),
                ('Maq. Pesada',         'CRISTALIZACIÓN', 'NPT4', 'MAQ. PESADA'),
                ('Agua',                'CRISTALIZACIÓN', 'NPT4', 'AGUA'),
                ('Ceniza de Soda',      'CRISTALIZACIÓN', 'NPT4', 'Ceniza de Soda'),
                ('Otros',               'CRISTALIZACIÓN', 'NPT4', 'Otros'),
                ('Mantención',          'CRISTALIZACIÓN', 'NPT4', 'Mantención'),
                ('Mant. Directos',      'CRISTALIZACIÓN', 'NPT4', 'Mant npt-Directos'),
                ('Mant. Dist Mant.',    'CRISTALIZACIÓN', 'NPT4', 'Mant.npt-Dist Mantenedores'),
                ('De Korda',            'CRISTALIZACIÓN', 'NPT4', 'De Korda'),
            ]),
        ],
        'Prilado': [
            ('Total Operación', [
                ('Remuneraciones',      'TERMINADOS', 'PRILADO', 'REMUNERACIONES'),
                ('Energía',             'TERMINADOS', 'PRILADO', 'Energía'),
                ('Petroleo/Gas',        'TERMINADOS', 'PRILADO', 'Petroleo/Gas'),
                ('Maq. Pesadas',        'TERMINADOS', 'PRILADO', 'Maq. Pesadas'),
                ('Aditivos',            'TERMINADOS', 'PRILADO', 'Aditivos / Modificadores'),
                ('Otros',               'TERMINADOS', 'PRILADO', 'Otros'),
                ('Mantención',          'TERMINADOS', 'PRILADO', 'Mantención'),
                ('Mant. Directos',      'TERMINADOS', 'PRILADO', 'Mant. Prilado-Directos'),
                ('Mant. Dist Mant.',    'TERMINADOS', 'PRILADO', 'Mant. Prilado-Dist Mantenedores'),
            ]),
        ],
        'DTP': [
            ('Total DTP', [
                ('Remuneraciones',      'TERMINADOS', 'DTP', 'REMUNERACIONES'),
                ('Energía',             'TERMINADOS', 'DTP', 'ENERGIA'),
                ('Petroleo/Gas',        'TERMINADOS', 'DTP', 'Petroleo/Gas'),
                ('Aditivos',            'TERMINADOS', 'DTP', 'Aditivos'),
                ('Otros',               'TERMINADOS', 'DTP', 'Otros'),
                ('Mantención',          'TERMINADOS', 'DTP', 'Mantencion'),
                ('Mant. Directos',      'TERMINADOS', 'DTP', 'Mant. DTP-Directos'),
                ('Mant. Dist Mant.',    'TERMINADOS', 'DTP', 'Mant. Prilado-Dist Mantenedores'),
            ]),
        ],
        'Secado': [
            ('Gasto Planta Secado KNO3', [
                ('Remuneración',        'TERMINADOS', 'SECADO', 'REMUNERACION'),
                ('Energía',             'TERMINADOS', 'SECADO', 'Energía'),
                ('Petroleo/Gas',        'TERMINADOS', 'SECADO', 'Petroleo/Gas'),
                ('Aditivos',            'TERMINADOS', 'SECADO', 'Aditivos'),
                ('Maq. Pesadas',        'TERMINADOS', 'SECADO', 'Maq. Pesadas'),
                ('Otros',               'TERMINADOS', 'SECADO', 'Otros'),
                ('Mantención',          'TERMINADOS', 'SECADO', 'Mantención'),
                ('Mant. Directos',      'TERMINADOS', 'SECADO', 'Mant. Secado-Directos'),
                ('Mant. Dist Mant.',    'TERMINADOS', 'SECADO', 'Mant. Secado-Dist Mantenedores'),
            ]),
        ],
        'Tpte CS-TOC': [
            ('Transporte Terminados', [
                ('Tpte Camiones',       'GASTO', 'TRANSPORTE', 'Tpte Camiones Terminados'),
            ]),
        ],
        'Puerto': [
            ('Puerto', [
                ('Embarque+Demurrage',  'Embarque Granel Trimestral', 'EMBARQUE',      'Embarque Granel + Demurrage'),
                ('Almacenaje',          'Almacenaje Trimestral',       'ALMACENAJE',    'Almacenaje Trimestral'),
                ('Distributivos',       'Distributivos Trimestral',    'DISTRIBUTIVOS', 'Distributivos Trimestral'),
                ('Depreciación Puerto', 'DEPRECIACION',                'PUERTO',        'Depreciacion Puerto'),
            ]),
        ],
    }
 
    # ── Helpers ───────────────────────────────────────────────────────────────
    fechas_g = sorted(df['Fecha'].unique())
    fecha_g  = fechas_g[mes] if mes < len(fechas_g) else fechas_g[-1]
 
    def det_ppto(area, sub, con):
        mask = (df['Fecha']==fecha_g)&(df['AREA']==area)&(df['SUBAREA']==sub)&(df['CONCEPTO']==con)&(df['Tipo']==tipo)&(df['Tipo_2']=='PPTO')
        for med in ['KUS$','KUS']:
            r = df[mask&(df['Medida']==med)]['GASTO/COSTO']
            if not r.empty: return float(r.values[0])
        r = df[mask]['GASTO/COSTO']
        return float(r.values[0]) if not r.empty else 0.0
 
    def det_rp(area, sub, con):
        for t2 in ['REAL','PROY']:
            mask = (df['Fecha']==fecha_g)&(df['AREA']==area)&(df['SUBAREA']==sub)&(df['CONCEPTO']==con)&(df['Tipo']==tipo)&(df['Tipo_2']==t2)
            for med in ['KUS$','KUS']:
                r = df[mask&(df['Medida']==med)]['GASTO/COSTO']
                if not r.empty and r.values[0] != 0: return float(r.values[0])
        return 0.0
 
    # ── Tabla principal tipo Plan Industrial ──────────────────────────────────
    nombres = [a[0] for a in AREAS_PRINCIPAL]
    vals_p  = [gv(df, a[1], a[2], a[3], mes, tipo, 'PPTO') for a in AREAS_PRINCIPAL]
    vals_r  = [rp_val(df, a[1], a[2], a[3], mes, tipo) for a in AREAS_PRINCIPAL]
    deltas  = [r - p for r, p in zip(vals_r, vals_p)]
 
    cols_h = st.columns([2] + [1]*len(nombres))
    cols_h[0].markdown("**COSTO [KUS]**")
    for i, n in enumerate(nombres):
        cols_h[i+1].markdown(f"<div style='text-align:center;font-size:11px;font-weight:bold'>{n}</div>", unsafe_allow_html=True)
 
    cols_p = st.columns([2] + [1]*len(nombres))
    cols_p[0].markdown("**PPTO**")
    for i, v in enumerate(vals_p):
        cols_p[i+1].markdown(f"<div style='text-align:center;background:#152578;border-radius:8px;padding:6px;font-size:12px'>{v:,.0f}</div>", unsafe_allow_html=True)
    st.markdown("")
 
    cols_r = st.columns([2] + [1]*len(nombres))
    cols_r[0].markdown("**R+P**")
    for i, v in enumerate(vals_r):
        cols_r[i+1].markdown(f"<div style='text-align:center;background:#1a3a1a;border-radius:8px;padding:6px;font-size:12px'>{v:,.0f}</div>", unsafe_allow_html=True)
    st.markdown("")
 
    cols_d = st.columns([2] + [1]*len(nombres))
    cols_d[0].markdown("**Δ**")
    for i, d in enumerate(deltas):
        color = "#D83030" if d > 0 else "#80BC00" if d < 0 else "#888"
        sym   = "▲" if d > 0 else "▼" if d < 0 else "—"
        cols_d[i+1].markdown(f"<div style='text-align:center;color:{color};font-size:11px;font-weight:bold'>{sym} {abs(d):,.0f}</div>", unsafe_allow_html=True)
 
    st.divider()
 
    # ── Apertura por área ─────────────────────────────────────────────────────
    st.subheader("Apertura por área")
 
    if 'gastos_area_sel' not in st.session_state:
        st.session_state['gastos_area_sel'] = nombres[0]
 
    btn_cols = st.columns(len(nombres))
    for i, n in enumerate(nombres):
        with btn_cols[i]:
            t = 'primary' if st.session_state['gastos_area_sel'] == n else 'secondary'
            if st.button(n, key=f"gastos_btn_{n}", type=t, use_container_width=True):
                st.session_state['gastos_area_sel'] = n
                st.rerun()
 
    area_sel = st.session_state['gastos_area_sel']
    grupos   = DETALLE_AREAS.get(area_sel, [])
 
    if grupos:
        st.markdown(f"##### {area_sel} — {MESES[mes]} ({modo})")
 
        for nombre_grupo, conceptos in grupos:
            vp_list = [det_ppto(c[1], c[2], c[3]) for c in conceptos]
            vr_list = [det_rp(c[1],   c[2], c[3]) for c in conceptos]
            tot_p   = sum(vp_list)
            tot_r   = sum(vr_list)
            det_d   = [r - p for r, p in zip(vr_list, vp_list)]
 
            # Gráfico del grupo
            det_nombres = [c[0] for c in conceptos]
            fig = go.Figure()
            fig.add_trace(go.Bar(name="PPTO", x=det_nombres, y=vp_list, marker_color='#152578',
                                 text=[f"${v:,.0f}" for v in vp_list], textposition="outside", textfont_size=9))
            fig.add_trace(go.Bar(name="R+P",  x=det_nombres, y=vr_list,
                                 marker_color=['#80BC00' if r<=p else '#D83030' for r,p in zip(vr_list,vp_list)],
                                 text=[f"${v:,.0f}" for v in vr_list], textposition="outside", textfont_size=9))
            anns = []
            for i, (n, d) in enumerate(zip(det_nombres, det_d)):
                if abs(d) > 0:
                    color = "#D83030" if d > 0 else "#80BC00"
                    sym   = "▲" if d > 0 else "▼"
                    anns.append(dict(x=n, y=max(vp_list[i], vr_list[i])*1.2,
                                     text=f"{sym} {d:+,.0f}", showarrow=False,
                                     font=dict(size=10, color=color, family="Arial Black"), xanchor="center"))
            fig.update_layout(
                title=f"<b>{nombre_grupo}</b> — PPTO: ${tot_p:,.0f} KUS | R+P: ${tot_r:,.0f} KUS | Δ: {tot_r-tot_p:+,.0f}",
                barmode="group", height=350, xaxis_tickangle=-15,
                legend=dict(orientation="h", y=1.12),
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                margin=dict(t=70, b=70), annotations=anns
            )
            fig.update_yaxes(gridcolor="#333333")
            st.plotly_chart(fig, use_container_width=True)
 
            # Tabla del grupo con fila total
            rows = [{"Concepto": c[0], "PPTO": round(p,0), "R+P": round(r,0), "Δ": round(r-p,0)}
                    for c, p, r in zip(conceptos, vp_list, vr_list)]
            rows.append({"Concepto": f"▶ {nombre_grupo}", "PPTO": round(tot_p,0), "R+P": round(tot_r,0), "Δ": round(tot_r-tot_p,0)})
            df_g = pd.DataFrame(rows)
 
            def hl_g(row):
                is_tot = str(row['Concepto']).startswith('▶')
                base   = 'font-weight:bold;' if is_tot else ''
                s      = [base]*4
                if row['Δ'] > 0:   s[3] = f'{base}color:#D83030'
                elif row['Δ'] < 0: s[3] = f'{base}color:#80BC00'
                return s
 
            st.dataframe(
                df_g.style.apply(hl_g, axis=1)
                    .format({"PPTO":"{:,.0f}", "R+P":"{:,.0f}", "Δ":"{:+,.0f}"}),
                use_container_width=True, hide_index=True,
                height=min(400, (len(rows))*38+50)
            )
            st.divider()
 


# ══════════════════════════════════════════════════════════════════════════════
# SIMULADOR GASTOS PPTO — versión corregida
# Fixes: BASE congelado, sin PCS_DEP, c14 prod_total, c13 con delta,
#        c11 consumo_cs incluye NPT3, BASE_*_SUM desde BASE congelado
# ══════════════════════════════════════════════════════════════════════════════
elif pagina == "Sim. Gastos PPTO":
    import copy
    st.title("Simulador de Sensibilidad — PPTO (Apertura de Gastos)")
 
    col_v, _ = st.columns([2, 6])
    with col_v:
        modo_sens = st.radio("Vista", ["Puntual", "Acumulado"], horizontal=True,
                             label_visibility="collapsed", key="modo_sg_ppto")
    tipo_sens = "Puntual" if modo_sens == "Puntual" else "Acumulado"
    mes = botones_mes("sg_ppto")
    st.divider()
 
    fechas_sorted = sorted(df['Fecha'].unique())
    if mes >= len(fechas_sorted):
        st.warning("Mes fuera de rango.")
        st.stop()
    fecha = fechas_sorted[mes]
 
    def _r(area, subarea, concepto, medida=None, nth=0):
        mask = ((df['Fecha']==fecha)&(df['AREA']==area)&(df['SUBAREA']==subarea)&
                (df['CONCEPTO']==concepto)&(df['Tipo']==tipo_sens)&(df['Tipo_2']=='PPTO'))
        if medida: mask = mask & (df['Medida']==medida)
        r = df[mask]['GASTO/COSTO']
        return float(r.values[nth]) if len(r) > nth else 0.0
 
    def _rdet(area, subarea, concepto):
        mask = ((df['Fecha']==fecha)&(df['AREA']==area)&(df['SUBAREA']==subarea)&
                (df['CONCEPTO']==concepto)&(df['Tipo']==tipo_sens)&(df['Tipo_2']=='PPTO')&
                (df['Medida']=='KUS$'))
        r = df[mask]['GASTO/COSTO']
        return float(r.values[0]) if not r.empty else 0.0
 
    def _area(area):
        mask = (df['Fecha']==fecha)&(df['AREA']==area)&(df['Tipo']==tipo_sens)&(df['Tipo_2']=='PPTO')
        r = df[mask]['GASTO/COSTO']
        return float(r.values[0]) if not r.empty else 0.0
 
    # ── BASE KPI ─────────────────────────────────────────────────────────────
    BASE_KPI = {
        'KNO3_T_NPT3':   _r('PRODUCCION','NPT3','- KNO3 T NPT III'),
        'KNO3_R_NPT3':   _r('PRODUCCION','NPT3','- KNO3 R NPT III'),
        'KNO3_L_NPT4':   _r('PRODUCCION','NPT4','- KNO3 L NPT II/IV'),
        'CSSI_NPT4':     _r('PRODUCCION','NPT4','- CSSI NPT II/IV'),
        'CSSR_NPT4':     _r('PRODUCCION','NPT4','- CSSR NPT II/IV'),
        'PRIL_DTP':      _r('PRODUCCION','TERMINADOS','PRILADO + DTP'),
        'SECADO':        _r('PRODUCCION','TERMINADOS','SECADO'),
        # Pozas — totales y extras (FIX: sin POZ_DEP_CS para evitar doble conteo)
        'G_POZAS_NV':        _r('GASTO','Operación Pozas (NV+CS+PV+PB)','Gasto Operación Pozas NV'),
        'G_POZAS_PB':        _r('GASTO','Operación Pozas (NV+CS+PV+PB)','Gasto Operación Pozas PB'),
        'G_POZAS_CS':        _r('GASTO','Operación Pozas (NV+CS+PV+PB)','Gasto Operación Pozas CS'),
        'G_DEPRECIACION_CS': _r('GASTO','Operación Pozas (NV+CS+PV+PB)','Gasto Depreciación CS'),
        'POZ_OP_PV':         _rdet('GASTO POZAS','POZAS','OPERACIONES PV'),
        # Cristalización — totales base para delta
        'G_NPT3': _r('GASTO','CRISTALIZACION','Gasto NPT III + Korda'),
        'G_NPT4': _r('GASTO','CRISTALIZACION','Gasto NPT IV'),
        # Terminados — totales base para delta (FIX: detalle Prilado incompleto en tabla)
        'G_PRIL':   _r('GASTO','TERMINADOS','Gasto Planta Prilado CS'),
        'G_DTP':    _r('GASTO','TERMINADOS','Gasto Planta DTP'),
        'G_SECADO': _r('GASTO','TERMINADOS','Gasto Planta Secado KNO3'),
        # Puerto
        'TON_EMBARQUE_TOTAL':  _r('Embarque Granel Trimestral','EMBARQUE','Embarque total','Kton'),
        'TON_EMBARQUE_GRANEL': _r('Embarque Granel Trimestral','EMBARQUE','Embarque Granel','Kton'),
        'G_ALMACENAJE':  _r('Almacenaje Trimestral','ALMACENAJE','Almacenaje Trimestral','KUS'),
        'TON_ALMACENAJE':_r('Almacenaje Trimestral','ALMACENAJE','Almacenaje Trimestral','Kton'),
        'G_DIST_T':      _r('Distributivos Trimestral','DISTRIBUTIVOS','Distributivos Trimestral','KUS'),
        'TON_DESPACHO':  _r('Distributivos Trimestral','DISTRIBUTIVOS','Despacho Camiones y contenedores','Kton'),
        # Transporte
        'G_TPTE_CAM':   _r('GASTO','TRANSPORTE','Tpte Camiones Terminados','KUS'),
        'TON_TPTE_CAM': _r('TRANSPORTE','TRANSPORTE','Tpte Camiones Terminados','kTon'),
        'G_TPTE_NV':    _r('TRANSPORTE DE SALES','Total Transporte de Sales NV + PB','- Transporte Sales NV','KUS'),
        'TON_TPTE_NV':  _r('TRANSPORTE DE SALES','Total Transporte Sales (Promedio)','Transporte de Sales NV a CS (Cat 1 + Cat 3)','KTon NaNO3'),
        'G_TPTE_PB':    _r('TRANSPORTE DE SALES','Total Transporte de Sales NV + PB','- Transporte Sales PB','KUS'),
        'TON_TPTE_PB':  _r('TRANSPORTE DE SALES','Total Transporte Sales (Promedio)','Transporte de Sales PB a CS','KTon NaNO3'),
        'G_CAMINOS_NV': _r('TRANSPORTE DE SALES','Total Transporte de Sales NV + PB','- Op Canchas + Caminos NV','KUS'),
        'TON_TPTE_CS':  _r('TRANSPORTE DE SALES','Total Transporte Sales (Promedio)','Transporte de Sales CS (Alimentación)','KTon NaNO3'),
        # FC KCl
        'FC_MOP90_NPT3': _r('KCl','Fc KCl NPT3','MOP 90',nth=0),
        'FC_MOP70_NPT3': _r('KCl','Fc KCl NPT3','MOP 70',nth=0),
        'FC_SS_NPT3':    _r('KCl','Fc KCl NPT3','SS',nth=0),
        'FC_MOP90_NPT4': _r('KCl','Fc KCl NPT4','MOP 90',nth=0),
        'FC_MOP70_NPT4': _r('KCl','Fc KCl NPT4','MOP 70',nth=0),
        'FC_SS_NPT4':    _r('KCl','Fc KCl NPT4','SS',nth=0),
        'P_MOP90':       _r('KCl','Costo Promedio KCl','MOP 90'),
        'P_MOP70':       _r('KCl','Costo Promedio KCl','MOP 70'),
        'P_SS':          _r('KCl','Costo Promedio KCl','SS'),
        # FC NaNO3
        'FC_NaNO3_CAT1_NPT3':      _r('FC NaNO3','NPT3','CAT1'),
        'FC_NaNO3_CS_NPT3':        _r('FC NaNO3','NPT3','CS'),
        'FC_NaNO3_PB_NPT3':        _r('FC NaNO3','NPT3','PB'),
        'FC_NaNO3_CS_NPT4':        _r('FC NaNO3','NPT4','CS'),
        'FC_NaNO3_PB_NPT4':        _r('FC NaNO3','NPT4','PB'),
        'FC_NaNO3_PB_CSSI_NPT4':   _r('FC NaNO3','NPT4','PB CSSI'),
        'FC_NaNO3_CAT1_CSSI_NPT4': _r('FC NaNO3','NPT4','CAT1 CSSI'),
        'FC_NaNO3_CAT1_CSSR_NPT4': _r('FC NaNO3','NPT4','CAT1 CSSR'),
        'FC_NaNO3_PURGA_NPT4':     _r('FC NaNO3','NPT4','FC PURGA'),
        # Depreciaciones fijas
        'DEP_PRIL':    _r('GASTO','TERMINADOS','Gasto Depreciación Prilado CS'),
        'DEP_DTP':     _r('GASTO','TERMINADOS','Gasto Depreciación DTP'),
        'DEP_SECADO':  _r('GASTO','TERMINADOS','Gasto Depreciación Secado KNO3'),
        'DEP_NPT3':    _r('GASTO','CRISTALIZACION','Gasto Depreciación NPT III'),
        'DEP_NPT4':    _r('GASTO','CRISTALIZACION','Gasto Depreciación NPT IV'),
        'DEPR_PUERTO': _r('DEPRECIACION','PUERTO','Depreciacion Puerto','KUS'),
        'G_TPTE_INT':  _r('GASTO','TERMINADOS','Gasto Transporte Intermedios'),
        'DIST_NITRATOS': _area('Distributivos Nitratos'),
        'DEPR_COM':      _area('Depreciación Costo Comun'),
        'GEN_FE':        _r('PERDIDAS','PERDIDAS','Generación Producto FE (Terminados)'),
        'GEN_Perdidas':  _r('PERDIDAS','PERDIDAS','Generación Perdidas / Costras (Terminados)'),
        'GEN_Perdidas_Puerto': _r('PERDIDAS','PERDIDAS','Perdidas / FE puerto y cancha'),
        'OTROS': gv(df,'COSTO TOTAL','1.9 OTROS','OTROS',mes,tipo_sens,'PPTO'),
    }
 
    # ── BASE DET — apertura completa (FIX: sin PCS_DEP) ─────────────────────
    BASE_DET = {
        # Pozas NV
        'PNV_REMUN':   _rdet('GASTO POZAS','POZAS NV','REMUNERACION'),
        'PNV_ENERG':   _rdet('GASTO POZAS','POZAS NV','ENERGIA'),
        'PNV_ARRDO':   _rdet('GASTO POZAS','POZAS NV','Arrdo y Servicios'),
        'PNV_OTROS':   _rdet('GASTO POZAS','POZAS NV','Otros'),
        'PNV_MANT_D':  _rdet('GASTO POZAS','POZAS NV','Mant. Pozas-Directos'),
        'PNV_MANT_M':  _rdet('GASTO POZAS','POZAS NV','Mant. Pozas-Dist Mantenedores'),
        'PNV_PRECO_A': _rdet('GASTO POZAS','POZAS NV','Arrdo y Servicios Preco'),
        'PNV_PRECO_O': _rdet('GASTO POZAS','POZAS NV','Otros Preco'),
        'PNV_PRODU_A': _rdet('GASTO POZAS','POZAS NV','Arrdo y Servicios Produ'),
        'PNV_PRODU_O': _rdet('GASTO POZAS','POZAS NV','Otros Produ'),
        # Pozas PB
        'PPB_REMUN':   _rdet('GASTO POZAS','POZAS PB','REMUNERACION'),
        'PPB_MYREP':   _rdet('GASTO POZAS','POZAS PB','Materiales y repuestos'),
        'PPB_COMB':    _rdet('GASTO POZAS','POZAS PB','Combustibles'),
        'PPB_ARRDO':   _rdet('GASTO POZAS','POZAS PB','Arrdo y Servicios'),
        'PPB_OTROS':   _rdet('GASTO POZAS','POZAS PB','Otros'),
        'PPB_DIST_EE': _rdet('GASTO POZAS','POZAS PB','Dist. Generación EE'),
        'PPB_MANT_D':  _rdet('GASTO POZAS','POZAS PB','Mant. Pozas-Directos'),
        'PPB_MANT_M':  _rdet('GASTO POZAS','POZAS PB','Mant. Pozas-Dist Mantenedores'),
        'PPB_PRECO_A': _rdet('GASTO POZAS','POZAS PB','Arrdo y Servicios Preco'),
        'PPB_PRECO_O': _rdet('GASTO POZAS','POZAS PB','Otros Preco'),
        'PPB_PRODU_A': _rdet('GASTO POZAS','POZAS PB','Arrdo y Servicios Produ'),
        'PPB_PRODU_O': _rdet('GASTO POZAS','POZAS PB','Otros Produ'),
        # Pozas CS — FIX: sin PCS_DEP (G_DEPRECIACION_CS va por separado en c12)
        'PCS_REMUN':   _rdet('GASTO POZAS','POZAS CS','REMUNERACION'),
        'PCS_MYREP':   _rdet('GASTO POZAS','POZAS CS','Materiales y repuestos'),
        'PCS_ENERG':   _rdet('GASTO POZAS','POZAS CS','Energia y Combustibles'),
        'PCS_ARRDO':   _rdet('GASTO POZAS','POZAS CS','Arriendo y Servicios'),
        'PCS_AGUA':    _rdet('GASTO POZAS','POZAS CS','Agua'),
        'PCS_OTROS':   _rdet('GASTO POZAS','POZAS CS','Otros'),
        'PCS_MANT_D':  _rdet('GASTO POZAS','POZAS CS','Mant. Pozas-Directos'),
        'PCS_MANT_M':  _rdet('GASTO POZAS','POZAS CS','Mant. Pozas-Dist Mantenedores'),
        'PCS_PRECO_A': _rdet('GASTO POZAS','POZAS CS','Arrdo y Servicios Preco'),
        'PCS_PRECO_O': _rdet('GASTO POZAS','POZAS CS','Otros Preco'),
        'PCS_PRODU_A': _rdet('GASTO POZAS','POZAS CS','Arrdo y Servicios Produ'),
        'PCS_PRODU_O': _rdet('GASTO POZAS','POZAS CS','Otros Produ'),
        # NPT3
        'N3_REMUN':  _rdet('CRISTALIZACIÓN','NPT3','REMUNERACION'),
        'N3_ENERG':  _rdet('CRISTALIZACIÓN','NPT3','Energía'),
        'N3_PETROL': _rdet('CRISTALIZACIÓN','NPT3','Petroleo/Gas'),
        'N3_MAQ':    _rdet('CRISTALIZACIÓN','NPT3','MAQ. PESADA'),
        'N3_AGUA':   _rdet('CRISTALIZACIÓN','NPT3','AGUAS'),
        'N3_MYREP':  _rdet('CRISTALIZACIÓN','NPT3','Materiales y Repuestos'),
        'N3_ARRDO':  _rdet('CRISTALIZACIÓN','NPT3','Arriendo y Servicios'),
        'N3_CSODA':  _rdet('CRISTALIZACIÓN','NPT3','Ceniza de Soda'),
        'N3_OTROS':  _rdet('CRISTALIZACIÓN','NPT3','Otros'),
        'N3_MANT_D': _rdet('CRISTALIZACIÓN','NPT3','Mant. NPT III-Directos'),
        'N3_MANT_M': _rdet('CRISTALIZACIÓN','NPT3','Mant. NPT III-Dist Mantenedores'),
        'N3_KORDA':  _rdet('CRISTALIZACIÓN','NPT3','De Korda'),
        # NPT4
        'N4_REMUN':  _rdet('CRISTALIZACIÓN','NPT4','REMUNERACIONES'),
        'N4_ENERG':  _rdet('CRISTALIZACIÓN','NPT4','ENERGÍA'),
        'N4_PETROL': _rdet('CRISTALIZACIÓN','NPT4','PETROLEO/GAS'),
        'N4_MAQ':    _rdet('CRISTALIZACIÓN','NPT4','MAQ. PESADA'),
        'N4_AGUA':   _rdet('CRISTALIZACIÓN','NPT4','AGUA'),
        'N4_CSODA':  _rdet('CRISTALIZACIÓN','NPT4','Ceniza de Soda'),
        'N4_OTROS':  _rdet('CRISTALIZACIÓN','NPT4','Otros'),
        'N4_MANT_D': _rdet('CRISTALIZACIÓN','NPT4','Mant npt-Directos'),
        'N4_MANT_M': _rdet('CRISTALIZACIÓN','NPT4','Mant.npt-Dist Mantenedores'),
        'N4_KORDA':  _rdet('CRISTALIZACIÓN','NPT4','De Korda'),
        # Prilado
        'PR_REMUN':  _rdet('TERMINADOS','PRILADO','REMUNERACIONES'),
        'PR_ENERG':  _rdet('TERMINADOS','PRILADO','Energía'),
        'PR_PETROL': _rdet('TERMINADOS','PRILADO','Petroleo/Gas'),
        'PR_MAQ':    _rdet('TERMINADOS','PRILADO','Maq. Pesadas'),
        'PR_ADITI':  _rdet('TERMINADOS','PRILADO','Aditivos / Modificadores'),
        'PR_OTROS':  _rdet('TERMINADOS','PRILADO','Otros'),
        'PR_MANT_D': _rdet('TERMINADOS','PRILADO','Mant. Prilado-Directos'),
        'PR_MANT_M': _rdet('TERMINADOS','PRILADO','Mant. Prilado-Dist Mantenedores'),
        # DTP
        'DT_REMUN':  _rdet('TERMINADOS','DTP','REMUNERACIONES'),
        'DT_ENERG':  _rdet('TERMINADOS','DTP','ENERGIA'),
        'DT_PETROL': _rdet('TERMINADOS','DTP','Petroleo/Gas'),
        'DT_ADITI':  _rdet('TERMINADOS','DTP','Aditivos'),
        'DT_OTROS':  _rdet('TERMINADOS','DTP','Otros'),
        'DT_MANT_D': _rdet('TERMINADOS','DTP','Mant. DTP-Directos'),
        'DT_MANT_M': _rdet('TERMINADOS','DTP','Mant. Prilado-Dist Mantenedores'),
        # Secado
        'SC_REMUN':  _rdet('TERMINADOS','SECADO','REMUNERACION'),
        'SC_ENERG':  _rdet('TERMINADOS','SECADO','Energía'),
        'SC_PETROL': _rdet('TERMINADOS','SECADO','Petroleo/Gas'),
        'SC_ADITI':  _rdet('TERMINADOS','SECADO','Aditivos'),
        'SC_MAQ':    _rdet('TERMINADOS','SECADO','Maq. Pesadas'),
        'SC_OTROS':  _rdet('TERMINADOS','SECADO','Otros'),
        'SC_MANT_D': _rdet('TERMINADOS','SECADO','Mant. Secado-Directos'),
        'SC_MANT_M': _rdet('TERMINADOS','SECADO','Mant. Secado-Dist Mantenedores'),
        # Puerto
        'G_EMBARQUE': _r('Embarque Granel Trimestral','EMBARQUE','Embarque Granel + Demurrage','KUS'),
    }
 
    BASE = {**BASE_KPI, **BASE_DET}
 
    # ── Session state — FIX: BASE congelado en sg_base para evitar drift ─────
    if ('sg_sv' not in st.session_state or
            st.session_state.get('sg_mes') != mes or
            st.session_state.get('sg_tipo') != tipo_sens):
        st.session_state['sg_sv']   = copy.deepcopy(BASE)
        st.session_state['sg_base'] = copy.deepcopy(BASE)   # ← BASE congelado
        st.session_state['sg_mes']  = mes
        st.session_state['sg_tipo'] = tipo_sens
        st.session_state['sg_rc']   = st.session_state.get('sg_rc', 0) + 1
    if 'sg_rc' not in st.session_state:
        st.session_state['sg_rc'] = 0
    sg_rc = st.session_state['sg_rc']
    V    = st.session_state['sg_sv']
    BASE = st.session_state['sg_base']   # ← usar BASE congelado, no el del render
    for k, val in st.session_state['sg_base'].items():
        if k not in V: V[k] = val
 
    # ── recalcular — todas las correcciones aplicadas ────────────────────────
    def recalcular(v):
        npt3       = v['KNO3_T_NPT3'] + v['KNO3_R_NPT3']
        npt4       = v['KNO3_L_NPT4'] + v['CSSI_NPT4']  + v['CSSR_NPT4']
        prod_total = npt3 + npt4
        prod_sin_sod = npt3 + v['KNO3_L_NPT4']
        prod_term  = v['PRIL_DTP'] + v['SECADO']
 
        # c11 — FIX: consumo_cs incluye npt3*FC_NaNO3_CS_NPT3 (importante en acumulado)
        Tt  = v['TON_TPTE_NV'] + v['TON_TPTE_PB'] + v['TON_TPTE_CS']
        p_nv = v['G_TPTE_NV']   / Tt if Tt > 0 else 0.0
        p_pb = v['G_TPTE_PB']   / Tt if Tt > 0 else 0.0
        p_cs = v['G_CAMINOS_NV'] / Tt if Tt > 0 else 0.0
        consumo_nv = (npt3 * v['FC_NaNO3_CAT1_NPT3'] +
                      v['CSSR_NPT4'] * v['FC_NaNO3_CAT1_CSSR_NPT4'] +
                      v['CSSI_NPT4'] * v['FC_NaNO3_CAT1_CSSI_NPT4'])
        consumo_pb = (npt3 * v['FC_NaNO3_PB_NPT3'] +
                      v['CSSI_NPT4'] * v['FC_NaNO3_PB_CSSI_NPT4'])
        consumo_cs = (npt3 * v['FC_NaNO3_CS_NPT3'] +          # ← FIX: incluye NPT3
                      v['KNO3_L_NPT4'] * v['FC_NaNO3_CS_NPT4'])
        fc_s = (consumo_nv + consumo_pb + consumo_cs) / prod_total if prod_total > 0 else 0.0
        c11  = (p_nv + p_pb + p_cs) * fc_s
 
        # c12 — FIX: numerador = total_base + delta_detalle + POZ_OP_PV + DEP (una vez)
        g_pnv = sum(v[k] for k in ['PNV_REMUN','PNV_ENERG','PNV_ARRDO','PNV_OTROS',
                                    'PNV_MANT_D','PNV_MANT_M',
                                    'PNV_PRECO_A','PNV_PRECO_O','PNV_PRODU_A','PNV_PRODU_O'])
        g_ppb = sum(v[k] for k in ['PPB_REMUN','PPB_MYREP','PPB_COMB','PPB_ARRDO','PPB_OTROS',
                                    'PPB_DIST_EE','PPB_MANT_D','PPB_MANT_M',
                                    'PPB_PRECO_A','PPB_PRECO_O','PPB_PRODU_A','PPB_PRODU_O'])
        g_pcs = sum(v[k] for k in ['PCS_REMUN','PCS_MYREP','PCS_ENERG','PCS_ARRDO','PCS_AGUA',
                                    'PCS_OTROS','PCS_MANT_D','PCS_MANT_M',
                                    'PCS_PRECO_A','PCS_PRECO_O','PCS_PRODU_A','PCS_PRODU_O'])
        # Sumas base del detalle (desde BASE congelado)
        B_PNV = sum(BASE[k] for k in ['PNV_REMUN','PNV_ENERG','PNV_ARRDO','PNV_OTROS',
                                       'PNV_MANT_D','PNV_MANT_M',
                                       'PNV_PRECO_A','PNV_PRECO_O','PNV_PRODU_A','PNV_PRODU_O'])
        B_PPB = sum(BASE[k] for k in ['PPB_REMUN','PPB_MYREP','PPB_COMB','PPB_ARRDO','PPB_OTROS',
                                       'PPB_DIST_EE','PPB_MANT_D','PPB_MANT_M',
                                       'PPB_PRECO_A','PPB_PRECO_O','PPB_PRODU_A','PPB_PRODU_O'])
        B_PCS = sum(BASE[k] for k in ['PCS_REMUN','PCS_MYREP','PCS_ENERG','PCS_ARRDO','PCS_AGUA',
                                       'PCS_OTROS','PCS_MANT_D','PCS_MANT_M',
                                       'PCS_PRECO_A','PCS_PRECO_O','PCS_PRODU_A','PCS_PRODU_O'])
        g_nv_fin = BASE['G_POZAS_NV'] + (g_pnv - B_PNV)
        g_pb_fin = BASE['G_POZAS_PB'] + (g_ppb - B_PPB)
        g_cs_fin = BASE['G_POZAS_CS'] + (g_pcs - B_PCS)
        c12 = (g_nv_fin + g_pb_fin + g_cs_fin + v['G_DEPRECIACION_CS']) / prod_total

        # c13 — FIX: total_base + delta_detalle (igual que c12/c15)
        g_n3 = sum(v[k] for k in ['N3_REMUN','N3_ENERG','N3_PETROL','N3_MAQ','N3_AGUA',
                                   'N3_MYREP','N3_ARRDO','N3_CSODA','N3_OTROS',
                                   'N3_MANT_D','N3_MANT_M','N3_KORDA'])
        g_n4 = sum(v[k] for k in ['N4_REMUN','N4_ENERG','N4_PETROL','N4_MAQ','N4_AGUA',
                                   'N4_CSODA','N4_OTROS','N4_MANT_D','N4_MANT_M','N4_KORDA'])
        B_N3 = sum(BASE[k] for k in ['N3_REMUN','N3_ENERG','N3_PETROL','N3_MAQ','N3_AGUA',
                                      'N3_MYREP','N3_ARRDO','N3_CSODA','N3_OTROS',
                                      'N3_MANT_D','N3_MANT_M','N3_KORDA'])
        B_N4 = sum(BASE[k] for k in ['N4_REMUN','N4_ENERG','N4_PETROL','N4_MAQ','N4_AGUA',
                                      'N4_CSODA','N4_OTROS','N4_MANT_D','N4_MANT_M','N4_KORDA'])
        g_n3_fin = BASE['G_NPT3'] + (g_n3 - B_N3)
        g_n4_fin = BASE['G_NPT4'] + (g_n4 - B_N4)
        c13 = (g_n3_fin + g_n4_fin + v['DEP_NPT3'] + v['DEP_NPT4']) / prod_total if prod_total > 0 else 0.0
 
        # c14 — FIX: denominador prod_total (no prod_sin_sod)
        # 1.4 KCl
        MOP90_NPT3 = (v['FC_MOP90_NPT3'] * npt3)
        MOP90_NPT4 = (v['FC_MOP90_NPT4'] * v['KNO3_L_NPT4'])
        MOP70_NPT3 = (v['FC_MOP70_NPT3'] * npt3)
        MOP70_NPT4 = (v['FC_MOP70_NPT4'] * v['KNO3_L_NPT4'])
        SS_NPT3 = (v['FC_SS_NPT3'] * npt3) 
        SS_NPT4 = (v['FC_SS_NPT4'] * v['KNO3_L_NPT4'])

        #CONSUMO
        c90 = MOP90_NPT3 + MOP90_NPT4
        c70 = MOP70_NPT3 + MOP70_NPT4
        css = SS_NPT3 + SS_NPT4
        
        cons_total = cons_mop90 + cons_mop70 + cons_ss
        
        costo_total_kcl = (v['P_MOP90'] * c90) + (v['P_MOP70'] * c70) + (v['P_SS'] * css)
        c14 = costo_total_kcl / prod_sin_sod if prod_sin_sod > 0 else 0.0

 
        # c15 — FIX: total_base + delta_detalle (detalle Prilado incompleto en tabla)
        g_pr = sum(v[k] for k in ['PR_REMUN','PR_ENERG','PR_PETROL','PR_MAQ',
                                   'PR_ADITI','PR_OTROS','PR_MANT_D','PR_MANT_M'])
        g_dt = sum(v[k] for k in ['DT_REMUN','DT_ENERG','DT_PETROL','DT_ADITI',
                                   'DT_OTROS','DT_MANT_D','DT_MANT_M'])
        g_sc = sum(v[k] for k in ['SC_REMUN','SC_ENERG','SC_PETROL','SC_ADITI',
                                   'SC_MAQ','SC_OTROS','SC_MANT_D','SC_MANT_M'])
        B_PR = sum(BASE[k] for k in ['PR_REMUN','PR_ENERG','PR_PETROL','PR_MAQ',
                                      'PR_ADITI','PR_OTROS','PR_MANT_D','PR_MANT_M'])
        B_DT = sum(BASE[k] for k in ['DT_REMUN','DT_ENERG','DT_PETROL','DT_ADITI',
                                      'DT_OTROS','DT_MANT_D','DT_MANT_M'])
        B_SC = sum(BASE[k] for k in ['SC_REMUN','SC_ENERG','SC_PETROL','SC_ADITI',
                                      'SC_MAQ','SC_OTROS','SC_MANT_D','SC_MANT_M'])
        g_pr_fin = BASE['G_PRIL']   + (g_pr - B_PR)
        g_dt_fin = BASE['G_DTP']    + (g_dt - B_DT)
        g_sc_fin = BASE['G_SECADO'] + (g_sc - B_SC)
        c15 = (g_pr_fin + g_dt_fin + g_sc_fin +
               v['G_TPTE_INT'] + v['DEP_PRIL'] + v['DEP_DTP'] + v['DEP_SECADO']) / prod_term if prod_term > 0 else 0.0
 
        # c16
        c_t  = v['G_TPTE_CAM']   / v['TON_TPTE_CAM']       if v['TON_TPTE_CAM'] > 0       else 0.0
        c_e  = v['G_EMBARQUE']   / v['TON_EMBARQUE_GRANEL'] if v['TON_EMBARQUE_GRANEL'] > 0 else 0.0
        c_a  = v['G_ALMACENAJE'] / v['TON_ALMACENAJE']      if v['TON_ALMACENAJE'] > 0      else 0.0
        vd   = v['TON_EMBARQUE_TOTAL'] + v['TON_DESPACHO']
        c_d  = v['G_DIST_T']    / vd if vd > 0 else 0.0
        c_dp = v['DEPR_PUERTO'] / vd if vd > 0 else 0.0
        c16  = c_t + c_e + c_a + c_d + c_dp
 
        # c17
        Op   = c11 + c12 + c13 + c14
        pfe  = (-(v['GEN_FE'] + v['GEN_Perdidas'])) / prod_term if prod_term > 0 else 0.0
        PFE  = Op * pfe
        base_c = Op + PFE + c15
        ppc  = prod_total + v['GEN_Perdidas_Puerto'] + v['GEN_FE'] + v['GEN_Perdidas']
        Pdeg = -(v['GEN_Perdidas_Puerto'] / (ppc - v['GEN_FE'] - v['GEN_Perdidas']))
        c17  = PFE + Pdeg * base_c
 
        c18 = (v['DIST_NITRATOS'] + v['DEPR_COM']) / prod_total if prod_total > 0 else 0.0
        c19 = v['OTROS']
 
        comp = {'1.1 Tpte Sales':c11, '1.2 Op. Pozas':c12, '1.3 Cristalización':c13,
                '1.4 KCl':c14, '1.5 Terminados':c15, '1.6 Tpte+Puerto':c16,
                '1.7 Pérdidas F/E':c17, '1.8 Distributivos':c18, '1.9 Otros':c19}
        return sum(comp.values()), comp
 
    col_inp, col_res = st.columns([3, 2], gap="large")
 
    # FIX: col_inp PRIMERO para que V tenga los valores actualizados antes de recalcular
    with col_inp:
        ptv = lambda: (V['KNO3_T_NPT3']+V['KNO3_R_NPT3'])+(V['KNO3_L_NPT4']+V['CSSI_NPT4']+V['CSSR_NPT4'])
        ptm = lambda: V['PRIL_DTP'] + V['SECADO']
 
        def ni(label, key, val, step=10.0, fmt="%.1f"):
            # FIX: no redondear a 3 decimales — respetar la precisión original del valor
            # El format del widget controla la visualización, el valor interno queda exacto
            return st.number_input(label, value=float(val), step=step, format=fmt, key=f"sg_{key}_{sg_rc}")
 
        def inputs_grupo(titulo, items_edit, items_mant, denom, denom_label="USD/T"):
            st.caption(f"**{titulo}**")
            for label, key in items_edit:
                c1, c2 = st.columns([3, 1])
                with c1: V[key] = ni(label, key, V[key])
                with c2: st.metric(denom_label, f"${V[key]/denom:.2f}" if denom > 0 else "-")
            if items_mant:
                mant = sum(V[k] for _, k in items_mant)
                st.caption(f"📌 Mantención = ${mant:,.0f} KUS$")
                for label, key in items_mant:
                    c1, c2 = st.columns([3, 1])
                    with c1: V[key] = ni(f"  ↳ {label}", key, V[key])
                    with c2: st.metric(denom_label, f"${V[key]/denom:.2f}" if denom > 0 else "-")
 
        tabs = st.tabs(["KPI","Pozas NV","Pozas PB","Pozas CS","NPT3","NPT4","Prilado","DTP","Secado","Puerto","Transporte","FC KCl","FC NaNO3"])
        tab_kpi,tab_pnv,tab_ppb,tab_pcs,tab_npt3,tab_npt4,tab_pril,tab_dtp,tab_sec,tab_puerto,tab_tpte,tab_fck,tab_fcn = tabs
 
        with tab_kpi:
            st.markdown("#### Producción (Kton)")
            pc1, pc2 = st.columns(2)
            with pc1:
                st.caption("NPT3")
                V['KNO3_T_NPT3'] = ni("T NPT3","KNO3_T_NPT3",V['KNO3_T_NPT3'],0.1,"%.3f")
                V['KNO3_R_NPT3'] = ni("R NPT3","KNO3_R_NPT3",V['KNO3_R_NPT3'],0.1,"%.3f")
                nv = V['KNO3_T_NPT3']+V['KNO3_R_NPT3']
                st.metric("Total NPT3",f"{nv:.3f}",delta=f"{nv-(BASE['KNO3_T_NPT3']+BASE['KNO3_R_NPT3']):+.3f}",delta_color="off")
            with pc2:
                st.caption("NPT4")
                V['KNO3_L_NPT4'] = ni("L NPT4",   "KNO3_L_NPT4",V['KNO3_L_NPT4'],0.1,"%.3f")
                V['CSSI_NPT4']   = ni("CSSI NPT4","CSSI_NPT4",  V['CSSI_NPT4'],  0.1,"%.3f")
                V['CSSR_NPT4']   = ni("CSSR NPT4","CSSR_NPT4",  V['CSSR_NPT4'],  0.1,"%.3f")
                nv4 = V['KNO3_L_NPT4']+V['CSSI_NPT4']+V['CSSR_NPT4']
                st.metric("Total NPT4",f"{nv4:.3f}",delta=f"{nv4-(BASE['KNO3_L_NPT4']+BASE['CSSI_NPT4']+BASE['CSSR_NPT4']):+.3f}",delta_color="off")
            pt1, pt2 = st.columns(2)
            with pt1:
                st.caption("Terminados")
                V['PRIL_DTP'] = ni("PRILADO+DTP","PRIL_DTP",V['PRIL_DTP'],0.1,"%.3f")
                V['SECADO']   = ni("SECADO",     "SECADO",  V['SECADO'],  0.1,"%.3f")
            with pt2:
                st.metric("Total Term.",f"{ptm():.3f}",delta=f"{ptm()-(BASE['PRIL_DTP']+BASE['SECADO']):+.3f}",delta_color="off")
                st.metric("Total NPT",  f"{ptv():.3f}",delta=f"{ptv()-(BASE['KNO3_T_NPT3']+BASE['KNO3_R_NPT3']+BASE['KNO3_L_NPT4']+BASE['CSSI_NPT4']+BASE['CSSR_NPT4']):+.3f}",delta_color="off")
 
        with tab_pnv:
            inputs_grupo("Gasto Operación",[("Remuneración","PNV_REMUN"),("Energía","PNV_ENERG"),("Arrdo y Servicios","PNV_ARRDO"),("Otros","PNV_OTROS")],[("Mant. Directos","PNV_MANT_D"),("Mant. Dist Mant.","PNV_MANT_M")],ptv())
            st.divider()
            inputs_grupo("Cosecha Preconcentrado",[("Arrdo y Servicios","PNV_PRECO_A"),("Otros","PNV_PRECO_O")],[],ptv())
            st.divider()
            inputs_grupo("Cosecha Producción",[("Arrdo y Servicios","PNV_PRODU_A"),("Otros","PNV_PRODU_O")],[],ptv())
            tot=sum(V[k] for k in ['PNV_REMUN','PNV_ENERG','PNV_ARRDO','PNV_OTROS','PNV_MANT_D','PNV_MANT_M','PNV_PRECO_A','PNV_PRECO_O','PNV_PRODU_A','PNV_PRODU_O'])
            st.success(f"**Total Pozas NV: ${tot:,.0f} KUS$ | Base: ${BASE['G_POZAS_NV']:,.0f}**")
 
        with tab_ppb:
            inputs_grupo("Gasto Total Pozas PB",[("Remuneración","PPB_REMUN"),("Mat. y Repuestos","PPB_MYREP"),("Combustibles","PPB_COMB"),("Arrdo y Servicios","PPB_ARRDO"),("Otros","PPB_OTROS"),("Dist. Gen. EE","PPB_DIST_EE")],[("Mant. Directos","PPB_MANT_D"),("Mant. Dist Mant.","PPB_MANT_M")],ptv())
            st.divider()
            inputs_grupo("Cosecha Preconcentrado",[("Arrdo y Servicios","PPB_PRECO_A"),("Otros","PPB_PRECO_O")],[],ptv())
            st.divider()
            inputs_grupo("Cosecha Producción",[("Arrdo y Servicios","PPB_PRODU_A"),("Otros","PPB_PRODU_O")],[],ptv())
            tot=sum(V[k] for k in ['PPB_REMUN','PPB_MYREP','PPB_COMB','PPB_ARRDO','PPB_OTROS','PPB_DIST_EE','PPB_MANT_D','PPB_MANT_M','PPB_PRECO_A','PPB_PRECO_O','PPB_PRODU_A','PPB_PRODU_O'])
            st.success(f"**Total Pozas PB: ${tot:,.0f} KUS$ | Base: ${BASE['G_POZAS_PB']:,.0f}**")
 
        with tab_pcs:
            inputs_grupo("Gasto Total Pozas CS",[("Remuneración","PCS_REMUN"),("Mat. y Repuestos","PCS_MYREP"),("Energía y Comb.","PCS_ENERG"),("Arriendo y Servicios","PCS_ARRDO"),("Agua","PCS_AGUA"),("Otros","PCS_OTROS")],[("Mant. Directos","PCS_MANT_D"),("Mant. Dist Mant.","PCS_MANT_M")],ptv())
            st.divider()
            inputs_grupo("Cosecha Preconcentrado",[("Arrdo y Servicios","PCS_PRECO_A"),("Otros","PCS_PRECO_O")],[],ptv())
            st.divider()
            inputs_grupo("Cosecha Producción",[("Arrdo y Servicios","PCS_PRODU_A"),("Otros","PCS_PRODU_O")],[],ptv())
            tot=sum(V[k] for k in ['PCS_REMUN','PCS_MYREP','PCS_ENERG','PCS_ARRDO','PCS_AGUA','PCS_OTROS','PCS_MANT_D','PCS_MANT_M','PCS_PRECO_A','PCS_PRECO_O','PCS_PRODU_A','PCS_PRODU_O'])
            st.success(f"**Total Pozas CS: ${tot:,.0f} KUS$ | Base: ${BASE['G_POZAS_CS']:,.0f}**")
            st.caption(f"📌 Dep. CS fija: ${BASE['G_DEPRECIACION_CS']:,.0f} KUS (no editable)")
 
        with tab_npt3:
            inputs_grupo("Gastos NPT III",[("Remuneración","N3_REMUN"),("Energía","N3_ENERG"),("Petroleo/Gas","N3_PETROL"),("Maq. Pesada","N3_MAQ"),("Aguas","N3_AGUA"),("Mat. y Repuestos","N3_MYREP"),("Arriendo y Servicios","N3_ARRDO"),("Ceniza de Soda","N3_CSODA"),("Otros","N3_OTROS"),("De Korda","N3_KORDA")],[("Mant. Directos","N3_MANT_D"),("Mant. Dist Mant.","N3_MANT_M")],ptv())
            tot=sum(V[k] for k in ['N3_REMUN','N3_ENERG','N3_PETROL','N3_MAQ','N3_AGUA','N3_MYREP','N3_ARRDO','N3_CSODA','N3_OTROS','N3_KORDA','N3_MANT_D','N3_MANT_M'])
            st.success(f"**Total NPT3: ${tot:,.0f} KUS$ | Base: ${BASE['G_NPT3']:,.0f}**")
 
        with tab_npt4:
            inputs_grupo("Gastos NPT IV",[("Remuneraciones","N4_REMUN"),("Energía","N4_ENERG"),("Petroleo/Gas","N4_PETROL"),("Maq. Pesada","N4_MAQ"),("Agua","N4_AGUA"),("Ceniza de Soda","N4_CSODA"),("Otros","N4_OTROS"),("De Korda","N4_KORDA")],[("Mant. Directos","N4_MANT_D"),("Mant. Dist Mant.","N4_MANT_M")],ptv())
            tot=sum(V[k] for k in ['N4_REMUN','N4_ENERG','N4_PETROL','N4_MAQ','N4_AGUA','N4_CSODA','N4_OTROS','N4_KORDA','N4_MANT_D','N4_MANT_M'])
            st.success(f"**Total NPT4: ${tot:,.0f} KUS$ | Base: ${BASE['G_NPT4']:,.0f}**")
 
        with tab_pril:
            inputs_grupo("Gasto Planta Prilado",[("Remuneraciones","PR_REMUN"),("Energía","PR_ENERG"),("Petroleo/Gas","PR_PETROL"),("Maq. Pesadas","PR_MAQ"),("Aditivos","PR_ADITI"),("Otros","PR_OTROS")],[("Mant. Directos","PR_MANT_D"),("Mant. Dist Mant.","PR_MANT_M")],ptm())
            tot=sum(V[k] for k in ['PR_REMUN','PR_ENERG','PR_PETROL','PR_MAQ','PR_ADITI','PR_OTROS','PR_MANT_D','PR_MANT_M'])
            st.success(f"**Total Prilado: ${tot:,.0f} KUS$ | Base total: ${BASE['G_PRIL']:,.0f}**")
 
        with tab_dtp:
            inputs_grupo("Gasto DTP",[("Remuneraciones","DT_REMUN"),("Energía","DT_ENERG"),("Petroleo/Gas","DT_PETROL"),("Aditivos","DT_ADITI"),("Otros","DT_OTROS")],[("Mant. Directos","DT_MANT_D"),("Mant. Dist Mant.","DT_MANT_M")],ptm())
            tot=sum(V[k] for k in ['DT_REMUN','DT_ENERG','DT_PETROL','DT_ADITI','DT_OTROS','DT_MANT_D','DT_MANT_M'])
            st.success(f"**Total DTP: ${tot:,.0f} KUS$ | Base: ${BASE['G_DTP']:,.0f}**")
 
        with tab_sec:
            inputs_grupo("Gasto Planta Secado",[("Remuneración","SC_REMUN"),("Energía","SC_ENERG"),("Petroleo/Gas","SC_PETROL"),("Aditivos","SC_ADITI"),("Maq. Pesadas","SC_MAQ"),("Otros","SC_OTROS")],[("Mant. Directos","SC_MANT_D"),("Mant. Dist Mant.","SC_MANT_M")],ptm())
            tot=sum(V[k] for k in ['SC_REMUN','SC_ENERG','SC_PETROL','SC_ADITI','SC_MAQ','SC_OTROS','SC_MANT_D','SC_MANT_M'])
            st.success(f"**Total Secado: ${tot:,.0f} KUS$ | Base: ${BASE['G_SECADO']:,.0f}**")
 
        with tab_puerto:
            c1,c2,c3=st.columns([2,2,1])
            with c1: V['G_EMBARQUE']        =ni("Embarque+Demurrage (KUS)","G_EMBARQUE",        V['G_EMBARQUE'])
            with c2: V['TON_EMBARQUE_GRANEL']=ni("Granel (Kton)",           "TON_EMBARQUE_GRANEL",V['TON_EMBARQUE_GRANEL'],0.1,"%.3f")
            with c3: st.metric("USD/T",f"${V['G_EMBARQUE']/V['TON_EMBARQUE_GRANEL']:.2f}" if V['TON_EMBARQUE_GRANEL']>0 else "-")
            c1,c2,c3=st.columns([2,2,1])
            with c1: V['G_ALMACENAJE']  =ni("Almacenaje (KUS)",  "G_ALMACENAJE",  V['G_ALMACENAJE'])
            with c2: V['TON_ALMACENAJE']=ni("Almacenaje (Kton)", "TON_ALMACENAJE",V['TON_ALMACENAJE'],1.0,"%.1f")
            with c3: st.metric("USD/T",f"${V['G_ALMACENAJE']/V['TON_ALMACENAJE']:.2f}" if V['TON_ALMACENAJE']>0 else "-")
            c1,c2,c3=st.columns([2,2,1])
            with c1: V['G_DIST_T']    =ni("Distributivos (KUS)","G_DIST_T",    V['G_DIST_T'])
            with c2: V['TON_DESPACHO']=ni("Despacho (Kton)",    "TON_DESPACHO",V['TON_DESPACHO'],0.1,"%.3f")
            with c3:
                vd=V['TON_EMBARQUE_TOTAL']+V['TON_DESPACHO']
                st.metric("USD/T",f"${V['G_DIST_T']/vd:.2f}" if vd>0 else "-")
 
        with tab_tpte:
            st.markdown("#### Transporte de Sales")
            Tt=V['TON_TPTE_NV']+V['TON_TPTE_PB']+V['TON_TPTE_CS']
            for lg,kg,lt,kt in [("NV→CS (KUS)","G_TPTE_NV","NV→CS (KTon)","TON_TPTE_NV"),
                                  ("PB→CS (KUS)","G_TPTE_PB","PB→CS (KTon)","TON_TPTE_PB")]:
                c1,c2,c3=st.columns([2,2,1])
                with c1: V[kg]=ni(lg,kg,V[kg])
                with c2: V[kt]=ni(lt,kt,V[kt],0.1,"%.3f")
                with c3: st.metric("USD/KTon",f"${V[kg]/Tt:.2f}" if Tt>0 else "-")
            c1,c2=st.columns([3,1])
            with c1: V['G_CAMINOS_NV']=ni("Caminos NV (KUS)","G_CAMINOS_NV",V['G_CAMINOS_NV'])
            with c2: st.metric("USD/KTon",f"${V['G_CAMINOS_NV']/Tt:.2f}" if Tt>0 else "-")
            st.divider()
            st.markdown("#### Transporte Terminados")
            c1,c2,c3=st.columns([2,2,1])
            with c1: V['G_TPTE_CAM']  =ni("Tpte Camiones (KUS)", "G_TPTE_CAM",  V['G_TPTE_CAM'])
            with c2: V['TON_TPTE_CAM']=ni("Tpte Camiones (Kton)","TON_TPTE_CAM",V['TON_TPTE_CAM'],0.1,"%.3f")
            with c3: st.metric("USD/T",f"${V['G_TPTE_CAM']/V['TON_TPTE_CAM']:.2f}" if V['TON_TPTE_CAM']>0 else "-")
 
        with tab_fck:
            st.markdown("#### ⚗️ Factor Consumo KCl (KTon KCl / Kton prod)")
            n3v=V['KNO3_T_NPT3']+V['KNO3_R_NPT3']; n4v=V['KNO3_L_NPT4']+V['CSSI_NPT4']+V['CSSR_NPT4']
            st.caption("NPT3")
            fck1,fck2,fck3=st.columns(3)
            with fck1: V['FC_MOP90_NPT3']=ni("MOP 90 NPT3","FC_MOP90_NPT3",V['FC_MOP90_NPT3'],0.001,"%.6f")
            with fck2: V['FC_MOP70_NPT3']=ni("MOP 70 NPT3","FC_MOP70_NPT3",V['FC_MOP70_NPT3'],0.001,"%.6f")
            with fck3: V['FC_SS_NPT3']   =ni("SS NPT3",    "FC_SS_NPT3",   V['FC_SS_NPT3'],   0.001,"%.6f")
            st.caption(f"Consumo KCl NPT3: {(V['FC_MOP90_NPT3']+V['FC_MOP70_NPT3']+V['FC_SS_NPT3'])*n3v:.3f} KTon")
            st.caption("NPT4")
            fck4,fck5,fck6=st.columns(3)
            with fck4: V['FC_MOP90_NPT4']=ni("MOP 90 NPT4","FC_MOP90_NPT4",V['FC_MOP90_NPT4'],0.001,"%.6f")
            with fck5: V['FC_MOP70_NPT4']=ni("MOP 70 NPT4","FC_MOP70_NPT4",V['FC_MOP70_NPT4'],0.001,"%.6f")
            with fck6: V['FC_SS_NPT4']   =ni("SS NPT4",    "FC_SS_NPT4",   V['FC_SS_NPT4'],   0.001,"%.6f")
            st.caption(f"Consumo KCl NPT4: {(V['FC_MOP90_NPT4']+V['FC_MOP70_NPT4']+V['FC_SS_NPT4'])*n4v:.3f} KTon")
            st.caption("Precio KCl (US$/T)")
            pk1,pk2,pk3=st.columns(3)
            with pk1: V['P_MOP90']=ni("MOP 90","P_MOP90",V['P_MOP90'],1.0,"%.2f")
            with pk2: V['P_MOP70']=ni("MOP 70","P_MOP70",V['P_MOP70'],1.0,"%.2f")
            with pk3: V['P_SS']   =ni("SS",    "P_SS",   V['P_SS'],   1.0,"%.2f")
 
        with tab_fcn:
            st.markdown("#### 🧂 FC NaNO3 por ruta y subproducto")
            nfc=V['KNO3_T_NPT3']+V['KNO3_R_NPT3']
            st.caption("NPT3")
            fn1,fn2,fn3=st.columns(3)
            with fn1: V['FC_NaNO3_CAT1_NPT3']     =ni("CAT1",    "FC_NaNO3_CAT1_NPT3",    V['FC_NaNO3_CAT1_NPT3'],    0.01,"%.4f")
            with fn2: V['FC_NaNO3_PB_NPT3']       =ni("PB",      "FC_NaNO3_PB_NPT3",      V['FC_NaNO3_PB_NPT3'],      0.01,"%.4f")
            with fn3: V['FC_NaNO3_CS_NPT3']       =ni("CS",      "FC_NaNO3_CS_NPT3",      V['FC_NaNO3_CS_NPT3'],      0.01,"%.4f")
            st.caption("NPT4")
            fn4,fn5,fn6,fn7,fn8=st.columns(5)
            with fn4: V['FC_NaNO3_CS_NPT4']       =ni("CS",        "FC_NaNO3_CS_NPT4",       V['FC_NaNO3_CS_NPT4'],       0.01,"%.4f")
            with fn5: V['FC_NaNO3_PB_CSSI_NPT4']  =ni("PB CSSI",   "FC_NaNO3_PB_CSSI_NPT4",  V['FC_NaNO3_PB_CSSI_NPT4'],  0.01,"%.4f")
            with fn6: V['FC_NaNO3_CAT1_CSSI_NPT4']=ni("CAT1 CSSI", "FC_NaNO3_CAT1_CSSI_NPT4",V['FC_NaNO3_CAT1_CSSI_NPT4'],0.01,"%.4f")
            with fn7: V['FC_NaNO3_CAT1_CSSR_NPT4']=ni("CAT1 CSSR", "FC_NaNO3_CAT1_CSSR_NPT4",V['FC_NaNO3_CAT1_CSSR_NPT4'],0.01,"%.4f")
            with fn8: V['FC_NaNO3_PURGA_NPT4']    =ni("FC Purga",  "FC_NaNO3_PURGA_NPT4",    V['FC_NaNO3_PURGA_NPT4'],    0.01,"%.4f")
            nv_c=(nfc*V['FC_NaNO3_CAT1_NPT3']+V['CSSR_NPT4']*V['FC_NaNO3_CAT1_CSSR_NPT4']+V['CSSI_NPT4']*V['FC_NaNO3_CAT1_CSSI_NPT4'])
            pb_c=(nfc*V['FC_NaNO3_PB_NPT3']+V['CSSI_NPT4']*V['FC_NaNO3_PB_CSSI_NPT4'])
            cs_c=nfc*V['FC_NaNO3_CS_NPT3']+V['KNO3_L_NPT4']*V['FC_NaNO3_CS_NPT4']
            Tt2=V['TON_TPTE_NV']+V['TON_TPTE_PB']+V['TON_TPTE_CS']
            pt2=ptv(); precio_t=(V['G_TPTE_NV']+V['G_TPTE_PB']+V['G_CAMINOS_NV'])/Tt2 if Tt2>0 else 0.0
            fc_t=(nv_c+pb_c+cs_c)/pt2 if pt2>0 else 0.0
            st.caption(f"NV:{nv_c:.3f} | PB:{pb_c:.3f} | CS:{cs_c:.3f} KTon")
            st.caption(f"FC:{fc_t:.4f} | Precio:${precio_t:.2f} | **=> 1.1=${precio_t*fc_t:.2f} USD/T**")
 
    # FIX: col_res DESPUÉS de col_inp — V ya tiene todos los valores actualizados
    with col_res:
        costo_base, comp_base = recalcular(BASE)
        costo_sim,  comp_sim  = recalcular(V)
        delta_total = costo_sim - costo_base
        dd = 0.0 if abs(delta_total) < 0.005 else round(delta_total, 2)
        ds = "0.00 USD/T" if dd == 0.0 else f"{dd:+.2f} USD/T"
        st.markdown(f"#### 📊 Resultado — {MESES[mes]}")
        st.metric("PPTO Base", f"${costo_base:.2f} / T")
        st.metric("Simulado",  f"${costo_sim:.2f} / T", delta=ds, delta_color="inverse")
        st.divider()
        rows_r = [{"Componente":k,"PPTO":round(b,2),"Sim":round(s,2),"Δ":round(s-b,2)}
                  for k,(b,s) in zip(comp_base.keys(), zip(comp_base.values(), comp_sim.values()))]
        df_res = pd.DataFrame(rows_r)
        def _cd(val):
            if isinstance(val, float):
                if val > 0: return 'color:#D83030;font-weight:bold'
                if val < 0: return 'color:#80BC00;font-weight:bold'
            return ''
        st.dataframe(df_res.style.map(_cd, subset=["Δ"]).format({"PPTO":"{:.2f}","Sim":"{:.2f}","Δ":"{:+.2f}"}),
                     use_container_width=True, hide_index=True, height=360)
        st.divider()
        if st.button("🔄 Restablecer todo", use_container_width=True, key="sg_reset"):
            st.session_state['sg_rc']   = st.session_state.get('sg_rc', 0) + 1
            st.session_state['sg_sv']   = copy.deepcopy(st.session_state['sg_base'])
            st.session_state['sg_mes']  = mes
            st.session_state['sg_tipo'] = tipo_sens
            st.rerun()