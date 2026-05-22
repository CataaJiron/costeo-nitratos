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

elif pagina == "Sensibilidad":
    st.title("Análisis de Sensibilidad — Costo Total US$/T")
 
    col_v, _ = st.columns([2, 6])
    with col_v:
        modo = st.radio("Vista", ["Puntual", "Acumulado"], horizontal=True,
                        label_visibility="collapsed")
    tipo = "Puntual" if modo == "Puntual" else "Acumulado"
 
    mes = botones_mes("sens")
    st.divider()
 
    # ── Rango de variación ──────────────────────────────────────────────────
    col_r, _ = st.columns([3, 5])
    with col_r:
        rango_pct = st.slider("Rango de variación (%)",
                              min_value=5, max_value=50, value=20, step=5)
 
    fechas_sorted = sorted(df['Fecha'].unique())
    if mes >= len(fechas_sorted):
        st.warning("Mes fuera de rango.")
        st.stop()
    fecha = fechas_sorted[mes]
 
    # ── Helpers de acceso al DataFrame ──────────────────────────────────────
    def _gv(area, subarea, concepto, medida=None):
        mask = (
            (df['Fecha']   == fecha) &
            (df['AREA']    == area)  &
            (df['SUBAREA'] == subarea) &
            (df['CONCEPTO']== concepto) &
            (df['Tipo']    == tipo)  &
            (df['Tipo_2']  == 'PPTO')
        )
        if medida:
            mask = mask & (df['Medida'] == medida)
        r = df[mask]['GASTO/COSTO']
        return float(r.values[0]) if not r.empty else 0.0
 
    # ── Leer insumos base ────────────────────────────────────────────────────
    # Producción
    npt3        = _gv('PRODUCCION', 'NPT3', 'PRODUCCION TOTAL NPT3')
    npt4        = _gv('PRODUCCION', 'NPT4', 'PRODUCCION TOTAL NPT4')
    prod_total  = npt3 + npt4
 
    prod_pril   = _gv('PRODUCCION', 'TERMINADOS', 'PRILADO + DTP')
    prod_sec    = _gv('PRODUCCION', 'TERMINADOS', 'SECADO')
    prod_term   = prod_pril + prod_sec
 
    # 1.1 – Transporte de Sales
    tpte_sales_precio = _gv('TRANSPORTE DE SALES',
                             'Total Transporte de Sales (promedio)',
                             'Total Transporte de Sales (promedio)')
    fc_sales          = _gv('TRANSPORTE DE SALES',
                             '- Factor Consumo de Sales',
                             '- Factor Consumo de Sales')
 
    # 1.2 – Pozas
    gasto_pozas = _gv('GASTO',
                      'Operación Pozas (NV+CS+PV+PB)',
                      'Operación Pozas (SV+CS+PV+PB)')
 
    # 1.3 – Cristalización
    gasto_crist = _gv('GASTO', 'CRISTALIZACION',
                      'Gasto Total Cristalización (NPT II/IV/NPT III)')
 
    # 1.4 – KCl
    fc_kcl_h    = _gv('KCl', 'f.c. KCl H (MOP-90 + MOP70)',
                      'f.c. KCl H (MOP-90 + MOP70)')
    fc_kcl_ss   = _gv('KCl', '- f.c. SS', '- f.c. SS')
    fc_kcl_total = fc_kcl_h + fc_kcl_ss
 
    cons_mop90  = _gv('KCl', 'CONSUMO TOTAL', 'MOP 90')
    cons_mop70  = _gv('KCl', 'CONSUMO TOTAL', 'MOP 70')
    cons_ss_kcl = _gv('KCl', 'CONSUMO TOTAL', 'SS')
    cons_kcl_tot = cons_mop90 + cons_mop70 + cons_ss_kcl
 
    precio_mop90 = _gv('KCl', 'Costo Promedio KCl', 'MOP 90')
    precio_mop70 = _gv('KCl', 'Costo Promedio KCl', 'MOP 70')
    precio_ss    = _gv('KCl', 'Costo Promedio KCl', 'SS')
 
    costo_prom_kcl = (
        (precio_mop90 * cons_mop90 +
         precio_mop70 * cons_mop70 +
         precio_ss    * cons_ss_kcl) / cons_kcl_tot
    ) if cons_kcl_tot > 0 else 0.0
 
    # 1.5 – Terminados
    gasto_term  = _gv('GASTO', 'TERMINADOS', 'GASTO TOTAL TERMINADOS')
 
    # 1.6 – Transporte y Puerto (ya vienen en US$/T en la tabla)
    tpte_cam    = _gv('Tpte Camiones Terminados', 'TRANSPORTE',
                      'Tpte Camiones Terminados', 'US$/T')
    embarque    = _gv('Embarque Granel Trimestral', 'EMBARQUE',
                      'Embarque Granel + Demurrage', 'US$/T')
    almacenaje  = _gv('Almacenaje Trimestral', 'ALMACENAJE',
                      'Almacenaje Trimestral', 'US$/T')
    distribut16 = _gv('Distributivos Trimestral', 'DISTRIBUTIVOS',
                      'DISTRIBUTIVOS', 'US$/T')
    depr_puerto = _gv('DEPRECIACION', 'PUERTO',
                      'Depreciacion Puerto', 'US$/T')
 
    # 1.7 – Perdidas F/E (pre-calculadas, se usan como referencia fija)
    perd_fe_term = _gv('Perdidas F/E', 'Perdidas F/E', 'Perdidas F/E')
    perd_fe_pue  = _gv('- Perdidas y FE (Puerto/Cancha)',
                       '- Perdidas y FE (Puerto/Cancha)',
                       '- Perdidas y FE (Puerto/Cancha)')
 
    # 1.8 – Distributivos + Depreciación
    dist_nit    = df.loc[
        (df['AREA'] == 'Distributivos Nitratos') &
        (df['Fecha'] == fecha) &
        (df['Tipo'] == tipo) &
        (df['Tipo_2'] == 'PPTO'), 'GASTO/COSTO'
    ]
    dist_nit = float(dist_nit.values[0]) if not dist_nit.empty else 0.0
 
    depr_com    = df.loc[
        (df['AREA'] == 'Depreciación Costo Comun') &
        (df['Fecha'] == fecha) &
        (df['Tipo'] == tipo) &
        (df['Tipo_2'] == 'PPTO'), 'GASTO/COSTO'
    ]
    depr_com = float(depr_com.values[0]) if not depr_com.empty else 0.0
 
    # ── Función de recálculo completo ────────────────────────────────────────
    def calcular_costo(
        v_prod_total   = prod_total,
        v_prod_term    = prod_term,
        v_tpte_sales_p = tpte_sales_precio,
        v_fc_sales     = fc_sales,
        v_gasto_pozas  = gasto_pozas,
        v_gasto_crist  = gasto_crist,
        v_fc_kcl       = fc_kcl_total,
        v_costo_kcl    = costo_prom_kcl,
        v_gasto_term   = gasto_term,
        v_tpte_cam     = tpte_cam,
        v_dist_nit     = dist_nit,
    ):
        c11 = v_tpte_sales_p * v_fc_sales
        c12 = v_gasto_pozas / v_prod_total   if v_prod_total  > 0 else 0.0
        c13 = v_gasto_crist / v_prod_total   if v_prod_total  > 0 else 0.0
        c14 = v_fc_kcl * v_costo_kcl
        c15 = v_gasto_term  / v_prod_term    if v_prod_term   > 0 else 0.0
        c16 = v_tpte_cam + embarque + almacenaje + distribut16 + depr_puerto
        c17 = perd_fe_term + perd_fe_pue          # fijo (depende de otros no variados)
        c18 = (v_dist_nit + depr_com) / v_prod_total if v_prod_total > 0 else 0.0
        c19 = gv(df, 'COSTO TOTAL', '1.9 OTROS', 'OTROS', mes, tipo, 'PPTO')
        return c11 + c12 + c13 + c14 + c15 + c16 + c17 + c18 + c19
 
    costo_base = calcular_costo()
 
    # ── Definición de variables de sensibilidad ──────────────────────────────
    variables = [
        {
            "nombre": "Producción Total (Kton)",
            "desc":   "NPT3 + NPT4",
            "kwargs_bajo": {"v_prod_total": prod_total  * (1 - rango_pct/100)},
            "kwargs_alto": {"v_prod_total": prod_total  * (1 + rango_pct/100)},
        },
        {
            "nombre": "Gasto Cristalización (KUS)",
            "desc":   "NPT3 + NPT4 + depreciaciones",
            "kwargs_bajo": {"v_gasto_crist": gasto_crist * (1 - rango_pct/100)},
            "kwargs_alto": {"v_gasto_crist": gasto_crist * (1 + rango_pct/100)},
        },
        {
            "nombre": "Precio Tpte Sales (USD/TNitr)",
            "desc":   "Promedio NV + PB + CS",
            "kwargs_bajo": {"v_tpte_sales_p": tpte_sales_precio * (1 - rango_pct/100)},
            "kwargs_alto": {"v_tpte_sales_p": tpte_sales_precio * (1 + rango_pct/100)},
        },
        {
            "nombre": "Factor Consumo Sales (NaNO3/Ton)",
            "desc":   "Sales consumidas por ton producida",
            "kwargs_bajo": {"v_fc_sales": fc_sales * (1 - rango_pct/100)},
            "kwargs_alto": {"v_fc_sales": fc_sales * (1 + rango_pct/100)},
        },
        {
            "nombre": "Gasto Operación Pozas (KUS)",
            "desc":   "NV + CS + PB + depreciaciones",
            "kwargs_bajo": {"v_gasto_pozas": gasto_pozas * (1 - rango_pct/100)},
            "kwargs_alto": {"v_gasto_pozas": gasto_pozas * (1 + rango_pct/100)},
        },
        {
            "nombre": "Precio Promedio KCl (USD/T)",
            "desc":   "MOP90 / MOP70 / SS ponderado",
            "kwargs_bajo": {"v_costo_kcl": costo_prom_kcl * (1 - rango_pct/100)},
            "kwargs_alto": {"v_costo_kcl": costo_prom_kcl * (1 + rango_pct/100)},
        },
        {
            "nombre": "Factor Consumo KCl (fc total)",
            "desc":   "fc MOP90-MOP70 + fc SS",
            "kwargs_bajo": {"v_fc_kcl": fc_kcl_total * (1 - rango_pct/100)},
            "kwargs_alto": {"v_fc_kcl": fc_kcl_total * (1 + rango_pct/100)},
        },
        {
            "nombre": "Gasto Total Terminados (KUS)",
            "desc":   "Prilado + DTP + Secado + Tpte Int.",
            "kwargs_bajo": {"v_gasto_term": gasto_term * (1 - rango_pct/100)},
            "kwargs_alto": {"v_gasto_term": gasto_term * (1 + rango_pct/100)},
        },
        {
            "nombre": "Precio Tpte Camiones (US$/T)",
            "desc":   "Transporte camiones terminados",
            "kwargs_bajo": {"v_tpte_cam": tpte_cam * (1 - rango_pct/100)},
            "kwargs_alto": {"v_tpte_cam": tpte_cam * (1 + rango_pct/100)},
        },
        {
            "nombre": "Distributivos Nitratos (KUS)",
            "desc":   "Distributivos + Depr. Costo Común",
            "kwargs_bajo": {"v_dist_nit": dist_nit * (1 - rango_pct/100)},
            "kwargs_alto": {"v_dist_nit": dist_nit * (1 + rango_pct/100)},
        },
    ]
 
    # ── Calcular impactos ────────────────────────────────────────────────────
    filas = []
    for v in variables:
        c_bajo = calcular_costo(**v["kwargs_bajo"])
        c_alto = calcular_costo(**v["kwargs_alto"])
        d_bajo = c_bajo - costo_base
        d_alto = c_alto - costo_base
        impacto = abs(d_alto - d_bajo)
        filas.append({
            "Variable":    v["nombre"],
            "Desc":        v["desc"],
            "c_bajo":      c_bajo,
            "c_alto":      c_alto,
            "d_bajo":      d_bajo,
            "d_alto":      d_alto,
            "impacto":     impacto,
        })
 
    filas.sort(key=lambda x: x["impacto"], reverse=True)
 
    # ── KPIs ─────────────────────────────────────────────────────────────────
    kpis_row(df, mes, tipo)
    st.divider()
 
    # ── Gráfico Tornado ──────────────────────────────────────────────────────
    st.subheader(f"Tornado — Costo Total US$/T | {MESES[mes]} {modo} | ±{rango_pct}%")
 
    etiquetas = [f["Variable"] for f in filas]
 
    # Para cada variable: la barra izquierda (reducción) y la derecha (aumento)
    x_neg = [min(f["d_bajo"], f["d_alto"]) for f in filas]
    x_pos = [max(f["d_bajo"], f["d_alto"]) for f in filas]
 
    fig_t = go.Figure()
 
    fig_t.add_trace(go.Bar(
        name=f"−{rango_pct}%  (baja costo)",
        y=etiquetas,
        x=x_neg,
        orientation='h',
        marker_color='#80BC00',
        text=[f"${v:+.1f}" for v in x_neg],
        textposition='outside',
        textfont=dict(size=10, color='#80BC00'),
    ))
    fig_t.add_trace(go.Bar(
        name=f"+{rango_pct}%  (sube costo)",
        y=etiquetas,
        x=x_pos,
        orientation='h',
        marker_color='#D83030',
        text=[f"${v:+.1f}" for v in x_pos],
        textposition='outside',
        textfont=dict(size=10, color='#D83030'),
    ))
 
    fig_t.add_vline(
        x=0,
        line_width=2,
        line_color='white',
        annotation_text=f"Base ${costo_base:.1f}/T",
        annotation_position='top',
        annotation_font=dict(color='white', size=12),
    )
 
    fig_t.update_layout(
        barmode='overlay',
        height=max(420, 52 * len(filas)),
        xaxis_title="Δ Costo US$/T respecto al PPTO base",
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        legend=dict(orientation='h', y=1.06),
        margin=dict(l=240, r=120, t=40, b=40),
        xaxis=dict(
            gridcolor='#333333',
            zeroline=True,
            zerolinecolor='white',
            zerolinewidth=2,
        ),
        yaxis=dict(autorange='reversed'),
    )
    st.plotly_chart(fig_t, use_container_width=True)
 
    # ── Tabla detalle ────────────────────────────────────────────────────────
    st.subheader("Detalle de impactos")
 
    df_tabla = pd.DataFrame([{
        "Variable":              f["Variable"],
        "Descripción":           f["Desc"],
        f"Costo −{rango_pct}%":  round(f["c_bajo"], 2),
        "Base PPTO (US$/T)":     round(costo_base,  2),
        f"Costo +{rango_pct}%":  round(f["c_alto"], 2),
        f"Δ −{rango_pct}%":      round(f["d_bajo"],  2),
        f"Δ +{rango_pct}%":      round(f["d_alto"],  2),
        "Impacto total (US$/T)": round(f["impacto"],  2),
    } for f in filas])
 
    col_d_neg = f"Δ −{rango_pct}%"
    col_d_pos = f"Δ +{rango_pct}%"
 
    def color_delta(val):
        if not isinstance(val, float):
            return ''
        return 'color: #D83030' if val > 0 else ('color: #80BC00' if val < 0 else '')
 
    num_cols = [c for c in df_tabla.columns if df_tabla[c].dtype == float]
    st.dataframe(
        df_tabla.style
            .applymap(color_delta, subset=[col_d_neg, col_d_pos])
            .format({c: "{:.2f}" for c in num_cols}),
        use_container_width=True,
        hide_index=True,
    )
 
    # ── Nota metodológica ────────────────────────────────────────────────────
    with st.expander("📐 Metodología de recálculo"):
        st.markdown(f"""
| Componente | Fórmula base |
|---|---|
| **1.1 Tpte Sales** | Precio_Tpte × FC_Consumo_Sales |
| **1.2 Op. Pozas** | Gasto_Pozas (KUS) ÷ Prod_Total (Kton) |
| **1.3 Cristalización** | Gasto_Total_Crist (KUS) ÷ Prod_Total (Kton) |
| **1.4 KCl** | FC_KCl_Total × Costo_Promedio_KCl |
| **1.5 Terminados** | Gasto_Total_Terminados (KUS) ÷ Prod_Terminados (Kton) |
| **1.6 Tpte + Puerto** | Tpte_Cam + Embarque + Almacenaje + Distributivos_T + Depr_Puerto (todos en US$/T) |
| **1.7 Pérdidas F/E** | Valor precomputado de la tabla (Perdidas_FE + Perdidas_Puerto) |
| **1.8 Distributivos** | (Dist_Nitratos + Depr_Costo_Común) (KUS) ÷ Prod_Total (Kton) |
 
Cada variable se perturba de forma **independiente** (ceteris paribus).  
El rango ±{rango_pct}% se aplica sobre el valor **PPTO** del mes seleccionado.
        """)
