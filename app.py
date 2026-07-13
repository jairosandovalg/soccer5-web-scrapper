import os
import sys
import subprocess
import streamlit as st

# --- 1. CONFIGURACIÓN DE RUTA PERSISTENTE PARA PLAYWRIGHT ---
# Definimos que los navegadores se instalen en la carpeta raíz del proyecto,
# así evitamos que el sistema borre el caché en cada reinicio.
BROWSER_PATH = os.path.join(os.getcwd(), "ms-playwright")
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = BROWSER_PATH

def preparar_navegador():
    if 'navegador_configurado' not in st.session_state:
        with st.spinner("Configurando entorno (solo ocurre una vez)..."):
            try:
                # Instalamos playwright y el binario de Firefox específicamente en la ruta definida
                subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright"])
                subprocess.check_call([sys.executable, "-m", "playwright", "install", "firefox"])
                st.session_state['navegador_configurado'] = True
                st.rerun()
            except Exception as e:
                st.error(f"Error crítico en instalación: {e}")
                st.stop()

preparar_navegador()

from playwright.sync_api import sync_playwright
import pandas as pd
import time
import requests
from bs4 import BeautifulSoup

# Configuración de página
st.set_page_config(page_title="Bot de Estadísticas Final", layout="wide")
st.title("📊 Monitor de Estadísticas en Vivo - Flashscore")

# --- 2. FUNCIONES DE EXTRACCIÓN ---
def extraer_estadisticas_partido(context, url_partido):
    datos = {"Marcador": "-", "Tiempo/Estado": "-", "Minuto": "-", "Stats": {}}
    page = None
    try:
        page = context.new_page()
        page.goto(url_partido, timeout=10000, wait_until="domcontentloaded")
        page.wait_for_selector("div.detailScore__wrapper", timeout=5000)
        
        soup = BeautifulSoup(page.content(), "html.parser")
        score = soup.select_one("div.detailScore__wrapper")
        if score: datos["Marcador"] = score.get_text(strip=True)
        
        # Intentar buscar estadísticas
        btn = page.locator("//button[@role='tab' and contains(., 'Estadísticas')]")
        if btn.count() > 0:
            btn.first.click()
            page.wait_for_timeout(1000)
            soup_stats = BeautifulSoup(page.content(), "html.parser")
            for fila in soup_stats.find_all("div", {"data-testid": "wcl-statistics"}):
                cat = fila.find("div", {"data-testid": "wcl-statistics-category"})
                if cat:
                    datos["Stats"][f"{cat.get_text(strip=True)} (L)"] = "..." 
        return datos
    except: return datos
    finally:
        if page: page.close()

# --- 3. CONTENEDOR DE MONITOREO ---
@st.fragment
def contenedor_monitoreo_vivo():
    st.info("Escaneando Flashscore con Firefox...")
    with sync_playwright() as p:
        try:
            # Firefox es más compatible con servidores Linux restringidos
            browser = p.firefox.launch(headless=True, args=["--no-sandbox"])
            context = browser.new_context(user_agent="Mozilla/5.0")
            
            # Navegación
            page = context.new_page()
            page.goto("https://www.flashscore.pe/", wait_until="domcontentloaded")
            page.locator("//div[contains(@class, 'filters__text') and text()='EN DIRECTO']").click()
            time.sleep(3)
            
            st.success("Escaneo exitoso.")
            browser.close()
        except Exception as e:
            st.error(f"Error de ejecución: {e}")
    
    time.sleep(60)
    st.rerun()

if st.button("🔄 Iniciar Monitoreo"):
    contenedor_monitoreo_vivo()
