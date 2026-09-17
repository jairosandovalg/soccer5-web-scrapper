import streamlit as st
import pandas as pd
import subprocess
import sys
import time
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

# --- FUNCIÓN DE EXTRACCIÓN DE ESTADÍSTICAS POR PARTIDO ---
def extraer_detalle_partido(playwright_context, id_partido):
    resultado = {
        "Marcador": "- - -",
        "Tiempo/Estado": "-",
        "Minuto": "-",
        "Stats": {}
    }
    page = None
    url = f"https://www.flashscore.pe/partido/{id_partido}/"

    try:
        page = playwright_context.new_page()

        # Bloquear elementos pesados para maximizar velocidad
        page.route(
            "**/*",
            lambda route: route.abort() if route.request.resource_type in ["image", "media", "font"] else route.continue_()
        )

        page.goto(url, timeout=30000, wait_until="domcontentloaded")

        # 1. Esperar al marcador y cabecera
        try:
            page.wait_for_selector("div.detailScore__wrapper", timeout=6000)
        except Exception:
            pass

        # 2. Hacer clic explícito en la pestaña "Estadísticas"
        tab_stats = page.locator('a[data-analytics-alias="match-statistics"], a[role="tab"]:has-text("Estadísticas")')
        if tab_stats.count() > 0:
            try:
                # Comprobar si ya está activo
                clases = tab_stats.first.get_attribute("class") or ""
                if "active" not in clases:
                    tab_stats.first.click(force=True)
            except Exception:
                pass

        # 3. Esperar a que el contenedor de estadísticas aparezca
        try:
            page.wait_for_selector(
                '[data-testid="statGroup"], [data-testid="wcl-statistics"], .tabContent__match-statistics',
                timeout=5000
            )
        except Exception:
            # Pausa mínima de cortesía para dar margen al renderizado asíncrono
            time.sleep(1)

        soup = BeautifulSoup(page.content(), "html.parser")

        # Marcador
        score = soup.select_one("div.detailScore__wrapper")
        if score:
            resultado["Marcador"] = score.get_text(separator=" ", strip=True)

        # Estado del encuentro
        status = soup.select_one("span.fixedHeaderDuel__detailStatus")
        if status:
            resultado["Tiempo/Estado"] = status.get_text(strip=True)

        # Minuto de juego
        minuto = soup.select_one("span.eventTime")
        if minuto:
            resultado["Minuto"] = minuto.get_text(strip=True)

        # 4. EXTRACCIÓN DE MÉTRICAS (Agnóstica de pestaña o período)
        # Buscar en todo el contenedor de estadísticas o en el cuerpo entero
        bloque_stats = soup.select_one('div.tabContent__match-statistics') or soup

        # Tipo 1: Filas estándar (xG, Posesión, Pases, Faltas, Fuera de juego, etc.)
        for fila in bloque_stats.select('[data-testid="wcl-statistics"], [class*="wcl-labelRow_"]'):
            nombre_el = (
                fila.select_one('[class*="wcl-name_"]') or
                fila.select_one('[class*="wcl-label_"]') or
                fila.select_one('[data-testid*="category"]')
            )
            vals = fila.select('[class*="wcl-value_"]')

            if nombre_el and len(vals) >= 2:
                nombre = nombre_el.get_text(strip=True)
                if nombre:
                    key_l = f"{nombre} (L)"
                    if key_l not in resultado["Stats"]:
                        resultado["Stats"][key_l] = vals[0].get_text(strip=True)
                        resultado["Stats"][f"{nombre} (V)"] = vals[-1].get_text(strip=True)

        # Tipo 2: Barras de remates / tiros al arco
        for shot_bar in bloque_stats.select('[class*="wcl-shotOnTargetStats_"]'):
            nombre_el = shot_bar.select_one('[class*="wcl-label_"]')
            vals = shot_bar.select('[class*="wcl-value_"]')
            if nombre_el and len(vals) >= 2:
                nombre = nombre_el.get_text(strip=True)
                if nombre:
                    resultado["Stats"][f"{nombre} (L)"] = vals[0].get_text(strip=True)
                    resultado["Stats"][f"{nombre} (V)"] = vals[-1].get_text(strip=True)

        # Tipo 3: Córneres y Tarjetas con iconos SVG
        for badge in bloque_stats.select('[class*="wcl-incidentValueBadge_"]'):
            spans = badge.find_all("span", recursive=False)
            svg = badge.find("svg")
            if len(spans) >= 2 and svg:
                svg_id = svg.get("data-testid", "").lower()
                nombre = "Córneres" if "corner" in svg_id else ("Tarjetas amarillas" if "yellow" in svg_id else "Tarjetas rojas")
                resultado["Stats"][f"{nombre} (L)"] = spans[0].get_text(strip=True)
                resultado["Stats"][f"{nombre} (V)"] = spans[-1].get_text(strip=True)

    except Exception as e:
        print(f"Error procesando {url}: {e}")
    finally:
        if page:
            page.close()

    return resultado


# --- INTERFAZ PRINCIPAL DE STREAMLIT ---
st.set_page_config(page_title="Monitor de Estadísticas en Vivo", layout="wide")
st.title("📊 Monitor de Estadísticas en Vivo")

if st.button("🔄 Ejecutar Escaneo Completo"):
    with st.spinner("Conectando con Flashscore y escaneando partidos en vivo..."):
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
                time.sleep(2.5)

                soup_main = BeautifulSoup(main.content(), "html.parser")
                partidos = soup_main.find_all("div", id=lambda x: x and x.startswith("g_1_"))

                if partidos:
                    res = []
                    limite = min(len(partidos), 10)
                    bar = st.progress(0)

                    for i, p_div in enumerate(partidos[:limite]):
                        id_p = p_div.get("id").split("_")[-1]

                        # 1. Nombres de equipos
                        h_team = p_div.find("div", class_=lambda c: c and "home" in c.lower() and "participant" in c.lower())
                        a_team = p_div.find("div", class_=lambda c: c and "away" in c.lower() and "participant" in c.lower())
                        nombre_partido = f"{h_team.get_text(strip=True) if h_team else 'Local'} vs {a_team.get_text(strip=True) if a_team else 'Visitante'}"

                        # 2. Extracción de cuotas directas de la fila principal (Garantiza que siempre haya cuota si la casa la cotiza)
                        cuotas_str = "- - -"
                        c_cells = p_div.select('[data-testid="wcl-oddsValue"], [class*="odds__value"]')
                        if len(c_cells) >= 3:
                            cuotas_str = f"1:{c_cells[0].get_text(strip=True)} X:{c_cells[1].get_text(strip=True)} 2:{c2.get_text(strip=True) if 'c2' in locals() else c_cells[2].get_text(strip=True)}"

                        # 3. Extracción profunda de estadísticas
                        detalle = extraer_detalle_partido(context, id_p)

                        # Si la fila principal tenía marcador/minuto de respaldo
                        marcador_final = detalle["Marcador"] if detalle["Marcador"] != "- - -" else "-"
                        estado_final = detalle["Tiempo/Estado"] if detalle["Tiempo/Estado"] != "-" else "-"
                        minuto_final = detalle["Minuto"] if detalle["Minuto"] != "-" else "-"

                        stats_dict = detalle.get("Stats", {})

                        fila_datos = {
                            "Partido en Vivo": nombre_partido,
                            "Marcador": marcador_final,
                            "Cuotas": cuotas_str,
                            "Tiempo/Estado": estado_final,
                            "Minuto": minuto_final
                        }
                        fila_datos.update(stats_dict)
                        res.append(fila_datos)

                        bar.progress((i + 1) / limite)

                    st.dataframe(pd.DataFrame(res).fillna("-"), use_container_width=True)
                    st.balloons()
                else:
                    st.warning("No se encontraron partidos en directo actualmente.")

            except Exception as e:
                st.error(f"Error durante el escaneo: {e}")
            finally:
                browser.close()
