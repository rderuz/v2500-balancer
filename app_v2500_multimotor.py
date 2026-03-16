import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import io
import math

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="V2500 Balancer Pro Suite", layout="wide")

st.markdown("""
    <style>
    .stMetric { border: 2px solid #58a6ff; background: #f0f7ff; padding: 10px; border-radius: 8px; }
    .motor-header { background-color: #1e3a8a; color: white; padding: 10px; border-radius: 5px; margin-top: 25px; }
    .info-trim { background-color: #e3f2fd; border-left: 5px solid #2196f3; padding: 15px; margin-top: 10px; color: #0d47a1; font-weight: bold; }
    .alert-bolt { background-color: #fff5f5; border-left: 5px solid #ff4b4b; padding: 15px; margin-top: 10px; color: #c53030; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- FUNCIONES AUXILIARES ---
def generar_plantilla():
    """Genera un archivo Excel de ejemplo"""
    data = []
    pesos = [155.2, 148.5, 152.1, 149.8, 154.3, 147.9, 150.0, 153.6, 149.1, 151.4, 156.0, 
            153.0, 156.8, 151.4, 153.6, 152.1, 148.8, 155.2, 146.2, 148.5, 149.6, 148.3]
    for i, p in enumerate(pesos):
        data.append(['M1', i+1, p, round(p*16.5, 2), round(p*0.8, 2), round(p*0.3, 2)])
    df = pd.DataFrame(data, columns=['Motor', 'Slot', 'Peso', 'Momento1', 'Momento2', 'Momento3'])
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    return output.getvalue()

def get_v2500_metrics(df, slot_col, metodo):
    if "Vectorial" in metodo:
        res_x, res_y, RADIO = 0.0, 0.0, 165.0 
        for _, row in df.iterrows():
            m1 = row.get('Momento1', row.get('Peso', 0) * 16.5)
            angle = math.radians((row[slot_col] - 1) * (360 / 22))
            res_x += float(m1) * math.cos(angle)
            res_y += float(m1) * math.sin(angle)
        mag = math.sqrt(res_x**2 + res_y**2)
        return round(mag / 3000, 2), round(mag / RADIO, 2), int(((180 - math.degrees(math.atan2(res_y, res_x))) % 360) / (360/22)) + 1
    else:
        m1 = df[df[slot_col] <= 11]['Peso'].sum()
        m2 = df[df[slot_col] > 11]['Peso'].sum()
        diff = round(abs(m1 - m2), 2)
        return diff, diff, (17 if (m1 - m2) > 0 else 6)

def render_fan(data, slot_col, titulo, bolt_w=0, bolt_s=0):
    fig = go.Figure()
    theta = np.linspace(0, 360, 22, endpoint=False)
    colores = ["#e74c3c" if row['Slot_Original'] != row['Nuevo_Slot'] else "#2ecc71" for _, row in data.sort_values(by=slot_col).iterrows()]
    fig.add_trace(go.Barpolar(r=[8]*22, theta=theta, width=[14]*22, marker_color=colores, marker_line_color="white"))
    for i in range(22):
        row = data[data[slot_col] == (i+1)].iloc[0]
        fig.add_trace(go.Scatterpolar(r=[6.2], theta=[theta[i]], mode='text', text=[f"A{int(row['Slot_Original'])}"], textfont=dict(size=10, color="white")))
    if bolt_w > 0.10:
        fig.add_trace(go.Scatterpolar(r=[4], theta=[theta[bolt_s-1]], mode='markers+text', marker=dict(symbol="star", size=20, color="#f1c40f"), text=[f"{bolt_w}g"], textposition="bottom center"))
    fig.update_layout(title=titulo, polar=dict(bgcolor='white', angularaxis=dict(tickvals=theta, rotation=90, direction="clockwise")), showlegend=False, height=400)
    return fig

# --- SIDEBAR ---
with st.sidebar:
    st.header("📂 Archivos")
    st.download_button("📥 Descargar Plantilla", data=generar_plantilla(), file_name="Plantilla_V2500.xlsx")
    uploaded_file = st.file_uploader("Subir Excel", type=["xlsx"])
    st.divider()
    ITERACIONES = st.number_input("Comprobaciones:", 1000, 50000, 15000, 1000)
    metodo_calc = st.selectbox("Método:", ["Vectorial (AMM)", "Mitades (Peso)"])
    TOLERANCIA = st.slider("Tolerancia (ips)", 0.0, 1.0, 0.50)

# --- PROCESO ---
if uploaded_file:
    df_full = pd.read_excel(uploaded_file, engine='openpyxl')
    df_full.columns = [c.strip().capitalize() for c in df_full.columns]
    resultados_excel = {}

    for idx, m_name in enumerate(df_full['Motor'].unique()):
        st.markdown(f"<div class='motor-header'><h3>📦 MOTOR: {m_name}</h3></div>", unsafe_allow_html=True)
        df_m = df_full[df_full['Motor'] == m_name].copy()
        df_m['Slot_Original'] = df_m['Slot'].astype(int)
        df_m['Nuevo_Slot'] = df_m['Slot_Original']
        
        v_ini, b_w_ini, b_s_ini = get_v2500_metrics(df_m, 'Slot_Original', metodo_calc)
        best = {"v": v_ini, "bolt": b_w_ini, "slot": b_s_ini, "df": df_m.copy(), "moves": 0}

        # Barra de progreso
        bar = st.progress(0)
        for i in range(ITERACIONES):
            temp = df_m.sample(frac=1).reset_index(drop=True)
            temp['Nuevo_Slot'] = range(1, 23)
            vt, bw, bs = get_v2500_metrics(temp, 'Nuevo_Slot', metodo_calc)
            mt = len(temp[temp['Slot_Original'] != temp['Nuevo_Slot']])
            if vt < best["v"]:
                best = {"v": vt, "bolt": bw, "slot": bs, "df": temp.copy(), "moves": mt}
            if i % 1500 == 0: bar.progress(i / ITERACIONES)
        bar.empty()

        # Resumen visual
        if best['moves'] == 0:
            st.markdown(f"<div class='info-trim'>✅ POSICIÓN ACTUAL ÓPTIMA. Solo instale Perno de {best['bolt']}g en Slot {best['slot']}.</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='alert-bolt'>➔ RE-INDEXACIÓN: Mueva {best['moves']} álabes + Perno de {best['bolt']}g en Slot {best['slot']}.</div>", unsafe_allow_html=True)

        c1, c2, c3 = st.columns(3)
        c1.metric("Vib. Inicial", f"{v_ini:.2f}")
        c2.metric("Vib. Final", f"{best['v']:.2f}")
        c3.metric("Mover", f"{best['moves']}")

        g1, g2 = st.columns(2)
        with g1: st.plotly_chart(render_fan(df_m, 'Slot_Original', "ACTUAL"), use_container_width=True)
        with g2: st.plotly_chart(render_fan(best['df'], 'Nuevo_Slot', "OPTIMIZADO", best['bolt'], best['slot']), use_container_width=True)
        
        df_tab = best['df'][['Slot_Original', 'Peso', 'Nuevo_Slot']].copy()
        df_tab['Acción'] = df_tab.apply(lambda x: "✅ MANTENER" if x['Slot_Original'] == x['Nuevo_Slot'] else f"➔ AL {int(x['Nuevo_Slot'])}", axis=1)
        st.table(df_tab.sort_values(by='Slot_Original'))
        
        resultados_excel[m_name] = df_tab

    # BOTÓN DE DESCARGA FINAL
    st.divider()
    output_res = io.BytesIO()
    with pd.ExcelWriter(output_res, engine='openpyxl') as writer:
        for m, df_res in resultados_excel.items():
            df_res.to_excel(writer, sheet_name=f"Motor_{m}", index=False)
    st.download_button("📥 DESCARGAR PLAN DE TALLER COMPLETO", data=output_res.getvalue(), file_name="Plan_Balanceo_Final.xlsx")

else:
    st.info("👋 Suba un archivo Excel para comenzar.")
