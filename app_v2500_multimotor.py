import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import io
import math

# 1. CONFIGURACIÓN DE PÁGINA
st.set_page_config(page_title="V2500 Dual Balancer", layout="wide")

st.markdown("""
    <style>
    .stMetric { border: 2px solid #58a6ff; background: #f0f7ff; padding: 10px; border-radius: 8px; }
    .motor-header { background-color: #1e3a8a; color: white; padding: 10px; border-radius: 5px; margin-top: 25px; }
    .excelencia { border: 2px solid #2ecc71; background: #e8f5e9; padding: 15px; border-radius: 10px; color: #2e7d32; font-weight: bold; text-align: center; }
    .bolt-info { background-color: #fff5f5; border-left: 5px solid #ff4b4b; padding: 10px; margin-top: 10px; color: #c53030; }
    </style>
    """, unsafe_allow_html=True)

st.title("🛡️ V2500 Aero-Master: Sistema de Balanceo Dual")

with st.sidebar:
    st.header("⚙️ Configuración")
    uploaded_file = st.file_uploader("Subir Excel Multimotor", type=["xlsx", "csv"])
    st.divider()
    # NUEVO SELECTOR DE MÉTODO
    metodo_calc = st.selectbox(
        "Seleccione Método de Cálculo:",
        ["Vectorial (AMM Precisión)", "Mitades (Tradicional 1-11 vs 12-22)"]
    )
    TOLERANCIA_AMM = 0.50 
    UMBRAL_EXCELENCIA = 0.10

# --- LÓGICA DE CÁLCULO VECTORIAL ---
def calc_vectorial(df, slot_col):
    res_x, res_y = 0, 0
    for _, row in df.iterrows():
        angle_deg = (row[slot_col] - 1) * (360 / 22)
        angle_rad = math.radians(angle_deg)
        res_x += row['Peso'] * math.cos(angle_rad)
        res_y += row['Peso'] * math.sin(angle_rad)
    v_total = math.sqrt(res_x**2 + res_y**2)
    angle_v = math.degrees(math.atan2(res_y, res_x))
    bolt_slot = int(((180 - angle_v) % 360) / (360/22)) + 1
    return round(v_total, 2), round(res_x - res_y, 2), bolt_slot # El diff aquí es simbólico para la lógica de d_t

# --- LÓGICA POR MITADES ---
def calc_mitades(df, slot_col):
    m1 = df[df[slot_col] <= 11]['Peso'].sum()
    m2 = df[df[slot_col] > 11]['Peso'].sum()
    diff = m1 - m2
    bolt_slot = 17 if diff > 0 else 6
    return round(abs(diff), 2), round(diff, 2), bolt_slot

# --- FUNCIÓN PUENTE (Ajusta el cálculo según selección) ---
def get_stats(df, slot_col):
    if metodo_calc == "Vectorial (AMM Precisión)":
        return calc_vectorial(df, slot_col)
    else:
        return calc_mitades(df, slot_col)

def get_moves(df):
    return len(df[df['Slot_Original'] != df['Nuevo_Slot']])

# --- GENERADOR DE OPCIONES ---
def generate_options(df_m):
    v_ini, d_ini, b_s_ini = get_stats(df_m, 'Slot_Original')
    df_base = df_m.copy()
    df_base['Nuevo_Slot'] = df_base['Slot_Original']
    
    best_bal = {"v": v_ini, "df": df_base.copy(), "moves": 0, "diff": d_ini, "b_slot": b_s_ini}
    best_min_moves = {"v": v_ini, "df": df_base.copy(), "moves": 0, "diff": d_ini, "b_slot": b_s_ini}
    best_mid = {"v": v_ini, "df": df_base.copy(), "moves": 0, "diff": d_ini, "b_slot": b_s_ini}
    
    for _ in range(8000):
        temp = df_m.sample(frac=1).reset_index(drop=True)
        temp['Nuevo_Slot'] = range(1, 23)
        v_t, d_t, b_s_t = get_stats(temp, 'Nuevo_Slot')
        m_t = get_moves(temp)
        
        if v_t < best_bal["v"]:
            best_bal = {"v": v_t, "df": temp.copy(), "moves": m_t, "diff": d_t, "b_slot": b_s_t}
        if v_t <= TOLERANCIA_AMM:
            if m_t < best_min_moves["moves"] or best_min_moves["v"] > TOLERANCIA_AMM:
                best_min_moves = {"v": v_t, "df": temp.copy(), "moves": m_t, "diff": d_t, "b_slot": b_s_t}
        if v_t <= 0.15:
            if m_t < best_mid["moves"] or best_mid["v"] > 0.15:
                best_mid = {"v": v_t, "df": temp.copy(), "moves": m_t, "diff": d_t, "b_slot": b_s_t}

    return [
        {"name": "1. Máximo Balance", "data": best_bal},
        {"name": "2. Mínimos Movimientos", "data": best_min_moves},
        {"name": "3. Opción Equilibrada", "data": best_mid}
    ]

# --- RENDERIZADO VISUAL ---
def render_fan(data, slot_col, titulo, bolt_w=0, bolt_s=0):
    fig = go.Figure()
    theta = np.linspace(0, 360, 22, endpoint=False)
    colores = ["#e74c3c" if row['Slot_Original'] != row['Nuevo_Slot'] else "#2ecc71" 
               for _, row in data.sort_values(by=slot_col).iterrows()]

    fig.add_trace(go.Barpolar(r=[8]*22, theta=theta, width=[14]*22, marker_color=colores, marker_line_color="white", marker_line_width=1.5))
    for i in range(22):
        row = data[data[slot_col] == (i+1)].iloc[0]
        fig.add_trace(go.Scatterpolar(r=[6.2], theta=[theta[i]], mode='text', text=[f"<b>{row['ID_Original']}</b>"], textfont=dict(size=13, color="white")))
    
    if bolt_w > UMBRAL_EXCELENCIA:
        fig.add_trace(go.Scatterpolar(r=[4], theta=[theta[bolt_s-1]], mode='markers+text', marker=dict(symbol="star", size=25, color="#f1c40f"),
                                     text=[f"BOLT {bolt_w:.2f}"], textposition="bottom center", textfont=dict(size=12, color="red")))
    
    fig.update_layout(title=f"<b>{titulo}</b>", polar=dict(bgcolor='white', angularaxis=dict(tickvals=theta, ticktext=[str(i+1) for i in range(22)], rotation=90, direction="clockwise")),
                      showlegend=False, height=500, margin=dict(t=50, b=30, l=30, r=30))
    return fig

# --- PROCESO ---
if uploaded_file:
    try:
        uploaded_file.seek(0)
        df_full = pd.read_excel(uploaded_file, engine='openpyxl')
        df_full.columns = [c.strip().capitalize() for c in df_full.columns]
        
        fleet_selection = {}

        for idx, m_name in enumerate(df_full['Motor'].unique()):
            st.markdown(f"<div class='motor-header'><h3>📦 MOTOR: {m_name} (Modo: {metodo_calc})</h3></div>", unsafe_allow_html=True)
            df_m = df_full[df_full['Motor'] == m_name].copy()
            df_m['ID_Original'] = [f"A{int(s)}" for s in df_m['Slot']]
            df_m['Slot_Original'] = df_m['Slot'].astype(int)
            df_m['Nuevo_Slot'] = df_m['Slot_Original'] 
            
            opts_list = generate_options(df_m)
            opt_names = [o["name"] for o in opts_list]
            
            col_sel, col_metrics = st.columns([1, 2])
            with col_sel:
                selected_name = st.radio(f"Estrategia:", opt_names, index=1, key=f"r_{idx}")
                choice = next(o["data"] for o in opts_list if o["name"] == selected_name)
                bolt_w = choice['v']
                bolt_s = choice['b_slot']

            with col_metrics:
                if choice['v'] <= UMBRAL_EXCELENCIA:
                    st.markdown(f"<div class='excelencia'>🏆 EXCELENCIA: {choice['v']:.2f} ips<br><small>Balance perfecto. No requiere añadir pesos.</small></div>", unsafe_allow_html=True)
                else:
                    c1, c2, c3 = st.columns(3)
                    v_ini_m, _, _ = get_stats(df_m, 'Slot_Original')
                    c1.metric("Vib. Inicial", f"{v_ini_m:.2f}")
                    c2.metric("Vib. Final", f"{choice['v']:.2f}")
                    c3.metric("Mover", f"{choice['moves']} álabes")
                    st.markdown(f"<div class='bolt-info'>⚖️ <b>COMPENSACIÓN:</b> Instalar Bolt de {bolt_w:.2f}g en alojamiento eje Slot {bolt_s}</div>", unsafe_allow_html=True)

            g1, g2 = st.columns(2)
            df_ini_view = df_m.copy(); df_ini_view['Nuevo_Slot'] = df_ini_view['Slot_Original']
            with g1: st.plotly_chart(render_fan(df_ini_view, 'Slot_Original', "SITUACIÓN ACTUAL"), use_container_width=True, key=f"g1_{idx}")
            with g2: st.plotly_chart(render_fan(choice['df'], 'Nuevo_Slot', f"AS LEFT"), use_container_width=True, key=f"g2_{idx}")

            # Tabla de Taller
            df_tab = choice['df'][['ID_Original', 'Peso', 'Slot_Original', 'Nuevo_Slot']].copy()
            df_tab['Acción'] = df_tab.apply(lambda x: "✅ OK" if x['Slot_Original'] == x['Nuevo_Slot'] else f"➔ MOVER AL {int(x['Nuevo_Slot'])}", axis=1)
            df_tab['Compensación'] = ""
            if bolt_w > UMBRAL_EXCELENCIA:
                df_tab.loc[df_tab['Nuevo_Slot'] == bolt_s, 'Compensación'] = f"🔩 BOLT {bolt_w:.2f}g"

            st.table(df_tab.sort_values(by='Slot_Original').style.apply(
                lambda x: ['background-color: #f8d7da' if 'MOVER' in str(v) or 'BOLT' in str(v) else 'background-color: #d4edda' for v in x], axis=1))
            
            fleet_selection[m_name] = {"choice": choice, "df_final": df_tab, "metodo": metodo_calc}

        # EXPORTACIÓN
        def get_xlsx(selections):
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                summary = []
                for m, info in selections.items():
                    summary.append({'Motor': m, 'Método': info['metodo'], 'Vib_Final': info['choice']['v'], 'Movimientos': info['choice']['moves'], 'Bolt': info['choice']['v'], 'Slot': info['choice']['b_slot']})
                pd.DataFrame(summary).to_excel(writer, sheet_name='RESUMEN', index=False)
                for m, info in selections.items():
                    info['df_final'].to_excel(writer, sheet_name=f"MOTOR_{m}", index=False)
            return output.getvalue()

        st.sidebar.download_button("📥 DESCARGAR PLAN DE TALLER", data=get_xlsx(fleet_selection), file_name="Balanceo_V2500_Dual.xlsx")

    except Exception as e:
        st.error(f"Error técnico: {e}")
else:
    st.info("👋 Bienvenida/o. Cargue el archivo y seleccione el método de cálculo en la izquierda.")
