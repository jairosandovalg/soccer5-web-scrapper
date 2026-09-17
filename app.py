import streamlit as st
import pandas as pd
import subprocess
import sys
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

# --- CONFIGURACIÓN E INSTALACIÓN DE PLAYWRIGHT ---
@st.cache_resource
def instalar_navegadores_playwright():
    try:
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True
        )
        return True
    except Exception as e:
        print(f"Error instalando Chromium: {e}")
        return False

instalar_navegadores_playwright()

# --- FUNCIÓN DE EXTRACCIÓN DE CADA PARTIDO ---
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

        # Optimización: abortar imágenes, fuentes y CSS innecesario para mayor velocidad
        def interceptar_rutas(route):
            if route.request.resource_type in ["image", "media", "font"]:
                route.abort()
            else:
                route.continue_()

        page.route("**/*", interceptar_rutas)

        # Cargar URL directa a estadísticas
        page.goto(url_partido, timeout=30000, wait_until="domcontentloaded")

        # 1. Esperar encabezado del marcador
        try:
            page.wait_for_selector("div.detailScore__wrapper", timeout=6000)
        except Exception:
            pass

        # 2. Asegurar que la pestaña "Estadísticas" esté activa si existe
        tab_stats = page.locator('a[data-analytics-alias="match-statistics"], a[role="tab"]:has-text("Estadísticas")')
        if tab_stats.count() > 0:
            try:
                clases = tab_stats.first.get_attribute("class") or ""
                if "active" not in clases:
                    tab_stats.first.click(force=True)
            except Exception:
                pass

        # Esperar a que el contenedor de estadísticas o grupos de datos se rendericen
        try:
            page.wait_for_selector(
                '[data-testid="statGroup"], [data-testid="wcl-statistics"], .section--teamStats, [data-analytics-context*="tab-"]',
                timeout=5000
            )
        except Exception:
            pass

        # Parsear con BeautifulSoup
        soup = BeautifulSoup(page.content(), "html.parser")

        # Marcador
        score = soup.select_one("div.detailScore__wrapper")
        if score:
            datos_partido["Marcador"] = score.get_text(separator=" ", strip=True)

        # Estado del partido (En juego, Descanso, Finalizado, etc.)
        status = soup.select_one("span.fixedHeaderDuel__detailStatus")
        if status:
            datos_partido["Tiempo/Estado"] = status.get_text(strip=True)

        # Minuto actual
        minuto = soup.select_one("span.eventTime")
        if minuto:
            datos_partido["Minuto"] = minuto.get_text(strip=True)

        # 3. EXTRACCIÓN DE CUOTAS (1X2)
        c1 = soup.select_one('[data-analytics-element="ODDS_COMPARISONS_ODD_CELL_1"] [data-testid="wcl-oddsValue"]')
        cx = soup.select_one('[data-analytics-element="ODDS_COMPARISONS_ODD_CELL_2"] [data-testid="wcl-oddsValue"]')
        c2 = soup.select_one('[data-analytics-element="ODDS_COMPARISONS_ODD_CELL_3"] [data-testid="wcl-oddsValue"]')

        if c1 and cx and c2:
            datos_partido["Cuotas"] = f"1:{c1.get_text(strip=True)} X:{cx.get_text(strip=True)} 2:{c2.get_text(strip=True)}"
        else:
            # Estrategia de respaldo: buscar la primera fila de 3 cuotas
            todas_cuotas = [o.get_text(strip=True) for o in soup.select('[data-testid="wcl-oddsValue"]') if o.get_text(strip=True)]
            if len(todas_cuotas) >= 3:
                datos_partido["Cuotas"] = f"1:{todas_cuotas[0]} X:{todas_cuotas[1]} 2:{todas_cuotas[2]}"

        # 4. EXTRACCIÓN ROBUSTA DE ESTADÍSTICAS (Agnóstica a tab-74, 12 o 13)
        contenedor = (
            soup.select_one('div.tabContent__match-statistics') or
            soup.select_one('div.section--teamStats') or
            soup
        )

        # A) Filas clásicas (data-testid="wcl-statistics")
        for fila in contenedor.select('[data-testid="wcl-statistics"]'):
            nombre_el = (
                fila.select_one('[class*="wcl-name_"]') or
                fila.select_one('[class*="wcl-label_"]') or
                fila.select_one('[data-testid*="category"]')
            )
            vals = fila.select('[class*="wcl-value_"]')

            if nombre_el and len(vals) >= 2:
                nombre = nombre_el.get_text(strip=True)
                val_l = vals[0].get_text(strip=True)
                val_v = vals[-1].get_text(strip=True)
                if nombre:
                    datos_partido["Stats"][f"{nombre} (L)"] = val_l
                    datos_partido["Stats"][f"{nombre} (V)"] = val_v

        # B) Barras de remates (Remates a puerta / fuera)
        for shot_bar in contenedor.select('[class*="wcl-shotOnTargetStats_"]'):
            nombre_el = shot_bar.select_one('[class*="wcl-label_"]')
            vals = shot_bar.select('[class*="wcl-value_"]')
            if nombre_el and len(vals) >= 2:
                nombre = nombre_el.get_text(strip=True)
                datos_partido["Stats"][f"{nombre} (L)"] = vals[0].get_text(strip=True)
                datos_partido["Stats"][f"{nombre} (V)"] = vals[-1].get_text(strip=True)

        # C) Incidentes con iconos SVG (Córneres y Tarjetas)
        for badge in contenedor.select('[class*="wcl-incidentValueBadge_"]'):
            spans = badge.find_all("span", recursive=False)
            svg = badge.find("svg")
            if len(spans) >= 2 and svg:
                svg_id = svg.get("data-testid", "").lower()
                if "corner" in svg_id:
                    nombre = "Córneres"
                elif "yellow" in svg_id:
                    nombre = "Tarjetas amarillas"
                elif "red" in svg_id:
                    nombre = "Tarjetas rojas"
                else:
                    nombre = "Incidentes"

                datos_partido["Stats"][f"{nombre} (L)"] = spans[0].get_text(strip=True)
                datos_partido["Stats"][f"{nombre} (V)"] = spans[-1].get_text(strip=True)

        # D) Respaldo general: estructura 3 elementos (Valor - Etiqueta - Valor)
        for row in contenedor.select('[class*="wcl-labelRow_"]'):
            vals = row.select('[class*="wcl-value_"]')
            lbl = row.select_one('[class*="wcl-name_"]') or row.select_one('[class*="wcl-label_"]')
            if lbl and len(vals) >= 2:
                nombre = lbl.get_text(strip=True)
                key_l = f"{nombre} (L)"
                if key_l not in datos_partido["Stats"]:
                    datos_partido["Stats"][key_l] = vals[0].get_text(strip=True)
                    datos_partido["Stats"][f"{nombre} (V)"] = vals[-1].get_text(strip=True)

    except Exception as e:
        print(f"Error procesando {url_partido}: {e}")
    finally:
        if page:
            page.close()

    return datos_partido

# --- INTERFAZ STREAMLIT ---
st.set_page_config(page_title="Bot de Estadísticas", layout="wide")
st.title("📊 Monitor de Estadísticas en Vivo")

if st.button("🔄 Ejecutar Escaneo Completo"):
    with st.spinner("Conectando con Flashscore..."):
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu"
                ]
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            main = context.new_page()

            try:
                main.goto("https://www.flashscore.pe/", timeout=30000, wait_until="domcontentloaded")

                # Clic en pestaña "EN DIRECTO"
                btn_live = "//div[contains(@class, 'filters__text') and text()='EN DIRECTO']"
                main.wait_for_selector(btn_live, timeout=10000)
                main.locator(btn_live).click()
                main.wait_for_timeout(2500)

                soup_main = BeautifulSoup(main.content(), "html.parser")
                partidos = soup_main.find_all("div", id=lambda x: x and x.startswith("g_1_"))

                if partidos:
                    res = []
                    limite_partidos = min(len(partidos), 10)
                    bar = st.progress(0)

                    for i, p_div in enumerate(partidos[:limite_partidos]):
                        id_p = p_div.get("id").split("_")[-1]

                        # Obtener nombres de los equipos
                        h_team = p_div.find("div", class_=lambda c: c and "home" in c.lower() and "participant" in c.lower())
                        a_team = p_div.find("div", class_=lambda c: c and "away" in c.lower() and "participant" in c.lower())
                        nombre_partido = f"{h_team.get_text(strip=True) if h_team else 'Local'} vs {a_team.get_text(strip=True) if a_team else 'Visitante'}"

                        # Extraer estadísticas y cuotas del partido
                        url = f"https://www.flashscore.pe/partido/{id_p}/#/resumen/estadisticas"
                        data = extraer_estadisticas_partido(context, url)

                        # Armar fila para el DataFrame
                        stats_dict = data.pop("Stats", {})
                        reg = {
                            "Partido en Vivo": nombre_partido,
                            "Marcador": data["Marcador"],
                            "Cuotas": data["Cuotas"],
                            "Tiempo/Estado": data["Tiempo/Estado"],
                            "Minuto": data["Minuto"]
                        }
                        reg.update(stats_dict)
                        res.append(reg)

                        bar.progress((i + 1) / limite_partidos)

                    st.dataframe(pd.DataFrame(res).fillna("-"), use_container_width=True)
                    st.balloons()
                else:
                    st.warning("No se encontraron partidos en directo en este momento.")

            except Exception as err:
                st.error(f"Ocurrió un error durante la extracción: {err}")
            finally:
                browser.close()
