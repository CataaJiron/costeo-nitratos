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
    pagina = st.radio("", ["Dashboard", "Analisis mensual", "Sensibilidad PPTO", "Sensibilidad R+P", "Asistente"],
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
        EMB_TOTAL = v["TON_EMBARQUE_ENVASADO"] + v[ 'TON_EMBARQUE_GRANEL']
        c_alm      = v['G_ALMACENAJE']/ v['TON_ALMACENAJE']      if v['TON_ALMACENAJE'] > 0      else 0.0
        vol_d      = EMB_TOTAL + v['TON_DESPACHO']
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

        def fila_usdton_puerto(label_usd, key_usd, label_ton, key_ton, step_ton=0.1):
            c1, c2, c3 = st.columns([2, 2, 1])
            with c1:
                V[key_usd] = st.number_input(label_usd, value=round(V[key_usd], 1), step=10.0, format="%.1f", key=f"ui_puerto_{key_usd}_{rc}")
            with c2:
                V[key_ton] = st.number_input(label_ton, value=round(V[key_ton], 3), step=step_ton, format="%.3f", key=f"ui_puerto_{key_ton}_{rc}")
            with c3:
                ratio = V[key_usd] / V[key_ton] if V[key_ton] != 0 else 0.0
                st.metric("=> USD/T", f"${ratio:.2f}")

        fila_usdton_puerto("Embarque+Demurrage (KUS)", "G_EMBARQUE",
                           "Embarque Granel (Kton)",    "TON_EMBARQUE_GRANEL","TON_EMBARQUE_ENVASADO"
                           step_ton=0.1)

        # Embarque envasado — editable
        c1, c2 = st.columns([3, 1])
        with c1:
            V['TON_EMBARQUE_ENVASADO'] = st.number_input("Embarque Envasado (Kton)", value=round(V['TON_EMBARQUE_ENVASADO'],3), step=0.1, format="%.3f", key=f"ui_puerto_TON_EMBARQUE_ENVASADO_{rc}")
        with c2:
            ton_emb_total = V['TON_EMBARQUE_GRANEL'] + V['TON_EMBARQUE_ENVASADO']
            st.metric("Total Emb.", f"{ton_emb_total:.3f}")
        # Actualizar TON_EMBARQUE_TOTAL como suma
        V['TON_EMBARQUE_TOTAL'] = V['TON_EMBARQUE_GRANEL'] + V['TON_EMBARQUE_ENVASADO']

        fila_usdton_puerto("Almacenaje (KUS)", "G_ALMACENAJE",
                           "Almacenaje (Kton)", "TON_ALMACENAJE",
                           step_ton=1.0)

        c1, c2, c3 = st.columns([2, 2, 1])
        with c1:
            V['G_DIST_T'] = st.number_input("Distributivos (KUS)", value=round(V['G_DIST_T'],1), step=10.0, format="%.1f", key=f"ui_G_DIST_T_{rc}")
        with c2:
            V['TON_DESPACHO'] = st.number_input("Despacho Cam. (Kton)", value=round(V['TON_DESPACHO'],3), step=0.1, format="%.3f", key=f"ui_TON_DESPACHO_{rc}")
        with c3:
            vol_d = V['TON_EMBARQUE_TOTAL'] + V['TON_DESPACHO']
            ratio_d = V['G_DIST_T'] / vol_d if vol_d > 0 else 0.0
            st.metric("=> USD/T", f"${ratio_d:.2f}")

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