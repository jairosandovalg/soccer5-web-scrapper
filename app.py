import os
import sys
import streamlit as st
import pandas as pd
import time
import subprocess
import requests

# --- 1. COMPROBACIÓN E INSTALACIÓN INTERNA DIRECTA ---
if 'navegador_configurado' not in st.session_state:
    with st.spinner("Inicializando binarios de Playwright en el servidor... (Solo la primera vez)"):
        try:
            subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
            st.session_state['navegador_configurado'] = True
        except Exception as e:
            st.error(f"Error al inicializar el entorno del navegador: {str(e)}")
            st.stop()
            
    from playwright.sync_api import sync_playwright
    st.rerun()

from playwright.sync_api import sync_playwright

# Configuración de la interfaz de Streamlit
st.set_page_config(page_title="Bot de Estadísticas Final", layout="wide")
st.title("📊 Monitor de Estadísticas en Vivo - Flashscore & Telegram")
st.subheader("Análisis de métricas en tiempo real con alertas automatizadas")

# --- 2. FUNCIÓN DE ENVÍO A TELEGRAM (CONFIGURADA) ---
def enviar_resumen_telegram(df):
    """Transforma el DataFrame de métricas vivas en un mensaje estructurado y lo envía."""
    
    # 🔐 TUS CREDENCIALES DE TELEGRAM (Vinculadas a @Soctatbot y tu ID personal de entrega)
    TOKEN = "892395866:AAES1dc4LAsedUKUsGR4p5D1SkaMt7nKyes"
    CHAT_ID = "7272170952"  # <-- Tu ID de User Info Get ID configurado de forma definitiva

    if not df.empty:
        mensaje = f"🚀 *ACTUALIZACIÓN EN VIVO* 🚀\n🕒 _Hora:_ {time.strftime('%H:%M:%S')}\n\n"
        
        # Iterar sobre las filas para construir alertas compactas por partido
        for _, fila in df.iterrows():
            mensaje += f"⚽ *{fila['Partido en Vivo']}*\n"
            mensaje += f"🏆 *Marcador:* `{fila['Marcador']}` | *Min:* `{fila['Minuto']}`\n"
            
            # Extraer estadísticas dinámicas si existen
            stats_disponibles = []
            for col in df.columns:
                if col not in ["Partido en Vivo", "Marcador", "Tiempo/Estado", "Minuto"] and fila[col] != "-":
                    stats_disponibles.append(f"• {col}: {fila[col]}")
            
            if stats_disponibles:
                # Limitamos a mostrar las estadísticas clave para evitar mensajes gigantescos
                mensaje += "\n".join(stats_disponibles[:6]) + "\n"
            
            mensaje += "───────────────────\n"
        
        # Envío vía API de Telegram
        url_api = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": mensaje,
            "parse_mode": "Markdown"
        }
        
        try:
            response = requests.post(url_api, json=payload, timeout=10)
            if response.status_code == 200:
                st.toast("✅ Resumen enviado con éxito a Telegram", icon="✉️")
            else:
                st.sidebar.error(f"Telegram Error: {response.text}")
        except Exception as e:
            st.sidebar.error(f"Error de conexión con Telegram: {str(e)}")

# --- 3. EXTRACCIÓN DE DATOS DE PARTIDOS ---
def extraer_estadisticas_partido(context, url_partido):
    datos_partido = {"Marcador": "- - -", "Tiempo/Estado": "-", "Minuto": "-", "Stats": {}}
    page = None
    try:
        page = context.new_page()
        page.route("**/*", lambda route: route.abort() if route.request.resource_type in ["image", "font", "stylesheet"] else route.continue_())
        
        page.goto(url_partido, timeout=7000, wait_until="domcontentloaded")
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
        if page: page.close()
    return datos_partido

# --- 4. CONTENEDOR DINÁMICO AUTOMÁTICO (FRAGMENT) ---
@st.fragment
def contenedor_monitoreo_vivo():
    st.caption(f"🔄 Última actualización del sistema: **{time.strftime('%H:%M:%S')}** (Próximo escaneo automático en 1 min)")
    
    estado_placeholder = st.empty()
    barra_placeholder = st.empty()
    tabla_placeholder = st.empty()

    estado_placeholder.info("Conectando con la sección EN DIRECTO desde el navegador virtual...")
    
    with sync_playwright() as p:
        browser = None
        context = None
        try:
            browser = p.firefox.launch(headless=True, args=["--no-sandbox"])
            context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
            
            main_page = context.new_page()
            main_page.goto("https://www.flashscore.pe/", wait_until="domcontentloaded")
            
            boton_directo = main_page.locator("//div[contains(@class, 'filters__text') and text()='EN DIRECTO']")
            boton_directo.wait_for(state="visible", timeout=10000)
            boton_directo.click()
            
            time.sleep(2.5)
            partidos_elementos = main_page.locator("div[id^='g_1_']").all()
            
            if not partidos_elementos:
                estado_placeholder.warning("No se encontraron partidos en directo activos en este momento.")
            else:
                # Limitar a los primeros 8 partidos para evitar saturación y spam en Telegram
                partidos_filtrados = partidos_elementos[:8] 
                estado_placeholder.success(f"Analizando {len(partidos_filtrados)} encuentros activos...")
                
                barra_progreso = barra_placeholder.progress(0)
                lista_registros_finales = []
                
                for idx, fila in enumerate(partidos_filtrados):
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
                    
                    barra_progreso.progress((idx + 1) / len(partidos_filtrados))
                
                barra_placeholder.empty()
                estado_placeholder.empty()
                
                if lista_registros_finales:
                    df_final = pd.DataFrame(lista_registros_finales).fillna("-")
                    columnas_fijas = ["Partido en Vivo", "Marcador", "Tiempo/Estado", "Minuto"]
                    columnas_stats = [col for col in df_final.columns if col not in columnas_fijas]
                    df_final = df_final[columnas_fijas + columnas_stats]
                    
                    # Mostrar en la web de Streamlit
                    tabla_placeholder.dataframe(df_final, use_container_width=True)
                    
                    # Enviar reporte automático a Telegram
                    enviar_resumen_telegram(df_final)
                
        except Exception as e:
            estado_placeholder.error(f"Error en la sesión del navegador: {str(e)}")
        finally:
            if context: context.close()
            if browser: browser.close()

    time.sleep(60)
    st.rerun()

# --- 5. RENDERIZADO PRINCIPAL ---
st.write("### 📈 Cuadro de Control General (Actualización Automática)")
contenedor_monitoreo_vivo()
