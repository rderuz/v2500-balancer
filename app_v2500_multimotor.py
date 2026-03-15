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
    
    metodo_calc = st.selectbox(
        "Seleccione Método de Cálculo:",
        ["Vectorial (Triple Momento - Precisión AMM)", "Mitades (Peso Tradicional 1-11 vs 12-22)"]
    )
    
    TOLERANCIA_VIB = st.slider("Tolerancia Objetivo (ips)", 0.0, 1.0, 0.50)
    UMBRAL_EXCELENCIA = 0.10

# --- LÓGICA DE INGENIERÍA ---
def get_v2500_metrics(df, slot_col):
    if "Vectorial" in metodo_calc:
        res_x, res_y = 0.0, 0.0
        RADIO_CONVERSION = 165.0 
        for _, row in df.iterrows():
            m1 = row.get('Momento1', row.get('Peso', 0) * 16.5)
            angle_rad = math.radians((row[slot_col] - 1) * (360 / 22))
            res_x += float(m1) * math.cos(angle_rad)
            res_y += float(m1) * math.sin(angle_rad)
        
        magnitud_momento = math.sqrt(res_x**2 + res_y**2)
        peso_bolt = round(magnitud_momento / RADIO_CONVERSION, 2)
        vibracion_ips = round(magnitud_momento / 3000, 2) 
        angle_v = math.degrees(math.atan2(res_y, res_x))
        bolt_slot = int(((180 - angle_v) % 360) / (360/22)) + 1
        return vibracion_ips, peso_bolt, bolt_slot
    else:
        m1 = df[df[slot_col] <= 11]['Peso'].sum()
        m2 = df[df[slot_col] > 11]['Peso'].sum()
        diff = round(abs(m1 - m2), 2)
        bolt_slot = 17 if (m1 - m2) > 0 else 6
        return diff, diff, bolt_slot

# --- FUNCIÓN DE GRÁFICOS ---
def render_visual_fan(data, slot_col, titulo, bolt_w=0, bolt_s=0):
    fig = go.Figure()
    theta = np.linspace(0, 360, 22, endpoint=False)
    colores = []
    for i in range(1, 23):
        subset = data[data[slot_col] == i]
        if not subset.empty:
            row = subset.iloc[0]
            if 'Nuevo_Slot' in data.columns and row['Slot_Original'] != row['Nuevo_Slot']:
                colores.append("#e74c3c")
            else:
                colores.append("#2ecc71")
        else:
            colores.append("#bdc3c7")

    fig.add_trace(go.Barpolar(r=[8]*22, theta=theta, width=[14]*22, marker_color=colores, marker_line_color="white", marker_line_width=1.5))
    
    for i in range(22):
        subset = data[data[slot_col] == (i+1)]
        if not subset.empty:
            row = subset.iloc[0]
            fig.add_trace(go.Scatterpolar(r=[6.2], theta=[theta[i]], mode='text', text=[f"A{int(row['Slot_Original'])}"], textfont=dict(size=10, color="white")))
    
    if bolt_w > UMBRAL_EXCELENCIA:
        fig.add_trace(go.Scatterpolar(r=[4], theta=[theta[bolt_s-1]], mode='markers+text', marker=dict(symbol="star", size=20, color="#f1c40f"),
                                     text=[f"{bolt_w:.1f}g"], textposition="bottom center", textfont=dict(size=11, color="red")))
    
    fig.update_layout(title=dict(text=titulo, font=dict(size=18)), polar=dict(bgcolor='white', angularaxis=dict(tickvals=theta, ticktext=[str(i+1) for i in range(22)], rotation=90, direction="clockwise")),
                      showlegend=False, height=450, margin=dict(t=80, b=30, l=30, r=30))
    return fig

# --- GENERADOR DE ESTRATEGIAS ---
def generate_dss_options(df_m):
    v_ini, b_w_ini, b_s_ini = get_v2500_metrics(df_m, 'Slot_Original')
    df_base = df_m.copy()
    df_base['Nuevo_Slot'] = df_base['Slot_Original']
    
    res = {
        "1. Máximo Balance": {"v": v_ini, "bolt": b_w_ini, "slot": b_s_ini, "df": df_base.copy(), "moves": 0},
        "2. Mínimos Movimientos": {"v": v_ini, "bolt": b_w_ini, "slot": b_s_ini, "df": df_base.copy(), "moves": 0},
        "3. Opción Equilibrada": {"v": v_ini, "bolt": b_w_ini, "slot": b_s_ini, "df": df_base.copy(), "moves": 0}
    }

    for _ in range(4000):
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
        df_full = pd.read_excel(uploaded_file, engine='openpyxl')
        df_full.columns = [c.strip().capitalize() for c in df_full.columns]
        
        for idx, m_name in enumerate(df_full['Motor'].unique()):
            st.markdown(f"<div class='motor-header'><h3>📦 MOTOR: {m_name}</h3></div>", unsafe_allow_html=True)
            df_m = df_full[df_full['Motor'] == m_name].copy()
            df_m['Slot_Original'] = df_m['Slot'].astype(int)
            df_m['ID_Original'] = df_m['Slot_Original'].apply(lambda x: f"A{x}")
            df_m['Nuevo_Slot'] = df_m['Slot_Original'] 
            
            opts = generate_dss_options(df_m)
            selected_name = st.radio(f"Estrategia para {m_name}:", list(opts.keys()), index=1, key=f"r_{idx}")
            choice = opts[selected_name]

            c1, c2, c3 = st.columns(3)
            v_ini_val, _, _ = get_v2500_metrics(df_m, 'Slot_Original')
            c1.metric("Vib. Inicial", f"{v_ini_val:.2f} ips")
            c2.metric("Vib. Final", f"{choice['v']:.2f} ips")
            c3.metric("Mover", f"{choice['moves']} álabes")
            
            if choice['v'] > UMBRAL_EXCELENCIA:
                st.markdown(f"<div class='bolt-info'>⚖️ COMPENSACIÓN: Bolt de {choice['bolt']:.2f}g en Slot {choice['slot']}</div>", unsafe_allow_html=True)
            else:
                st.markdown("<div class='excelencia'>🏆 EXCELENCIA: Balance perfecto.</div>", unsafe_allow_html=True)

            g1, g2 = st.columns(2)
            df_ini_view = df_m.copy()
            df_ini_view['Nuevo_Slot'] = df_ini_view['Slot_Original']
            with g1:
                st.plotly_chart(render_visual_fan(df_ini_view, 'Slot_Original', "AS FOUND"), use_container_width=True, key=f"v1_{idx}")
            with g2:
                st.plotly_chart(render_visual_fan(choice['df'], 'Nuevo_Slot', "AS LEFT", choice['bolt'], choice['slot']), use_container_width=True, key=f"v2_{idx}")

            df_tab = choice['df'][['ID_Original', 'Peso', 'Slot_Original', 'Nuevo_Slot']].copy()
            df_tab['Acción'] = df_tab.apply(lambda x: "✅ OK" if x['Slot_Original'] == x['Nuevo_Slot'] else f"➔ MOVER AL {int(x['Nuevo_Slot'])}", axis=1)
            
            st.table(df_tab.sort_values(by='Slot_Original').style.apply(
                lambda x: ['background-color: #f8d7da' if 'MOVER' in str(v) else 'background-color: #d4edda' for v in x], axis=1))

    except Exception as e:
        st.error(f"Error técnico: {e}")
else:
    st.info("👋 Suba el archivo Excel para activar el panel.")
