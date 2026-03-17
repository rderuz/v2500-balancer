import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import io
import math

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="V2500 Balancer DSS - Total Edition", layout="wide")

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
            # Si no hay momento1, usa peso * 16.5 como aproximación técnica
            m1 = row.get('momento1', row.get('peso', 0) * 16.5)
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
        m1_sum = df[df[slot_col] <= 11]['peso'].sum()
        m2_sum = df[df[slot_col] > 11]['peso'].sum()
        diff = round(abs(m1_sum - m2_sum), 2)
        b_slot = 17 if (m1_sum - m2_sum) > 0 else 6
        return diff, diff, b_slot

def render_fan(data, slot_col, titulo, bolt_w=0, bolt_s=0, fijos=[]):
    fig = go.Figure()
    theta = np.linspace(0, 360, 22, endpoint=False)
    colores = []
    for _, row in data.sort_values(by=slot_col).iterrows():
        if fijos and row['slot_original'] in fijos:
            colores.append("#bdc3c7") # Gris para bloqueados
        else:
            if 'nuevo_slot' in row and row['slot_original'] != row['nuevo_slot']:
                colores.append("#e74c3c") # Rojo para movidos
            else:
                colores.append("#2ecc71") # Verde OK
    
    fig.add_trace(go.Barpolar(r=[8]*22, theta=theta, width=[14]*22, marker_color=colores, marker_line_color="white"))
    for i in range(22):
        row = data[data[slot_col] == (i+1)].iloc[0]
        label = f"A{int(row['slot_original'])}"
        fig.add_trace(go.Scatterpolar(r=[6.2], theta=[theta[i]], mode='text', text=[label], 
                                     textfont=dict(size=10, color="black" if fijos and row['slot_original'] in fijos else "white")))
    if bolt_w > 0.05:
        fig.add_trace(go.Scatterpolar(r=[4], theta=[theta[bolt_s-1]], mode='markers+text', marker=dict(symbol="star", size=20, color="#f1c40f"), 
                                     text=[f"{bolt_w}g"], textposition="bottom center"))
    fig.update_layout(title=titulo, polar=dict(bgcolor='white', angularaxis=dict(tickvals=theta, rotation=90, direction="clockwise")), showlegend=False, height=450)
    return fig

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Configuración Global")
    uploaded_file = st.file_uploader("Subir Excel", type=["xlsx"])
    st.divider()
    
    # INTERRUPTOR DE MODO
    modo_parcial = st.checkbox("🛠️ Modo Reemplazo Parcial (Solo 5)")
    slots_a_optimizar = []
    if modo_parcial:
        slots_a_optimizar = st.multiselect("Slots móviles (seleccione 5):", list(range(1, 23)), default=[1,2,3,4,5])
        if len(slots_a_optimizar) != 5:
            st.warning("Seleccione exactamente 5 slots para el modo parcial.")

    metodo_calc = st.selectbox("Método de Análisis:", ["Vectorial (AMM)", "Mitades (Peso)"])
    ITERACIONES = st.number_input("Comprobaciones (Ciclos):", 1000, 100000, 15000, 5000)
    TOLERANCIA = st.slider("Tolerancia Taller (ips)", 0.0, 1.0, 0.20)

# --- PROCESAMIENTO CON MEMORIA ---
if uploaded_file:
    # Generamos ID único incluyendo el modo parcial
    config_id = f"{uploaded_file.name}_{metodo_calc}_{ITERACIONES}_{modo_parcial}_{slots_a_optimizar}"
    
    if "last_config_id" not in st.session_state or st.session_state.last_config_id != config_id:
        st.session_state.last_config_id = config_id
        st.session_state.resultados_motores = {}

        df_raw = pd.read_excel(uploaded_file, engine='openpyxl')
        df_raw.columns = df_raw.columns.str.strip().str.lower()
        
        for m_name in df_raw['motor'].unique():
            df_m = df_raw[df_raw['motor'] == m_name].copy()
            df_m['slot_original'] = df_m['slot'].astype(int)
            df_m['nuevo_slot'] = df_m['slot_original']
            
            v_ini, b_ini, s_ini = get_v2500_metrics(df_m, 'slot_original', metodo_calc)
            
            # Memorias de estrategia
            est_min_vib = {"v": v_ini, "moves": 0, "df": df_m.copy(), "bolt": b_ini, "slot": s_ini}
            est_eficiencia = {"v": v_ini, "moves": 0, "df": df_m.copy(), "bolt": b_ini, "slot": s_ini}
            est_balance = {"v": v_ini, "moves": 0, "df": df_m.copy(), "bolt": b_ini, "slot": s_ini}

            progress_bar = st.progress(0)
            for i in range(ITERACIONES):
                temp = df_m.copy()
                if modo_parcial and len(slots_a_optimizar) == 5:
                    # Mezclamos solo los pesos de los slots elegidos
                    rows_to_mix = temp[temp['slot_original'].isin(slots_a_optimizar)].copy()
                    shuffled_weights = rows_to_mix['peso'].sample(frac=1).values
                    temp.loc[temp['slot_original'].isin(slots_a_optimizar), 'peso'] = shuffled_weights
                else:
                    temp = df_m.sample(frac=1).reset_index(drop=True)
                    temp['nuevo_slot'] = range(1, 23)
                
                vt, bw, bs = get_v2500_metrics(temp, 'nuevo_slot' if not modo_parcial else 'slot_original', metodo_calc)
                mt = len(temp[temp['slot_original'] != temp['nuevo_slot']]) if not modo_parcial else 5
                
                if vt < est_min_vib["v"]: est_min_vib = {"v": vt, "moves": mt, "df": temp.copy(), "bolt": bw, "slot": bs}
                if vt <= TOLERANCIA:
                    if mt < est_eficiencia["moves"] or est_eficiencia["v"] > TOLERANCIA:
                        est_eficiencia = {"v": vt, "moves": mt, "df": temp.copy(), "bolt": bw, "slot": bs}
                if vt < (v_ini * 0.6) and mt <= 12:
                    if vt < est_balance["v"]: est_balance = {"v": vt, "moves": mt, "df": temp.copy(), "bolt": bw, "slot": bs}

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

    # --- RENDERIZADO Y EXPORTACIÓN ---
    plan_excel = {}
    resumen_flota = []

    for m_name, datos in st.session_state.resultados_motores.items():
        st.markdown(f"<div class='motor-header'><h3>📦 MOTOR: {m_name}</h3></div>", unsafe_allow_html=True)
        v_ini, b_ini, s_ini, df_m_ini = datos["ini"]
        
        seleccionada = st.radio(f"Estrategia para {m_name}:", list(datos["estrategias"].keys()), horizontal=True, key=f"sel_{m_name}")
        res = datos["estrategias"][seleccionada]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Vib. Inicial", f"{v_ini:.2f} ips")
        c2.metric("Vib. Objetivo", f"{res['v']:.2f} ips")
        c3.metric("Perno (Bolt)", f"{res['bolt']:.2f} g")
        c4.metric("Movimientos", f"{res['moves']}")

        g1, g2 = st.columns(2)
        with g1: st.plotly_chart(render_fan(df_m_ini, 'slot_original', "ACTUAL"), use_container_width=True, key=f"p1_{m_name}")
        with g2: 
            fijos = [s for s in range(1, 23) if s not in slots_a_optimizar] if modo_parcial else []
            st.plotly_chart(render_fan(res['df'], 'nuevo_slot' if not modo_parcial else 'slot_original', 
                                       "PROPUESTA", res['bolt'], res['slot'], fijos=fijos), 
                            use_container_width=True, key=f"p2_{m_name}")
        
        df_tab = res['df'][['slot_original', 'peso', 'nuevo_slot']].copy()
        df_tab['Acción'] = df_tab.apply(lambda x: "✅ MANTENER" if x['slot_original'] == x['nuevo_slot'] else f"➔ AL {int(x['nuevo_slot'])}", axis=1)
        st.table(df_tab.sort_values(by='slot_original').style.apply(lambda x: ['background-color: #d4edda' if 'MANTENER' in str(v) else 'background-color: #f8d7da' for v in x], axis=1))
        
        # Reporte Excel
        export_df = df_tab.sort_values(by='slot_original').copy()
        export_df['Perno_g'] = ""
        export_df['Slot_Perno'] = ""
        target_slot_col = 'nuevo_slot' if not modo_parcial else 'slot_original'
        export_df.loc[export_df[target_slot_col] == res['slot'], 'Perno_g'] = res['bolt']
        export_df.loc[export_df[target_slot_col] == res['slot'], 'Slot_Perno'] = res['slot']
        plan_excel[m_name] = export_df
        resumen_flota.append({"Motor": m_name, "Vib_Inicial": v_ini, "Vib_Final": res['v'], "Movimientos": res['moves'], "Perno_g": res['bolt'], "Slot_Perno": res['slot']})

    st.divider()
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        pd.DataFrame(resumen_flota).to_excel(writer, sheet_name="RESUMEN", index=False)
        for m, d in plan_excel.items(): d.to_excel(writer, sheet_name=m[:30], index=False)
    st.download_button("📥 DESCARGAR PLAN DE TRABAJO COMPLETO", data=output.getvalue(), file_name="Reporte_V2500_DSS.xlsx")

else:
    st.info("👋 Suba su Excel. Puede elegir entre balanceo de motor completo o re-indexado parcial de 5 álabes.")
