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
    st.dataframe(df_tabla.style.apply(highlight, axis=1),
                 use_container_width=True, hide_index=True, height=500)


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

    # Bases
    costo_base = sum(gv(df,'COSTO TOTAL',sa,c,mes,tipo,'PPTO') for sa,c,_ in COSTOS)
    prod_npt3  = gv(df,'PRODUCCION','NPT3','PRODUCCION TOTAL NPT3',mes,tipo,'PPTO','Kton')
    prod_npt4  = gv(df,'PRODUCCION','NPT4','PRODUCCION TOTAL NPT4',mes,tipo,'PPTO','Kton')
    prod_total = prod_npt3 + prod_npt4
    prod_pril_dtp = gv(df,'PRODUCCION','TERMINADOS','PRILADO + DTP',mes,tipo,'PPTO','Kton')
    prod_secado   = gv(df,'PRODUCCION','TERMINADOS','SECADO',mes,tipo,'PPTO','Kton')
    prod_term     = prod_pril_dtp + prod_secado

    st.info(
        f"**{MESES[mes]} — {modo} (PPTO)** | "
        f"Costo base: **${costo_base:.1f}/T** | "
        f"Prod total: {prod_total:.1f} Kton | "
        f"Terminados: {prod_term:.1f} Kton"
    )

    tab_g, tab_p, tab_fc = st.tabs(["Gastos (KUS)", "Producción (Kton)", "Factores de consumo"])

    deltas_g  = {}
    deltas_p  = {}
    deltas_fc = {}

    # ── TAB GASTOS ──────────────────────────────────────────────────────────
    GASTOS_DEF = [
        ('TRANSPORTE DE SALES','Total Transporte de Sales NV + PB','- Transporte Sales NV',  'KUS','Gasto Tpte NV',      'prod_total'),
        ('TRANSPORTE DE SALES','Total Transporte de Sales NV + PB','- Transporte Sales PB',  'KUS','Gasto Tpte PB',      'prod_total'),
        ('GASTO','CRISTALIZACION','Gasto NPT III + Korda',                                   'KUS','Gasto Planta NPT3',  'prod_total'),
        ('GASTO','CRISTALIZACION','Gasto NPT IV',                                             'KUS','Gasto Planta NPT4',  'prod_total'),
        ('GASTO','TERMINADOS','Gasto Transporte Intermedios',                                 'KUS','Gasto Tpte CS-TOC',  'prod_total'),
        ('GASTO','TERMINADOS','Gasto Planta Prilado CS',                                      'KUS','Gasto Prilado',      'prod_pril_dtp'),
        ('GASTO','TERMINADOS','Gasto Planta DTP',                                             'KUS','Gasto DTP',          'prod_pril_dtp'),
        ('GASTO','TERMINADOS','Gasto Planta Secado KNO3',                                     'KUS','Gasto Secado',       'prod_secado'),
        ('Embarque Granel Trimestral','EMBARQUE','Embarque Granel + Demurrage',               'KUS','Gasto Embarque',     'prod_total'),
        ('Almacenaje Trimestral','ALMACENAJE','Almacenaje Trimestral',                        'KUS','Gasto Almacenaje',   'prod_total'),
        ('Distributivos Trimestral','DISTRIBUTIVOS','Distributivos Trimestral',               'KUS','Distributivos',      'prod_total'),
        ('GASTO','Operación Pozas (NV+CS+PV+PB)','Gasto Operación Pozas NV',                 'KUS','Gasto Pozas NV',     'prod_total'),
        ('GASTO','Operación Pozas (NV+CS+PV+PB)','Gasto Operación Pozas CS',                 'KUS','Gasto Pozas CS',     'prod_total'),
        ('GASTO','Operación Pozas (NV+CS+PV+PB)','Gasto Operación Pozas PB',                 'KUS','Gasto Pozas PB',     'prod_total'),
    ]

    with tab_g:
        st.caption("Delta en KUS (positivo = sube gasto = sube costo)")
        col1, col2 = st.columns(2)
        for i, (a,sa,c,med,label,prod_key) in enumerate(GASTOS_DEF):
            base = gv(df, a, sa, c, mes, tipo, 'PPTO', med)
            with (col1 if i%2==0 else col2):
                d = st.number_input(f"{label}  *(base: {base:.0f})*", value=0, step=50, key=f"g_{i}")
                deltas_g[label] = (d, prod_key, base)

    # ── TAB PRODUCCIÓN ──────────────────────────────────────────────────────
    PROD_DEF = [
        ('PRODUCCION','TERMINADOS','PRILADO + DTP',     'Kton','Prod Prilado+DTP',   'prod_pril_dtp'),
        ('PRODUCCION','TERMINADOS','SECADO',            'Kton','Prod Secado',         'prod_secado'),
        ('PRODUCCION','NPT3','- KNO3 T NPT III',        'Kton','KNO3 T NPT III',      'prod_npt3'),
        ('PRODUCCION','NPT3','- KNO3 R NPT III',        'Kton','KNO3 R NPT III',      'prod_npt3'),
        ('PRODUCCION','NPT4','- CSSR NPT II/IV',        'Kton','CSSR NPT II/IV',      'prod_npt4'),
        ('PRODUCCION','NPT4','- CSSI NPT II/IV',        'Kton','CSSI NPT II/IV',      'prod_npt4'),
        ('PRODUCCION','NPT4','- KNO3 L NPT II/IV',      'Kton','KNO3 L NPT II/IV',   'prod_npt4'),
    ]

    with tab_p:
        st.caption("Delta en Kton (positivo = sube producción)")
        col1, col2 = st.columns(2)
        for i, (a,sa,c,med,label,prod_key) in enumerate(PROD_DEF):
            base = gv(df, a, sa, c, mes, tipo, 'PPTO', med)
            with (col1 if i%2==0 else col2):
                d = st.number_input(f"{label}  *(base: {base:.2f})*", value=0.0, step=0.5, key=f"p_{i}")
                deltas_p[label] = (d, prod_key, base)

    # ── TAB FACTORES ────────────────────────────────────────────────────────
    FC_DEF = [
        ('TRANSPORTE DE SALES','- Factor Consumo de Sales','- Factor Consumo de Sales','NaNO3/Ton','Fc NaNO3',           'fc_npt3_mop90'),
        ('KCl','Fc KCl NPT3','MOP 90',   'KTon KCl 95%','Fc KCl MOP90 NPT3', 'fc_npt3_mop90'),
        ('KCl','CONSUMO NPT3','MOP 70',   'KTon KCl 95%','Fc KCl MOP70 NPT3', 'fc_npt3_mop70'),
        ('KCl','CONSUMO NPT3','SS',       'KTon KCl 95%','Fc KCl SS NPT3',    'fc_npt3_ss'),
        ('KCl','Fc KCl NPT4','MOP 70',   'KTon KCl 95%','Fc KCl MOP70 NPT4', 'fc_npt4_mop70'),
    ]

    with tab_fc:
        st.caption("Delta en el factor (ajuste directo sobre el valor base)")
        col1, col2 = st.columns(2)
        for i, (a,sa,c,med,label,fc_key) in enumerate(FC_DEF):
            base = gv(df, a, sa, c, mes, tipo, 'PPTO', med)
            with (col1 if i%2==0 else col2):
                d = st.number_input(f"{label}  *(base: {base:.4f})*", value=0.0, step=0.01, format="%.4f", key=f"fc_{i}")
                deltas_fc[label] = (d, fc_key, base)

    st.divider()

    # ── CALCULAR IMPACTO ────────────────────────────────────────────────────
    # Producción nueva
    new_prod = {
        'prod_npt3': prod_npt3,
        'prod_npt4': prod_npt4,
        'prod_pril_dtp': prod_pril_dtp,
        'prod_secado': prod_secado,
    }
    for label, (d, prod_key, base) in deltas_p.items():
        if d != 0:
            new_prod[prod_key] = new_prod.get(prod_key, 0) + d

    new_prod['prod_total'] = new_prod['prod_npt3'] + new_prod['prod_npt4']
    new_prod['prod_term']  = new_prod['prod_pril_dtp'] + new_prod['prod_secado']

    impacto = 0
    detalle = []

    # Impacto gastos
    for label, (d, prod_key, base) in deltas_g.items():
        if d != 0:
            pbase = {'prod_total': prod_total, 'prod_pril_dtp': prod_pril_dtp, 'prod_secado': prod_secado}.get(prod_key, prod_total)
            pnew  = new_prod.get(prod_key, pbase)
            if pbase > 0:
                imp = (base + d) / pbase - base / pbase if pnew == pbase else (base + d) / pnew - base / pbase
                imp = d / pbase
                impacto += imp
                detalle.append((label, f"{d:+.0f} KUS", round(imp,2)))

    # Impacto producción sobre costos existentes
    componentes_por_prod = {
        'prod_total':    [0,1,2,3,5,6,7,8],
        'prod_term':     [4],
    }
    for pk, idxs in componentes_por_prod.items():
        pbase = prod_total if pk=='prod_total' else prod_term
        pnew  = new_prod.get(pk, pbase)
        if pnew != pbase and pbase > 0 and pnew > 0:
            for idx in idxs:
                sa, c, nom = COSTOS[idx]
                val = gv(df,'COSTO TOTAL',sa,c,mes,tipo,'PPTO')
                gasto_est = val * pbase
                nuevo_costo = gasto_est / pnew
                imp = nuevo_costo - val
                if abs(imp) > 0.01:
                    impacto += imp
                    detalle.append((f"Prod {pk} → {nom}", f"{pnew-pbase:+.1f} Kton", round(imp,2)))

    # Impacto factores (simplificado: delta fc × precio promedio KCl o precio tpte)
    precio_tpte = gv(df,'TRANSPORTE DE SALES','Total Transporte de Sales (promedio)',
                     'Total Transporte de Sales (promedio)',mes,tipo,'PPTO','USD/TNitr sales')
    precio_kcl  = gv(df,'KCl','Total KCl','Total KCl',mes,tipo,'PPTO','US$/T')

    for label, (d, fc_key, base) in deltas_fc.items():
        if d != 0:
            if 'NaNO3' in label:
                imp = d * precio_tpte if precio_tpte > 0 else 0
            else:
                imp = d * precio_kcl if precio_kcl > 0 else 0
            if abs(imp) > 0.001:
                impacto += imp
                detalle.append((label, f"{d:+.4f}", round(imp,2)))

    costo_nuevo = costo_base + impacto

    k1, k2, k3 = st.columns(3)
    k1.metric(f"Costo base PPTO {MESES[mes]}", f"${costo_base:.1f}/T")
    k2.metric("Impacto total", f"{impacto:+.1f} US$/T", delta_color="inverse")
    k3.metric("Nuevo costo estimado", f"${costo_nuevo:.1f}/T",
              delta=f"{impacto:+.1f}", delta_color="inverse")

    if detalle:
        st.subheader("Detalle del impacto")
        df_d = pd.DataFrame(detalle, columns=["Variable","Cambio","Impacto US$/T"])
        def col_imp(val):
            if isinstance(val, float):
                return "color: red" if val > 0 else "color: green"
            return ""
        st.dataframe(df_d.style.applymap(col_imp, subset=["Impacto US$/T"]),
                     use_container_width=True, hide_index=True)