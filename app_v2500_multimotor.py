import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import io
import math

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="V2500 Aero-Master Dual", layout="wide")

st.markdown("""
    <style>
    .stMetric { border: 2px solid #58a6ff; background: #f0f7ff; padding: 10px; border-radius: 8px; }
    .emergency-header { background-color: #78281f; color: white; padding: 15px; border-radius: 10px; text-align: center; margin-bottom: 20px; }
    .instructions { background-color: #f4f6f7; border-left: 5px solid #2c3e50; padding: 15px; margin-bottom: 20px; }
    </style>
    """, unsafe_allow_html=True)

# --- NÚCLEO TÉCNICO ---
def calculate_resultant(weights, slots):
    """Calcula la magnitud del desbalance de un grupo de álabes"""
    res_x, res_y = 0.0, 0.0
    for w, s in zip(weights, slots):
        angle = math.radians((s - 1) * (360 / 22))
        res_x += float(w) * math.cos(angle)
        res_y += float(w) * math.sin(angle)
    return math.sqrt(res_x**2 + res_y**2)

# --- INTERFAZ DE NAVEGACIÓN ---
modo_app = st.sidebar.radio("Seleccione Modo de Operación:", ["📂 Carga de Fichero (Flota Completa)", "🚨 Balanceo Manual (Grupo Aislado)"])

if modo_app == "🚨 Balanceo Manual (Grupo Aislado)":
    st.markdown("<div class='emergency-header'><h1>🚨 MODO DE EMERGENCIA: Balanceo de Grupo Aislado</h1></div>", unsafe_allow_html=True)
    
    st.markdown("""
    <div class='instructions'>
    <b>Instrucciones:</b> Use este modo cuando solo tenga unos pocos álabes y no conozca el peso del resto del motor. 
    El sistema calculará la posición óptima para que estos álabes se cancelen entre sí.
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("1. Marque los Slots vacíos")
        slots_seleccionados = st.multiselect("Seleccione los alojamientos disponibles en el disco:", 
                                            options=list(range(1, 23)), 
                                            default=[3, 8, 13, 18, 21])
        
        n = len(slots_seleccionados)
        if n > 0:
            st.subheader(f"2. Introduzca Pesos para {n} álabes")
            pesos_input = []
            for i in range(n):
                p = st.number_input(f"Peso Álabe {i+1} (g):", min_value=100.0, max_value=200.0, value=150.0 + i, key=f"p_{i}")
                pesos_input.append(p)
    
    with col2:
        if n >= 2:
            st.subheader("3. Optimización de Posiciones")
            # Simulación por permutación para grupos pequeños (N! es pequeño para 5-10 álabes)
            import itertools
            
            # En grupos pequeños podemos calcular TODAS las combinaciones reales
            mejores_pos = None
            min_mag = float('inf')
            
            # Probamos todas las permutaciones de los pesos en los slots elegidos
            for p_perm in itertools.permutations(pesos_input):
                mag = calculate_resultant(p_perm, slots_seleccionados)
                if mag < min_mag:
                    min_mag = mag
                    mejores_pos = p_perm
            
            # Gráfico de Resultados
            fig = go.Figure()
            theta = np.linspace(0, 360, 22, endpoint=False)
            colores = ["#e74c3c" if i+1 in slots_seleccionados else "#ebedef" for i in range(22)]
            
            fig.add_trace(go.Barpolar(r=[8]*22, theta=theta, width=[14]*22, marker_color=colores, marker_line_color="#bdc3c7"))
            
            # Mostrar etiquetas de peso en los slots elegidos
            for p, s in zip(mejores_pos, slots_seleccionados):
                angle = (s - 1) * (360 / 22)
                fig.add_trace(go.Scatterpolar(r=[6.5], theta=[angle], mode='text', 
                                             text=[f"{p}g"], textfont=dict(size=12, color="red", family="Arial Black")))

            fig.update_layout(polar=dict(angularaxis=dict(tickvals=theta, ticktext=[str(i+1) for i in range(22)], rotation=90, direction="clockwise")),
                              showlegend=False, height=500, title="DISTRIBUCIÓN NEUTRA SUGERIDA")
            st.plotly_chart(fig, use_container_width=True)

            # Tabla de Resultados
            res_df = pd.DataFrame({
                "Alojamiento (Slot)": slots_seleccionados,
                "Peso a Instalar (g)": mejores_pos
            }).sort_values(by="Alojamiento (Slot)")
            
            st.table(res_df)
            st.success(f"Desbalance residual del grupo: {min_mag:.2f} g-mm (Objetivo: Cero)")
        else:
            st.warning("Seleccione al menos 2 slots para calcular un balanceo.")

else:
    # --- AQUÍ VA TODO EL CÓDIGO ANTERIOR SIN TOCAR NI UNA LÍNEA ---
    # (Manteniendo la lógica de Carga de Excel, 3 estrategias, etc.)
    st.title("📂 Modo Profesional: Balanceo de Disco Completo")
    # ... [Resto del código previo] ...
    st.info("Suba su archivo Excel en la barra lateral para ver el análisis de flota.")
