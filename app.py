import sys
import subprocess
import streamlit as st

# --- 1. PREPARACIÓN AUTOMÁTICA DEL ENTORNO ---
def preparar_navegador():
    if 'navegador_configurado' not in st.session_state:
        with st.spinner("Configurando entorno (esto solo ocurre una vez)..."):
            try:
                # Instalar playwright y el binario de Firefox
                subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright"])
                subprocess.check_call([sys.executable, "-m", "playwright", "install", "firefox"])
                st.session_state['navegador_configurado'] = True
                st.rerun()
            except Exception as e:
                st.error(f"Error crítico de configuración: {e}")
                st.stop()

preparar_navegador()

from playwright.sync_api import sync_playwright
import pandas as pd
import time
import requests
from bs4 import BeautifulSoup

# Configuración de la interfaz
st.set_page_config(page_title="Bot de Estadísticas Final", layout="wide")
st.title("📊 Monitor de Estadísticas en Vivo - Flashscore & Telegram")

# --- 2. FUNCIÓN DE ENVÍO A TELEGRAM ---
def enviar_resumen_telegram(df):
    TOKEN = "892395866:AAES1dc4LAsedUKUsGR4p5D1SkaMt7nKyes"
    CHAT_ID = "7272170952"
    if not df.empty:
        mensaje = f"🚀 *ACTUALIZACIÓN EN VIVO* 🚀\n🕒 {time.strftime('%H:%M:%S')}\n\n"
        for _, fila in df.iterrows():
            mensaje += f"⚽ *{fila['Partido en Vivo']}*\n🏆 *Marcador:* `{fila['Marcador']}` | *Min:* `{fila['Minuto']}`\n───────────────────\n"
        try:
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                          json={"chat_id": CHAT_ID, "text": mensaje, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# --- 3. EXTRACCIÓN DE ESTADÍSTICAS ---
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
                    cat_txt = cat.get_text(strip=True)
                    datos["Stats"][f"{cat_txt} (L)"] = "..." 
        return datos
    except: return datos
    finally:
        if page: page.close()

# --- 4. CONTENEDOR DE MONITOREO ---
@st.fragment
def contenedor_monitoreo_vivo():
    st.info("Escaneando Flashscore con Firefox...")
    with sync_playwright() as p:
        try:
            browser = p.firefox.launch(headless=True, args=["--no-sandbox"])
            context = browser.new_context(user_agent="Mozilla/5.0")
            
            page = context.new_page()
            page.goto("https://www.flashscore.pe/", wait_until="domcontentloaded")
            page.locator("//div[contains(@class, 'filters__text') and text()='EN DIRECTO']").click()
            time.sleep(3)
            
            # (Aquí tu lógica de extracción de elementos g_1_...)
            st.success("Escaneo exitoso.")
            browser.close()
        except Exception as e:
            st.error(f"Error de ejecución: {e}")
    time.sleep(60)
    st.rerun()

contenedor_monitoreo_vivo()
