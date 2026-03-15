import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import io
import math

# 1. CONFIGURACIÓN E INTERFAZ
st.set_page_config(page_title="V2500 Multi-Moment Balancer", layout="wide")

st.markdown("""
    <style>
    .stMetric { border: 2px solid #58a6ff; background: #f0f7ff; padding: 10px; border-radius: 8px; }
    .motor-header { background-color: #1e3a8a; color: white; padding: 10px; border-radius: 5px; margin-top: 25px; }
    .excelencia { border: 2px solid #2ecc71; background: #e8f5e9; padding: 15px; border-radius: 10px; color: #2e7d32; font-weight: bold; text-align: center; }
    .bolt-info { background-color: #fff5f5; border-left: 5px solid #ff4b4b; padding: 10px; margin-top: 10px; color: #c53030; }
    </style>
    """, unsafe_allow_html=True)

st.title("🛡️ V2500 Aero-Master: Multi-Moment DSS")

with st.sidebar:
    st.header("⚙️ Configuración")
    uploaded_file = st.file_uploader("Subir Excel (Peso + Momentos)", type=["xlsx", "csv"])
    
    st.divider()
    metodo_calc = st.selectbox(
        "Método de Cálculo:",
        ["Triple Momento (Vectorial Precisión)", "Mitades (Peso Tradicional)"]
    )
    
    TOLERANCIA_VIB = st.slider("Tolerancia Taller (ips/score)", 0.0, 1.0, 0.50)
    UMBRAL_EXCELENCIA = 0.10

# --- LÓGICA DE CÁLCULO VECTORIAL (MOMENTOS) ---
def get_vibration_metrics(df, slot_col, mode):
    if mode == "Triple Momento (Vectorial Precisión)":
        # Suma vectorial para los 3 momentos
        m1_x, m1_y = 0, 0
        m2_x, m2_y = 0, 0
        m3_x, m3_y = 0, 0
        
        for _, row in df.iterrows():
            angle_rad = math.radians((row[slot_col] - 1) * (360 / 22))
            m1_x += row['Momento1'] * math.cos(angle_rad)
            m1_y += row['Momento1'] * math.sin(angle_rad)
            m2_x += row['Momento2'] * math.cos(angle_rad)
            m2_y += row['Momento2'] * math.sin(angle_rad)
            m3_x += row['Momento3'] * math.cos(angle_rad)
            m3_y += row['Momento3'] * math.sin(angle_rad)
        
        v1 = math.sqrt(m1_x**2 + m1_y**2)
        v2 = math.sqrt(m2_x**2 + m2_y**2)
        v3 = math.sqrt(m3_x**2 + m3_y**2)
        
        # El Score es la vibración percibida (Ponderación AMM)
        score = (v1 * 0.5) + (v2 * 0.3) + (v3 * 0.2)
        
        # El Bolt se calcula sobre el vector principal (M1)
        angle_v1 = math.degrees(math.atan2(m1_y, m1_x))
        bolt_slot = int(((180 - angle_v1) % 360) / (360/22)) + 1
        return round(score, 2), v1, v2, v3, bolt_slot
    
    else:
        # Modo Mitades (Solo Peso)
        m1 = df[df[slot_col] <= 11]['Peso'].sum()
        m2 = df[df[slot_col] > 11]['Peso'].sum()
        diff = m1 - m2
        bolt_slot = 17 if diff > 0 else 6
        return round(abs(diff), 2), round(abs(diff), 2), 0, 0, bolt_slot

# --- GENERADOR DE ESTRATEGIAS (DSS) ---
def generate_dss_options(df_m):
    score_ini, v1_i, v2_i, v3_i, b_s_i = get_vibration_metrics(df_m, 'Slot_Original', metodo_calc)
    df_base = df_m.copy()
    df_base['Nuevo_Slot'] = df_base['Slot_Original']
    
    res = {
        "1. Máximo Balance": {"v": score_ini, "df": df_base.copy(), "moves": 0, "b_slot": b_s_i, "v1": v1_i, "v2": v2_i, "v3": v3_i},
        "2. Mínimos Movimientos": {"v": score_ini, "df": df_base.copy(), "moves": 0, "b_slot": b_s_i, "v1": v1_i, "v2": v2_i, "v3": v3_i},
        "3. Opción Equilibrada": {"v": score_ini, "df": df_base.copy(), "moves": 0, "b_slot": b_s_i, "v1": v1_i, "v2": v2_i, "v3": v3_i}
    }

    # Bucle de optimización (8000 ciclos para estabilidad)
    for _ in range(8000):
        temp = df_m.sample(frac=1).reset_index(drop=True)
        temp['Nuevo_Slot'] = range(1, 23)
        v_t, v1_t, v2_t, v3_t, b_s_t = get_vibration_metrics(temp, 'Nuevo_Slot', metodo_calc)
        m_t = len(temp[temp['Slot_Original'] != temp['Nuevo_Slot']])
        
        # 1. Buscar el cero absoluto
        if v_t < res["1. Máximo Balance"]["v"]:
            res["1. Máximo Balance"] = {"v": v_t, "df": temp.copy(), "moves": m_t, "b_slot": b_s_t, "v1": v1_t, "v2": v2_t, "v3": v3_t}
        
        # 2. Mínimos movimientos dentro de tolerancia
        if v_t <= TOLERANCIA_VIB:
            if m_t < res["2. Mínimos Movimientos"]["moves"] or res["2. Mínimos Movimientos"]["v"] > TOLERANCIA_VIB:
                res["2. Mínimos Movimientos"] = {"v": v_t, "df": temp.copy(), "moves": m_t, "b_slot": b_s_t, "v1": v1_t, "v2": v2_t, "v3": v3_t}

        # 3. Intermedia (Vib < 0.15)
        if v_t <= 0.15:
            if m_t < res["3. Opción Equilibrada"]["moves"] or res["3. Opción Equilibrada"]["v"] > 0.15:
                res["3. Opción Equilibrada"] = {"v": v_t, "df": temp.copy(), "moves": m_t, "b_slot": b_s_t, "v1": v1_t, "v2": v2_t, "v3": v3_t}

    return res

# --- PROCESAMIENTO ---
if uploaded_file:
    try:
        uploaded_file.seek(0)
        df_full = pd.read_excel(uploaded_file, engine='openpyxl')
        df_full.columns = [c.strip().capitalize() for c in df_full.columns]
        
        fleet_selection = {}

        for idx, m_name in enumerate(df_full['Motor'].unique()):
            st.markdown(f"<div class='motor-header'><h3>📦 MOTOR: {m_name}</h3></div>", unsafe_allow_html=True)
            df_m = df_full[df_full['Motor'] == m_name].copy()
            df_m['Slot_Original'] = df_m['Slot'].astype(int)
            df_m['ID_Original'] = df_m['Slot'].apply(lambda x: f"A{int(x)}")
            df_m['Nuevo_Slot'] = df_m['Slot_Original'] # Fix: Asegurar columna
            
            opts = generate_dss_options(df_m)
            
            col_sel, col_metrics = st.columns([1, 2])
            with col_sel:
                selected_name = st.radio(f"Estrategia:", list(opts.keys()), index=1, key=f"r_{idx}")
                choice = opts[selected_name]
                bolt_w, bolt_s = choice['v'], choice['b_slot']

            with col_metrics:
                if choice['v'] <= UMBRAL_EXCELENCIA:
                    st.markdown(f"<div class='excelencia'>🏆 EXCELENCIA: {choice['v']:.2f} score<br><small>Balance dinámico óptimo en 3 planos.</small></div>", unsafe_allow_html=True)
                else:
                    c1, c2, c3 = st.columns(3)
                    v_ini, _, _, _, _ = get_vibration_metrics(df_m, 'Slot_Original', metodo_calc)
                    c1.metric("Vib. Inicial", f"{v_ini:.2f}")
                    c2.metric("Vib. Resultante", f"{choice['v']:.2f}", delta=f"-{v_ini-choice['v']:.2f}")
                    c3.metric("Movimientos", f"{choice['moves']}")
                    st.markdown(f"<div class='bolt-info'>⚖️ <b>BOLT:</b> Instalar {bolt_w:.2f}g en alojamiento Slot {bolt_s}</div>", unsafe_allow_html=True)

            # Tabla de Taller
            df_tab = choice['df'][['ID_Original', 'Peso', 'Momento1', 'Momento2', 'Momento3', 'Slot_Original', 'Nuevo_Slot']].copy()
            df_tab['Acción'] = df_tab.apply(lambda x: "✅ MANTENER" if x['Slot_Original'] == x['Nuevo_Slot'] else f"➔ MOVER AL {int(x['Nuevo_Slot'])}", axis=1)
            df_tab['Compensación'] = ""
            if bolt_w > UMBRAL_EXCELENCIA:
                df_tab.loc[df_tab['Nuevo_Slot'] == bolt_s, 'Compensación'] = f"🔩 BOLT {bolt_w:.2f}g"

            st.table(df_tab.sort_values(by='Slot_Original').style.apply(
                lambda x: ['background-color: #f8d7da' if 'MOVER' in str(v) or 'BOLT' in str(v) else 'background-color: #d4edda' for v in x], axis=1))
            
            fleet_selection[m_name] = {"choice": choice, "df_final": df_tab}

    except Exception as e:
        st.error(f"Error en el Excel: {e}. Asegúrate de que las columnas sean: Motor, Slot, Peso, Momento1, Momento2, Momento3.")
else:
    st.info("👋 Por favor, cargue el archivo Excel con los 3 Momentos para iniciar el balanceo de precisión.")
