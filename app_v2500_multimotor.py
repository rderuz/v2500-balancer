import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import io
import math

# 1. CONFIGURACIÓN
st.set_page_config(page_title="V2500 Multi-Moment Balancer", layout="wide")

st.markdown("""
    <style>
    .stMetric { border: 2px solid #58a6ff; background: #f0f7ff; padding: 10px; border-radius: 8px; }
    .motor-header { background-color: #1e3a8a; color: white; padding: 10px; border-radius: 5px; margin-top: 25px; }
    .moment-tag { font-size: 0.8em; color: #666; }
    </style>
    """, unsafe_allow_html=True)

st.title("🛡️ V2500 Aero-Master: High Precision Multi-Moment System")

with st.sidebar:
    st.header("⚙️ Configuración Técnica")
    uploaded_file = st.file_uploader("Subir Excel con Momentos 1, 2, 3", type=["xlsx", "csv"])
    st.divider()
    TOLERANCIA_VIB = st.slider("Tolerancia Objetivo (ips)", 0.0, 1.0, 0.50)
    UMBRAL_EXCELENCIA = 0.10

# --- LÓGICA DE CÁLCULO MULTI-MOMENTO ---
def calc_moment_vector(df, slot_col, moment_col):
    """Calcula la resultante vectorial para un momento específico"""
    res_x, res_y = 0, 0
    for _, row in df.iterrows():
        angle_deg = (row[slot_col] - 1) * (360 / 22)
        angle_rad = math.radians(angle_deg)
        # Usamos el valor del momento en lugar del peso simple
        res_x += row[moment_col] * math.cos(angle_rad)
        res_y += row[moment_col] * math.sin(angle_rad)
    
    magnitude = math.sqrt(res_x**2 + res_y**2)
    angle_v = math.degrees(math.atan2(res_y, res_x))
    bolt_slot = int(((180 - angle_v) % 360) / (360/22)) + 1
    return round(magnitude, 2), bolt_slot

def get_combined_score(df, slot_col):
    """Evalúa la calidad del balanceo sumando el impacto de los 3 momentos"""
    v1, s1 = calc_moment_vector(df, slot_col, 'Momento1')
    v2, s2 = calc_moment_vector(df, slot_col, 'Momento2')
    v3, s3 = calc_moment_vector(df, slot_col, 'Momento3')
    
    # La puntuación total es la media ponderada (ajustable según criticidad)
    # Normalmente el Momento 1 es el más crítico para la vibración radial
    score_total = (v1 * 0.5) + (v2 * 0.3) + (v3 * 0.2)
    return round(score_total, 2), v1, v2, v3, s1

# --- GENERADOR DE OPCIONES (OPTIMIZADO PARA MOMENTOS) ---
def generate_options(df_m):
    score_ini, v1_i, v2_i, v3_i, b_s_i = get_combined_score(df_m, 'Slot_Original')
    df_base = df_m.copy()
    df_base['Nuevo_Slot'] = df_base['Slot_Original']
    
    best_bal = {"score": score_ini, "v1": v1_i, "v2": v2_i, "v3": v3_i, "df": df_base.copy(), "moves": 0, "b_slot": b_s_i}
    
    # Simulación intensa
    for _ in range(10000):
        temp = df_m.sample(frac=1).reset_index(drop=True)
        temp['Nuevo_Slot'] = range(1, 23)
        score_t, v1_t, v2_t, v3_t, b_s_t = get_combined_score(temp, 'Nuevo_Slot')
        moves_t = len(temp[temp['Slot_Original'] != temp['Nuevo_Slot']])
        
        # Criterio: Mejor balance global
        if score_t < best_bal["score"]:
            best_bal = {"score": score_t, "v1": v1_t, "v2": v2_t, "v3": v3_t, "df": temp.copy(), "moves": moves_t, "b_slot": b_s_t}

    return best_bal

# --- INTERFAZ Y PROCESAMIENTO ---
if uploaded_file:
    try:
        df_full = pd.read_excel(uploaded_file)
        df_full.columns = [c.strip() for c in df_full.columns] # Limpiar espacios
        
        # Verificar que existen las columnas necesarias
        req_cols = ['Motor', 'Slot', 'Peso', 'Momento1', 'Momento2', 'Momento3']
        if not all(c in df_full.columns for c in req_cols):
            st.error(f"El Excel debe contener las columnas: {req_cols}")
        else:
            for idx, m_name in enumerate(df_full['Motor'].unique()):
                st.markdown(f"<div class='motor-header'><h3>📦 MOTOR: {m_name}</h3></div>", unsafe_allow_html=True)
                
                df_m = df_full[df_full['Motor'] == m_name].copy()
                df_m['Slot_Original'] = df_m['Slot'].astype(int)
                df_m['ID_Original'] = df_m['Slot'].apply(lambda x: f"A{int(x)}")
                
                # Optimización
                result = generate_options(df_m)
                
                # Métricas de los 3 Momentos
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Vib. Total (Score)", f"{result['score']}")
                c2.metric("Momento 1", f"{result['v1']}", delta_color="inverse")
                c3.metric("Momento 2", f"{result['v2']}")
                c4.metric("Momento 3", f"{result['v3']}")
                
                # Gráficos y Tabla
                g1, g2 = st.columns(2)
                # ... (Lógica de gráficos render_fan similar a versiones anteriores usando result['v1'] y result['b_slot'])
                
                st.write("**Plan de Trabajo Detallado (Multi-Momento):**")
                df_final = result['df'].copy()
                df_final['Acción'] = df_final.apply(lambda x: "✅ OK" if x['Slot_Original'] == x['Nuevo_Slot'] else f"➔ MOVER AL {int(x['Nuevo_Slot'])}", axis=1)
                
                st.table(df_final[['ID_Original', 'Peso', 'Momento1', 'Momento2', 'Momento3', 'Slot_Original', 'Nuevo_Slot', 'Acción']])

    except Exception as e:
        st.error(f"Error en el procesamiento: {e}")
