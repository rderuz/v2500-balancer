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

# --- NÚCLEO TÉCNICO ---
def get_v2500_metrics(df, slot_col, metodo):
    RADIO_CONV = 165.0 
    if "Vectorial" in metodo:
        res_x, res_y = 0.0, 0.0
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
    colores = []
    for _, row in data.sort_values(by=slot_col).iterrows():
        if 'Nuevo_Slot' in row and 'Slot_Original' in row:
            colores.append("#e74c3c" if row['Slot_Original'] != row['Nuevo_Slot'] else "#2ecc71")
        else:
            colores.append("#2ecc71")
    
    fig.add_trace(go.Barpolar(r=[8]*22, theta=theta, width=[14]*22, marker_color=colores, marker_line_color="white"))
    for i in range(22):
        row = data[data[slot_col] == (i+1)].iloc[0]
        label = f"A{int(row['Slot_Original'])}" if 'Slot_Original' in row else f"A{i+1}"
        fig.add_trace(go.Scatterpolar(r=[6.2], theta=[theta[i]], mode='text', text=[label], textfont=dict(size=10, color="white")))
    if bolt_w > 0.05:
        fig.add_trace(go.Scatterpolar(r=[4], theta=[theta[bolt_s-1]], mode='markers+text', marker=dict(symbol="star", size=20, color="#f1c40f"), text=[f"{bolt_w}g"], textposition="bottom center"))
    fig.update_layout(title=titulo, polar=dict(bgcolor='white', angularaxis=dict(tickvals=theta, rotation=90, direction="clockwise")), showlegend=False, height=450)
    return fig

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Configuración")
    uploaded_file = st.file_uploader("Subir Excel", type=["xlsx"])
    st.divider()
    metodo_calc = st.selectbox("Método de Análisis:", ["Vectorial (AMM)", "Mitades (Peso)"])
    ITERACIONES = st.number_input("Comprobaciones (Ciclos):", 1000, 100000, 15000, 5000)
    TOLERANCIA = st.slider("Tolerancia Taller (ips)", 0.0, 1.0, 0.20)

# --- LÓGICA DE MEMORIA (SESSION STATE) ---
if uploaded_file:
    config_id = f"{uploaded_file.name}_{metodo_calc}_{ITERACIONES}"
    
    if "last_config_id" not in st.session_state or st.session_state.last_config_id != config_id:
        st.session_state.last_config_id = config_id
        st.session_state.resultados_motores = {}

        df_full = pd.read_excel(uploaded_file, engine='openpyxl')
        df_full.columns = [c.strip().capitalize() for c in df_full.columns]
        
        for m_name in df_full['Motor'].unique():
            df_m = df_full[df_full['Motor'] == m_name].copy()
            df_m['Slot_Original'] = df_m['Slot'].astype(int)
            df_m['Nuevo_Slot'] = df_m['Slot_Original']
            
            v_ini, b_ini, s_ini = get_v2500_metrics(df_m, 'Slot_Original', metodo_calc)
            
            est_min_vib = {"v": v_ini, "moves": 0, "df": df_m.copy(), "bolt": b_ini, "slot": s_ini}
            est_eficiencia = {"v": v_ini, "moves": 0, "df": df_m.copy(), "bolt": b_ini, "slot": s_ini}
            est_balance = {"v": v_ini, "moves": 0, "df": df_m.copy(), "bolt": b_ini, "slot": s_ini}

            progress_bar = st.progress(0)
            for i in range(ITERACIONES):
                temp = df_m.sample(frac=1).reset_index(drop=True)
                temp['Nuevo_Slot'] = range(1, 23)
                vt, bw, bs = get_v2500_metrics(temp, 'Nuevo_Slot', metodo_calc)
                mt = len(temp[temp['Slot_Original'] != temp['Nuevo_Slot']])
                
                if vt < est_min_vib["v"]:
                    est_min_vib = {"v": vt, "moves": mt, "df": temp.copy(), "bolt": bw, "slot": bs}
                if vt <= TOLERANCIA:
                    if mt < est_eficiencia["moves"] or est_eficiencia["v"] > TOLERANCIA:
                        est_eficiencia = {"v": vt, "moves": mt, "df": temp.copy(), "bolt": bw, "slot": bs}
                if vt < (v_ini * 0.6) and mt <= 10:
                    if vt < est_balance["v"]:
                        est_balance = {"v": vt, "moves": mt, "df": temp.copy(), "bolt": bw, "slot": bs}
                if i % 3000 == 0: progress_bar.progress(i / ITERACIONES)
            
            progress_bar.empty()
            st.session_state.resultados_motores[m_name] = {
                "ini": (v_ini, b_ini, s_ini, df_m),
                "estrategias": {
                    "🚀 Mínima Vibración": est_min_vib,
                    "⚖️ Eficiencia Operativa": est_eficiencia,
                    "🛠️ Balanceado Moderado": est_balance
                }
            }

    # --- RENDERIZADO E INSTANTANEIDAD ---
    plan_taller_hojas = {}
    resumen_motores = []

    for m_name, datos in st.session_state.resultados_motores.items():
        st.markdown(f"<div class='motor-header'><h3>📦 MOTOR: {m_name}</h3></div>", unsafe_allow_html=True)
        v_ini, b_ini, s_ini, df_m_ini = datos["ini"]
        
        seleccionada = st.radio(f"Estrategia Seleccionada para {m_name}:", list(datos["estrategias"].keys()), horizontal=True, key=f"sel_{m_name}")
        res = datos["estrategias"][seleccionada]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Vib. Inicial", f"{v_ini:.2f} ips")
        c2.metric("Vib. tras Movimientos", f"{res['v']:.2f} ips")
        c3.metric("Perno (Bolt)", f"{res['bolt']:.2f} g")
        c4.metric("Slot Perno", f"{res['slot']}")

        g1, g2 = st.columns(2)
        with g1: st.plotly_chart(render_fan(df_m_ini, 'Slot_Original', "AS FOUND"), use_container_width=True, key=f"p1_{m_name}")
        with g2: st.plotly_chart(render_fan(res['df'], 'Nuevo_Slot', "AS LEFT", res['bolt'], res['slot']), use_container_width=True, key=f"p2_{m_name}")
        
        df_tab = res['df'][['Slot_Original', 'Peso', 'Nuevo_Slot']].copy()
        df_tab['Acción'] = df_tab.apply(lambda x: "✅ MANTENER" if x['Slot_Original'] == x['Nuevo_Slot'] else f"➔ AL {int(x['Nuevo_Slot'])}", axis=1)
        st.table(df_tab.sort_values(by='Slot_Original').style.apply(lambda x: ['background-color: #d4edda' if 'MANTENER' in str(v) else 'background-color: #f8d7da' for v in x], axis=1))
        
        # PREPARAR DATOS PARA EL EXCEL (Incluyendo pernos)
        export_df = df_tab.sort_values(by='Slot_Original').copy()
        export_df['Perno_A_Instalar_g'] = res['bolt']
        export_df['Slot_Perno'] = res['slot']
        plan_taller_hojas[m_name] = export_df
        
        resumen_motores.append({
            "Motor": m_name, "Vib_Inicial": v_ini, "Vib_Final": res['v'], 
            "Peso_Perno_g": res['bolt'], "Slot_Perno": res['slot'], "Movimientos": res['moves']
        })

    st.divider()
    # EXPORTACIÓN MEJORADA
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        pd.DataFrame(resumen_motores).to_excel(writer, sheet_name="RESUMEN_FLOTA", index=False)
        for m, d in plan_taller_hojas.items():
            d.to_excel(writer, sheet_name=f"DETALLE_{m}", index=False)
    st.download_button("📥 DESCARGAR PLAN DE TALLER CON PERNOS (EXCEL)", data=output.getvalue(), file_name="Plan_Mantenimiento_V2500.xlsx")

else:
    st.info("Cargue el Excel para generar el plan de taller con datos de pernos.")
