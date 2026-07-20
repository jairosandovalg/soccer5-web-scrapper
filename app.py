import streamlit as st
import pandas as pd
import subprocess
import sys
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

# --- CONFIGURACIÓN E INSTALACIÓN ---
@st.cache_resource
def instalar_navegadores_playwright():
    try:
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        return True
    except:
        return False

instalar_navegadores_playwright()

# --- FUNCIÓN DE EXTRACCIÓN ---
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
        page.goto(url_partido, timeout=25000, wait_until="domcontentloaded")
        page.wait_for_selector("div.detailScore__wrapper", timeout=10000)
        
        try:
            page.wait_for_selector("button[data-analytics-bookmaker-id='660']", timeout=5000)
            page.wait_for_timeout(1500)
        except: pass 

        soup = BeautifulSoup(page.content(), "html.parser")
        
        score = soup.select_one("div.detailScore__wrapper")
        if score: datos_partido["Marcador"] = score.get_text(strip=True)
        
        status = soup.select_one("span.fixedHeaderDuel__detailStatus")
        if status: datos_partido["Tiempo/Estado"] = status.get_text(strip=True)
        
        minuto = soup.select_one("span.eventTime")
        if minuto: datos_partido["Minuto"] = minuto.get_text(strip=True)

        botones = soup.find_all("button", {"data-analytics-bookmaker-id": "660"})
        valores = []
        for btn in botones:
            span = btn.find("span", {"data-testid": "wcl-oddsValue"})
            if span: valores.append(span.get_text(strip=True))
        
        if len(valores) >= 3:
            datos_partido["Cuotas"] = f"1:{valores[0]} X:{valores[1]} 2:{valores[2]}"

        selector_boton = "//button[@role='tab' and contains(., 'Estadísticas')]"
        if page.locator(selector_boton).count() > 0:
            page.locator(selector_boton).first.click(force=True)
            page.wait_for_timeout(1000)
            soup_s = BeautifulSoup(page.content(), "html.parser")
            for fila in soup_s.find_all("div", {"data-testid": "wcl-statistics"}):
                cat = fila.find("div", {"data-testid": "wcl-statistics-category"})
                if cat:
                    h = fila.find("div", class_=lambda x: x and 'wcl-homeValue' in x)
                    v = fila.find("div", class_=lambda x: x and 'wcl-awayValue' in x)
                    datos_partido["Stats"][f"{cat.get_text(strip=True)} (L)"] = h.get_text(strip=True) if h else "0"
                    datos_partido["Stats"][f"{cat.get_text(strip=True)} (V)"] = v.get_text(strip=True) if v else "0"
    except: pass
    finally:
        if page: page.close()
    return datos_partido

# --- INTERFAZ ---
st.set_page_config(page_title="Bot de Estadísticas", layout="wide")
st.title("📊 Monitor de Estadísticas en Vivo")

if st.button("🔄 Ejecutar Escaneo Completo"):
    with st.spinner("Conectando..."):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
            main = context.new_page()
            main.goto("https://www.flashscore.pe/")
            
            btn_live = "//div[contains(@class, 'filters__text') and text()='EN DIRECTO']"
            main.wait_for_selector(btn_live)
            main.locator(btn_live).click()
            main.wait_for_timeout(3000)
            
            soup = BeautifulSoup(main.content(), "html.parser")
            partidos = soup.find_all("div", id=lambda x: x and x.startswith("g_1_"))
            
            if partidos:
                res = []
                bar = st.progress(0)
                for i, p_div in enumerate(partidos[:8]):
                    id_p = p_div.get('id').split('_')[-1]
                    
                    # Extraer nombres de equipos desde la lista principal
                    h_team = p_div.find("div", class_=lambda c: c and "home" in c.lower() and "participant" in c.lower())
                    a_team = p_div.find("div", class_=lambda c: c and "away" in c.lower() and "participant" in c.lower())
                    nombre_partido = f"{h_team.get_text(strip=True) if h_team else 'Local'} vs {a_team.get_text(strip=True) if a_team else 'Visitante'}"
                    
                    url = f"https://www.flashscore.pe/partido/{id_p}/#/resumen/estadisticas"
                    data = extraer_estadisticas_partido(context, url)
                    
                    # Estructura del registro con "Partido en Vivo"
                    stats_dict = data.pop("Stats", {}) #Se agrego
                    reg = {"Partido en Vivo": nombre_partido, 
                           #"ID": id_p, 
                           "Marcador": data["Marcador"],
                           "Cuotas": data["Cuotas"],
                            "Tiempo/Estado": data["Tiempo/Estado"],
                            "Minuto": data["Minuto"]
                           #**data
                          }
                    #reg.update(data.pop("Stats"))
                    reg.update(stats_dict)
                    res.append(reg)    

                    bar.progress((i + 1) / len(partidos[:8]))
                
                st.dataframe(pd.DataFrame(res).fillna("-"), use_container_width=True)
                st.balloons()
            browser.close()
