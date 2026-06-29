import os
import sys
import streamlit as st
import pandas as pd
import time
import subprocess
import gc  # <--- Crucial para limpiar la memoria RAM manualmente

# --- 1. COMPROBACIÓN E INSTALACIÓN INTERNA CON STEALTH ---
if 'navegador_configurado' not in st.session_state:
    with st.spinner("Inicializando entorno optimizado de Playwright... (Solo la primera vez)"):
        try:
            # Descargamos el binario de chromium correspondiente a Playwright
            subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
            st.session_state['navegador_configurado'] = True
        except Exception as e:
            st.error(f"Error al inicializar el entorno del navegador: {str(e)}")
            st.stop()
            
    from playwright.sync_api import sync_playwright
    st.rerun()

# Importaciones seguras una vez garantizado el entorno de la nube
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync

# Configuración de la interfaz de Streamlit
st.set_page_config(page_title="Bot de Estadísticas Final", layout="wide")
st.title("📊 Monitor de Estadísticas en Vivo - Flashscore (Anti-Bot Pro)")
st.subheader("Análisis de métricas en tiempo real con optimización extrema de memoria RAM")

# --- 2. EXTRACCIÓN DE DATOS DE PARTIDOS ---
def extraer_estadisticas_partido(context, url_partido):
    """Abre una pestaña nueva, extrae la info y libera memoria inmediatamente."""
    datos_partido = {
        "Marcador": "- - -",
        "Tiempo/Estado": "-",
        "Minuto": "-",
        "Stats": {}
    }
    page = None
    try:
        page = context.new_page()
        
        # 🛡️ Aplicamos camuflaje anti-bot a la subpestaña del partido
        stealth_sync(page)
        
        # Bloquear recursos pesados de forma ultra-estricta
        page.route("**/*", lambda route: route.abort() if route.request.resource_type in ["image", "font", "stylesheet", "media"] else route.continue_())
        
        page.goto(url_partido, timeout=8000, wait_until="domcontentloaded")
        page.wait_for_selector("div.detailScore__wrapper", timeout=4000)
        
        marcador_el = page.locator("div.detailScore__wrapper").first
        if marcador_el.count() > 0:
            datos_partido["Marcador"] = marcador_el.text_content(timeout=500).strip()
            
        estado_el = page.locator("span.fixedHeaderDuel__detailStatus").first
        if estado_el.count() > 0:
            datos_partido["Tiempo/Estado"] = estado_el.text_content(timeout=500).strip()
            
        minuto_el = page.locator("span.eventTime").first
        if minuto_el.count() > 0:
            datos_partido["Minuto"] = minuto_el.text_content(timeout=500).strip()
            
        # Hacer clic en la pestaña de Estadísticas si existe
        boton_stats = page.locator("//button[@role='tab' and contains(., 'Estadísticas')]").first
        if boton_stats.count() > 0:
            boton_stats.click(timeout=1000)
            page.wait_for_selector("div[data-testid='wcl-statistics']", timeout=2000)
            
            filas = page.locator("div[data-testid='wcl-statistics']").all()
            for fila in filas:
                cat_el = fila.locator("div[data-testid='wcl-statistics-category']").first
                if cat_el.count() > 0:
                    categoria = cat_el.text_content().strip()
                    
                    home_el = fila.locator("div[class*='wcl-homeValue']").first
                    away_el = fila.locator("div[class*='wcl-awayValue']").first
                    
                    val_home = home_el.text_content().strip() if home_el.count() > 0 else "0"
                    val_away = away_el.text_content().strip() if away_el.count() > 0 else "0"
                    
                    datos_partido["Stats"][f"{categoria} (L)"] = val_home
                    datos_partido["Stats"][f"{categoria} (V)"] = val_away
    except Exception:
        pass
    finally:
        if page:
            page.close()
            del page  # Eliminar referencia para que Python limpie la RAM
            gc.collect()  # <--- Forzar vaciado de RAM al instante
            
    return datos_partido

# --- 3. CONTENEDOR DINÁMICO AUTOMÁTICO (FRAGMENT) ---
@st.fragment
def contenedor_monitoreo_vivo():
    """Este bloque se ejecuta de forma independiente y se auto-refresca cada 60 segundos."""
    st.caption(f"🔄 Última actualización del sistema: **{time.strftime('%H:%M:%S')}** (Próximo escaneo automático en 1 min)")
    
    estado_placeholder = st.empty()
    barra_placeholder = st.empty()
    tabla_placeholder = st.empty()

    estado_placeholder.info("Conectando con la sección EN DIRECTO desde el navegador camuflado...")
    
    with sync_playwright() as p:
        browser = None
        context = None
        try:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--single-process"] # <-- single-process ahorra mucha RAM
            )
            
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                viewport={'width': 1280, 'height': 720},
                locale="es-PE"
            )
            
            main_page = context.new_page()
            stealth_sync(main_page)
            
            main_page.goto("https://www.flashscore.pe/", wait_until="domcontentloaded")
            
            boton_directo = main_page.locator("//div[contains(@class, 'filters__text') and text()='EN DIRECTO']")
            boton_directo.wait_for(state="visible", timeout=10000)
            boton_directo.click()
            
            time.sleep(3.0)
            
            partidos_elementos = main_page.locator("div[id^='g_1_']").all()
            
            if not partidos_elementos:
                estado_placeholder.warning("No se encontraron partidos en directo activos en este momento.")
            else:
                # 🛑 Limitamos el escaneo a un máximo de 10-15 partidos simultáneos para que la RAM de Streamlit no explote
                partidos_a_escanear = partidos_elementos[:15]
                
                estado_placeholder.success(f"Analizando los primeros {len(partidos_a_escanear)} encuentros activos (Optimización de RAM)...")
                
                barra_progreso = barra_placeholder.progress(0)
                lista_registros_finales = []
                
                for idx, fila in enumerate(partidos_a_escanear):
                    id_completo = fila.get_attribute("id")
                    id_partido = id_completo.split('_')[-1]
                    url_match_stats = f"https://www.flashscore.pe/partido/{id_partido}/#/resumen/estadisticas"
                    
                    local_el = fila.locator("div[class*='home'][class*='participant']").first
                    away_el = fila.locator("div[class*='away'][class*='participant']").first
                    
                    nom_local = local_el.text_content().strip() if local_el.count() > 0 else "Local"
                    nom_visitante = away_el.text_content().strip() if away_el.count() > 0 else "Visitante"
                    
                    resultado_profundo = extraer_estadisticas_partido(context, url_match_stats)
                    
                    registro = {
                        "Partido en Vivo": f"{nom_local} vs {nom_visitante}",
                        "Marcador": resultado_profundo["Marcador"],
                        "Tiempo/Estado": resultado_profundo["Tiempo/Estado"],
                        "Minuto": resultado_profundo["Minuto"]
                    }
                    registro.update(resultado_profundo["Stats"])
                    lista_registros_finales.append(registro)
                    
                    barra_progreso.progress((idx + 1) / len(partidos_a_escanear))
                    time.sleep(0.5) # Pausa pequeña para no estresar la CPU
                
                barra_placeholder.empty()
                estado_placeholder.empty()
                
                df_final = pd.DataFrame(lista_registros_finales).fillna("-")
                columnas_fijas = ["Partido en Vivo", "Marcador", "Tiempo/Estado", "Minuto"]
                columnas_stats = [col for col in df_final.columns if col not in columnas_fijas]
                df_final = df_final[columnas_fijas + columnas_stats]
                
                tabla_placeholder.dataframe(df_final, use_container_width=True)
                
        except Exception as e:
            estado_placeholder.error(f"Error en la iteración actual: {str(e)}")
        finally:
            if context:
                context.close()
            if browser:
                browser.close()
            gc.collect() # Limpieza final de RAM

    time.sleep(60)
    st.rerun()

# --- 4. RENDERIZADO PRINCIPAL ---
st.write("### 📈 Cuadro de Control General (Actualización Automática)")
contenedor_monitoreo_vivo()
