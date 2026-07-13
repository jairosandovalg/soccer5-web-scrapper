import os
import sys
import subprocess
import streamlit as st

# --- CONFIGURACIÓN DE RUTA PARA PLAYWRIGHT ---
BROWSER_PATH = os.path.join(os.getcwd(), "ms-playwright")
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = BROWSER_PATH

def preparar_navegador():
    if 'navegador_configurado' not in st.session_state:
        with st.spinner("Configurando entorno (solo ocurre una vez)..."):
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright"])
                subprocess.check_call([sys.executable, "-m", "playwright", "install", "firefox"])
                st.session_state['navegador_configurado'] = True
                st.rerun()
            except Exception as e:
                st.error(f"Error crítico: {e}")
                st.stop()

preparar_navegador()

from playwright.sync_api import sync_playwright
import pandas as pd
import time
import requests
from bs4 import BeautifulSoup

st.set_page_config(page_title="Bot de Estadísticas Final", layout="wide")
st.title("📊 Monitor de Estadísticas en Vivo - Flashscore & Telegram")

# --- FUNCIÓN TELEGRAM ---
def enviar_resumen_telegram(df):
    TOKEN = "892395866:AAES1dc4LAsedUKUsGR4p5D1SkaMt7nKyes"
    CHAT_ID = "7272170952"
    if not df.empty:
        mensaje = f"🚀 *ACTUALIZACIÓN VIVO* 🚀\n🕒 {time.strftime('%H:%M:%S')}\n\n"
        for _, fila in df.iterrows():
            mensaje += f"⚽ *{fila['Partido en Vivo']}*\n🏆 *Marcador:* `{fila['Marcador']}`\n💰 *Cuotas Betano:* `{fila['Cuotas']}`\n───────────────────\n"
        try:
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                          json={"chat_id": CHAT_ID, "text": mensaje, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# --- EXTRACCIÓN ---
def extraer_estadisticas_partido(context, url_partido):
    datos = {"Marcador": "-", "Tiempo/Estado": "-", "Minuto": "-", "Cuotas": "No disp."}
    page = None
    try:
        page = context.new_page()
        page.goto(url_partido, timeout=10000, wait_until="domcontentloaded")
        
        # Esperar a que cargue el marcador y las cuotas
        page.wait_for_selector("div.detailScore__wrapper", timeout=5000)
        
        soup = BeautifulSoup(page.content(), "html.parser")
        
        # Marcador
        score = soup.select_one("div.detailScore__wrapper")
        if score: datos["Marcador"] = score.get_text(strip=True)
        
        # Extracción específica de cuota Betano (ID 660)
        betano = soup.find("div", {"data-analytics-bookmaker-id": "660"})
        if betano:
            odds = betano.find_all("span", {"data-testid": "wcl-oddsValue"})
            if len(odds) >= 3:
                datos["Cuotas"] = f"1:{odds[0].get_text()} X:{odds[1].get_text()} 2:{odds[2].get_text()}"
        
        return datos
    except: return datos
    finally:
        if page: page.close()

# --- MONITOREO ---
@st.fragment
def contenedor_monitoreo_vivo():
    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context(user_agent="Mozilla/5.0")
        
        # Navegación inicial
        page = context.new_page()
        page.goto("https://www.flashscore.pe/", wait_until="domcontentloaded")
        page.locator("//div[contains(@class, 'filters__text') and text()='EN DIRECTO']").click()
        time.sleep(3)
        
        partidos = page.locator("div[id^='g_1_']").all()
        lista_resultados = []
        
        for p_elem in partidos[:5]: # Primeros 5 partidos
            id_part = p_elem.get_attribute("id").split('_')[-1]
            res = extraer_estadisticas_partido(context, f"https://www.flashscore.pe/partido/{id_part}/#/resumen")
            
            lista_resultados.append({
                "Partido en Vivo": "Encuentro", 
                "Marcador": res["Marcador"], 
                "Minuto": "-", 
                "Cuotas": res["Cuotas"]
            })
            
        df = pd.DataFrame(lista_resultados)
        st.dataframe(df)
        enviar_resumen_telegram(df)
        browser.close()
    
    time.sleep(60)
    st.rerun()

if st.button("🔄 Iniciar Monitoreo"):
    contenedor_monitoreo_vivo()
