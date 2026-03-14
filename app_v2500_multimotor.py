import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
import io
import random

# 1. CONFIGURACIÓN
st.set_page_config(page_title="V2500 Fleet Balancer", layout="wide")

st.markdown("""
    <style>
    .stMetric { border-radius: 10px; border: 1px solid #58a6ff; background: rgba(88,166,255,0.05); padding: 15px; }
    .bolt-box { border: 2px solid #ff4b4b; padding: 20px; border-radius: 10px; background: rgba(255,75,75,0.05); }
    [data-testid="stExpander"] { border: 1px solid #58a6ff; border-radius: 10px; margin-bottom: 20px; }
    </style>
    """, unsafe_allow_html=True)

st.title("🚀 V2500 Aero-Master: Gestión de Flota Multimotor")

with st.sidebar:
    st.header("📋 Carga de Flota")
    tecnico = st.text_input("Técnico Responsable", "Certificado Nivel II")
    st.divider()
    uploaded_file = st.file_uploader("Cargar Excel Multimotor", type=["xlsx", "csv"])
    st.info("Asegúrese de que el Excel tiene la columna 'Motor'.")

# --- FUNCIONES DE ALTA VISIBILIDAD ---
def calc_stats(df, slot_col):
    m1 = df[df[slot_col] <= 11]['Peso'].sum()
    m2 = df[df[slot_col] > 11]['Peso'].sum()
    diff = m1 - m2
    return abs(diff), diff

def render_clean_fan(data, slot_col, titulo, bolt_w=0, bolt_s=0):
    fig = go.Figure()
    theta = np.linspace(0, 360, 22, endpoint=False)
    # Cuerpo del Fan
    fig.add_trace(go.Barpolar(r=[8]*22, theta=theta, width=[14]*22, marker_color="#455a64", marker_line_color="white", marker_line_width=2))
    # Spinner
    fig.add_trace(go.Scatterpolar(r=[0], theta=[0], mode='markers', marker=dict(size=60, color="#263238", line=dict(width=2, color="#58a6ff"))))
    
    # IDs de Álabes (Visibilidad Máxima)
    for i in range(22):
        pieza = data[data[slot_col] == (i+1)].iloc[0]
        fig.add_trace(go.Scatterpolar(r=[6.5], theta=[theta[i]], mode='text', text=[f"<b>{pieza['ID_Original']}</b>"], textfont=dict(size=12, color="white")))

    if bolt_w > 0.01:
        fig.add_trace(go.Scatterpolar(r=[4.5], theta=[theta[bolt_s-1]], mode='markers+text',
                                     marker=dict(symbol="star", size=25, color="#ffeb3b", line=dict(width=2, color="red")),
                                     text=[f"<b>BOLT {bolt_w:.2f}</b>"], textposition="bottom center", textfont=dict(size=13, color="#ff5252")))

    fig.update_layout(title=dict(text=f"<b>{titulo}</b>", font=dict(size=18, color="#58a6ff")),
                      polar=dict(bgcolor='rgba(0,0,0,0)', angularaxis=dict(tickvals=theta, ticktext=[f"<b>{i+1}</b>" for i in range(22)], rotation=90, direction="clockwise", gridcolor="#cfd8dc")),
                      showlegend=False, height=550, margin=dict(t=50, b=30, l=30, r=30))
    return fig

# --- PROCESAMIENTO MULTIMOTOR ---
if uploaded_file:
    df_full = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
    df_full.columns = [c.strip().capitalize() for c in df_full.columns]
    
    if 'Motor' not in df_full.columns:
        st.error("Error Crítico: No existe la columna 'Motor' en el archivo cargado.")
    else:
        lista_motores = df_full['Motor'].unique()
        resultados_excel = []
        
        for idx, m_name in enumerate(lista_motores):
            with st.expander(f"📦 ANÁLISIS MOTOR: {m_name}", expanded=True):
                # Preparación de datos
                df_m = df_full[df_full['Motor'] == m_name].copy()
                df_m['ID_Original'] = [f"Á{int(s)}" for s in df_m['Slot']]
                df_m['Slot_Original'] = df_m['Slot'].astype(int)
                
                v_ini, d_ini = calc_stats(df_m, 'Slot_Original')

                # Optimización Consistente (Monte Carlo)
                best_v = v_ini
                best_df = df_m.copy()
                best_df['Nuevo_Slot'] = df_m['Slot_Original']
                
                with st.empty():
                    st.caption(f"Calculando solución óptima para {m_name}...")
                    for _ in range(10000):
                        temp_df = df_m.sample(frac=1).reset_index(drop=True)
                        temp_df['Test_Slot'] = range(1, 23)
                        v_test, d_test = calc_stats(temp_df, 'Test_Slot')
                        if v_test < best_v:
                            best_v = v_test
                            best_df = temp_df.copy()
                            best_df['Nuevo_Slot'] = best_df['Test_Slot']
                            best_d = d_test

                if best_v < (v_ini - 0.01):
                    df_final = best_df; v_final = best_v; d_final = best_d; usa_prop = True
                else:
                    df_final = df_m.copy(); df_final['Nuevo_Slot'] = df_final['Slot_Original']; v_final = v_ini; d_final = d_ini; usa_prop = False

                bolt_w = v_final
                bolt_s = 17 if d_final > 0 else 6

                # --- INTERFAZ DEL MOTOR ---
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Vib. Inicial", f"{v_ini:.2f}")
                m2.metric("Vib. Optimizada", f"{v_final:.2f}", delta=f"-{v_ini-v_final:.2f}" if usa_prop else None)
                m3.metric("Bolt Masa", f"{bolt_w:.2f}")
                m4.metric("Bolt Slot", f"{bolt_s}")

                g1, g2 = st.columns(2)
                # AQUÍ ESTÁ LA SOLUCIÓN: Usamos keys únicas basadas en el nombre del motor e índice
                with g1: st.plotly_chart(render_clean_fan(df_m, 'Slot_Original', f"{m_name} - AS FOUND"), 
                                         use_container_width=True, key=f"plot_ini_{idx}")
                with g2: st.plotly_chart(render_clean_fan(df_final, 'Nuevo_Slot', f"{m_name} - AS LEFT", bolt_w, bolt_s), 
                                         use_container_width=True, key=f"plot_fin_{idx}")
                
                df_final['Acción'] = df_final.apply(lambda x: "✔️ MANTENER" if x['Slot_Original'] == x['Nuevo_Slot'] else f"➡️ MOVER AL {int(x['Nuevo_Slot'])}", axis=1)
                st.dataframe(df_final[['ID_Original', 'Peso', 'Slot_Original', 'Nuevo_Slot', 'Acción']].sort_values(by='Slot_Original'), use_container_width=True)
                
                resultados_excel.append({'Motor': m_name, 'Ini': v_ini, 'Fin': v_final, 'Bolt': bolt_w, 'Slot': bolt_s, 'Data': df_final})

        # --- EXPORTACIÓN ---
        def download_fleet_report(res_list):
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                # Resumen de todos los motores
                summary = pd.DataFrame([{'Motor': r['Motor'], 'Vib_Inicial': r['Ini'], 'Vib_Optimizado': r['Fin'], 'Bolt_Peso': r['Bolt'], 'Bolt_Slot': r['Slot']} for r in res_list])
                summary.to_excel(writer, sheet_name='RESUMEN_FLOTA', index=False)
                # Hoja individual por motor
                for r in res_list:
                    r['Data'][['ID_Original', 'Peso', 'Slot_Original', 'Nuevo_Slot', 'Acción']].to_excel(writer, sheet_name=f"Steps_{r['Motor']}", index=False)
            return output.getvalue()

        st.sidebar.divider()
        st.sidebar.download_button("📥 DESCARGAR INFORME DE FLOTA", data=download_fleet_report(resultados_excel), file_name="Reporte_V2500_Flota.xlsx")

else:
    st.info("Cargue un Excel con la columna 'Motor' para procesar múltiples unidades simultáneamente.")