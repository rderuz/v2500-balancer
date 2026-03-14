import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
import io
import random

# 1. CONFIGURACIÓN E INTERFAZ
st.set_page_config(page_title="V2500 Industrial Balancer", layout="wide")

st.markdown("""
    <style>
    .stMetric { border-radius: 10px; border: 1px solid #58a6ff; background: rgba(88,166,255,0.05); padding: 15px; }
    .bolt-box { border: 2px solid #ff4b4b; padding: 20px; border-radius: 10px; background: rgba(255,75,75,0.05); }
    .stExpander { border: 1px solid #58a6ff; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

st.title("🚀 V2500 Aero-Master: Gestión de Flotas")

with st.sidebar:
    st.header("📋 Carga de Datos")
    tecnico = st.text_input("Técnico Responsable", "")
    st.divider()
    uploaded_file = st.file_uploader("Cargar Excel Multimotor", type=["xlsx", "csv"])
    st.info("Asegúrate de que el Excel tiene las columnas: 'Motor', 'Slot', 'Peso'.")

# --- FUNCIONES DE ALTA VISIBILIDAD ---
def calc_stats(df, slot_col):
    m1 = df[df[slot_col] <= 11]['Peso'].sum()
    m2 = df[df[slot_col] > 11]['Peso'].sum()
    diff = m1 - m2
    return abs(diff), diff

def render_industrial_fan(data, slot_col, titulo, bolt_w=0, bolt_s=0, key_suffix=""):
    fig = go.Figure()
    # 22 posiciones fijas
    theta = np.linspace(0, 360, 22, endpoint=False)
    
    # REPRESENTACIÓN DE ÁLABES (Rectángulos limpios de alto contraste)
    fig.add_trace(go.Barpolar(
        r=[8]*22, 
        theta=theta, 
        width=[14]*22, 
        marker_color="#1f77b4", # Azul sólido
        marker_line_color="white",
        marker_line_width=2,
        hoverinfo="none"
    ))
    
    # NÚMEROS DE ÁLABE (Gigantes y centrados)
    for i in range(22):
        pieza = data[data[slot_col] == (i+1)].iloc[0]
        fig.add_trace(go.Scatterpolar(
            r=[6.0], # Un poco más adentro para que no choque con los bordes
            theta=[theta[i]], 
            mode='text', 
            text=[f"<b>{pieza['ID_Original']}</b>"], 
            textfont=dict(size=16, color="white") # MÁS GRANDE
        ))

    # MARCADOR DEL BOLT
    if bolt_w > 0.01:
        fig.add_trace(go.Scatterpolar(
            r=[4], theta=[theta[bolt_s-1]], mode='markers+text',
            marker=dict(symbol="star", size=30, color="#f1c40f", line=dict(width=2, color="red")),
            text=[f"<b>BOLT {bolt_w:.2f}</b>"], 
            textposition="bottom center", 
            textfont=dict(size=14, color="red")
        ))

    fig.update_layout(
        title=dict(text=f"<b>{titulo}</b>", font=dict(size=24, color="#1f77b4")),
        polar=dict(
            bgcolor='white', # Fondo blanco para máxima claridad
            angularaxis=dict(
                tickvals=theta, 
                ticktext=[f"<b>{i+1}</b>" for i in range(22)], # NÚMERO DE SLOT
                rotation=90, 
                direction="clockwise",
                gridcolor="#d3d3d3",
                tickfont=dict(size=18, color="black", family="Arial Black")
            ),
            radialaxis=dict(visible=False, range=[0, 10])
        ),
        showlegend=False, 
        height=700, 
        margin=dict(t=80, b=80, l=80, r=80)
    )
    return fig

# --- PROCESAMIENTO ---
if uploaded_file:
    try:
        # Blindaje contra errores de lectura
        if uploaded_file.name.endswith('.csv'):
            df_full = pd.read_csv(uploaded_file)
        else:
            df_full = pd.read_excel(uploaded_file, engine='openpyxl')
            
        df_full.columns = [c.strip().capitalize() for c in df_full.columns]
        motores = df_full['Motor'].unique()
        res_excel = []
        
        for idx, m_name in enumerate(motores):
            with st.expander(f"📦 ANALIZANDO MOTOR: {m_name}", expanded=True):
                df_m = df_full[df_full['Motor'] == m_name].copy()
                df_m['ID_Original'] = [f"Á{int(s)}" for s in df_m['Slot']]
                df_m['Slot_Original'] = df_m['Slot'].astype(int)
                
                v_ini, d_ini = calc_stats(df_m, 'Slot_Original')

                # OPTIMIZACIÓN GLOBAL (Monte Carlo 10k) - Garantiza consistencia
                best_v = v_ini
                best_df = df_m.copy()
                pesos_base = df_m.copy()
                
                for _ in range(10000):
                    temp_df = pesos_base.sample(frac=1).reset_index(drop=True)
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

                # MÉTRICAS
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Vib. Inicial", f"{v_ini:.2f}")
                c2.metric("Vib. Optimizada", f"{v_final:.2f}")
                c3.metric("Bolt Masa", f"{bolt_w:.2f}")
                c4.metric("Bolt Slot", f"{bolt_s}")

                # GRÁFICOS
                g1, g2 = st.columns(2)
                with g1: st.plotly_chart(render_industrial_fan(df_m, 'Slot_Original', "AS FOUND"), use_container_width=True, key=f"ini_{idx}")
                with g2: st.plotly_chart(render_industrial_fan(df_final, 'Nuevo_Slot', "AS LEFT", bolt_w, bolt_s), use_container_width=True, key=f"fin_{idx}")
                
                # TABLA DE MOVIMIENTOS
                df_final['Acción'] = df_final.apply(lambda x: "MANTENER" if x['Slot_Original'] == x['Nuevo_Slot'] else f"MOVER AL {int(x['Nuevo_Slot'])}", axis=1)
                st.dataframe(df_final[['ID_Original', 'Peso', 'Slot_Original', 'Nuevo_Slot', 'Acción']].sort_values(by='Slot_Original'), use_container_width=True)
                
                res_excel.append({'Motor': m_name, 'Data': df_final, 'v_ini': v_ini, 'v_fin': v_final, 'bolt': bolt_w, 'slot': bolt_s})

        # EXPORTACIÓN
        def get_xlsx(data_list):
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                resumen = pd.DataFrame([{'Motor': d['Motor'], 'Vib_Ini': d['v_ini'], 'Vib_Fin': d['v_fin'], 'Bolt': d['bolt'], 'Slot': d['slot']} for d in data_list])
                resumen.to_excel(writer, sheet_name='Resumen_Flota', index=False)
                for d in data_list:
                    d['Data'][['ID_Original', 'Peso', 'Slot_Original', 'Nuevo_Slot', 'Acción']].to_excel(writer, sheet_name=f"Motor_{d['Motor']}", index=False)
            return output.getvalue()

        st.sidebar.divider()
        st.sidebar.download_button("📥 DESCARGAR EXCEL DE FLOTA", data=get_xlsx(res_excel), file_name="Flota_V2500.xlsx")

    except Exception as e:
        st.error(f"Error de lectura: {e}")
        st.info("Recomendación: Asegúrate de que el Excel no esté protegido y que las columnas se llamen 'Motor', 'Slot' y 'Peso'.")
else:
    st.info("Cargue un Excel para iniciar el análisis multimotor de alta visibilidad.")