import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import io
import math

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="V2500 Balancer DSS Pro", layout="wide")

st.markdown("""
    <style>
    .stMetric { border: 2px solid #58a6ff; background: #f0f7ff; padding: 10px; border-radius: 8px; }
    .motor-header { background-color: #1e3a8a; color: white; padding: 10px; border-radius: 5px; margin-top: 25px; }
    .estrategia-box { background-color: #f1f8ff; border: 1px solid #c8e1ff; padding: 15px; border-radius: 10px; margin-bottom: 20px; }
    </style>
    """, unsafe_allow_html=True)

# --- FUNCIONES TÉCNICAS ---
def get_v2500_metrics(df, slot_col, metodo):
    if "Vectorial" in metodo:
        res_x, res_y, RADIO_CONV = 0.0, 0.0, 165.0 
        for _, row in df.iterrows():
            m1 = row.get('Momento1', row.get('Peso', 0) * 16.5)
            angle_rad = math.radians((row[slot_col] - 1) * (360 / 22))
            res_x += float(m1) * math.cos(angle_rad)
            res_y += float(m1) * math.sin(angle_rad)
        mag = math.sqrt(res_x**2 + res_y**2)
        v_ips = round(mag / 3000, 2)
        p_bolt = round(mag / RADIO_CONV, 2)
        ang = math.degrees(math.atan2(res_y, res_x))
        b_slot = int(((180 - ang) % 360) / (360/22)) + 1
        return v_ips, p_bolt, b_slot
    else:
        m1_sum = df[df[slot_col] <= 11]['Peso'].sum()
        m2_sum = df[df[slot_col] > 11]['Peso'].sum()
        diff = round(abs(m1_sum - m2_sum), 2)
        b_slot = 17 if (m1_sum - m2_sum) > 0 else 6
        return diff, diff, b_slot

def render_fan(data, slot_col, titulo, bolt_w=0, bolt_s=0):
    fig = go.Figure()
    theta = np.linspace(0, 360, 22, endpoint=False)
    colores = ["#e74c3c" if row['Slot_Original'] != row['Nuevo_Slot'] else "#2ecc71" for _, row in data.sort_values(by=slot_col).iterrows()]
    fig.add_trace(go.Barpolar(r=[8]*22, theta=theta, width=[14]*22, marker_color=colores, marker_line_color="white"))
    for i in range(22):
        row = data[data[slot_col] == (i+1)].iloc[0]
        fig.add_trace(go.Scatterpolar(r=[6.2], theta=[theta[i]], mode='text', text=[f"A{int(row['Slot_Original'])}"], textfont=dict(size=10, color="white")))
    if bolt_w > 0.05:
        fig.add_trace(go.Scatterpolar(r=[4], theta=[theta[bolt_s-1]], mode='markers+text', marker=dict(symbol="star", size=20, color="#f1c40f"), text=[f"{bolt_w}g"], textposition="bottom center"))
    fig.update_layout(title=titulo, polar=dict(bgcolor='white', angularaxis=dict(tickvals=theta, rotation=90, direction="clockwise")), showlegend=False, height=450)
    return fig

# --- SIDEBAR ---
with st.sidebar:
    st.header("📂 Datos")
    uploaded_file = st.file_uploader("Subir Excel", type=["xlsx"])
    st.divider()
    st.header("⚙️ Simulación")
    metodo_calc = st.selectbox("Método:", ["Vectorial (AMM)", "Mitades (Peso)"])
    ITERACIONES = st.number_input("Iteraciones:", 1000, 100000, 15000, 5000)
    TOLERANCIA = st.slider("Tolerancia Objetivo (ips)", 0.0, 1.0, 0.20)

# --- PROCESAMIENTO ---
if uploaded_file:
    df_full = pd.read_excel(uploaded_file, engine='openpyxl')
    df_full.columns = [c.strip().capitalize() for c in df_full.columns]
    descargas = {}

    for idx, m_name in enumerate(df_full['Motor'].unique()):
        st.markdown(f"<div class='motor-header'><h3>📦 MOTOR: {m_name}</h3></div>", unsafe_allow_html=True)
        df_m = df_full[df_full['Motor'] == m_name].copy()
        df_m['Slot_Original'] = df_m['Slot'].astype(int)
        
        v_ini, b_ini, s_ini = get_v2500_metrics(df_m, 'Slot_Original', metodo_calc)
        
        # CONTENEDOR DE ESTRATEGIAS
        estrategias = {
            "1. Máxima Precisión (Mínima Vib.)": {"v": v_ini, "moves": 0, "df": df_m.copy(), "bolt": b_ini, "slot": s_ini},
            "2. Eficiencia (Mínimo Movimiento < Tol)": {"v": v_ini, "moves": 0, "df": df_m.copy(), "bolt": b_ini, "slot": s_ini},
            "3. Punto Intermedio": {"v": v_ini, "moves": 0, "df": df_m.copy(), "bolt": b_ini, "slot": s_ini}
        }

        # Ejecución de Simulación
        progress_bar = st.progress(0)
        for i in range(ITERACIONES):
            temp = df_m.sample(frac=1).reset_index(drop=True)
            temp['Nuevo_Slot'] = range(1, 23)
            vt, bw, bs = get_v2500_metrics(temp, 'Nuevo_Slot', metodo_calc)
            mt = len(temp[temp['Slot_Original'] != temp['Nuevo_Slot']])
            
            # Lógica Estrategia 1: Solo importa la vibración más baja
            if vt < estrategias["1. Máxima Precisión (Mínima Vib.)"]["v"]:
                estrategias["1. Máxima Precisión (Mínima Vib.)"] = {"v": vt, "moves": mt, "df": temp.copy(), "bolt": bw, "slot": bs}
            
            # Lógica Estrategia 2: Estar bajo tolerancia con los mínimos movimientos posibles
            if vt <= TOLERANCIA:
                if mt < estrategias["2. Eficiencia (Mínimo Movimiento < Tol)"]["moves"] or estrategias["2. Eficiencia (Mínimo Movimiento < Tol)"]["v"] > TOLERANCIA:
                    estrategias["2. Eficiencia (Mínimo Movimiento < Tol)"] = {"v": vt, "moves": mt, "df": temp.copy(), "bolt": bw, "slot": bs}
            
            # Lógica Estrategia 3: Equilibrio (Mejora del 50% con movimientos moderados)
            if vt < (v_ini * 0.5) and mt < 12:
                if vt < estrategias["3. Punto Intermedio"]["v"]:
                    estrategias["3. Punto Intermedio"] = {"v": vt, "moves": mt, "df": temp.copy(), "bolt": bw, "slot": bs}

            if i % 3000 == 0: progress_bar.progress(i / ITERACIONES)
        progress_bar.empty()

        # Selector de Estrategia para este motor
        st.markdown("<div class='estrategia-box'>", unsafe_allow_html=True)
        seleccionada = st.radio(f"Seleccione Plan para {m_name}:", list(estrategias.keys()), horizontal=True, key=f"sel_{idx}")
        res = estrategias[seleccionada]
        st.markdown("</div>", unsafe_allow_html=True)

        # Métricas de Trazabilidad
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("1. Vib. Inicial", f"{v_ini:.2f} ips")
        c2.metric("2. Vib. tras Movimientos", f"{res['v']:.2f} ips")
        c3.metric("3. Perno Propuesto", f"{res['bolt']:.2f} g")
        c4.metric("4. Movimientos", f"{res['moves']}")

        g1, g2 = st.columns(2)
        with g1: st.plotly_chart(render_fan(df_m, 'Slot_Original', "AS FOUND"), use_container_width=True)
        with g2: st.plotly_chart(render_fan(res['df'], 'Nuevo_Slot', f"AS LEFT ({seleccionada})", res['bolt'], res['slot']), use_container_width=True)
        
        df_tab = res['df'][['Slot_Original', 'Peso', 'Nuevo_Slot']].copy()
        df_tab['Acción'] = df_tab.apply(lambda x: "✅ MANTENER" if x['Slot_Original'] == x['Nuevo_Slot'] else f"➔ MOVER AL {int(x['Nuevo_Slot'])}", axis=1)
        st.table(df_tab.sort_values(by='Slot_Original'))
        
        descargas[m_name] = df_tab

    # Exportación
    st.divider()
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        for m, d in descargas.items(): d.to_excel(writer, sheet_name=m, index=False)
    st.download_button("📥 DESCARGAR PLANES DE TRABAJO (EXCEL)", data=output.getvalue(), file_name="Plan_V2500_Final.xlsx")

else:
    st.info("Cargue el Excel para comparar las 3 estrategias de balanceo.")
