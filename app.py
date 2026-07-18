import streamlit as st
import pandas as pd
import time
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
    except Exception as e:
        st.error(f"Error al instalar navegadores: {e}")
        return False

instalar_navegadores_playwright()

def extraer_estadisticas_partido(playwright_context, url_partido):
    datos_partido = {
        "Marcador": "- - -",
        "Cuotas": "- - -",
        "Tiempo/Estado": "-",
        "Minuto": "-",
        "Stats": {}
    }
    page = None
    try:
        page = playwright_context.new_page()
        page.goto(url_partido, timeout=20000, wait_until="domcontentloaded")
        
        # Esperar a que carguen elementos clave
        page.wait_for_selector("div.detailScore__wrapper", timeout=8000)
        
        # Extraer cuotas específicamente de los botones de Betano (ID 660)
        # Esperamos a que los botones estén presentes
        try:
            page.wait_for_selector("button[data-analytics-bookmaker-id='660']", timeout=5000)
        except:
            pass # Si no hay cuotas, continuamos igual

        soup = BeautifulSoup(page.content(), "html.parser")
        
        # Marcador y Estado
        score_wrapper = soup.select_one("div.detailScore__wrapper")
        if score_wrapper: datos_partido["Marcador"] = score_wrapper.get_text(strip=True)
        
        status_span = soup.select_one("span.fixedHeaderDuel__detailStatus")
        if status_span: datos_partido["Tiempo/Estado"] = status_span.get_text(strip=True)
        
        minuto_span = soup.select_one("span.eventTime")
        if minuto_span: datos_partido["Minuto"] = minuto_span.get_text(strip=True)

        # --- CORRECCIÓN: Extracción de Cuotas Betano ---
        botones_betano = soup.find_all("button", {"data-analytics-bookmaker-id": "660"})
        if len(botones_betano) >= 3:
            lista_cuotas = []
            for btn in botones_betano:
                span_valor = btn.find("span", {"data-testid": "wcl-oddsValue"})
                if span_valor:
                    lista_cuotas.append(span_valor.get_text(strip=True))
            
            if len(lista_cuotas) >= 3:
                datos_partido["Cuotas"] = f"1:{lista_cuotas[0]} X:{lista_cuotas[1]} 2:{lista_cuotas[2]}"

        # Estadísticas
        selector_boton = "//button[@role='tab' and contains(., 'Estadísticas')]"
        if page.locator(selector_boton).count() > 0:
            page.locator(selector_boton).first.click(force=True)
            page.wait_for_timeout(1500)
            soup_stats = BeautifulSoup(page.content(), "html.parser")
            filas_estadisticas = soup_stats.find_all("div", {"data-testid": "wcl-statistics"})
            
            for fila in filas_estadisticas:
                cat_div = fila.find("div", {"data-testid": "wcl-statistics-category"})
                if cat_div:
                    cat = cat_div.get_text(strip=True)
                    home = fila.find("div", class_=lambda x: x and 'wcl-homeValue' in x)
                    away = fila.find("div", class_=lambda x: x and 'wcl-awayValue' in x)
                    datos_partido["Stats"][f"{cat} (L)"] = home.get_text(strip=True) if home else "0"
                    datos_partido["Stats"][f"{cat} (V)"] = away.get_text(strip=True) if away else "0"
    except:
        pass
    finally:
        if page: page.close()
    return datos_partido

# --- PROCESO PRINCIPAL ---
if st.button("🔄 Ejecutar Escaneo Completo"):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
        
        main_page = context.new_page()
        main_page.goto("https://www.flashscore.pe/", timeout=25000)
        
        # Clic en "EN DIRECTO"
        btn_directo = "//div[contains(@class, 'filters__text') and text()='EN DIRECTO']"
        main_page.wait_for_selector(btn_directo)
        main_page.locator(btn_directo).click()
        main_page.wait_for_timeout(3000)
        
        soup = BeautifulSoup(main_page.content(), "html.parser")
        partidos = soup.find_all("div", id=lambda x: x and x.startswith("g_1_"))
        
        resultados = []
        for p_div in partidos[:5]: # Limitado a 5 para evitar bloqueos
            id_partido = p_div.get('id').split('_')[-1]
            url = f"https://www.flashscore.pe/partido/{id_partido}/#/resumen/estadisticas"
            
            datos = extraer_estadisticas_partido(context, url)
            registro = {"Partido": id_partido, **datos}
            registro.update(datos.pop("Stats"))
            resultados.append(registro)
        
        df = pd.DataFrame(resultados)
        st.dataframe(df)
        browser.close()
