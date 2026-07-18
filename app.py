import streamlit as st
import pandas as pd
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import sys
import subprocess

# Configuración de página
st.set_page_config(page_title="Bot de Estadísticas Final", layout="wide")
st.title("📊 Monitor de Estadísticas en Vivo - Flashscore")

@st.cache_resource
def instalar_navegadores_playwright():
    try:
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        return True
    except:
        return False

instalar_navegadores_playwright()

def extraer_estadisticas_partido(context, url_partido):
    datos = {"Marcador": "-", "Cuotas": "-", "Tiempo": "-", "Minuto": "-", "Stats": {}}
    page = context.new_page()
    try:
        page.goto(url_partido, timeout=15000, wait_until="domcontentloaded")
        page.wait_for_selector("div.detailScore__wrapper", timeout=8000)
        
        soup = BeautifulSoup(page.content(), "html.parser")
        
        # Datos básicos
        score = soup.select_one("div.detailScore__wrapper")
        if score: datos["Marcador"] = score.get_text(strip=True)
        
        status = soup.select_one("span.fixedHeaderDuel__detailStatus")
        if status: datos["Tiempo"] = status.get_text(strip=True)
        
        minuto = soup.select_one("span.eventTime")
        if minuto: datos["Minuto"] = minuto.get_text(strip=True)

        # Cuotas (Betano 660)
        btns = soup.find_all("button", {"data-analytics-bookmaker-id": "660"})
        cuotas = []
        for btn in btns:
            val = btn.find("span", {"data-testid": "wcl-oddsValue"})
            if val: cuotas.append(val.get_text(strip=True))
        if len(cuotas) >= 3:
            datos["Cuotas"] = f"1:{cuotas[0]} X:{cuotas[1]} 2:{cuotas[2]}"

        # Estadísticas
        btn_stats = "//button[@role='tab' and contains(., 'Estadísticas')]"
        if page.locator(btn_stats).count() > 0:
            page.locator(btn_stats).first.click()
            page.wait_for_timeout(1000)
            soup_s = BeautifulSoup(page.content(), "html.parser")
            for fila in soup_s.find_all("div", {"data-testid": "wcl-statistics"}):
                cat = fila.find("div", {"data-testid": "wcl-statistics-category"})
                if cat:
                    h = fila.find("div", class_=lambda x: x and 'wcl-homeValue' in x)
                    a = fila.find("div", class_=lambda x: x and 'wcl-awayValue' in x)
                    datos["Stats"][f"{cat.get_text(strip=True)} (L)"] = h.get_text(strip=True) if h else "0"
                    datos["Stats"][f"{cat.get_text(strip=True)} (V)"] = a.get_text(strip=True) if a else "0"
    except:
        pass
    finally:
        page.close()
    return datos

# --- PROCESO PRINCIPAL CON BARRA DE PROGRESO ---
if st.button("🔄 Ejecutar Escaneo Completo"):
    with st.spinner("Iniciando conexión con Flashscore..."):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
            
            page = context.new_page()
            page.goto("https://www.flashscore.pe/")
            
            # Clic en EN DIRECTO
            btn_live = "//div[contains(@class, 'filters__text') and text()='EN DIRECTO']"
            page.wait_for_selector(btn_live)
            page.locator(btn_live).click()
            page.wait_for_timeout(3000)
            
            soup = BeautifulSoup(page.content(), "html.parser")
            partidos = soup.find_all("div", id=lambda x: x and x.startswith("g_1_"))
            
            if not partidos:
                st.warning("No se encontraron partidos en vivo.")
            else:
                st.success(f"Se detectaron {len(partidos)} partidos. Extrayendo datos...")
                bar = st.progress(0)
                resultados = []
                
                for i, p_div in enumerate(partidos[:10]): # Max 10 para rapidez
                    id_p = p_div.get('id').split('_')[-1]
                    url = f"https://www.flashscore.pe/partido/{id_p}/#/resumen/estadisticas"
                    
                    data = extraer_estadisticas_partido(context, url)
                    registro = {"ID": id_p, **data}
                    registro.update(data.pop("Stats"))
                    resultados.append(registro)
                    
                    # Actualizar barra
                    bar.progress((i + 1) / len(partidos[:10]))
                
                df = pd.DataFrame(resultados)
                st.dataframe(df, use_container_width=True)
                st.balloons()
            
            browser.close()
