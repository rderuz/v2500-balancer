import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import io
import math

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="V2500 Balancer Enterprise", layout="wide")

st.markdown("""
    <style>
    .stMetric { border: 2px solid #58a6ff; background: #f0f7ff; padding: 10px; border-radius: 8px; }
    .motor-header { background-color: #1e3a8a; color: white; padding: 10px; border-radius: 5px; margin-top: 25px; }
    .bolt-info { background-color: #fff5f5; border-left: 5px solid #ff4b4b; padding: 15px; margin-top: 10px; color: #c53030; font-weight: bold; }
    .info-trim { background-color: #e3f2fd; border-left: 5px solid #2196f3; padding: 15px; margin-top: 10px; color: #0d47a1; font-weight: bold; }
    .excelencia { border: 2px solid #2ecc71; background: #e8f5e9; padding: 15px; border-radius: 10px; color: #2e7d32; text-align: center; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- FUNCIONES DE SOPORTE ---
def generar_plantilla():
    data = []
    pesos = [155.2, 148.5, 152.1, 149.8, 154.3, 147.9, 150.0, 153.6, 149.1, 151.4, 156.0, 
            153.0, 156.8, 151.4, 153.6, 152.1, 148.8, 155.2, 146.2, 148.5, 149.6, 148.3]
    for i, p in enumerate(pesos):
        data.append(['M1', i+1, p, round(p*16.5, 2), round(p*0.8, 2), round(p*0.3, 2)])
    return pd.DataFrame(data, columns=['Motor', 'Slot', 'Peso', 'Momento1', 'Momento2', 'Momento3'])

def get_v2500_metrics(df, slot_col, metodo):
    if "Vectorial" in metodo:
        res_x, res_y, RADIO_CONV = 0.0, 0.0, 165.0 
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
    colores = ["#e74c3c" if row['Slot_Original'] != row['Nuevo_Slot'] else "#2ecc71" for _, row in data.sort_values(by=slot_col).iterrows()]
    fig.add_trace(go.Barpolar(r=[8]*22, theta=theta, width=[14]*22, marker_color=colores, marker_line_color="white", marker_line_width=1.5))
    for i in range(22):
        row = data[data[slot_col] == (i+1)].iloc[0]
        fig.add_trace(go.Scatterpolar(r=[6.2], theta=[theta[i]], mode='text', text=[f"A{int(row['Slot_Original'])}"], textfont=dict(size=10, color="white")))
    if bolt_w > 0.10:
        fig.add_trace(go.Scatterpolar(r=[4], theta=[theta[bolt_s-1]], mode='markers+text', marker=dict(symbol="star", size=20, color="#f1c40f"), text=[f"{bolt_w}g"], textposition="bottom center", textfont=dict(size=11, color="red")))
    fig.update_layout(title=titulo, polar=dict(bgcolor='white', angularaxis=dict(tickvals=theta, rotation=90, direction="clockwise")), showlegend=False, height=450, margin=dict(t=80, b=30, l=30, r=30))
    return fig

# --- SIDEBAR ---
with st.sidebar:
    st.header("📂 Gestión de Datos")
    # Descarga de Plantilla
    tmp_df = generar_plantilla()
    output_tmp = io.BytesIO()
    with pd.ExcelWriter(output_tmp, engine='openpyxl') as writer:
        tmp_df.to_excel(writer, index=False)
    st.download_button("📥 Descargar Plantilla Excel", data=output_tmp.getvalue(), file_name="Plantilla_V2500_Momentos.xlsx")
    
    uploaded_file = st.file_uploader("Subir Fichero de Pesos", type=["xlsx"])
    st.divider()
    
    st.header("⚙️ Configuración del Cálculo")
    metodo_calc = st.selectbox("Método de Análisis:", ["Vectorial (Precisión AMM)", "Mitades (Peso Estático)"])
    ITERACIONES = st.number_input("Número de Iteraciones (Profundidad):", min_value=1000, max_value=100000, value=15000, step=5000)
    TOLERANCIA = st.slider("Tolerancia de Aceptación (ips)", 0.0, 1.0, 0.20)

# --- PROCESAMIENTO PRINCIPAL ---
if uploaded_file:
    df_full = pd.read_excel(uploaded_file, engine='openpyxl')
    df_full.columns = [c.strip().capitalize() for c in df_full.columns]
    
    all_results_for_excel = {}

    for idx, m_name in enumerate(df_full['Motor'].unique()):
        st.markdown(f"<div class='motor-header'><h3>📦 MOTOR: {m_name}</h3></div>", unsafe_allow_html=True)
        df_m = df_full[df_full['Motor'] == m_name].copy()
        df_m['Slot_Original'] = df_m['Slot'].astype(int)
        df_m['Nuevo_Slot'] = df_m['Slot_Original']
        
        v_ini, b_w_ini, b_s_ini = get_v2500_metrics(df_m, 'Slot_Original', metodo_calc)
        
        # Lógica de Decisión Jerárquica
        if v_ini <= TOLERANCIA:
            best = {"v": v_ini, "bolt": b_w_ini, "slot": b_s_ini, "df": df_m.copy(), "moves": 0}
            msg = f"✅ ESTADO ACTUAL ÓPTIMO ({v_ini} ips). No se requiere re-indexado."
            color_msg = "info-trim"
        else:
            best = {"v": v_ini, "bolt": b_w_ini, "slot": b_s_ini, "df": df_m.copy(), "moves": 0}
            bar = st.progress(0)
            for i in range(ITERACIONES):
                temp = df_m.sample(frac=1).reset_index(drop=True)
                temp['Nuevo_Slot'] = range(1, 23)
                vt, bw, bs = get_v2500_metrics(temp, 'Nuevo_Slot', metodo_calc)
                mt = len(temp[temp['Slot_Original'] != temp['Nuevo_Slot']])
                # Filtro de mejora significativa (mínimo 0.05 ips de ganancia para mover álabes)
                if vt < (best["v"] - 0.05):
                    best = {"v": vt, "bolt": bw, "slot": bs, "df": temp.copy(), "moves": mt}
                if i % 2000 == 0: bar.progress(i / ITERACIONES)
            bar.empty()
            msg = f"➔ RE-INDEXADO SUGERIDO: Mejora de {v_ini} a {best['v']} ips."
            color_msg = "alert-bolt"

        st.markdown(f"<div class='{color_msg}'>{msg}</div>", unsafe_allow_html=True)

        # MÉTRICAS DE TRAZABILIDAD
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("1. Vib. Inicial", f"{v_ini:.2f} ips")
        c2.metric("2. Vib. tras Movimientos", f"{best['v']:.2f} ips")
        c3.metric("3. Perno Propuesto", f"{best['bolt']:.2f} g")
        v_final_teorica = 0.00 if best['bolt'] > 0.05 else best['v']
        c4.metric("4. Vib. Final (Teórica)", f"{v_final_teorica:.2f} ips")

        # GRÁFICOS
        g1, g2 = st.columns(2)
        with g1: st.plotly_chart(render_fan(df_m, 'Slot_Original', "CONFIGURACIÓN INICIAL (As Found)"), use_container_width=True, key=f"v1_{idx}")
        with g2: st.plotly_chart(render_fan(best['df'], 'Nuevo_Slot', "CONFIGURACIÓN FINAL (As Left)", best['bolt'], best['slot']), use_container_width=True, key=f"v2_{idx}")
        
        # TABLA DE TALLER
        df_tab = best['df'][['Slot_Original', 'Peso', 'Nuevo_Slot']].copy()
        df_tab['Acción'] = df_tab.apply(lambda x: "✅ MANTENER" if x['Slot_Original'] == x['Nuevo_Slot'] else f"➔ MOVER AL {int(x['Nuevo_Slot'])}", axis=1)
        st.table(df_tab.sort_values(by='Slot_Original').style.apply(lambda x: ['background-color: #d4edda' if 'MANTENER' in str(v) else 'background-color: #f8d7da' for v in x], axis=1))
        
        all_results_for_excel[m_name] = df_tab

    # BOTÓN DE EXPORTACIÓN FINAL
    st.divider()
    if all_results_for_excel:
        output_final = io.BytesIO()
        with pd.ExcelWriter(output_final, engine='openpyxl') as writer:
            for motor, df_res in all_results_for_excel.items():
                df_res.to_excel(writer, sheet_name=f"Workshop_Plan_{motor}", index=False)
        st.download_button("📥 DESCARGAR PLAN DE TALLER FINAL (EXCEL)", data=output_final.getvalue(), file_name="V2500_Workshop_Execution_Plan.xlsx")

else:
    st.info("👋 Bienvenida/o. Por favor, cargue el fichero Excel para iniciar el análisis de balanceo dinámico.")
