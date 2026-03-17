import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import io
import math

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="V2500 Balancer DSS - Total Fix", layout="wide")

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

def render_fan(data, slot_col, titulo, bolt_w=0, bolt_s=0, fijos=[], es_propuesta=False):
    fig = go.Figure()
    theta = np.linspace(0, 360, 22, endpoint=False)
    colores = []
    
    # Asegurar orden por el slot que se visualiza
    viz_data = data.sort_values(by=slot_col).reset_index()
    
    for _, row in viz_data.iterrows():
        if es_propuesta:
            if row['slot_original'] in fijos: colores.append("#bdc3c7")
            elif row['slot_original'] != row['nuevo_slot']: colores.append("#e74c3c")
            else: colores.append("#2ecc71")
        else:
            colores.append("#2ecc71") # El gráfico inicial siempre es verde (base)
    
    fig.add_trace(go.Barpolar(r=[8]*22, theta=theta, width=[14]*22, marker_color=colores, marker_line_color="white"))
    
    for i in range(22):
        row = data[data[slot_col] == (i+1)].iloc[0]
        label = f"A{int(row['slot_original'])}"
        t_color = "black" if (es_propuesta and row['slot_original'] in fijos) else "white"
        fig.add_trace(go.Scatterpolar(r=[6.2], theta=[theta[i]], mode='text', text=[label], textfont=dict(size=10, color=t_color)))
    
    if bolt_w > 0.05:
        fig.add_trace(go.Scatterpolar(r=[4], theta=[theta[bolt_s-1]], mode='markers+text', marker=dict(symbol="star", size=20, color="#f1c40f"), text=[f"{bolt_w}g"], textposition="bottom center"))
    
    fig.update_layout(title=titulo, polar=dict(bgcolor='white', angularaxis=dict(tickvals=theta, rotation=90, direction="clockwise")), showlegend=False, height=400, margin=dict(t=80, b=30, l=30, r=30))
    return fig

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Parámetros")
    uploaded_file = st.file_uploader("Subir Fichero Excel", type=["xlsx"])
    st.divider()
    slots_moviles = st.multiselect("Slots móviles para optimizar:", options=list(range(1, 23)), default=list(range(1, 23)))
    metodo_calc = st.selectbox("Método de Análisis:", ["Vectorial (AMM)", "Mitades (Peso)"])
    ITERACIONES = st.number_input("Ciclos de Simulación:", 1000, 100000, 15000, 5000)
    TOLERANCIA = st.slider("Tolerancia Objetivo (ips)", 0.0, 1.0, 0.20)

# --- PROCESAMIENTO ---
if uploaded_file and len(slots_moviles) >= 2:
    config_id = f"{uploaded_file.name}_{metodo_calc}_{ITERACIONES}_{slots_moviles}"
    
    if "last_config_id" not in st.session_state or st.session_state.last_config_id != config_id:
        st.session_state.last_config_id = config_id
        st.session_state.resultados_motores = {}
        df_raw = pd.read_excel(uploaded_file, engine='openpyxl')
        df_raw.columns = df_raw.columns.str.strip().str.lower()
        
        for m_name in df_raw['motor'].unique():
            df_m = df_raw[df_raw['motor'] == m_name].copy()
            df_m['slot_original'] = df_m['slot'].astype(int)
            v_ini, b_ini, s_ini = get_v2500_metrics(df_m, 'slot_original', metodo_calc)
            
            mems = {k: {"v": v_ini, "moves": 0, "df": df_m.copy(), "bolt": b_ini, "slot": s_ini} for k in ["vib", "efi", "bal"]}
            fijos = [s for s in range(1, 23) if s not in slots_moviles]
            
            pb = st.progress(0)
            for i in range(ITERACIONES):
                temp = df_m.copy()
                mov_df = temp[temp['slot_original'].isin(slots_moviles)].copy()
                shuf = mov_df.sample(frac=1).reset_index(drop=True)
                shuf['nuevo_slot'] = mov_df['slot_original'].values
                fij_df = temp[temp['slot_original'].isin(fijos)].copy()
                fij_df['nuevo_slot'] = fij_df['slot_original']
                comb = pd.concat([shuf, fij_df]).sort_values(by='nuevo_slot')
                
                vt, bw, bs = get_v2500_metrics(comb, 'nuevo_slot', metodo_calc)
                mt = len(shuf[shuf['slot_original'] != shuf['nuevo_slot']])
                
                if vt < mems["vib"]["v"]: mems["vib"] = {"v": vt, "moves": mt, "df": comb.copy(), "bolt": bw, "slot": bs}
                if vt <= TOLERANCIA:
                    if mt < mems["efi"]["moves"] or mems["efi"]["v"] > TOLERANCIA:
                        mems["efi"] = {"v": vt, "moves": mt, "df": comb.copy(), "bolt": bw, "slot": bs}
                if vt < (v_ini * 0.5) and mt <= 12:
                    if vt < mems["bal"]["v"]: mems["bal"] = {"v": vt, "moves": mt, "df": comb.copy(), "bolt": bw, "slot": bs}
                if i % 3000 == 0: pb.progress(i / ITERACIONES)
            pb.empty()
            st.session_state.resultados_motores[m_name] = {
                "ini": (v_ini, b_ini, s_ini, df_m, fijos),
                "estrategias": {"🚀 Mínima Vibración": mems["vib"], "⚖️ Eficiencia Operativa": mems["efi"], "🛠️ Balanceado Moderado": mems["bal"]}
            }

    # --- RENDERIZADO ---
    plan_taller = {}
    resumen = []
    for m_name, datos in st.session_state.resultados_motores.items():
        st.markdown(f"<div class='motor-header'><h3>📦 MOTOR: {m_name}</h3></div>", unsafe_allow_html=True)
        v_ini, b_ini, s_ini, df_m_ini, fijos = datos["ini"]
        sel = st.radio(f"Seleccionar Plan:", list(datos["estrategias"].keys()), horizontal=True, key=f"sel_{m_name}")
        res = datos["estrategias"][sel]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Vib. Inicial", f"{v_ini:.2f}")
        c2.metric("Vib. Final", f"{res['v']:.2f}")
        c3.metric("Perno", f"{res['bolt']:.2f}g")
        c4.metric("Movimientos", f"{res['moves']}")

        g1, g2 = st.columns(2)
        with g1: st.plotly_chart(render_fan(df_m_ini, 'slot_original', "ACTUAL (As Found)"), use_container_width=True, key=f"gra1_{m_name}")
        with g2: st.plotly_chart(render_fan(res['df'], 'nuevo_slot', "PROPUESTA (As Left)", res['bolt'], res['slot'], fijos, es_propuesta=True), use_container_width=True, key=f"gra2_{m_name}")
        
        # TABLA REFORZADA
        df_tab = res['df'][['slot_original', 'peso', 'nuevo_slot']].sort_values(by='slot_original').reset_index(drop=True)
        df_tab['Acción'] = df_tab.apply(lambda x: "🔘 BLOQUEADO" if x['slot_original'] in fijos else 
                                       ("✅ MANTENER" if x['slot_original'] == x['nuevo_slot'] else f"➔ AL {int(x['nuevo_slot'])}"), axis=1)
        
        st.dataframe(df_tab, use_container_width=True)
        
        # Excel
        exp = df_tab.copy()
        exp['Perno_g'] = ""
        exp.loc[exp['nuevo_slot'] == res['slot'], 'Perno_g'] = res['bolt']
        plan_taller[m_name] = exp
        resumen.append({"Motor": m_name, "Vib_Ini": v_ini, "Vib_Fin": res['v'], "Perno_g": res['bolt'], "Slot": res['slot'], "Moves": res['moves']})

    st.divider()
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        pd.DataFrame(resumen).to_excel(writer, sheet_name="RESUMEN", index=False)
        for m, d in plan_taller.items(): d.to_excel(writer, sheet_name=m[:30], index=False)
    st.download_button("📥 DESCARGAR PLAN", data=output.getvalue(), file_name="Plan_V2500_Total.xlsx")
else:
    st.info("Suba el Excel para comenzar.")
