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
# SENSIBILIDAD
# ══════════════════════════════════════════════════════════════════════════════
elif pagina == "Sensibilidad":
    st.title("Simulador de sensibilidad")
    st.caption("Modifica variables para ver el impacto en el costo total US$/T")

    col_v, _ = st.columns([2,6])
    with col_v:
        modo = st.radio("Vista base", ["Puntual","Acumulado"], horizontal=True, label_visibility="collapsed")
    tipo = "Puntual" if modo == "Puntual" else "Acumulado"

    mes = botones_mes("sens")
    st.divider()

    # ── helper ──────────────────────────────────────────────────────────────
    label_esc = "PPTO"
    def get(a, sa, c, med='KUS'):
        return gv(df, a, sa, c, mes, tipo, 'PPTO', med)

    # ── Bases ────────────────────────────────────────────────────────────────
    costo_base    = sum(get('COSTO TOTAL', sa, c) for sa, c, _ in COSTOS)
    prod_npt3     = get('PRODUCCION','NPT3','PRODUCCION TOTAL NPT3','Kton')
    prod_npt4     = get('PRODUCCION','NPT4','PRODUCCION TOTAL NPT4','Kton')
    prod_total    = prod_npt3 + prod_npt4
    prod_pril_dtp = get('PRODUCCION','TERMINADOS','PRILADO + DTP','Kton')
    prod_secado   = get('PRODUCCION','TERMINADOS','SECADO','Kton')
    prod_term     = prod_pril_dtp + prod_secado

    st.info(
        f"**{MESES[mes]} — {modo} (PPTO)** | "
        f"Costo base: **${costo_base:.1f}/T** | "
        f"Prod total: {prod_total:.1f} Kton | "
        f"Terminados: {prod_term:.1f} Kton"
    )

    tab_g, tab_p, tab_fc = st.tabs(["Gastos (KUS)", "Producción (Kton)", "Factores de consumo"])
    deltas_g, deltas_p, deltas_fc = {}, {}, {}

    GASTOS_DEF = [
        ('TRANSPORTE DE SALES','Total Transporte de Sales NV + PB','- Transporte Sales NV',  'KUS','Gasto Tpte NV',     'prod_total'),
        ('TRANSPORTE DE SALES','Total Transporte de Sales NV + PB','- Transporte Sales PB',  'KUS','Gasto Tpte PB',     'prod_total'),
        ('GASTO','CRISTALIZACION','Gasto NPT III + Korda',                                   'KUS','Gasto Planta NPT3', 'prod_total'),
        ('GASTO','CRISTALIZACION','Gasto NPT IV',                                             'KUS','Gasto Planta NPT4', 'prod_total'),
        ('GASTO','TERMINADOS','Gasto Transporte Intermedios',                                 'KUS','Gasto Tpte CS-TOC', 'prod_total'),
        ('GASTO','TERMINADOS','Gasto Planta Prilado CS',                                      'KUS','Gasto Prilado',     'prod_pril_dtp'),
        ('GASTO','TERMINADOS','Gasto Planta DTP',                                             'KUS','Gasto DTP',         'prod_pril_dtp'),
        ('GASTO','TERMINADOS','Gasto Planta Secado KNO3',                                     'KUS','Gasto Secado',      'prod_secado'),
        ('Embarque Granel Trimestral','EMBARQUE','Embarque Granel + Demurrage',               'KUS','Gasto Embarque',    'prod_total'),
        ('Almacenaje Trimestral','ALMACENAJE','Almacenaje Trimestral',                        'KUS','Gasto Almacenaje',  'prod_total'),
        ('Distributivos Trimestral','DISTRIBUTIVOS','Distributivos Trimestral',               'KUS','Distributivos',     'prod_total'),
        ('GASTO','Operación Pozas (NV+CS+PV+PB)','Gasto Operación Pozas NV',                 'KUS','Gasto Pozas NV',    'prod_total'),
        ('GASTO','Operación Pozas (NV+CS+PV+PB)','Gasto Operación Pozas CS',                 'KUS','Gasto Pozas CS',    'prod_total'),
        ('GASTO','Operación Pozas (NV+CS+PV+PB)','Gasto Operación Pozas PB',                 'KUS','Gasto Pozas PB',    'prod_total'),
    ]
    with tab_g:
        st.caption("Delta en KUS (positivo = sube gasto = sube costo)")
        col1, col2 = st.columns(2)
        for i, (a, sa, c, med, label, prod_key) in enumerate(GASTOS_DEF):
            base = get(a, sa, c, med)
            with (col1 if i % 2 == 0 else col2):
                d = st.number_input(f"{label}  *(base: {base:.0f})*", value=0, step=50, key=f"g_{i}")
                deltas_g[label] = (d, prod_key, base)

    PROD_DEF = [
        ('PRODUCCION','TERMINADOS','PRILADO + DTP',    'Kton','Prod Prilado+DTP',  'prod_pril_dtp'),
        ('PRODUCCION','TERMINADOS','SECADO',           'Kton','Prod Secado',        'prod_secado'),
        ('PRODUCCION','NPT3','- KNO3 T NPT III',       'Kton','KNO3 T NPT III',    'prod_npt3'),
        ('PRODUCCION','NPT3','- KNO3 R NPT III',       'Kton','KNO3 R NPT III',    'prod_npt3'),
        ('PRODUCCION','NPT4','- CSSR NPT II/IV',       'Kton','CSSR NPT II/IV',    'prod_npt4'),
        ('PRODUCCION','NPT4','- CSSI NPT II/IV',       'Kton','CSSI NPT II/IV',    'prod_npt4'),
        ('PRODUCCION','NPT4','- KNO3 L NPT II/IV',    'Kton','KNO3 L NPT II/IV',  'prod_npt4'),
    ]
    with tab_p:
        st.caption("Delta en Kton (positivo = sube producción)")
        col1, col2 = st.columns(2)
        for i, (a, sa, c, med, label, prod_key) in enumerate(PROD_DEF):
            base = get(a, sa, c, med)
            with (col1 if i % 2 == 0 else col2):
                d = st.number_input(f"{label}  *(base: {base:.2f})*", value=0.0, step=0.5, key=f"p_{i}")
                deltas_p[label] = (d, prod_key, base)

    FC_DEF = [
        ('TRANSPORTE DE SALES','- Factor Consumo de Sales','- Factor Consumo de Sales','NaNO3/Ton','Fc NaNO3',          'fc_npt3_mop90'),
        ('KCl','Fc KCl NPT3','MOP 90',  'KTon KCl 95%','Fc KCl MOP90 NPT3','fc_npt3_mop90'),
        ('KCl','CONSUMO NPT3','MOP 70', 'KTon KCl 95%','Fc KCl MOP70 NPT3','fc_npt3_mop70'),
        ('KCl','CONSUMO NPT3','SS',     'KTon KCl 95%','Fc KCl SS NPT3',   'fc_npt3_ss'),
        ('KCl','Fc KCl NPT4','MOP 70',  'KTon KCl 95%','Fc KCl MOP70 NPT4','fc_npt4_mop70'),
    ]
    with tab_fc:
        st.caption("Delta en el factor (ajuste directo sobre el valor base)")
        col1, col2 = st.columns(2)
        for i, (a, sa, c, med, label, fc_key) in enumerate(FC_DEF):
            base = get(a, sa, c, med)
            with (col1 if i % 2 == 0 else col2):
                d = st.number_input(f"{label}  *(base: {base:.4f})*", value=0.0, step=0.01, format="%.4f", key=f"fc_{i}")
                deltas_fc[label] = (d, fc_key, base)

    st.divider()

    # ── CALCULAR IMPACTO ─────────────────────────────────────────────────────
    new_prod = {
        'prod_npt3':     prod_npt3,
        'prod_npt4':     prod_npt4,
        'prod_pril_dtp': prod_pril_dtp,
        'prod_secado':   prod_secado,
    }
    for label, (d, prod_key, base) in deltas_p.items():
        if d != 0:
            new_prod[prod_key] = new_prod[prod_key] + d

    new_prod['prod_total'] = new_prod['prod_npt3'] + new_prod['prod_npt4']
    new_prod['prod_term']  = new_prod['prod_pril_dtp'] + new_prod['prod_secado']

    pt    = new_prod['prod_total']
    p3    = new_prod['prod_npt3']
    p4    = new_prod['prod_npt4']
    pterm = new_prod['prod_term']

    def gd(label, a, sa, c, med='KUS'):
        base = get(a, sa, c, med)
        d, _, _ = deltas_g.get(label, (0, None, None))
        return base + d

    def fcd(label, a, sa, c, med):
        base = get(a, sa, c, med)
        d, _, _ = deltas_fc.get(label, (0, None, None))
        return base + d

    detalle     = []
    costo_nuevo = 0

    # 1.1 Tpte Sales
    precio_tpte = get('TRANSPORTE DE SALES','Total Transporte de Sales (promedio)','Total Transporte de Sales (promedio)','USD/TNitr sales')
    fc_nano3_b  = get('TRANSPORTE DE SALES','- Factor Consumo de Sales','- Factor Consumo de Sales','NaNO3/Ton')
    fc_nano3_n  = fcd('Fc NaNO3','TRANSPORTE DE SALES','- Factor Consumo de Sales','- Factor Consumo de Sales','NaNO3/Ton')
    tpte_b = fc_nano3_b * precio_tpte
    tpte_n = fc_nano3_n * precio_tpte
    costo_nuevo += tpte_n
    if abs(tpte_n - tpte_b) > 0.01:
        detalle.append(("Tpte Sales", f"Fc:{fc_nano3_n:.4f} × ${precio_tpte:.1f}", round(tpte_n - tpte_b, 1)))

    # 1.2 Op. Pozas
    g_pozas_b = (get('GASTO','Operación Pozas (NV+CS+PV+PB)','Gasto Operación Pozas NV') +
                 get('GASTO','Operación Pozas (NV+CS+PV+PB)','Gasto Operación Pozas PB') +
                 get('GASTO','Operación Pozas (NV+CS+PV+PB)','Gasto Operación Pozas CS') +
                 get('GASTO','Operación Pozas (NV+CS+PV+PB)','Depreciación Pozas NV'))
    g_pozas_n = (gd('Gasto Pozas NV','GASTO','Operación Pozas (NV+CS+PV+PB)','Gasto Operación Pozas NV') +
                 gd('Gasto Pozas PB','GASTO','Operación Pozas (NV+CS+PV+PB)','Gasto Operación Pozas PB') +
                 gd('Gasto Pozas CS','GASTO','Operación Pozas (NV+CS+PV+PB)','Gasto Operación Pozas CS') +
                 get('GASTO','Operación Pozas (NV+CS+PV+PB)','Depreciación Pozas NV'))
    pozas_b = g_pozas_b / prod_total if prod_total > 0 else 0
    pozas_n = g_pozas_n / pt         if pt > 0         else 0
    costo_nuevo += pozas_n
    if abs(pozas_n - pozas_b) > 0.01:
        detalle.append(("Op. Pozas", f"${g_pozas_n:.0f} KUS / {pt:.1f} Kton", round(pozas_n - pozas_b, 1)))

    # 1.3 Cristalización
    g_crist_b = (get('GASTO','CRISTALIZACION','Gasto NPT IV') +
                 get('GASTO','CRISTALIZACION','Gasto NPT III + Korda') +
                 get('GASTO','CRISTALIZACION','Depreciación NPT III') +
                 get('GASTO','CRISTALIZACION','Depreciación NPT IV'))
    g_crist_n = (gd('Gasto Planta NPT4','GASTO','CRISTALIZACION','Gasto NPT IV') +
                 gd('Gasto Planta NPT3','GASTO','CRISTALIZACION','Gasto NPT III + Korda') +
                 get('GASTO','CRISTALIZACION','Depreciación NPT III') +
                 get('GASTO','CRISTALIZACION','Depreciación NPT IV'))
    crist_b = g_crist_b / prod_total if prod_total > 0 else 0
    crist_n = g_crist_n / pt         if pt > 0         else 0
    costo_nuevo += crist_n
    if abs(crist_n - crist_b) > 0.01:
        detalle.append(("Cristalización", f"${g_crist_n:.0f} KUS / {pt:.1f} Kton", round(crist_n - crist_b, 1)))

    # 1.4 KCl
    fc_mop90_npt3_b = get('KCl','Fc KCl NPT3','MOP 90','KTon KCl 95%')
    fc_mop70_npt3_b = get('KCl','CONSUMO NPT3','MOP 70','KTon KCl 95%')
    fc_ss_npt3_b    = get('KCl','CONSUMO NPT3','SS','KTon KCl 95%')
    fc_mop90_npt4_b = get('KCl','Fc KCl NPT4','MOP 90','KTon KCl 95%') or 0
    fc_mop70_npt4_b = get('KCl','Fc KCl NPT4','MOP 70','KTon KCl 95%')
    fc_ss_npt4_b    = get('KCl','Fc KCl NPT4','SS','KTon KCl 95%') or 0

    fc_mop90_npt3_n = fcd('Fc KCl MOP90 NPT3','KCl','Fc KCl NPT3','MOP 90','KTon KCl 95%')
    fc_mop70_npt3_n = fcd('Fc KCl MOP70 NPT3','KCl','CONSUMO NPT3','MOP 70','KTon KCl 95%')
    fc_ss_npt3_n    = fcd('Fc KCl SS NPT3','KCl','CONSUMO NPT3','SS','KTon KCl 95%')
    fc_mop70_npt4_n = fcd('Fc KCl MOP70 NPT4','KCl','Fc KCl NPT4','MOP 70','KTon KCl 95%')
    fc_mop90_npt4_n = fc_mop90_npt4_b
    fc_ss_npt4_n    = fc_ss_npt4_b

    precio_mop90 = get('KCl','Precio KCl','MOP 90','US$/T')
    precio_mop70 = get('KCl','Precio KCl','MOP 70','US$/T')
    precio_ss    = get('KCl','Precio KCl','SS','US$/T')

    def calc_kcl(p3_, p4_, fc90_3, fc70_3, fcss_3, fc90_4, fc70_4, fcss_4):
        cons_90 = fc90_3 * p3_ + fc90_4 * p4_
        cons_70 = fc70_3 * p3_ + fc70_4 * p4_
        cons_ss = fcss_3 * p3_ + fcss_4 * p4_
        cons_tot = cons_90 + cons_70 + cons_ss
        pt_ = p3_ + p4_
        fc_global  = cons_tot / pt_ if pt_ > 0 else 0
        costo_prom = (precio_mop90 * cons_90 + precio_mop70 * cons_70 + precio_ss * cons_ss) / cons_tot if cons_tot > 0 else 0
        return fc_global * costo_prom

    kcl_b = calc_kcl(prod_npt3, prod_npt4, fc_mop90_npt3_b, fc_mop70_npt3_b, fc_ss_npt3_b, fc_mop90_npt4_b, fc_mop70_npt4_b, fc_ss_npt4_b)
    kcl_n = calc_kcl(p3, p4, fc_mop90_npt3_n, fc_mop70_npt3_n, fc_ss_npt3_n, fc_mop90_npt4_n, fc_mop70_npt4_n, fc_ss_npt4_n)
    costo_nuevo += kcl_n
    if abs(kcl_n - kcl_b) > 0.01:
        detalle.append(("KCl", f"Fc×CostoPromedio → ${kcl_n:.1f}/T", round(kcl_n - kcl_b, 1)))

    # 1.5 Terminados + Tpte Intermedios
    g_term_b = (get('GASTO','TERMINADOS','Gasto Planta Prilado CS') +
                get('GASTO','TERMINADOS','Gasto Planta DTP') +
                get('GASTO','TERMINADOS','Gasto Planta Secado KNO3') +
                get('GASTO','TERMINADOS','Gasto Transporte Intermedios') +
                get('GASTO','TERMINADOS','Depreciación Planta Prilado CS') +
                get('GASTO','TERMINADOS','Depreciación Planta DTP') +
                get('GASTO','TERMINADOS','Depreciación Planta Secado KNO3'))
    g_term_n = (gd('Gasto Prilado','GASTO','TERMINADOS','Gasto Planta Prilado CS') +
                gd('Gasto DTP','GASTO','TERMINADOS','Gasto Planta DTP') +
                gd('Gasto Secado','GASTO','TERMINADOS','Gasto Planta Secado KNO3') +
                gd('Gasto Tpte CS-TOC','GASTO','TERMINADOS','Gasto Transporte Intermedios') +
                get('GASTO','TERMINADOS','Depreciación Planta Prilado CS') +
                get('GASTO','TERMINADOS','Depreciación Planta DTP') +
                get('GASTO','TERMINADOS','Depreciación Planta Secado KNO3'))
    term_b = g_term_b / prod_term if prod_term > 0 else 0
    term_n = g_term_n / pterm     if pterm > 0     else 0
    costo_nuevo += term_n
    if abs(term_n - term_b) > 0.01:
        detalle.append(("Terminados+Tpte", f"${g_term_n:.0f} KUS / {pterm:.1f} Kton", round(term_n - term_b, 1)))

    # 1.6 Tpte y Puerto
    tpte_cam_ton     = get('PRODUCCION','TERMINADOS','Transporte Camiones Terminados','Kton')
    emb_granel_ton   = get('PRODUCCION','TERMINADOS','Embarque Granel','Kton')
    emb_envasado_ton = get('PRODUCCION','TERMINADOS','Embarque Envasado','Kton')
    emb_total_ton    = emb_granel_ton + emb_envasado_ton
    desp_cam_ton     = get('PRODUCCION','TERMINADOS','Despacho Camiones','Kton')
    consol_ton       = get('PRODUCCION','TERMINADOS','Consolidación Container','Kton')
    alm_ton          = get('PRODUCCION','TERMINADOS','Almacenaje','Kton')
    tot_despacho     = emb_total_ton + desp_cam_ton + consol_ton

    tpte_cam_usd_b = (get('TRANSPORTE DE SALES','Total Transporte de Sales NV + PB','- Transporte Sales NV') +
                      get('TRANSPORTE DE SALES','Total Transporte de Sales NV + PB','- Transporte Sales PB'))
    tpte_cam_usd_n = (gd('Gasto Tpte NV','TRANSPORTE DE SALES','Total Transporte de Sales NV + PB','- Transporte Sales NV') +
                      gd('Gasto Tpte PB','TRANSPORTE DE SALES','Total Transporte de Sales NV + PB','- Transporte Sales PB'))
    tpte_cam_b = tpte_cam_usd_b / tpte_cam_ton if tpte_cam_ton > 0 else 0
    tpte_cam_n = tpte_cam_usd_n / tpte_cam_ton if tpte_cam_ton > 0 else 0

    emb_usd_b  = get('Embarque Granel Trimestral','EMBARQUE','Embarque Granel + Demurrage')
    emb_usd_n  = gd('Gasto Embarque','Embarque Granel Trimestral','EMBARQUE','Embarque Granel + Demurrage')
    alm_usd_b  = get('Almacenaje Trimestral','ALMACENAJE','Almacenaje Trimestral')
    alm_usd_n  = gd('Gasto Almacenaje','Almacenaje Trimestral','ALMACENAJE','Almacenaje Trimestral')
    dist_usd_b = get('Distributivos Trimestral','DISTRIBUTIVOS','Distributivos Trimestral')
    dist_usd_n = gd('Distributivos','Distributivos Trimestral','DISTRIBUTIVOS','Distributivos Trimestral')
    dep_pto    = get('GASTO','PUERTO','Depreciación Puerto')

    embarque_b  = emb_usd_b  / emb_granel_ton if emb_granel_ton > 0 else 0
    embarque_n  = emb_usd_n  / emb_granel_ton if emb_granel_ton > 0 else 0
    almacenaje_b = alm_usd_b / alm_ton         if alm_ton > 0       else 0
    almacenaje_n = alm_usd_n / alm_ton         if alm_ton > 0       else 0
    distrib_b   = dist_usd_b / tot_despacho    if tot_despacho > 0  else 0
    distrib_n   = dist_usd_n / tot_despacho    if tot_despacho > 0  else 0
    dep_pto_usd = dep_pto    / tot_despacho    if tot_despacho > 0  else 0

    pto_b = tpte_cam_b + embarque_b + almacenaje_b + distrib_b + dep_pto_usd
    pto_n = tpte_cam_n + embarque_n + almacenaje_n + distrib_n + dep_pto_usd
    costo_nuevo += pto_n
    if abs(pto_n - pto_b) > 0.01:
        detalle.append(("Tpte y Puerto", f"Cam+Pto: ${pto_n:.1f}/T", round(pto_n - pto_b, 1)))

    # 1.7 Pérdidas y FE
    op_dep_b = tpte_b + pozas_b + crist_b + kcl_b
    op_dep_n = tpte_n + pozas_n + crist_n + kcl_n

    gen_fe_b     = get('GASTO','PERDIDAS','Generación Producto FE (Terminados)')
    gen_perd_b   = get('GASTO','PERDIDAS','Generación Perdidas / Costras (Terminados)')
    perd_pto_pct = get('GASTO','PERDIDAS','Perdidas y degradaciones puerto y cancha','%')

    perd_term_b = ((gen_fe_b + gen_perd_b) / prod_term if prod_term > 0 else 0) * op_dep_b
    perd_term_n = ((gen_fe_b + gen_perd_b) / pterm     if pterm > 0     else 0) * op_dep_n
    perd_pto_b  = perd_pto_pct * (op_dep_b + term_b + perd_term_b)
    perd_pto_n  = perd_pto_pct * (op_dep_n + term_n + perd_term_n)
    perdidas_b  = perd_term_b + perd_pto_b
    perdidas_n  = perd_term_n + perd_pto_n
    costo_nuevo += perdidas_n
    if abs(perdidas_n - perdidas_b) > 0.01:
        detalle.append(("Pérdidas y FE", f"Term+Pto: ${perdidas_n:.1f}/T", round(perdidas_n - perdidas_b, 1)))

    # 1.8 Distributivos + Depreciación
    dist_nit  = get('GASTO','DISTRIBUTIVOS','Distributivos Nitratos KUSD')
    dep_comun = get('GASTO','DISTRIBUTIVOS','Depreciación Costo Común')
    distdep_b = (dist_nit + dep_comun) / prod_total if prod_total > 0 else 0
    distdep_n = (dist_nit + dep_comun) / pt         if pt > 0         else 0
    costo_nuevo += distdep_n
    if abs(distdep_n - distdep_b) > 0.01:
        detalle.append(("Dist+Depreciación", f"${dist_nit+dep_comun:.0f} KUS / {pt:.1f} Kton", round(distdep_n - distdep_b, 1)))

    # ── MÉTRICAS ─────────────────────────────────────────────────────────────
    impacto = costo_nuevo - costo_base

    k1, k2, k3 = st.columns(3)
    k1.metric(f"Costo base {label_esc} {MESES[mes]}", f"${costo_base:.1f}/T")
    k2.metric("Impacto total", f"{impacto:+.1f} US$/T", delta_color="inverse")
    k3.metric("Nuevo costo estimado", f"${costo_nuevo:.1f}/T",
              delta=f"{impacto:+.1f}", delta_color="inverse")

    if detalle:
        st.subheader("Detalle del impacto")
        df_d = pd.DataFrame(detalle, columns=["Componente","Detalle cálculo","Impacto US$/T"])
        def col_imp(val):
            if isinstance(val, float):
                return "color: red" if val > 0 else "color: green"
            return ""
        st.dataframe(
            df_d.style
                .map(col_imp, subset=["Impacto US$/T"])
                .format({"Impacto US$/T": "{:.1f}"}),
            use_container_width=True, hide_index=True
        )