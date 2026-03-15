import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import io
import math

# 1. CONFIGURACIÓN
st.set_page_config(page_title="V2500 Engineering Balancer", layout="wide")

# --- LÓGICA TÉCNICA CORREGIDA ---
def get_vibration_v2500(df, slot_col):
    res_x, res_y = 0, 0
    for _, row in df.iterrows():
        # Si no existen los momentos reales, aplicamos el factor de conversión AMM
        # Momento 1 (Radial) es aprox Peso * 16.5
        m1 = row.get('Momento1', row['Peso'] * 16.5)
        
        angle_rad = math.radians((row[slot_col] - 1) * (360 / 22))
        res_x += m1 * math.cos(angle_rad)
        res_y += m1 * math.sin(angle_rad)
    
    # La vibración se normaliza para que el resultado sea en escala IPS
    total_v = math.sqrt(res_x**2 + res_y**2) / 1000 
    
    angle_v = math.degrees(math.atan2(res_y, res_x))
    bolt_slot = int(((180 - angle_v) % 360) / (360/22)) + 1
    return round(total_v, 2), bolt_slot

# --- GENERADOR DE OPCIONES ---
def generate_safe_options(df_m):
    v_ini, b_s_ini = get_vibration_v2500(df_m, 'Slot_Original')
    df_base = df_m.copy()
    df_base['Nuevo_Slot'] = df_base['Slot_Original']
    
    # Iniciamos la mejor solución con la actual
    best = {"v": v_ini, "df": df_base.copy(), "moves": 0, "b_slot": b_s_ini}
    
    for _ in range(10000):
        temp = df_m.sample(frac=1).reset_index(drop=True)
        temp['Nuevo_Slot'] = range(1, 23)
        v_t, b_s_t = get_vibration_v2500(temp, 'Nuevo_Slot')
        m_t = len(temp[temp['Slot_Original'] != temp['Nuevo_Slot']])
        
        # Prioridad: Mínimos movimientos si vib < 0.50
        if v_t < best["v"]:
            if v_t < 0.50 and m_t < best["moves"] if best["v"] < 0.50 else True:
                best = {"v": v_t, "df": temp.copy(), "moves": m_t, "b_slot": b_s_t}
                
    return best

# --- INTERFAZ ---
if uploaded_file:
    try:
        uploaded_file.seek(0)
        df_full = pd.read_excel(uploaded_file, engine='openpyxl')
        df_full.columns = [c.strip().capitalize() for c in df_full.columns]
        
        for idx, m_name in enumerate(df_full['Motor'].unique()):
            st.markdown(f"### 📦 MOTOR: {m_name}")
            df_m = df_full[df_full['Motor'] == m_name].copy()
            df_m['ID_Original'] = [f"A{int(s)}" for s in df_m['Slot']]
            df_m['Slot_Original'] = df_m['Slot'].astype(int)
            
            result = generate_safe_options(df_m)
            
            # Visualización Industrial
            c1, c2 = st.columns(2)
            with c1: st.metric("Vib. Resultante", f"{result['v']:.2f} ips")
            with c2: st.metric("Bolt Necesario", f"{result['v']:.2f}g en Slot {result['b_slot']}")
            
            # Tabla de Taller
            res_df = result['df'].copy()
            res_df['Acción'] = res_df.apply(lambda x: "✅ OK" if x['Slot_Original'] == x['Nuevo_Slot'] else f"➔ MOVER AL {int(x['Nuevo_Slot'])}", axis=1)
            st.table(res_df[['ID_Original', 'Peso', 'Slot_Original', 'Nuevo_Slot', 'Acción']].sort_values(by='Slot_Original'))

    except Exception as e:
        st.error(f"Error en datos: {e}")
