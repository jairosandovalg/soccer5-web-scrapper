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
        page.goto(url_partido, timeout=30000, wait_until="domcontentloaded")

        # 1. Esperar al contenedor principal del partido
        try:
            page.wait_for_selector("div.detailScore__wrapper", timeout=7000)
        except Exception:
            pass

        # 2. Navegar a la pestaña 'Estadísticas' si no está activa
        tab_stats = page.locator('a[data-analytics-alias="match-statistics"], a[role="tab"]:has-text("Estadísticas")')
        if tab_stats.count() > 0:
            try:
                # Solo hacer clic si no tiene la clase active
                if "active" not in (tab_stats.first.get_attribute("class") or ""):
                    tab_stats.first.click(force=True)
                    page.wait_for_timeout(1000)
            except Exception:
                pass

        # 3. Esperar que cargue el widget de estadísticas o de cuotas
        try:
            page.wait_for_selector('div[data-analytics-context="widget-team-stats"], div[data-testid="statGroup"]', timeout=4000)
        except Exception:
            pass

        # Parsear con BeautifulSoup
        soup = BeautifulSoup(page.content(), "html.parser")

        # Marcador
        score = soup.select_one("div.detailScore__wrapper")
        if score:
            datos_partido["Marcador"] = score.get_text(separator=" ", strip=True)

        # Estado del partido
        status = soup.select_one("span.fixedHeaderDuel__detailStatus")
        if status:
            datos_partido["Tiempo/Estado"] = status.get_text(strip=True)

        # Minuto actual
        minuto = soup.select_one("span.eventTime")
        if minuto:
            datos_partido["Minuto"] = minuto.get_text(strip=True)

        # 4. EXTRACCIÓN DE CUOTAS (1X2) - Universal e independiente del Bookmaker ID
        odd_1 = soup.select_one('[data-analytics-element="ODDS_COMPARISONS_ODD_CELL_1"] [data-testid="wcl-oddsValue"]')
        odd_x = soup.select_one('[data-analytics-element="ODDS_COMPARISONS_ODD_CELL_2"] [data-testid="wcl-oddsValue"]')
        odd_2 = soup.select_one('[data-analytics-element="ODDS_COMPARISONS_ODD_CELL_3"] [data-testid="wcl-oddsValue"]')

        if odd_1 and odd_x and odd_2:
            datos_partido["Cuotas"] = f"1:{odd_1.get_text(strip=True)} X:{odd_x.get_text(strip=True)} 2:{odd_2.get_text(strip=True)}"
        else:
            # Fallback a cualquier grupo de 3 cuotas disponible
            all_odds = [o.get_text(strip=True) for o in soup.select('[data-testid="wcl-oddsValue"]') if o.get_text(strip=True)]
            if len(all_odds) >= 3:
                datos_partido["Cuotas"] = f"1:{all_odds[0]} X:{all_odds[1]} 2:{all_odds[2]}"

        # 5. EXTRACCIÓN ROBUSTA DE ESTADÍSTICAS
        # Ubicar la sección activa (por defecto tab-74: Partido Completo)
        bloque_stats = soup.select_one('div[data-analytics-context="tab-74"]') or soup.select_one('div.section--teamStats')

        if bloque_stats:
            # Caso A: Filas estándar (xG, Posesión, Pases, Faltas, etc.)
            for fila in bloque_stats.select('div[data-testid="wcl-statistics"]'):
                # Busca el nombre del indicador
                label_el = (fila.select_one('span[class*="wcl-name_"]') or 
                            fila.select_one('div[class*="wcl-label_"]') or
                            fila.select_one('[data-testid*="category"]'))
                
                # Busca los valores numéricos
                valores = fila.select('[class*="wcl-value_"]')
                if label_el and len(valores) >= 2:
                    nombre = label_el.get_text(strip=True)
                    val_local = valores[0].get_text(strip=True)
                    val_visita = valores[-1].get_text(strip=True)
                    datos_partido["Stats"][f"{nombre} (L)"] = val_local
                    datos_partido["Stats"][f"{nombre} (V)"] = val_visita

            # Caso B: Barras de remates (Remates a puerta / fuera)
            for shot_bar in bloque_stats.select('[class*="wcl-shotOnTargetStats_"]'):
                label_el = shot_bar.select_one('[class*="wcl-label_"]')
                valores = shot_bar.select('[class*="wcl-value_"]')
                if label_el and len(valores) >= 2:
                    nombre = label_el.get_text(strip=True)
                    datos_partido["Stats"][f"{nombre} (L)"] = valores[0].get_text(strip=True)
                    datos_partido["Stats"][f"{nombre} (V)"] = valores[-1].get_text(strip=True)

            # Caso C: Incidentes con iconos (Córneres y Tarjetas)
            for badge in bloque_stats.select('[class*="wcl-incidentValueBadge_"]'):
                spans = badge.find_all("span", recursive=False)
                svg = badge.find("svg")
                if len(spans) >= 2 and svg:
                    svg_testid = svg.get("data-testid", "")
                    nombre = "Incidentes"
                    if "corner" in svg_testid:
                        nombre = "Córneres"
                    elif "yellowCard" in svg_testid:
                        nombre = "Tarjetas amarillas"
                    elif "redCard" in svg_testid:
                        nombre = "Tarjetas rojas"
                    
                    datos_partido["Stats"][f"{nombre} (L)"] = spans[0].get_text(strip=True)
                    datos_partido["Stats"][f"{nombre} (V)"] = spans[-1].get_text(strip=True)

    except Exception as e:
        print(f"Error parseando partido: {e}")
    finally:
        if page:
            page.close()

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
                for i, p_div in enumerate(partidos[:10]):
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

                    bar.progress((i + 1) / len(partidos[:10]))
                
                st.dataframe(pd.DataFrame(res).fillna("-"), use_container_width=True)
                st.balloons()
            browser.close()
