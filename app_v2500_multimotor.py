import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
import io

# 1. CONFIGURACIÓN
st.set_page_config(page_title="V2500 Vector Precision", layout="wide")

# --- LÓGICA VECTORIAL AVANZADA ---
def calc_vectorial_stats(df, slot_col):
    # Ángulos para 22 álabes (en radianes para math)
    # Slot 1 está en 0 grados
    angles = np.radians([(i - 1) * (360 / 22) for i in df[slot_col]])
    
    # Componentes vectoriales
    x_comp = np.sum(df['Peso'] * np.cos(angles))
    y_comp = np.sum(df['Peso'] * np.sin(angles))
    
    # Magnitud Resultante
    magnitude = np.sqrt(x_comp**2 + y_comp**2)
    
    # Ángulo del desbalance (para saber dónde poner el peso)
    # El peso va 180 grados opuesto al desbalance
    angle_deg = np.degrees(np.arctan2(y_comp, x_comp))
    bolt_angle = (angle_deg + 180) % 360
    bolt_slot = int(round(bolt_angle / (360 / 22))) + 1
    if bolt_slot > 22: bolt_slot = 1
        
    return round(magnitude, 2), bolt_slot

# --- GENERADOR DE OPCIONES (3 VÍAS) ---
def generate_options_vectorial(df_m):
    v_ini, s_ini = calc_vectorial_stats(df_m, 'Slot_Original')
    df_base = df_m.copy()
    df_base['Nuevo_Slot'] = df_base['Slot_Original']
    
    best_bal = {"v": v_ini, "df": df_base.copy(), "moves": 0, "slot": s_ini}
    best_min_moves = {"v": v_ini, "df": df_base.copy(), "moves": 0, "slot": s_ini}
    best_mid = {"v": v_ini, "df": df_base.copy(), "moves": 0, "slot": s_ini}
    
    TOLERANCIA_AMM = 0.50
    
    for _ in range(8000):
        temp = df_m.sample(frac=1).reset_index(drop=True)
        temp['Nuevo_Slot'] = range(1, 23)
        v_t, s_t = calc_vectorial_stats(temp, 'Nuevo_Slot')
        m_t = len(temp[temp['Slot_Original'] != temp['Nuevo_Slot']])
        
        # 1. Máximo Balance
        if v_t < best_bal["v"]:
            best_bal = {"v": v_t, "df": temp.copy(), "moves": m_t, "slot": s_t}
        # 2. Mínimos Movimientos
        if v_t <= TOLERANCIA_AMM:
            if m_t < best_min_moves["moves"] or best_min_moves["v"] > TOLERANCIA_AMM:
                best_min_moves = {"v": v_t, "df": temp.copy(), "moves": m_t, "slot": s_t}
        # 3. Intermedia
        if v_t <= 0.15:
            if m_t < best_mid["moves"] or best_mid["v"] > 0.15:
                best_mid = {"v": v_t, "df": temp.copy(), "moves": m_t, "slot": s_t}

    return [
        {"name": "1. Máximo Balance (Cálculo Vectorial)", "data": best_bal},
        {"name": "2. Mínimos Movimientos (Default < 0.50)", "data": best_min_moves},
        {"name": "3. Opción Equilibrada (Vib < 0.15)", "data": best_mid}
    ]

# --- RENDERIZADO VISUAL ---
def render_industrial_fan(data, slot_col, titulo, bolt_w=0, bolt_s=0):
    fig = go.Figure()
    theta = np.linspace(0, 360, 22, endpoint=False)
    
    # Colores: Rojo si se mueve, Verde si se queda
    colores = ["#e74c3c" if row['Slot_Original'] != row['Nuevo_Slot'] else "#2ecc71" 
               for _, row in data.sort_values(by=slot_col).iterrows()]

    fig.add_trace(go.Barpolar(r=[8]*22, theta=theta, width=[14]*22, marker_color=colores, marker_line_color="white", marker_line_width=1.5))
    
    for i in range(22):
        row = data[data[slot_col] == (i+1)].iloc[0]
        fig.add_trace(go.Scatterpolar(r=[6.2], theta=[theta[i]], mode='text', text=[f"<b>{row['ID_Original']}</b>"], textfont=dict(size=14, color="white")))
    
    if bolt_w > 0.10:
        fig.add_trace(go.Scatterpolar(r=[4], theta=[theta[bolt_s-1]], mode='markers+text', marker=dict(symbol="star", size=25, color="#f1c40f"),
                                     text=[f"BOLT {bolt_w:.2f}"], textposition="bottom center", textfont=dict(size=12, color="red")))
    
    fig.update_layout(title=f"<b>{titulo}</b>", polar=dict(bgcolor='white', angularaxis=dict(tickvals=theta, ticktext=[str(i+1) for i in range(22)], rotation=90, direction="clockwise")),
                      showlegend=False, height=550, margin=dict(t=50, b=30, l=30, r=30))
    return fig

# --- PROCESAMIENTO STREAMLIT ---
st.markdown("<style>.stMetric { border: 2px solid #58a6ff; background: #f0f7ff; padding: 10px; border-radius: 8px; }</style>", unsafe_allow_html=True)

uploaded_file = st.sidebar.file_uploader("Subir Excel", type=["xlsx", "csv"])

if uploaded_file:
    try:
        df_full = pd.read_excel(uploaded_file, engine='openpyxl')
        df_full.columns = [c.strip().capitalize() for c in df_full.columns]
        
        for idx, m_name in enumerate(df_full['Motor'].unique()):
            st.subheader(f"📦 Motor: {m_name}")
            df_m = df_full[df_full['Motor'] == m_name].copy()
            df_m['ID_Original'] = [f"A{int(s)}" for s in df_m['Slot']]
            df_m['Slot_Original'] = df_m['Slot'].astype(int)
            
            opts = generate_options_vectorial(df_m)
            selected_name = st.radio(f"Estrategia {m_name}:", [o["name"] for o in opts], index=1, key=f"r_{idx}")
            choice = next(o["data"] for o in opts if o["name"] == selected_name)
            
            # Métricas
            c1, c2, c3 = st.columns(3)
            v_ini, _ = calc_vectorial_stats(df_m, 'Slot_Original')
            c1.metric("Vib. Vectorial Inicial", f"{v_ini:.2f}")
            c2.metric("Vib. Vectorial Final", f"{choice['v']:.2f}")
            c3.metric("Bolt Recomendado", f"{choice['v']:.2f}g en Slot {choice['slot']}")

            # Gráficos y Tablas
            g1, g2 = st.columns(2)
            with g1: st.plotly_chart(render_industrial_fan(df_m, 'Slot_Original', "AS FOUND"), use_container_width=True, key=f"g1_{idx}")
            with g2: st.plotly_chart(render_visual_fan(choice['df'], 'Nuevo_Slot', "AS LEFT", choice['v'], choice['slot']), use_container_width=True, key=f"g2_{idx}")
            
            choice['df']['Acción'] = choice['df'].apply(lambda x: "✅ OK" if x['Slot_Original'] == x['Nuevo_Slot'] else f"➔ MOVER AL {int(x['Nuevo_Slot'])}", axis=1)
            choice['df']['Peso_Compensación'] = ""
            choice['df'].loc[choice['df']['Nuevo_Slot'] == choice['slot'], 'Peso_Compensación'] = f"🔩 BOLT {choice['v']:.2f}g"
            
            st.table(choice['df'][['ID_Original', 'Peso', 'Slot_Original', 'Nuevo_Slot', 'Acción', 'Peso_Compensación']].sort_values(by='Slot_Original'))

    except Exception as e:
        st.error(f"Error: {e}")
else:
    st.info("Suba el archivo para activar el cálculo vectorial de precisión.")
