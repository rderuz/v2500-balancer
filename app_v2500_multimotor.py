import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import io
import math

# 1. CONFIGURACIÓN DE INTERFAZ
st.set_page_config(page_title="V2500 Precision Balancer PRO", layout="wide")

st.markdown("""
    <style>
    .stMetric { border: 2px solid #58a6ff; background: #f0f7ff; padding: 10px; border-radius: 8px; }
    .motor-header { background-color: #1e3a8a; color: white; padding: 10px; border-radius: 5px; margin-top: 25px; }
    .excelencia { border: 2px solid #2ecc71; background: #e8f5e9; padding: 15px; border-radius: 10px; color: #2e7d32; font-weight: bold; text-align: center; }
    .bolt-info { background-color: #fff5f5; border-left: 5px solid #ff4b4b; padding: 15px; margin-top: 10px; color: #c53030; font-size: 1.2em; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

st.title("🛡️ V2500 Aero-Master: Sistema de Balanceo Profesional")

with st.sidebar:
    st.header("⚙️ Configuración de Planta")
    uploaded_file = st.file_uploader("Subir Excel (Peso + Momentos)", type=["xlsx"])
    st.divider()
    
    # SELECTOR DE MODO (Vuelve a estar disponible)
    metodo_calc = st.selectbox(
        "Seleccione Método de Cálculo:",
        ["Vectorial (Triple Momento - Precisión AMM)", "Mitades (Peso Tradicional 1-11 vs 12-22)"]
    )
    
    TOLERANCIA_VIB = st.slider("Tolerancia Objetivo (ips)", 0.0, 1.0, 0.50)
    UMBRAL_EXCELENCIA = 0.10

# --- LÓGICA DE INGENIERÍA (CÁLCULO DE VIBRACIÓN Y BOLT) ---
def get_v2500_metrics(df, slot_col):
    if "Vectorial" in metodo_calc:
        res_x, res_y = 0, 0
        # RADIO_CONVERSION: Factor para pasar de Desbalance (g-mm) a Peso de Tornillo (g)
        # En el V2500, el alojamiento del tornillo está a ~165mm del centro.
        RADIO_CONVERSION = 165.0 

        for _, row in df.iterrows():
            # Si no hay momentos, estimamos M1 = Peso * 16.5
            m1 = row.get('Momento1', row['Peso'] * 16.5)
            angle_rad = math.radians((row[slot_col] - 1) * (360 / 22))
            res_x += m1 * math.cos(angle_rad)
            res_y += m1 * math.sin(angle_rad)
        
        magnitud_momento = math.sqrt(res_x**2 + res_y**2)
        
        # El Bolt es la fuerza necesaria dividida por el brazo de palanca
        peso_bolt = round(magnitud_momento / RADIO_CONVERSION, 2)
        # La vibración se escala para mostrarse en IPS (0.0 a 1.0)
        vibracion_ips = round(magnitud_momento / 3000, 2) 

        angle_v = math.degrees(math.atan2(res_y, res_x))
        bolt_slot = int(((180 - angle_v) % 360) / (360/22)) + 1
        return vibracion_ips, peso_bolt, bolt_slot
    
    else:
        # MODO MITADES (Solo Peso)
        m1 = df[df[slot_col] <= 11]['Peso'].sum()
        m2 = df[df[slot_col] > 11]['Peso'].sum()
        diff = round(abs(m1 - m2), 2)
        bolt_slot = 17 if (m1 - m2) > 0 else 6
        return diff, diff, bolt_slot

# --- FUNCIÓN DE GRÁFICOS (Vuelve a estar disponible) ---
def render_visual_fan(data, slot_col, titulo, bolt_w=0, bolt_s=0):
    fig = go.Figure()
    theta = np.linspace(0, 360, 22, endpoint=False)
    
    # Código de colores: Rojo para lo que se mueve, Verde para lo que se queda
    colores = []
    for i in range(22):
        row = data[data[slot_col] == (i+1)].iloc[0]
        if row['Slot_Original'] != row['Nuevo_Slot']:
            colores.append("#e74c3c") # Rojo
        else:
            colores.append("#2ecc71") # Verde

    fig.add_trace(go.Barpolar(r=[8]*22, theta=theta, width=[14]*22, marker_color=colores, marker_line_color="white", marker_line_width=1.5))
    
    for i in range(22):
        row = data[data[slot_col] == (i+1)].iloc[0]
        fig.add_trace(go.Scatterpolar(r=[6.2], theta=[theta[i]], mode='text', text=[f"<b>{row['ID_Original']}</b>"], textfont=dict(size=12, color="white")))
    
    if bolt_w > UMBRAL_EXCELENCIA:
        fig.add_trace(go.Scatterpolar(r=[4], theta=[theta[bolt_s-1]], mode='markers+text', marker=dict(symbol="star", size=25, color="#f1c40f"),
                                     text=[f"BOLT {bolt_w:.2f}g"], textposition="bottom center", textfont=dict(size=12, color="red")))
    
    fig.update_layout(title=f"<b>{titulo}</b>", polar=dict(bgcolor='white', angularaxis=dict(tickvals=theta, ticktext=[str(i+1) for i in range(22)], rotation=90, direction="clockwise")),
                      showlegend=False, height=500, margin=dict(t=50, b=30, l=30, r=30))
    return fig

# --- GENERADOR DE ESTRATEGIAS (DSS) ---
def generate_dss_options(df_m):
    v_ini, b_w_ini, b_s_ini = get_v2500_metrics(df_m, 'Slot_Original')
    df_base = df_m.copy()
    df_base['Nuevo_Slot'] = df_base['Slot_Original']
    
    res = {
        "1. Máximo Balance": {"v": v_ini, "bolt": b_w_ini, "slot": b_s_ini, "df": df_base.copy(), "moves": 0},
        "2. Mínimos Movimientos": {"v": v_ini, "bolt": b_w_ini, "slot": b_s_ini, "df": df_base.copy(), "moves": 0},
        "3. Opción Equilibrada": {"v": v_ini, "bolt": b_w_ini, "slot": b_s_ini, "df": df_base.copy(), "moves": 0}
    }

    for _ in range(5000): # 5000 ciclos para agilidad en móvil
        temp = df_m.sample(frac=1).reset_index(drop=True)
        temp['Nuevo_Slot'] = range(1, 23)
        v_t, b_w_t, b_s_t = get_v2500_metrics(temp, 'Nuevo_Slot')
        m_t = len(temp[temp['Slot_Original'] != temp['Nuevo_Slot']])
        
        if v_t < res["1. Máximo Balance"]["v"]:
            res["1. Máximo Balance"] = {"v": v_t, "bolt": b_w_t, "slot": b_s_t, "df": temp.copy(), "moves": m_t}
        if v_t <= TOLERANCIA_VIB:
            if m_t < res["2. Mínimos Movimientos"]["moves"] or res["2. Mínimos Movimientos"]["v"] > TOLERANCIA_VIB:
                res["2. Mínimos Movimientos"] = {"v": v_t, "bolt": b_w_t, "slot": b_s_t, "df": temp.copy(), "moves": m_t}
        if v_t <= 0.15:
            if m_t < res["3. Opción Equilibrada"]["moves"] or res["3. Opción Equilibrada"]["v"] > 0.15:
                res["3. Opción Equilibrada"] = {"v": v_t, "bolt": b_w_t, "slot": b_s_t, "df": temp.copy(), "moves": m_t}

    return res

# --- PROCESAMIENTO ---
if uploaded_file:
    try:
        uploaded_file.seek(0)
        df_full = pd.read_excel(uploaded_file, engine='openpyxl')
        df_full.columns = [c.strip().capitalize() for c in df_full.columns]
        
        for idx, m_name in enumerate(df_full['Motor'].unique()):
            st.markdown(f"<div class='motor-header'><h3>📦 MOTOR: {m_name}</h3></div>", unsafe_allow_html=True)
            df_m = df_full[df_full['Motor'] == m_name].copy()
            df_m['Slot_Original'] = df_m['Slot'].astype(int)
            df_m['ID_Original'] = df_m['Slot'].apply(lambda x: f"A{int(x)}")
            df_m['Nuevo_Slot'] = df_m['Slot_Original'] 
            
            opts = generate_dss_options(df_m)
            
            col_sel, col_metrics = st.columns([1, 2])
            with col_sel:
                selected_name = st.radio(f"Estrategia:", list(opts.keys()), index=1, key=f"r_{idx}")
                choice = opts[selected_name]

            with col_metrics:
                if choice['v'] <= UMBRAL_EXCELENCIA:
                    st.markdown(f"<div class='excelencia'>🏆 EXCELENCIA: {choice['v']:.2f} ips<br><small>No requiere pesos adicionales.</small></div>", unsafe_allow_html=True)
                else:
                    c1, c2, c3 = st.columns(3)
                    v_ini, _, _ = get_v2500_metrics(df_m, 'Slot_Original')
                    c1.metric("Vib. Inicial", f"{v_ini:.2f} ips")
                    c2.metric("Vib. Final", f"{choice['v']:.2f} ips")
                    c3.metric("Mover", f"{choice['moves']} álabes")
                    st.markdown(f"<div class='bolt-info'>⚖️ COMPENSACIÓN: Bolt de {choice['bolt']:.2f}g en Slot {choice['slot']}</div>", unsafe_allow_html=True)

            # Gráficos Semafóricos
            g1, g2 = st.columns(2)
            df_ini_view = df_m.copy(); df_ini_view['Nuevo_Slot'] = df_ini_view['Slot_Original']
            with g1: st.plotly_chart(render_visual_fan(df_ini_view, 'Slot_Original', "SITUACIÓN ACTUAL"), use_container_width=True, key=f"g1_{idx}")
            with g2: st.plotly_chart(render_visual_fan(choice['df'], 'Nuevo_Slot', f"PROPUESTA: {selected_name}", choice['bolt'], choice['slot']), use_container_width=True, key=f"g2_{idx}")

            # Tabla de Taller
            df_tab = choice['df'][['ID_Original', 'Peso', 'Slot_Original', 'Nuevo_Slot']].copy()
            df_tab['Acción'] = df_tab.apply(lambda x: "✅ OK" if x['Slot_Original'] == x['Nuevo_Slot'] else f"➔ MOVER AL {int(x['Nuevo_Slot'])}", axis=1)
            df_tab['Compensación'] = ""
            if choice['bolt'] > UMBRAL_EXCELENCIA:
                df_tab.loc[df_tab['Nuevo_Slot'] == choice['slot'], 'Compensación'] = f"🔩 BOLT {choice['bolt']:.2f}g"

            st.table(df_tab.sort_values(by='Slot_Original').style.apply(
                lambda x: ['background-color: #f8d7da' if 'MOVER' in str(v) or 'BOLT' in str(v) else 'background-color: #d4edda' for v in x], axis=1))

    except Exception as e:
        st.error(f"Error técnico: {e}")
else:
    st.info("👋 Cargue el Excel para activar el panel visual con física corregida.")
        # Usamos Momento 1 (Radial) como vector principal de vibración
        m1 = row['Momento1']
        angle_rad = math.radians((row[slot_col] - 1) * (360 / 22))
        res_x += m1 * math.cos(angle_rad)
        res_y += m1 * math.sin(angle_rad)
    
    # Magnitud total del desbalance de momento
    magnitud_momento = math.sqrt(res_x**2 + res_y**2)
    
    # 1. El Bolt real: desbalance de momento / brazo de palanca del tornillo
    peso_bolt = round(magnitud_momento / RADIO_CONVERSION, 2)
    
    # 2. La Vibración (ips): Normalizada según la sensibilidad típica del motor
    # Un desbalance de 3000 g-mm suele dar ~1.0 ips
    vibracion_ips = round(magnitud_momento / 3000, 2) 

    angle_v = math.degrees(math.atan2(res_y, res_x))
    bolt_slot = int(((180 - angle_v) % 360) / (360/22)) + 1
    
    return vibracion_ips, peso_bolt, bolt_slot

# --- GENERADOR DE ESTRATEGIAS (DSS) ---
def generate_dss_options(df_m):
    v_ini, b_w_ini, b_s_ini = get_v2500_metrics(df_m, 'Slot_Original')
    df_base = df_m.copy()
    df_base['Nuevo_Slot'] = df_base['Slot_Original']
    
    # Estructura de opciones
    res = {
        "1. Máximo Balance": {"v": v_ini, "bolt": b_w_ini, "slot": b_s_ini, "df": df_base.copy(), "moves": 0},
        "2. Mínimos Movimientos": {"v": v_ini, "bolt": b_w_ini, "slot": b_s_ini, "df": df_base.copy(), "moves": 0},
        "3. Opción Equilibrada": {"v": v_ini, "bolt": b_w_ini, "slot": b_s_ini, "df": df_base.copy(), "moves": 0}
    }

    # Optimización Monte Carlo (8000 iteraciones)
    for _ in range(8000):
        temp = df_m.sample(frac=1).reset_index(drop=True)
        temp['Nuevo_Slot'] = range(1, 23)
        v_t, b_w_t, b_s_t = get_v2500_metrics(temp, 'Nuevo_Slot')
        m_t = len(temp[temp['Slot_Original'] != temp['Nuevo_Slot']])
        
        # Lógica de selección para cada estrategia
        if v_t < res["1. Máximo Balance"]["v"]:
            res["1. Máximo Balance"] = {"v": v_t, "bolt": b_w_t, "slot": b_s_t, "df": temp.copy(), "moves": m_t}
        
        if v_t <= TOLERANCIA_VIB:
            if m_t < res["2. Mínimos Movimientos"]["moves"] or res["2. Mínimos Movimientos"]["v"] > TOLERANCIA_VIB:
                res["2. Mínimos Movimientos"] = {"v": v_t, "bolt": b_w_t, "slot": b_s_t, "df": temp.copy(), "moves": m_t}

        if v_t <= 0.15:
            if m_t < res["3. Opción Equilibrada"]["moves"] or res["3. Opción Equilibrada"]["v"] > 0.15:
                res["3. Opción Equilibrada"] = {"v": v_t, "bolt": b_w_t, "slot": b_s_t, "df": temp.copy(), "moves": m_t}

    return res

# --- PROCESAMIENTO PRINCIPAL ---
if uploaded_file:
    try:
        uploaded_file.seek(0)
        df_full = pd.read_excel(uploaded_file, engine='openpyxl')
        df_full.columns = [c.strip().capitalize() for c in df_full.columns]
        
        for idx, m_name in enumerate(df_full['Motor'].unique()):
            st.markdown(f"<div class='motor-header'><h3>📦 MOTOR: {m_name}</h3></div>", unsafe_allow_html=True)
            df_m = df_full[df_full['Motor'] == m_name].copy()
            df_m['Slot_Original'] = df_m['Slot'].astype(int)
            df_m['ID_Original'] = df_m['Slot'].apply(lambda x: f"A{int(x)}")
            df_m['Nuevo_Slot'] = df_m['Slot_Original'] 
            
            # Generar Opciones
            opts = generate_dss_options(df_m)
            
            col_sel, col_metrics = st.columns([1, 2])
            with col_sel:
                selected_name = st.radio(f"Estrategia para {m_name}:", list(opts.keys()), index=1, key=f"r_{idx}")
                choice = opts[selected_name]

            with col_metrics:
                if choice['v'] <= UMBRAL_EXCELENCIA:
                    st.markdown(f"<div class='excelencia'>🏆 EXCELENCIA: {choice['v']:.2f} ips<br><small>Balance perfecto. No requiere añadir pesos.</small></div>", unsafe_allow_html=True)
                else:
                    c1, c2, c3 = st.columns(3)
                    v_ini, _, _ = get_v2500_metrics(df_m, 'Slot_Original')
                    c1.metric("Vib. Inicial", f"{v_ini:.2f} ips")
                    c2.metric("Vib. Final", f"{choice['v']:.2f} ips", delta=f"-{v_ini-choice['v']:.2f}")
                    c3.metric("Mover", f"{choice['moves']} álabes")
                    st.markdown(f"<div class='bolt-info'>⚖️ <b>COMPENSACIÓN:</b> Instalar Bolt de {choice['bolt']:.2f}g en Slot {choice['slot']}</div>", unsafe_allow_html=True)

            # Tabla de Taller
            df_tab = choice['df'][['ID_Original', 'Peso', 'Momento1', 'Momento2', 'Momento3', 'Slot_Original', 'Nuevo_Slot']].copy()
            df_tab['Acción'] = df_tab.apply(lambda x: "✅ OK" if x['Slot_Original'] == x['Nuevo_Slot'] else f"➔ MOVER AL {int(x['Nuevo_Slot'])}", axis=1)
            df_tab['Compensación'] = ""
            if choice['bolt'] > UMBRAL_EXCELENCIA:
                df_tab.loc[df_tab['Nuevo_Slot'] == choice['slot'], 'Compensación'] = f"🔩 BOLT {choice['bolt']:.2f}g"

            st.table(df_tab.sort_values(by='Slot_Original').style.apply(
                lambda x: ['background-color: #f8d7da' if 'MOVER' in str(v) or 'BOLT' in str(v) else 'background-color: #d4edda' for v in x], axis=1))

    except Exception as e:
        st.error(f"Error en el Excel: {e}. Asegúrate de que las columnas sean: Motor, Slot, Peso, Momento1, Momento2, Momento3.")
else:
    st.info("👋 Por favor, cargue el archivo Excel para iniciar el balanceo de precisión.")
