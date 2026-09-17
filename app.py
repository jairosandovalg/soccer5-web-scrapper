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

        # 1. Esperar al contenedor principal del marcador
        try:
            page.wait_for_selector("div.detailScore__wrapper", timeout=6000)
        except Exception:
            pass

        # 2. Esperar explícitamente a que aparezcan los elementos de cuotas en el DOM
        try:
            page.wait_for_selector(
                '[data-testid="wcl-oddsValue"], [data-analytics-element^="ODDS_COMPARISONS_ODD_CELL_"]',
                timeout=4000
            )
        except Exception:
            # Si no están visibles en el resumen, intentar abrir la pestaña "Cuotas"
            tab_cuotas = page.locator('div[data-analytics-alias="odds"], div.filters__tab:has-text("Cuotas")')
            if tab_cuotas.count() > 0:
                try:
                    tab_cuotas.first.click(force=True)
                    page.wait_for_selector('[data-testid="wcl-oddsValue"]', timeout=3000)
                except Exception:
                    pass

        # 3. Asegurar que la pestaña de Estadísticas esté cargada si se requiere
        tab_stats = page.locator('a[data-analytics-alias="match-statistics"], a[role="tab"]:has-text("Estadísticas")')
        if tab_stats.count() > 0:
            try:
                clases = tab_stats.first.get_attribute("class") or ""
                if "active" not in clases:
                    tab_stats.first.click(force=True)
                    page.wait_for_timeout(1000)
            except Exception:
                pass

        # Parsear con BeautifulSoup
        soup = BeautifulSoup(page.content(), "html.parser")

        # Marcador, tiempo y minuto
        score = soup.select_one("div.detailScore__wrapper")
        if score:
            datos_partido["Marcador"] = score.get_text(separator=" ", strip=True)

        status = soup.select_one("span.fixedHeaderDuel__detailStatus")
        if status:
            datos_partido["Tiempo/Estado"] = status.get_text(strip=True)

        minuto = soup.select_one("span.eventTime")
        if minuto:
            datos_partido["Minuto"] = minuto.get_text(strip=True)

        # 4. EXTRACCIÓN ROBUSTA DE CUOTAS (1X2)
        cuotas_encontradas = None

        # Estrategia A: Fila de cuotas contenedora (wclOddsRow)
        for fila in soup.select("div.wclOddsRow, div[class*='wclOddsRow']"):
            c1 = fila.select_one('[data-analytics-element="ODDS_COMPARISONS_ODD_CELL_1"] [data-testid="wcl-oddsValue"]')
            cx = fila.select_one('[data-analytics-element="ODDS_COMPARISONS_ODD_CELL_2"] [data-testid="wcl-oddsValue"]')
            c2 = fila.select_one('[data-analytics-element="ODDS_COMPARISONS_ODD_CELL_3"] [data-testid="wcl-oddsValue"]')
            
            if c1 and cx and c2:
                v1 = c1.get_text(strip=True)
                vx = cx.get_text(strip=True)
                v2 = c2.get_text(strip=True)
                if v1 and vx and v2:
                    cuotas_encontradas = f"1:{v1} X:{vx} 2:{v2}"
                    break

        # Estrategia B: Búsqueda global directa por celdas ODD_CELL_1, 2 y 3
        if not cuotas_encontradas:
            c1 = soup.select_one('[data-analytics-element="ODDS_COMPARISONS_ODD_CELL_1"] [data-testid="wcl-oddsValue"]')
            cx = soup.select_one('[data-analytics-element="ODDS_COMPARISONS_ODD_CELL_2"] [data-testid="wcl-oddsValue"]')
            c2 = soup.select_one('[data-analytics-element="ODDS_COMPARISONS_ODD_CELL_3"] [data-testid="wcl-oddsValue"]')
            if c1 and cx and c2:
                cuotas_encontradas = f"1:{c1.get_text(strip=True)} X:{cx.get_text(strip=True)} 2:{c2.get_text(strip=True)}"

        # Estrategia C: Fallback genérico por lista de valores wcl-oddsValue
        if not cuotas_encontradas:
            todos_valores = [v.get_text(strip=True) for v in soup.select('[data-testid="wcl-oddsValue"]') if v.get_text(strip=True)]
            if len(todos_valores) >= 3:
                cuotas_encontradas = f"1:{todos_valores[0]} X:{todos_valores[1]} 2:{todos_valores[2]}"

        if cuotas_encontradas:
            datos_partido["Cuotas"] = cuotas_encontradas

        # 5. EXTRACCIÓN DE ESTADÍSTICAS
        bloque_stats = soup.select_one('div[data-analytics-context="tab-74"]') or soup.select_one('div.section--teamStats')

        if bloque_stats:
            # Filas estándar (xG, Posesión, Pases, Faltas, etc.)
            for fila in bloque_stats.select('div[data-testid="wcl-statistics"]'):
                label_el = (fila.select_one('span[class*="wcl-name_"]') or 
                            fila.select_one('div[class*="wcl-label_"]') or
                            fila.select_one('[data-testid*="category"]'))
                valores = fila.select('[class*="wcl-value_"]')
                if label_el and len(valores) >= 2:
                    nombre = label_el.get_text(strip=True)
                    datos_partido["Stats"][f"{nombre} (L)"] = valores[0].get_text(strip=True)
                    datos_partido["Stats"][f"{nombre} (V)"] = valores[-1].get_text(strip=True)

            # Barras de remates (Remates a puerta / fuera)
            for shot_bar in bloque_stats.select('[class*="wcl-shotOnTargetStats_"]'):
                label_el = shot_bar.select_one('[class*="wcl-label_"]')
                valores = shot_bar.select('[class*="wcl-value_"]')
                if label_el and len(valores) >= 2:
                    nombre = label_el.get_text(strip=True)
                    datos_partido["Stats"][f"{nombre} (L)"] = valores[0].get_text(strip=True)
                    datos_partido["Stats"][f"{nombre} (V)"] = valores[-1].get_text(strip=True)

            # Incidentes con iconos (Córneres y Tarjetas)
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
