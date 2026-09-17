import streamlit as st
import pandas as pd
import subprocess
import sys
import time
from playwright.sync_api import sync_playwright

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


# --- EXTRACCIÓN GARANTIZADA: CUOTAS PRIMERO, LUEGO ESTADÍSTICAS ---
def extraer_detalle_partido(page, id_partido):
    url = f"https://www.flashscore.pe/partido/{id_partido}/"
    
    resultado = {
        "Marcador": "- - -",
        "Cuotas": "- - -",
        "Tiempo/Estado": "-",
        "Minuto": "-",
        "Stats": {}
    }

    try:
        page.goto(url, timeout=35000, wait_until="domcontentloaded")

        # 1. Esperar encabezado del partido
        try:
            page.wait_for_selector("div.detailScore__wrapper", timeout=6000)
        except Exception:
            pass

        # 2. PASO CRÍTICO: EXTRAER CUOTAS ANTES DE CUALQUIER CLIC
        # Esperar a que el bloque o celdas de cuotas aparezcan en el DOM
        try:
            page.wait_for_selector('[data-testid="wcl-oddsValue"], [data-analytics-context="widget-match-summary-odds"]', timeout=3500)
        except Exception:
            pass

        cuotas_extraidas = page.evaluate('''() => {
            // Estrategia 1: Buscar botones semánticos 1, X, 2
            const c1 = document.querySelector('[data-analytics-element="ODDS_COMPARISONS_ODD_CELL_1"] [data-testid="wcl-oddsValue"]');
            const cX = document.querySelector('[data-analytics-element="ODDS_COMPARISONS_ODD_CELL_2"] [data-testid="wcl-oddsValue"]');
            const c2 = document.querySelector('[data-analytics-element="ODDS_COMPARISONS_ODD_CELL_3"] [data-testid="wcl-oddsValue"]');

            if (c1 && cX && c2) {
                const v1 = c1.innerText.trim();
                const vx = cX.innerText.trim();
                const v2 = c2.innerText.trim();
                if (v1 && vx && v2 && !isNaN(parseFloat(v1))) {
                    return `1:${v1} X:${vx} 2:${v2}`;
                }
            }

            // Estrategia 2: Fila contenedora wclOddsRow
            const fila = document.querySelector(".wclOddsRow, [class*='wclOddsRow']");
            if (fila) {
                const vals = Array.from(fila.querySelectorAll('[data-testid="wcl-oddsValue"]'))
                                  .map(el => el.innerText.trim())
                                  .filter(t => t && !isNaN(parseFloat(t)));
                if (vals.length >= 3) {
                    return `1:${vals[0]} X:${vals[1]} 2:${vals[2]}`;
                }
            }

            // Estrategia 3: Cualquier bloque widget-match-summary-odds
            const bloque = document.querySelector('[data-analytics-context="widget-match-summary-odds"]');
            if (bloque) {
                const vals = Array.from(bloque.querySelectorAll('[data-testid="wcl-oddsValue"]'))
                                  .map(el => el.innerText.trim())
                                  .filter(t => t && !isNaN(parseFloat(t)));
                if (vals.length >= 3) {
                    return `1:${vals[0]} X:${vals[1]} 2:${vals[2]}`;
                }
            }

            return "- - -";
        }''')
        
        resultado["Cuotas"] = cuotas_extraidas

        # 3. NAVEGAR A ESTADÍSTICAS
        try:
            tab_stats = page.locator('a[data-analytics-alias="match-statistics"], a[role="tab"]:has-text("Estadísticas")')
            if tab_stats.count() > 0:
                clases = tab_stats.first.get_attribute("class") or ""
                if "active" not in clases:
                    tab_stats.first.click(force=True)
                    time.sleep(0.8)
        except Exception:
            pass

        # Asegurar sub-pestaña "Partido" (alias 74)
        try:
            tab_partido_completo = page.locator('a[data-analytics-alias="74"], a:has-text("Partido")')
            if tab_partido_completo.count() > 0:
                clases_sub = tab_partido_completo.first.get_attribute("class") or ""
                if "active" not in clases_sub:
                    tab_partido_completo.first.click(force=True)
                    time.sleep(0.5)
        except Exception:
            pass

        # 4. ESPERAR Y EXTRAER ESTADÍSTICAS PRINCIPALES
        try:
            page.wait_for_selector('[data-testid="statGroup"], [data-testid="wcl-statistics"]', timeout=5000)
        except Exception:
            time.sleep(1)

        payload = page.evaluate('''() => {
            const data = {
                marcador: "- - -",
                tiempo: "-",
                minuto: "-",
                stats: {}
            };

            const elMarcador = document.querySelector("div.detailScore__wrapper");
            if (elMarcador) data.marcador = elMarcador.innerText.replace(/\\n/g, " ").trim();

            const elTiempo = document.querySelector("span.fixedHeaderDuel__detailStatus");
            if (elTiempo) data.tiempo = elTiempo.innerText.trim();

            const elMinuto = document.querySelector("span.eventTime");
            if (elMinuto) data.minuto = elMinuto.innerText.trim();

            // Ubicar exclusivamente el bloque de Estadísticas Principales
            const grupos = Array.from(document.querySelectorAll('[data-testid="statGroup"]'));
            let targetGroup = grupos.find(g => {
                const header = g.querySelector('[data-testid="wcl-headerSection-text"]');
                return header && header.innerText.toLowerCase().includes("principal");
            }) || grupos[0] || document.querySelector('.section--teamStats') || document.body;

            if (targetGroup) {
                // Filas estándar
                const filas = targetGroup.querySelectorAll('[data-testid="wcl-statistics"], [class*="wcl-labelRow_"]');
                filas.forEach(f => {
                    const nombreEl = f.querySelector('[class*="wcl-name_"]') || f.querySelector('[class*="wcl-label_"]') || f.querySelector('[data-testid*="category"]');
                    const valores = Array.from(f.querySelectorAll('[class*="wcl-value_"]')).map(v => v.innerText.trim());
                    if (nombreEl && valores.length >= 2) {
                        const nombre = nombreEl.innerText.trim();
                        if (nombre) {
                            data.stats[`${nombre} (L)`] = valores[0];
                            data.stats[`${nombre} (V)`] = valores[valores.length - 1];
                        }
                    }
                });

                // Barras de remates
                const shotBars = targetGroup.querySelectorAll('[class*="wcl-shotOnTargetStats_"]');
                shotBars.forEach(sb => {
                    const lbl = sb.querySelector('[class*="wcl-label_"]');
                    const valores = Array.from(sb.querySelectorAll('[class*="wcl-value_"]')).map(v => v.innerText.trim());
                    if (lbl && valores.length >= 2) {
                        const nombre = lbl.innerText.trim();
                        data.stats[`${nombre} (L)`] = valores[0];
                        data.stats[`${nombre} (V)`] = valores[valores.length - 1];
                    }
                });

                // Córneres y tarjetas
                const badges = targetGroup.querySelectorAll('[class*="wcl-incidentValueBadge_"]');
                badges.forEach(b => {
                    const spans = Array.from(b.querySelectorAll("span")).map(s => s.innerText.trim());
                    const svg = b.querySelector("svg");
                    if (spans.length >= 2 && svg) {
                        const tid = (svg.getAttribute("data-testid") || "").toLowerCase();
                        let nombre = "Incidentes";
                        if (tid.includes("corner")) nombre = "Córneres";
                        else if (tid.includes("yellow")) nombre = "Tarjetas amarillas";
                        else if (tid.includes("red")) nombre = "Tarjetas rojas";

                        data.stats[`${nombre} (L)`] = spans[0];
                        data.stats[`${nombre} (V)`] = spans[spans.length - 1];
                    }
                });
            }

            return data;
        }''')

        resultado["Marcador"] = payload.get("marcador", "- - -")
        resultado["Tiempo/Estado"] = payload.get("tiempo", "-")
        resultado["Minuto"] = payload.get("minuto", "-")
        resultado["Stats"] = payload.get("stats", {})

    except Exception as e:
        print(f"Error procesando {id_partido}: {e}")

    return resultado


# --- INTERFAZ STREAMLIT ---
st.set_page_config(page_title="Monitor de Estadísticas en Vivo", layout="wide")
st.title("📊 Monitor de Estadísticas en Vivo")

if st.button("🔄 Ejecutar Escaneo Completo"):
    with st.spinner("Escaneando datos y cuotas en tiempo real..."):
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled"
                ]
            )

            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={"width": 1366, "height": 768}
            )

            context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")

            main = context.new_page()

            try:
                main.goto("https://www.flashscore.pe/", timeout=35000, wait_until="domcontentloaded")

                # Clic en "EN DIRECTO"
                btn_live = main.locator("//div[contains(@class, 'filters__text') and text()='EN DIRECTO']")
                btn_live.wait_for(timeout=15000)
                btn_live.click()
                time.sleep(2.5)

                # Obtener listado de partidos
                partidos_base = main.evaluate('''() => {
                    const filas = Array.from(document.querySelectorAll("div[id^='g_1_']"));
                    return filas.map(f => {
                        const h = f.querySelector("div[class*='home'][class*='participant']");
                        const a = f.querySelector("div[class*='away'][class*='participant']");
                        return {
                            id: f.id.replace("g_1_", ""),
                            nombre: `${h ? h.innerText.trim() : 'Local'} vs ${a ? a.innerText.trim() : 'Visitante'}`
                        };
                    });
                }''')

                if partidos_base:
                    res = []
                    limite = min(len(partidos_base), 10)
                    progreso = st.progress(0)

                    detalle_page = context.new_page()

                    for i, base in enumerate(partidos_base[:limite]):
                        detalle = extraer_detalle_partido(detalle_page, base["id"])

                        fila = {
                            "Partido en Vivo": base["nombre"],
                            "Marcador": detalle["Marcador"],
                            "Cuotas": detalle["Cuotas"],
                            "Tiempo/Estado": detalle["Tiempo/Estado"],
                            "Minuto": detalle["Minuto"]
                        }
                        fila.update(detalle["Stats"])
                        res.append(fila)

                        progreso.progress((i + 1) / limite)

                    detalle_page.close()

                    st.dataframe(pd.DataFrame(res).fillna("-"), use_container_width=True)
                    st.balloons()
                else:
                    st.warning("No se encontraron partidos en directo actualmente.")

            except Exception as e:
                st.error(f"Error en el escaneo: {e}")
            finally:
                browser.close()
