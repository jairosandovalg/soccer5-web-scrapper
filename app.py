import streamlit as st
import pandas as pd
import time
import os
import subprocess
import sys
from bs4 import BeautifulSoup

# --- BLOQUE DE AUTO-INSTALACIÓN DE BINARIOS PARA PLAYWRIGHT ---
# Este bloque descarga automáticamente el navegador Chromium si no existe en el servidor
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    # Si por alguna razón la librería no está instalada, detenemos la ejecución de forma segura
    st.error("La librería 'playwright' no está lista. Verifica tu requirements.txt.")
    st.stop()

@st.cache_resource
def instalar_navegadores_playwright():
    """Ejecuta el comando de instalación de navegadores de Playwright de forma interna."""
    with st.spinner("Configurando el entorno del navegador por primera vez (esto puede tomar un minuto)..."):
        try:
            # Ejecuta 'playwright install chromium' internamente en el servidor de Streamlit
            subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
            return True
        except Exception as e:
            st.error(f"Error al instalar los binarios del navegador: {e}")
            return False

# Ejecutamos la instalación automática antes de renderizar la app
instalar_navegadores_playwright()
# --------------------------------------------------------------

# Configuración de la interfaz de Streamlit
st.set_page_config(page_title="Bot de Estadísticas Final", layout="wide")
st.title("📊 Monitor de Estadísticas en Vivo - Flashscore")
st.subheader("Análisis de métricas en tiempo real para decisiones de apuestas")

def extraer_estadisticas_partido(playwright_context, url_partido):
    """Navega de forma segura a la URL del partido usando Playwright y extrae la información."""
    datos_partido = {
        "Marcador": "- - -",
        "Tiempo/Estado": "-",
        "Minuto": "-",  
        "Stats": {}
    }
    page = None
    try:
        page = playwright_context.new_page()
        page.goto(url_partido, timeout=15000, wait_until="domcontentloaded")
        
        page.wait_for_selector("div.detailScore__wrapper", timeout=6000)
        
        soup = BeautifulSoup(page.content(), "html.parser")
        
        # Captura de Marcador
        score_wrapper = soup.select_one("div.detailScore__wrapper")
        if score_wrapper:
            datos_partido["Marcador"] = score_wrapper.get_text(strip=True)
            
        # Captura de Tiempo/Estado
        status_span = soup.select_one("span.fixedHeaderDuel__detailStatus")
        if status_span:
            datos_partido["Tiempo/Estado"] = status_span.get_text(strip=True)

        # Captura del Minuto Exacto
        minuto_span = soup.select_one("span.eventTime")
        if minuto_span:
            datos_partido["Minuto"] = minuto_span.get_text(strip=True)
        
        # Localiza el botón de pestañas de 'Estadísticas' y hace click
        selector_boton = "//button[@role='tab' and contains(., 'Estadísticas')]"
        if page.locator(selector_boton).count() > 0:
            page.locator(selector_boton).first.click(force=True)
            page.wait_for_timeout(1000)
            
            soup_stats = BeautifulSoup(page.content(), "html.parser")
            filas_estadisticas = soup_stats.find_all("div", {"data-testid": "wcl-statistics"})
            
            for fila in filas_estadisticas:
                cat_div = fila.find("div", {"data-testid": "wcl-statistics-category"})
                if cat_div:
                    categoria = cat_div.get_text(strip=True)
                    home_val_div = fila.find("div", class_=lambda x: x and 'wcl-homeValue' in x)
                    away_val_div = fila.find("div", class_=lambda x: x and 'wcl-awayValue' in x)
                    
                    datos_partido["Stats"][f"{categoria} (L)"] = home_val_div.get_text(strip=True) if home_val_div else "0"
                    datos_partido["Stats"][f"{categoria} (V)"] = away_val_div.get_text(strip=True) if away_val_div else "0"
                    
    except Exception:
        pass
    finally:
        if page:
            try: page.close()
            except: pass
            
    return datos_partido

# --- PROCESO PRINCIPAL EN INTERFAZ ---

if st.button("🔄 Ejecutar Escaneo Completo y Generar Tabla"):
    with st.spinner("Conectando de forma estable a la sección EN DIRECTO con Playwright..."):
        with sync_playwright() as p:
            browser = None
            try:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
                )
                
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                    locale="es-ES"
                )
                
                main_page = context.new_page()
                main_page.goto("https://www.flashscore.pe/", timeout=25000)
                
                selector_directo = "//div[contains(@class, 'filters__text') and text()='EN DIRECTO']"
                main_page.wait_for_selector(selector_directo, timeout=15000)
                main_page.locator(selector_directo).click(force=True)
                main_page.wait_for_timeout(3500)
                
                soup = BeautifulSoup(main_page.content(), "html.parser")
                partidos_en_vivo = soup.find_all("div", id=lambda x: x and x.startswith("g_1_"))
                
                if not partidos_en_vivo:
                    st.warning("No se encontraron partidos en directo para analizar en este momento.")
                else:
                    st.success(f"Se detectaron {len(partidos_en_vivo)} partidos activos. Procesando métricas...")
                    
                    barra_progreso = st.progress(0)
                    lista_registros_finales = []
                    
                    for idx, fila in enumerate(partidos_en_vivo):
                        id_partido = fila.get('id').split('_')[-1]
                        url_match_stats = f"https://www.flashscore.pe/partido/{id_partido}/#/resumen/estadisticas"
                        
                        local_div = fila.find("div", class_=lambda c: c and "home" in c.lower() and "participant" in c.lower())
                        visitante_div = fila.find("div", class_=lambda c: c and "away" in c.lower() and "participant" in c.lower())
                        nom_local = local_div.get_text(strip=True) if local_div else "Local"
                        nom_visitante = visitante_div.get_text(strip=True) if visitante_div else "Visitante"
                        
                        resultado_profundo = extraer_estadisticas_partido(context, url_match_stats)
                        
                        registro = {
                            "Partido en Vivo": f"{nom_local} vs {nom_visitante}",
                            "Marcador": resultado_profundo["Marcador"],
                            "Tiempo/Estado": resultado_profundo["Tiempo/Estado"],
                            "Minuto": resultado_profundo["Minuto"]
                        }
                        registro.update(resultado_profundo["Stats"])
                        lista_registros_finales.append(registro)
                        
                        barra_progreso.progress((idx + 1) / len(partidos_en_vivo))
                    
                    df_final = pd.DataFrame(lista_registros_finales).fillna("-")
                    
                    columnas_fijas = ["Partido en Vivo", "Marcador", "Tiempo/Estado", "Minuto"]
                    columnas_stats = [col for col in df_final.columns if col not in columnas_fijas]
                    df_final = df_final[columnas_fijas + columnas_stats]
                    
                    st.write("### 📈 Cuadro de Control General")
                    st.dataframe(df_final, use_container_width=True)
                    st.balloons()
                    
            except Exception as e:
                st.error(f"Fallo crítico en el motor de Playwright: {str(e)}")
            finally:
                if browser:
                    try: browser.close()
                    except: pass
