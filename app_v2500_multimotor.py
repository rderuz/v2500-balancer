import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
import io
import random

# 1. CONFIGURACIÓN Y ESTILO
st.set_page_config(page_title="V2500 Master Fan Balancer", layout="wide")

st.markdown("""
    <style>
    .stMetric { border-radius: 12px; border: 1px solid #58a6ff; background: white; padding: 15px; box-shadow: 2px 2px 5px rgba(0,0,0,0.05); }
    .bolt-card { border: 3px solid #ff4b4b; padding: 20px; border-radius: 10px; background: #fff5f5; text-align: center; }
    [data-testid="stExpander"] { border: 1px solid #58a6ff; border-radius: 10px; margin-bottom: 20px; background-color: #fdfdfd; }
    </style>
    """, unsafe_allow_html=True)

st.title("⚙️ V2500 Aero-Master: Gestión Circular de Flotas")

with st.sidebar:
    st.header("🛂 Panel de Control")
    tecnico = st.text_input("Técnico Certificado", "Nivel II")
    st.divider()
    uploaded_file = st.file_uploader("Cargar Datos (.xlsx, .csv)", type=["xlsx", "csv"])
    st.info("El archivo debe tener las columnas: 'Motor', 'Slot', 'Peso'.")

# --- FUNCIONES DE CÁLCULO ---
def calc_stats(df, slot_col):
    m1 = df[df[slot_col] <= 11]['Peso'].sum()
    m2 = df[df[slot_col] > 11]['Peso'].sum()
    diff = m1 - m2
    return abs(diff), diff

# --- GRÁFICO CIRCULAR DE ALTA VISIBILIDAD ---
def render_circular_fan(data, slot_col, titulo, bolt_w=0, bolt_s=0, is_final=False):
    fig = go.Figure()
    theta = np.linspace(0, 360, 22, endpoint=False)
    
    # Colores según acción
    colors = []
    for s in range(1, 23):
        row = data[data[slot_col] == s].iloc[0]
        if is_final and 'Acción' in data.columns and "MOVER" in str(row['Acción']):
            colors.append('#ff9800') # Naranja: Requiere movimiento
        else:
            colors.append('#1f77b4') # Azul: Posición correcta

    # Dibujar el cuerpo de los álabes
    fig.add_trace(go.Barpolar(
        r=[8]*22, theta=theta, width=[14]*22,
        marker=dict(color=colors, line=dict(color='white', width=2)),
        hoverinfo="none"
    ))
    
    # Texto de los IDs de álabes (Dentro de la pieza)
    for i in range(22):
        pieza = data[data[slot_col] == (i+1)].iloc[0]
        fig.add_trace(go.Scatterpolar(
            r=[6.2], theta=[theta[i]], mode='text',
            text=[f"<b>{pieza['ID_Original']}</b>"],
            textfont=dict(size=14, color="white")
        ))

    # Indicador de Peso de Compensación (Bolt)
    if bolt_w > 0.01:
        fig.add_trace(go.Scatterpolar(
            r=[4.5], theta=[theta[bolt_s-1]], mode='markers+text',
            marker=dict(symbol="star", size=25, color="#f1c40f", line=dict(width=2, color="red")),
            text=[f"<b>BOLT {bolt_w:.2f}g</b>"], textposition="bottom center",
            textfont=dict(size=14, color="red")
        ))

    fig.update_layout(
        title=dict(text=f"<b>{titulo}</b>", font=dict(size=22, color="#1f77b4")),
        polar=dict(
            bgcolor='white',
            angularaxis=dict(
                tickvals=theta, 
                ticktext=[f"<b>{i+1}</b>" for i in range(22)], # NÚMERO DE SLOT EXTERIOR
                rotation=90, direction="clockwise", gridcolor="#e0e0e0",
                tickfont=dict(size=18, color="black")
            ),
            radialaxis=dict(visible=False, range=[0, 10])
        ),
        showlegend=False, height=700, margin=dict(t=80, b=80, l=50, r=50)
    )
    return fig

# --- PROCESAMIENTO ---
if uploaded_file:
    try:
        # Blindaje contra errores de Android (lectura directa de bytes)
        file_content = uploaded_file.read()
        if uploaded_file.name.endswith('.csv'):
            df_full = pd.read_csv(io.BytesIO(file_content))
        else:
            df_full = pd.read_excel(io.BytesIO(file_content), engine='openpyxl')
        
        df_full.columns = [c.strip().capitalize() for c in df_full.columns]
        motores_ids = df_full['Motor'].unique()
        fleet_results = []

        for idx, m_name in enumerate(motores_ids):
            with st.expander(f"📦 MOTOR: {m_name}", expanded=True):
                df_m = df_full[df_full['Motor'] == m_name].copy()
                df_m['ID_Original'] = [f"Á{int(s)}" for s in df_m['Slot']]
                df_m['Slot_Original'] = df_m['Slot'].astype(int)
                
                v_ini, d_ini = calc_stats(df_m, 'Slot_Original')

                # Optimización Global (Consistencia absoluta con 15k pruebas)
                best_v = v_ini
                best_df = df_m.copy()
                pesos_lista = df_m.copy()
                for _ in range(15000):
                    temp = pesos_lista.sample(frac=1).reset_index(drop=True)
                    temp['Test_Slot'] = range(1, 23)
                    v_t, d_t = calc_stats(temp, 'Test_Slot')
                    if v_t < best_v:
                        best_v = v_t; best_df = temp.copy(); best_df['Nuevo_Slot'] = best_df['Test_Slot']; best_d = d_t

                if best_v < (v_ini - 0.01):
                    df_final = best_df; v_f = best_v; d_f = best_d; usa_prop = True
                else:
                    df_final = df_m.copy(); df_final['Nuevo_Slot'] = df_final['Slot_Original']; v_f = v_ini; d_f = d_ini; usa_prop = False

                bolt_w = v_f
                bolt_s = 17 if d_f > 0 else 6
                
                # Asignar Acción para el gráfico
                df_final['Acción'] = df_final.apply(lambda x: "MANTENER" if x['Slot_Original'] == x['Nuevo_Slot'] else f"MOVER AL {int(x['Nuevo_Slot'])}", axis=1)

                # MÉTRICAS
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Vib. Inicial", f"{v_ini:.2f}")
                c2.metric("Vib. Propuesta", f"{v_f:.2f}", delta=f"-{v_ini-v_f:.2f}" if usa_prop else None)
                c3.metric("Masa Bolt", f"{bolt_w:.2f}")
                c4.metric("Slot Bolt", f"{bolt_s}")

                # GRÁFICOS CIRCULARES
                g_ini, g_fin = st.columns(2)
                with g_ini: st.plotly_chart(render_circular_fan(df_m, 'Slot_Original', "AS FOUND (ACTUAL)"), use_container_width=True, key=f"p1_{idx}")
                with g_fin: st.plotly_chart(render_circular_fan(df_final, 'Nuevo_Slot', "AS LEFT (PROPUESTA)", bolt_w, bolt_s, is_final=True), use_container_width=True, key=f"p2_{idx}")
                
                # TABLA DE TALLER
                st.write("### 📋 Guía de Movimientos")
                st.dataframe(df_final[['ID_Original', 'Peso', 'Slot_Original', 'Nuevo_Slot', 'Acción']].sort_values(by='Slot_Original'), use_container_width=True)
                
                fleet_results.append({'Motor': m_name, 'Data': df_final, 'v_ini': v_ini, 'v_f': v_f, 'bolt': bolt_w, 'slot': bolt_s})

        # EXPORTACIÓN EXCEL
        def get_fleet_report(results):
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                resumen = pd.DataFrame([{'Motor': r['Motor'], 'Vib_Ini': r['v_ini'], 'Vib_Fin': r['v_f'], 'Bolt': r['bolt'], 'Slot': r['slot']} for r in results])
                resumen.to_excel(writer, sheet_name='RESUMEN_FLOTA', index=False)
                for r in results:
                    r['Data'][['ID_Original', 'Peso', 'Slot_Original', 'Nuevo_Slot', 'Acción']].to_excel(writer, sheet_name=f"Steps_{r['Motor']}", index=False)
            return output.getvalue()

        st.sidebar.divider()
        st.sidebar.download_button("📥 DESCARGAR REPORTE DE FLOTA", data=get_fleet_report(fleet_results), file_name="Flota_V2500_Final.xlsx")

    except Exception as e:
        st.error(f"Error de procesamiento: {e}")
else:
    st.info("Cargue un Excel con la columna 'Motor' para iniciar el estudio de flota con referencia circular.")