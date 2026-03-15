import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import io
import math

# 1. CONFIGURACIÓN
st.set_page_config(page_title="V2500 Vectorial DSS", layout="wide")

st.markdown("""
    <style>
    .stMetric { border: 2px solid #58a6ff; background: #f0f7ff; padding: 10px; border-radius: 8px; }
    .motor-header { background-color: #1e3a8a; color: white; padding: 10px; border-radius: 5px; margin-top: 25px; }
    .excelencia { border: 2px solid #2ecc71; background: #e8f5e9; padding: 15px; border-radius: 10px; color: #2e7d32; font-weight: bold; text-align: center; }
    .bolt-info { background-color: #fff5f5; border-left: 5px solid #ff4b4b; padding: 10px; margin-top: 10px; color: #c53030; }
    </style>
    """, unsafe_allow_html=True)

st.title("🛡️ V2500 Aero-Master: Vectorial Decision Support")

with st.sidebar:
    st.header("⚙️ Configuración")
    uploaded_file = st.file_uploader("Subir Excel Multimotor", type=["xlsx", "csv"])
    TOLERANCIA_AMM = 0.50 
    UMBRAL_EXCELENCIA = 0.10

# --- LÓGICA VECTORIAL (AMM) ---
def get_vectorial_vibration(df, slot_col):
    # Ángulo por slot (360 / 22 = 16.3636°)
    # El Slot 1 empieza en 0 grados
    res_x = 0
    res_y = 0
    for _, row in df.iterrows():
        angle_deg = (row[slot_col] - 1) * (360 / 22)
        angle_rad = math.radians(angle_deg)
        res_x += row['Peso'] * math.cos(angle_rad)
        res_y += row['Peso'] * math.sin(angle_rad)
    
    total_v = math.sqrt(res_x**2 + res_y**2)
    # El ángulo del desbalance es el opuesto para el Bolt
    angle_v = math.degrees(math.atan2(res_y, res_x))
    bolt_slot = int(((180 - angle_v) % 360) / (360/22)) + 1
    return round(total_v, 2), bolt_slot

def get_moves(df):
    return len(df[df['Slot_Original'] != df['Nuevo_Slot']])

def generate_options(df_m):
    v_ini, b_slot_ini = get_vectorial_vibration(df_m, 'Slot_Original')
    df_base = df_m.copy()
    df_base['Nuevo_Slot'] = df_base['Slot_Original']
    
    best_bal = {"v": v_ini, "df": df_base.copy(), "moves": 0, "b_slot": b_slot_ini}
    best_min_moves = {"v": v_ini, "df": df_base.copy(), "moves": 0, "b_slot": b_slot_ini}
    best_mid = {"v": v_ini, "df": df_base.copy(), "moves": 0, "b_slot": b_slot_ini}
    
    # 8000 iteraciones para no colapsar Android
    for _ in range(8000):
        temp = df_m.sample(frac=1).reset_index(drop=True)
        temp['Nuevo_Slot'] = range(1, 23)
        v_t, b_s_t = get_vectorial_vibration(temp, 'Nuevo_Slot')
        m_t = get_moves(temp)
        
        if v_t < best_bal["v"]:
            best_bal = {"v": v_t, "df": temp.copy(), "moves": m_t, "b_slot": b_s_t}
        if v_t <= TOLERANCIA_AMM:
            if m_t < best_min_moves["moves"] or best_min_moves["v"] > TOLERANCIA_AMM:
                best_min_moves = {"v": v_t, "df": temp.copy(), "moves": m_t, "b_slot": b_s_t}
        if v_t <= 0.15:
            if m_t < best_mid["moves"] or best_mid["v"] > 0.15:
                best_mid = {"v": v_t, "df": temp.copy(), "moves": m_t, "b_slot": b_s_t}

    return [
        {"name": "1. Máximo Balance (Prioriza 0.00)", "data": best_bal},
        {"name": "2. Mínimos Movimientos (Default < 0.50)", "data": best_min_moves},
        {"name": "3. Opción Equilibrada (Vib < 0.15)", "data": best_mid}
    ]

def render_fan(data, slot_col, titulo, bolt_w=0, bolt_s=0):
    fig = go.Figure()
    theta = np.linspace(0, 360, 22, endpoint=False)
    colores = ["#e74c3c" if row['Slot_Original'] != row['Nuevo_Slot'] else "#2ecc71" 
               for _, row in data.sort_values(by=slot_col).iterrows()]

    fig.add_trace(go.Barpolar(r=[8]*22, theta=theta, width=[14]*22, marker_color=colores, marker_line_color="white", marker_line_width=1.5))
    for i in range(22):
        row = data[data[slot_col] == (i+1)].iloc[0]
        fig.add_trace(go.Scatterpolar(r=[6], theta=[theta[i]], mode='text', text=[f"<b>{row['ID_Original']}</b>"], textfont=dict(size=14, color="white")))
    
    if bolt_w > UMBRAL_EXCELENCIA:
        fig.add_trace(go.Scatterpolar(r=[4], theta=[theta[bolt_s-1]], mode='markers+text', marker=dict(symbol="star", size=20, color="#f1c40f"),
                                     text=[f"BOLT {bolt_w:.2f}"], textposition="bottom center", textfont=dict(size=12, color="red")))
    
    fig.update_layout(title=f"<b>{titulo}</b>", polar=dict(bgcolor='white', angularaxis=dict(tickvals=theta, ticktext=[str(i+1) for i in range(22)], rotation=90, direction="clockwise")),
                      showlegend=False, height=500, margin=dict(t=50, b=30, l=30, r=30))
    return fig

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
            df_m['ID_Original'] = [f"A{int(s)}" for s in df_m['Slot']]
            df_m['Slot_Original'] = df_m['Slot'].astype(int)
            df_m['Nuevo_Slot'] = df_m['Slot_Original'] # Inicialización para evitar error
            
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
                    st.markdown(f"<div class='excelencia'>🏆 EXCELENCIA: {choice['v']:.2f} ips<br><small>No requiere pesos adicionales.</small></div>", unsafe_allow_html=True)
                else:
                    c1, c2, c3 = st.columns(3)
                    v_ini_m, _ = get_vectorial_vibration(df_m, 'Slot_Original')
                    c1.metric("Vib. Inicial", f"{v_ini_m:.2f}")
                    c2.metric("Vib. Final", f"{choice['v']:.2f}")
                    c3.metric("Mover", f"{choice['moves']} álabes")
                    st.markdown(f"<div class='bolt-info'>⚖️ <b>COMPENSACIÓN:</b> Instalar {bolt_w:.2f}g en alojamiento eje Slot {bolt_s}</div>", unsafe_allow_html=True)

            g1, g2 = st.columns(2)
            df_ini_view = df_m.copy(); df_ini_view['Nuevo_Slot'] = df_ini_view['Slot_Original']
            with g1: st.plotly_chart(render_fan(df_ini_view, 'Slot_Original', "AS FOUND"), use_container_width=True, key=f"g1_{idx}")
            with g2: st.plotly_chart(render_fan(choice['df'], 'Nuevo_Slot', f"AS LEFT"), use_container_width=True, key=f"g2_{idx}")

            # Tabla de Taller
            df_tab = choice['df'][['ID_Original', 'Peso', 'Slot_Original', 'Nuevo_Slot']].copy()
            df_tab['Acción'] = df_tab.apply(lambda x: "✅ OK" if x['Slot_Original'] == x['Nuevo_Slot'] else f"➔ MOVER AL {int(x['Nuevo_Slot'])}", axis=1)
            df_tab['Compensación'] = ""
            if bolt_w > UMBRAL_EXCELENCIA:
                df_tab.loc[df_tab['Nuevo_Slot'] == bolt_s, 'Compensación'] = f"🔩 BOLT {bolt_w:.2f}g"

            st.table(df_tab.sort_values(by='Slot_Original').style.apply(
                lambda x: ['background-color: #f8d7da' if 'MOVER' in str(v) or 'BOLT' in str(v) else 'background-color: #d4edda' for v in x], axis=1))
            
            fleet_selection[m_name] = {"choice": choice, "df_final": df_tab}

        # EXPORTACIÓN
        def get_xlsx(selections):
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                summary = []
                for m, info in selections.items():
                    summary.append({'Motor': m, 'Vib_Final': info['choice']['v'], 'Movimientos': info['choice']['moves'], 'Bolt': info['choice']['v'], 'Slot': info['choice']['b_slot']})
                pd.DataFrame(summary).to_excel(writer, sheet_name='RESUMEN', index=False)
                for m, info in selections.items():
                    info['df_final'].to_excel(writer, sheet_name=f"TALLER_{m}", index=False)
            return output.getvalue()

        st.sidebar.download_button("📥 DESCARGAR PLAN FINAL", data=get_xlsx(fleet_selection), file_name="Balanceo_V2500_Final.xlsx")

    except Exception as e:
        st.error(f"Error técnico: {e}")
else:
    st.info("Esperando Excel...")
