import streamlit as st
import pandas as pd
import subprocess
import sys
import time
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

# --- INSTALACIÓN AUTOMÁTICA DE CHROMIUM EN STREAMLIT CLOUD ---
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


# --- EXTRACCIÓN INDEPENDIENTE DE CUOTAS Y ESTADÍSTICAS PRINCIPALES ---
def extraer_detalle_partido(playwright_context, id_partido):
    resultado = {
        "Marcador": "- - -",
        "Cuotas": "- - -",
        "Tiempo/Estado": "-",
        "Minuto": "-",
        "Stats": {}
    }
    page = None
    url = f"https://www.flashscore.pe/partido/{id_partido}/"

    try:
        page = playwright_context.new_page()

        # Cargar página completa sin abortar scripts para no romper React
        page.goto(url, timeout=30000, wait_until="domcontentloaded")

        # 1. Esperar encabezado del partido
        try:
            page.wait_for_selector("div.detailScore__wrapper", timeout=6000)
        except Exception:
            pass

        # 2. EXTRACCIÓN INDEPENDIENTE: CUOTAS 1X2
        # Esperar a que el bloque de cuotas se hidrate en el DOM
        try:
            page.wait_for_selector(
                '[data-analytics-context="widget-match-summary-odds"], [data-analytics-element*="ODDS_COMPARISONS_ODD_CELL"]',
                timeout=4000
            )
        except Exception:
            pass

        soup_inicial = BeautifulSoup(page.content(), "html.parser")

        # Extraer cuotas 1X2 sin depender de ningún bookmaker ID
        btn_1 = soup_inicial.select_one('[data-analytics-element="ODDS_COMPARISONS_ODD_CELL_1"] [data-testid="wcl-oddsValue"]')
        btn_x = soup_inicial.select_one('[data-analytics-element="ODDS_COMPARISONS_ODD_CELL_2"] [data-testid="wcl-oddsValue"]')
        btn_2 = soup_inicial.select_one('[data-analytics-element="ODDS_COMPARISONS_ODD_CELL_3"] [data-testid="wcl-oddsValue"]')

        if btn_1 and btn_x and btn_2:
            resultado["Cuotas"] = f"1:{btn_1.get_text(strip=True)} X:{btn_x.get_text(strip=True)} 2:{btn_2.get_text(strip=True)}"
        else:
            # Respaldo dentro del contenedor general de cuotas
            bloque_cuotas = soup_inicial.select_one('div[data-analytics-context="widget-match-summary-odds"]')
            if bloque_cuotas:
                valores = [span.get_text(strip=True) for span in bloque_cuotas.select('[data-testid="wcl-oddsValue"]')]
                if len(valores) >= 3:
                    resultado["Cuotas"] = f"1:{valores[0]} X:{valores[1]} 2:{valores[2]}"

        # 3. EXTRACCIÓN INDEPENDIENTE: ESTADÍSTICAS PRINCIPALES
        # Asegurar navegación a la pestaña de estadísticas si no está activa
        tab_stats = page.locator('a[data-analytics-alias="match-statistics"], a[role="tab"]:has-text("Estadísticas")')
        if tab_stats.count() > 0:
            try:
                clases = tab_stats.first.get_attribute("class") or ""
                if "active" not in clases:
                    tab_stats.first.click(force=True)
            except Exception:
                pass

        # Esperar a que el grupo de estadísticas aparezca
        try:
            page.wait_for_selector(
                '[data-testid="statGroup"], div.section--teamStats, div.tabContent__match-statistics',
                timeout=6000
            )
        except Exception:
            time.sleep(1.5)

        soup_stats = BeautifulSoup(page.content(), "html.parser")

        # Datos básicos
        score = soup_stats.select_one("div.detailScore__wrapper")
        if score:
            resultado["Marcador"] = score.get_text(separator=" ", strip=True)

        status = soup_stats.select_one("span.fixedHeaderDuel__detailStatus")
        if status:
            resultado["Tiempo/Estado"] = status.get_text(strip=True)

        minuto = soup_stats.select_one("span.eventTime")
        if minuto:
            resultado["Minuto"] = minuto.get_text(strip=True)

        # 4. AISLAR EXCLUSIVAMENTE EL GRUPO: "Estadísticas principales"
        primer_grupo = None
        for grupo in soup_stats.select('div[data-testid="statGroup"]'):
            titulo = grupo.select_one('[data-testid="wcl-headerSection-text"]')
            if titulo and "principal" in titulo.get_text(strip=True).lower():
                primer_grupo = grupo
                break

        # Si no tiene título explícito, tomar el primer statGroup disponible
        if not primer_grupo:
            grupos = soup_stats.select('div[data-testid="statGroup"]')
            if grupos:
                primer_grupo = grupos[0]

        if primer_grupo:
            # 4.1. Filas estándar (xG, Posesión, Pases, Faltas)
            for fila in primer_grupo.select('[data-testid="wcl-statistics"]'):
                nombre_el = (
                    fila.select_one('[class*="wcl-name_"]') or
                    fila.select_one('[class*="wcl-label_"]')
                )
                valores = fila.select('[class*="wcl-value_"]')
                if nombre_el and len(valores) >= 2:
                    nombre = nombre_el.get_text(strip=True)
                    if nombre:
                        resultado["Stats"][f"{nombre} (L)"] = valores[0].get_text(strip=True)
                        resultado["Stats"][f"{nombre} (V)"] = valores[-1].get_text(strip=True)

            # 4.2. Gráficos de barra (Remates a puerta / fuera)
            for shot_bar in primer_grupo.select('[class*="wcl-shotOnTargetStats_"]'):
                nombre_el = shot_bar.select_one('[class*="wcl-label_"]')
                valores = shot_bar.select('[class*="wcl-value_"]')
                if nombre_el and len(valores) >= 2:
                    nombre = nombre_el.get_text(strip=True)
                    if nombre:
                        resultado["Stats"][f"{nombre} (L)"] = valores[0].get_text(strip=True)
                        resultado["Stats"][f"{nombre} (V)"] = valores[-1].get_text(strip=True)

            # 4.3. Badges de incidentes SVG (Córneres y Tarjetas)
            for badge in primer_grupo.select('[class*="wcl-incidentValueBadge_"]'):
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

                    resultado["Stats"][f"{nombre} (L)"] = spans[0].get_text(strip=True)
                    resultado["Stats"][f"{nombre} (V)"] = spans[-1].get_text(strip=True)

    except Exception as e:
        print(f"Error procesando partido {id_partido}: {e}")
    finally:
        if page:
            page.close()

    return resultado


# --- INTERFAZ STREAMLIT ---
st.set_page_config(page_title="Monitor de Estadísticas en Vivo", layout="wide")
st.title("📊 Monitor de Estadísticas en Vivo")

if st.button("🔄 Ejecutar Escaneo Completo"):
    with st.spinner("Conectando con Flashscore y leyendo partidos en directo..."):
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
                main.goto("https://www.flashscore.pe/", timeout=35000, wait_until="domcontentloaded")

                # Clic en "EN DIRECTO"
                btn_live = "//div[contains(@class, 'filters__text') and text()='EN DIRECTO']"
                main.wait_for_selector(btn_live, timeout=12000)
                main.locator(btn_live).click()
                time.sleep(2.5)

                soup_main = BeautifulSoup(main.content(), "html.parser")
                partidos = soup_main.find_all("div", id=lambda x: x and x.startswith("g_1_"))

                if partidos:
                    res = []
                    limite = min(len(partidos), 10)
                    bar = st.progress(0)

                    for i, p_div in enumerate(partidos[:limite]):
                        id_p = p_div.get("id").split("_")[-1]

                        # Obtener nombres de equipos
                        h_team = p_div.find("div", class_=lambda c: c and "home" in c.lower() and "participant" in c.lower())
                        a_team = p_div.find("div", class_=lambda c: c and "away" in c.lower() and "participant" in c.lower())
                        nombre_partido = f"{h_team.get_text(strip=True) if h_team else 'Local'} vs {a_team.get_text(strip=True) if a_team else 'Visitante'}"

                        # Extracción modular e independiente
                        detalle = extraer_detalle_partido(context, id_p)

                        stats_dict = detalle.get("Stats", {})
                        fila = {
                            "Partido en Vivo": nombre_partido,
                            "Marcador": detalle["Marcador"],
                            "Cuotas": detalle["Cuotas"],
                            "Tiempo/Estado": detalle["Tiempo/Estado"],
                            "Minuto": detalle["Minuto"]
                        }
                        fila.update(stats_dict)
                        res.append(fila)

                        bar.progress((i + 1) / limite)

                    st.dataframe(pd.DataFrame(res).fillna("-"), use_container_width=True)
                    st.balloons()
                else:
                    st.warning("No se encontraron partidos en directo.")

            except Exception as e:
                st.error(f"Error en la ejecución: {e}")
            finally:
                browser.close()
