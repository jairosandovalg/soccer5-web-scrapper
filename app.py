import streamlit as st
import pandas as pd
import subprocess
import sys
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

# --- CONFIGURACIÓN E INSTALACIÓN AUTOMÁTICA DE PLAYWRIGHT ---
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


# --- FUNCIÓN DE EXTRACCIÓN ROBUSTA DE PARTIDO ---
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
        
        # 1. Esperar al encabezado del partido
        try:
            page.wait_for_selector("div.detailScore__wrapper", timeout=8000)
        except Exception:
            pass

        # 2. ESPERA Y EXTRACCIÓN DE CUOTAS (TU BLOQUE ORIGINAL)
        try:
            # Esperar a que las cuotas de Betano / Bookmaker aparezcan
            page.wait_for_selector("button[data-analytics-bookmaker-id]", timeout=5000)
            page.wait_for_timeout(1500)
        except Exception:
            pass 

        # Primer snapshot con BeautifulSoup para Marcador y Cuotas
        soup = BeautifulSoup(page.content(), "html.parser")
        
        score = soup.select_one("div.detailScore__wrapper")
        if score: 
            datos_partido["Marcador"] = score.get_text(separator=" ", strip=True)
        
        status = soup.select_one("span.fixedHeaderDuel__detailStatus")
        if status: 
            datos_partido["Tiempo/Estado"] = status.get_text(strip=True)
        
        minuto = soup.select_one("span.eventTime")
        if minuto: 
            datos_partido["Minuto"] = minuto.get_text(strip=True)

        # --- TU BLOQUE DE CUOTAS REFORZADO ---
        # Prioridad 1: Bookmaker 660 (Betano / Casa principal)
        botones = soup.find_all("button", {"data-analytics-bookmaker-id": "660"})
        valores = []
        for btn in botones:
            span = btn.find("span", {"data-testid": "wcl-oddsValue"})
            if span and span.get_text(strip=True):
                valores.append(span.get_text(strip=True))

        # Prioridad 2: Si no fue 660, buscar cualquier otra casa de apuestas disponible
        if len(valores) < 3:
            botones_genericos = soup.find_all("button", attrs={"data-analytics-bookmaker-id": True})
            for btn in botones_genericos:
                span = btn.find("span", {"data-testid": "wcl-oddsValue"})
                if span and span.get_text(strip=True):
                    valores.append(span.get_text(strip=True))
                if len(valores) == 3:
                    break

        if len(valores) >= 3:
            datos_partido["Cuotas"] = f"1:{valores[0]} X:{valores[1]} 2:{valores[2]}"

        # 3. CAMBIAR A LA PESTAÑA DE ESTADÍSTICAS
        selector_stats = 'a[data-analytics-alias="match-statistics"], a[role="tab"]:has-text("Estadísticas"), button:has-text("Estadísticas")'
        tab_stats = page.locator(selector_stats)
        if tab_stats.count() > 0:
            try:
                clases = tab_stats.first.get_attribute("class") or ""
                if "active" not in clases:
                    tab_stats.first.click(force=True)
                    page.wait_for_timeout(1000)
            except Exception:
                pass

        # Sub-pestaña "Partido" completo (alias 74)
        tab_partido = page.locator('a[data-analytics-alias="74"], a:has-text("Partido")')
        if tab_partido.count() > 0:
            try:
                clases_sub = tab_partido.first.get_attribute("class") or ""
                if "active" not in clases_sub:
                    tab_partido.first.click(force=True)
                    page.wait_for_timeout(600)
            except Exception:
                pass

        # Esperar a que el bloque de estadísticas se renderice
        try:
            page.wait_for_selector('[data-testid="statGroup"], [data-testid="wcl-statistics"], .tabContent__match-statistics', timeout=5000)
        except Exception:
            page.wait_for_timeout(1000)

        # 4. EXTRACCIÓN DE ESTADÍSTICAS PRINCIPALES
        soup_s = BeautifulSoup(page.content(), "html.parser")
        
        # Buscar el bloque específico de "Estadísticas principales"
        primer_grupo = None
        for grupo in soup_s.select('div[data-testid="statGroup"]'):
            titulo = grupo.select_one('[data-testid="wcl-headerSection-text"]')
            if titulo and "principal" in titulo.get_text(strip=True).lower():
                primer_grupo = grupo
                break

        if not primer_grupo:
            grupos = soup_s.select('div[data-testid="statGroup"]')
            if grupos:
                primer_grupo = grupos[0]
            else:
                primer_grupo = soup_s.select_one('div.tabContent__match-statistics') or soup_s

        if primer_grupo:
            # A. Filas estándar (xG, Posesión, Pases, etc.)
            for fila in primer_grupo.select('[data-testid="wcl-statistics"], [class*="wcl-labelRow_"]'):
                nombre_el = (
                    fila.select_one('[class*="wcl-name_"]') or
                    fila.select_one('[class*="wcl-label_"]') or
                    fila.select_one('[data-testid*="category"]')
                )
                vals = fila.select('[class*="wcl-value_"]')
                if nombre_el and len(vals) >= 2:
                    nombre = nombre_el.get_text(strip=True)
                    if nombre and f"{nombre} (L)" not in datos_partido["Stats"]:
                        datos_partido["Stats"][f"{nombre} (L)"] = vals[0].get_text(strip=True)
                        datos_partido["Stats"][f"{nombre} (V)"] = vals[-1].get_text(strip=True)

            # B. Remates a puerta (barras)
            for shot_bar in primer_grupo.select('[class*="wcl-shotOnTargetStats_"]'):
                nombre_el = shot_bar.select_one('[class*="wcl-label_"]')
                vals = shot_bar.select('[class*="wcl-value_"]')
                if nombre_el and len(vals) >= 2:
                    nombre = nombre_el.get_text(strip=True)
                    if nombre and f"{nombre} (L)" not in datos_partido["Stats"]:
                        datos_partido["Stats"][f"{nombre} (L)"] = vals[0].get_text(strip=True)
                        datos_partido["Stats"][f"{nombre} (V)"] = vals[-1].get_text(strip=True)

            # C. Incidentes con SVG (Córneres y Tarjetas)
            for badge in primer_grupo.select('[class*="wcl-incidentValueBadge_"]'):
                spans = badge.find_all("span", recursive=False)
                svg = badge.find("svg")
                if len(spans) >= 2 and svg:
                    svg_id = svg.get("data-testid", "").lower()
                    nombre = "Córneres" if "corner" in svg_id else ("Tarjetas amarillas" if "yellow" in svg_id else "Tarjetas rojas")
                    if f"{nombre} (L)" not in datos_partido["Stats"]:
                        datos_partido["Stats"][f"{nombre} (L)"] = spans[0].get_text(strip=True)
                        datos_partido["Stats"][f"{nombre} (V)"] = spans[-1].get_text(strip=True)

    except Exception as e:
        print(f"Error parseando {url_partido}: {e}")
    finally:
        if page:
            page.close()

    return datos_partido


# --- INTERFAZ STREAMLIT ---
st.set_page_config(page_title="Monitor de Estadísticas en Vivo", layout="wide")
st.title("📊 Monitor de Estadísticas en Vivo")

if st.button("🔄 Ejecutar Escaneo Completo"):
    with st.spinner("Conectando con Flashscore y escaneando datos en directo..."):
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage"
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
                main.wait_for_timeout(2500)

                soup_main = BeautifulSoup(main.content(), "html.parser")
                partidos = soup_main.find_all("div", id=lambda x: x and x.startswith("g_1_"))

                if partidos:
                    res = []
                    limite = min(len(partidos), 10)
                    bar = st.progress(0)

                    for i, p_div in enumerate(partidos[:limite]):
                        id_p = p_div.get("id").split("_")[-1]

                        # Nombres de los equipos
                        h_team = p_div.find("div", class_=lambda c: c and "home" in c.lower() and "participant" in c.lower())
                        a_team = p_div.find("div", class_=lambda c: c and "away" in c.lower() and "participant" in c.lower())
                        nombre_partido = f"{h_team.get_text(strip=True) if h_team else 'Local'} vs {a_team.get_text(strip=True) if a_team else 'Visitante'}"

                        # URL directa a la vista del partido
                        url = f"https://www.flashscore.pe/partido/{id_p}/#/resumen/estadisticas"
                        data = extraer_estadisticas_partido(context, url)

                        # Armar fila
                        stats_dict = data.pop("Stats", {})
                        fila = {
                            "Partido en Vivo": nombre_partido,
                            "Marcador": data["Marcador"],
                            "Cuotas": data["Cuotas"],
                            "Tiempo/Estado": data["Tiempo/Estado"],
                            "Minuto": data["Minuto"]
                        }
                        fila.update(stats_dict)
                        res.append(fila)

                        bar.progress((i + 1) / limite)

                    st.dataframe(pd.DataFrame(res).fillna("-"), use_container_width=True)
                    st.balloons()
                else:
                    st.warning("No se encontraron partidos en directo actualmente.")

            except Exception as e:
                st.error(f"Error en el escaneo: {e}")
            finally:
                browser.close()
