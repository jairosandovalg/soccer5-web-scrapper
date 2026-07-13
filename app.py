import os
import sys
import streamlit as st
import pandas as pd
import time
import subprocess
import requests

# --- 1. COMPROBACIÓN E INSTALACIÓN CON VERIFICACIÓN ---
def preparar_navegador():
    if 'navegador_configurado' not in st.session_state:
        with st.spinner("Descargando navegador Firefox y configurando entorno..."):
            try:
                # Instalamos playwright y el navegador firefox
                subprocess.run([sys.executable, "-m", "pip", "install", "playwright"], check=True)
                subprocess.run([sys.executable, "-m", "playwright", "install", "firefox"], check=True)
                
                st.session_state['navegador_configurado'] = True
                st.rerun()
            except Exception as e:
                st.error(f"Error crítico: {e}")
                st.stop()

preparar_navegador()
from playwright.sync_api import sync_playwright

# ... (El resto de tus funciones: enviar_resumen_telegram, extraer_estadisticas_partido) ...

# --- 4. CONTENEDOR DINÁMICO AUTOMÁTICO ---
@st.fragment
def contenedor_monitoreo_vivo():
    # ... (Tu código actual) ...
    
    with sync_playwright() as p:
        try:
            # Firefox suele ser más estable en estos entornos que Chromium
            browser = p.firefox.launch(headless=True, args=["--no-sandbox"])
            context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/120.0")
            
            # ... (Toda tu lógica de scraping igual que la tenías) ...
            
        except Exception as e:
            st.error(f"Error en sesión: {e}")
        finally:
            if 'browser' in locals() and browser: browser.close()
    
    time.sleep(60)
    st.rerun()

# --- 5. RENDERIZADO ---
contenedor_monitoreo_vivo()
