import os
import sys
import streamlit as st
import pandas as pd
import time
import subprocess
import requests

# --- 1. ESTRUCTURA ROBUSTA DE AUTO-INSTALACIÓN ---
def instalar_playwright_y_navegador():
    if 'navegador_configurado' not in st.session_state:
        with st.spinner("Configurando el entorno del navegador (solo ocurre una vez)..."):
            try:
                # 1. Instala la librería
                subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright"])
                # 2. Instala el binario de Chromium
                subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
                st.session_state['navegador_configurado'] = True
            except Exception as e:
                st.error(f"Error crítico en la instalación: {e}")
                st.stop()

# Llamamos a la instalación antes de cualquier importación de Playwright
instalar_playwright_y_navegador()

# Ahora sí, importamos de forma segura
from playwright.sync_api import sync_playwright

# Configuración de página
st.set_page_config(page_title="Bot de Estadísticas Final", layout="wide")
st.title("📊 Monitor de Estadísticas en Vivo - Flashscore & Telegram")

# --- 2. RESTO DE TUS FUNCIONES (enviar_resumen_telegram, extraer_estadisticas_partido) ---
# ... (Mantén tus funciones actuales aquí, no necesitan cambios) ...

# --- 3. CONTENEDOR DE MONITOREO ---
@st.fragment
def contenedor_monitoreo_vivo():
    st.caption(f"🔄 Última actualización: {time.strftime('%H:%M:%S')}")
    
    # IMPORTANTE: Aseguramos que sync_playwright se use dentro del bloque try para evitar errores de memoria
    with sync_playwright() as p:
        browser = None
        try:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            context = browser.new_context(user_agent="Mozilla/5.0...")
            
            # ... (Toda tu lógica de extracción aquí) ...
            
        except Exception as e:
            st.error(f"Error en ejecución: {e}")
        finally:
            if browser: browser.close()

    time.sleep(60)
    st.rerun()

# --- 4. RENDERIZADO ---
contenedor_monitoreo_vivo()
