import streamlit as st
import pandas as pd
import time
import subprocess
import sys
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

# --- BLOQUE DE AUTO-INSTALACIÓN ---
@st.cache_resource
def instalar_navegadores_playwright():
    try:
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        return True
    except Exception as e:
        return False

instalar_navegadores_playwright()

# --- FUNCIÓN DE EXTRACCIÓN ACTUALIZADA ---
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
        
        # Esperar a elementos clave
        page.wait_for_selector("div.detailScore__wrapper", timeout=8000)
        
        soup = BeautifulSoup(page.content(), "html.parser")
        
        # Marcador, Tiempo y Minuto
        score_wrapper = soup.select_one("div.detailScore__wrapper")
        if score_wrapper: datos_partido["Marcador"] = score_wrapper.get_text(strip=True)
        
        status_span = soup.select_one("span.fixedHeaderDuel__detailStatus")
        if status_span: datos_partido["Tiempo/Estado"] = status_span.get_text(strip=True)
        
        minuto_span = soup.select_one("span.eventTime")
        if minuto_span: datos_partido["Minuto"] = minuto_span.get_text(strip=True)

        # --- EXTRACCIÓN DE CUOTAS (CORRECCIÓN) ---
        # Buscamos los botones de Betano por su ID de casa de apuestas
        botones_cuotas = soup.find_all("button", {"data-analytics-bookmaker-id": "660"})
        valores_cuotas = []
        
        for btn in botones_cuotas:
            span_val = btn.find("span", {"data-testid": "wcl-oddsValue"})
            if span_val:
                valores_cuotas.append(span_val.get_text(strip=True))
        
        if len(valores_cuotas) >= 3:
            datos_partido["Cuotas"] = f"1:{valores_cuotas[0]} X:{valores_cuotas[1]} 2:{valores_cuotas[2]}"

        # Estadísticas
        selector_boton = "//button[@role='tab' and contains(., 'Estadísticas')]"
        if page.locator(selector_boton).count() > 0:
            page.locator(selector_boton).first.click(force=True)
            page.wait_for_timeout(1500)
            soup_stats = BeautifulSoup(page.content(), "html.parser")
            filas = soup_stats.find_all("div", {"data-testid": "wcl-statistics"})
            
            for fila in filas:
                cat = fila.find("div", {"data-testid": "wcl-statistics-category"})
                if cat:
                    categoria = cat.get_text(strip=True)
                    h = fila.find("div", class_=lambda x: x and 'wcl-homeValue' in x)
                    v = fila.find("div", class_=lambda x: x and 'wcl-awayValue' in x)
                    datos_partido["Stats"][f"{categoria} (L)"] = h.get_text(strip=True) if h else "0"
                    datos_partido["Stats"][f"{categoria} (V)"] = v.get_text(strip=True) if v else "0"
    except:
        pass
    finally:
        if page: page.close()
    return datos_partido

# --- INTERFAZ PRINCIPAL ---
st.set_page_config(page_title="Bot de Estadísticas Final", layout="wide")
st.title("📊 Monitor de Estadísticas en Vivo - Flashscore")

if st.button("🔄 Ejecutar Escaneo Completo y Generar Tabla"):
    with st.spinner("Procesando partidos en vivo..."):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
            
            main_page = context.new_page()
            main_page.goto("https://www.flashscore.pe/", timeout=25000)
            
            selector_directo = "//div[contains(@class, 'filters__text') and text()='EN DIRECTO']"
            main_page.wait_for_selector(selector_directo)
            main_page.locator(selector_directo).click(force=True)
            main_page.wait_for_timeout(3500)
            
            soup = BeautifulSoup(main_page.content(), "html.parser")
            partidos = soup.find_all("div", id=lambda x: x and x.startswith("g_1_"))
            
            if not partidos:
                st.warning("No se encontraron partidos en directo.")
            else:
                lista_final = []
                bar = st.progress(0)
                for idx, fila in enumerate(partidos):
                    id_partido = fila.get('id').split('_')[-1]
                    url = f"https://www.flashscore.pe/partido/{id_partido}/#/resumen/estadisticas"
                    
                    data = extraer_estadisticas_partido(context, url)
                    
                    if "final" not in data["Tiempo/Estado"].lower() and len(data["Stats"]) > 0:
                        reg = {"Partido": f"{id_partido}", **data}
                        reg.update(data.pop("Stats"))
                        lista_final.append(reg)
                    
                    bar.progress((idx + 1) / len(partidos))
                
                if lista_final:
                    df = pd.DataFrame(lista_final).fillna("-")
                    st.dataframe(df, use_container_width=True)
                    st.balloons()
                else:
                    st.warning("No se pudieron extraer datos válidos.")
            browser.close()
