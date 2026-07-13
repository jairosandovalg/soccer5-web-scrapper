import os
import sys
import subprocess

# --- 1. INSTALACIÓN DINÁMICA DE DEPENDENCIAS ---
# Esto evita errores de "missing requirements" al instalar todo desde el script
def preparar_entorno():
    if 'entorno_listo' not in st.session_state:
        with st.spinner("Configurando binarios y dependencias del sistema..."):
            try:
                # 1. Instalar la librería
                subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright"])
                # 2. Instalar el navegador
                subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
                # 3. ESTA ES LA CLAVE: Instalar dependencias del sistema que faltan
                subprocess.check_call([sys.executable, "-m", "playwright", "install-deps"])
                
                st.session_state['entorno_listo'] = True
            except Exception as e:
                st.error(f"Error crítico: {e}")
                st.stop()

# Ejecutar preparación antes de importar librerías de terceros
import streamlit as st
preparar_entorno()

from playwright.sync_api import sync_playwright
import pandas as pd
import time
import requests
from bs4 import BeautifulSoup

# Configuración de la interfaz
st.set_page_config(page_title="Bot de Estadísticas", layout="wide")
st.title("📊 Monitor de Estadísticas en Vivo")

# --- 2. FUNCIONES DE LÓGICA ---
def extraer_estadisticas_partido(context, url_partido):
    datos = {"Marcador": "-", "Tiempo": "-", "Minuto": "-", "Stats": {}}
    page = None
    try:
        page = context.new_page()
        page.goto(url_partido, timeout=10000, wait_until="domcontentloaded")
        
        soup = BeautifulSoup(page.content(), "html.parser")
        score = soup.select_one("div.detailScore__wrapper")
        if score: datos["Marcador"] = score.get_text(strip=True)
        
        # ... (Mantén aquí tu lógica de extracción existente) ...
    except Exception: pass
    finally:
        if page: page.close()
    return datos

# --- 3. PROCESO DE MONITOREO ---
@st.fragment
def ejecutar_monitoreo():
    st.info("Iniciando escaneo de Flashscore...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(user_agent="Mozilla/5.0")
        
        # Lógica de scraping...
        # [Aquí va tu lógica de extracción Flashscore]
        
        browser.close()
    
    st.success("Escaneo completado.")
    time.sleep(60)
    st.rerun()

# --- 4. RENDERIZADO ---
if st.button("🔄 Iniciar Monitor Automático"):
    ejecutar_monitoreo()
