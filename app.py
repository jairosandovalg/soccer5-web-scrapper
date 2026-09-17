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


# --- EXTRACCIÓN ROBUSTA EN EL NAVEGADOR (JS NATIVO) ---
def extraer_datos_partido(page, id_partido):
    url = f"https://www.flashscore.pe/partido/{id_partido}/#/resumen/estadisticas"
    
    datos = {
        "Marcador": "- - -",
        "Cuotas": "- - -",
        "Tiempo/Estado": "-",
        "Minuto": "-",
        "Stats": {}
    }

    try:
        page.goto(url, timeout=35000, wait_until="domcontentloaded")

        # 1. Esperar al marcador
        try:
            page.wait_for_selector("div.detailScore__wrapper", timeout=7000)
        except Exception:
            pass

        # 2. Si no abrió la pestaña de estadísticas directamente por el hash, forzar el clic
        try:
            tab_stats = page.locator('a[data-analytics-alias="match-statistics"], a[role="tab"]:has-text("Estadísticas")')
            if tab_stats.count() > 0:
                clases = tab_stats.first.get_attribute("class") or ""
                if "active" not in clases:
                    tab_stats.first.click(force=True)
        except Exception:
            pass

        # 3. Espera activa para que React inyecte las estadísticas o cuotas
        try:
            page.wait_for_selector('[data-testid="statGroup"], [data-testid="wcl-statistics"], [data-testid="wcl-oddsValue"]', timeout=6000)
        except Exception:
            time.sleep(1.5)

        # 4. EXTRACCIÓN MEDIANTE JAVASCRIPT DIRECTO (Garantiza acceso al DOM hidratado)
        payload = page.evaluate('''() => {
            const res = {
                marcador: "- - -",
                tiempo: "-",
                minuto: "-",
                cuotas: "- - -",
                stats: {}
            };

            // Marcador
            const elMarcador = document.querySelector("div.detailScore__wrapper");
            if (elMarcador) res.marcador = elMarcador.innerText.replace(/\\n/g, " ").trim();

            // Tiempo y Minuto
            const elTiempo = document.querySelector("span.fixedHeaderDuel__detailStatus");
            if (elTiempo) res.tiempo = elTiempo.innerText.trim();

            const elMinuto = document.querySelector("span.eventTime");
            if (elMinuto) res.minuto = elMinuto.innerText.trim();

            // Cuotas 1X2
            const odd1 = document.querySelector('[data-analytics-element="ODDS_COMPARISONS_ODD_CELL_1"] [data-testid="wcl-oddsValue"]');
            const oddX = document.querySelector('[data-analytics-element="ODDS_COMPARISONS_ODD_CELL_2"] [data-testid="wcl-oddsValue"]');
            const odd2 = document.querySelector('[data-analytics-element="ODDS_COMPARISONS_ODD_CELL_3"] [data-testid="wcl-oddsValue"]');

            if (odd1 && oddX && odd2) {
                res.cuotas = `1:${odd1.innerText.trim()} X:${oddX.innerText.trim()} 2:${odd2.innerText.trim()}`;
            } else {
                const todosOdds = Array.from(document.querySelectorAll('[data-testid="wcl-oddsValue"]')).map(e => e.innerText.trim()).filter(Boolean);
                if (todosOdds.length >= 3) {
                    res.cuotas = `1:${todosOdds[0]} X:${todosOdds[1]} 2:${todosOdds[2]}`;
                }
            }

            // Estadísticas Principales
            // Buscar el primer statGroup que contenga el texto "principal" o el primero disponible
            const grupos = Array.from(document.querySelectorAll('[data-testid="statGroup"]'));
            let targetGroup = grupos.find(g => {
                const t = g.querySelector('[data-testid="wcl-headerSection-text"]');
                return t && t.innerText.toLowerCase().includes("principal");
            }) || grupos[0] || document.querySelector('.section--teamStats') || document.body;

            if (targetGroup) {
                // A. Filas estándar (xG, Posesión, etc.)
                const filas = targetGroup.querySelectorAll('[data-testid="wcl-statistics"], [class*="wcl-labelRow_"]');
                filas.forEach(f => {
                    const nombreEl = f.querySelector('[class*="wcl-name_"]') || f.querySelector('[class*="wcl-label_"]');
                    const vals = Array.from(f.querySelectorAll('[class*="wcl-value_"]')).map(v => v.innerText.trim());
                    if (nombreEl && vals.length >= 2) {
                        const nombre = nombreEl.innerText.trim();
                        if (nombre) {
                            res.stats[`${nombre} (L)`] = vals[0];
                            res.stats[`${nombre} (V)`] = vals[vals.length - 1];
                        }
                    }
                });

                // B. Remates a puerta (wcl-shotOnTargetStats_)
                const shotBars = targetGroup.querySelectorAll('[class*="wcl-shotOnTargetStats_"]');
                shotBars.forEach(sb => {
                    const lbl = sb.querySelector('[class*="wcl-label_"]');
                    const vals = Array.from(sb.querySelectorAll('[class*="wcl-value_"]')).map(v => v.innerText.trim());
                    if (lbl && vals.length >= 2) {
                        const nombre = lbl.innerText.trim();
                        res.stats[`${nombre} (L)`] = vals[0];
                        res.stats[`${nombre} (V)`] = vals[vals.length - 1];
                    }
                });

                // C. Córneres y tarjetas (Badges SVG)
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
                        
                        res.stats[`${nombre} (L)`] = spans[0];
                        res.stats[`${nombre} (V)`] = spans[spans.length - 1];
                    }
                });
            }

            return res;
        }''')

        datos["Marcador"] = payload.get("marcador", "- - -")
        datos["Tiempo/Estado"] = payload.get("tiempo", "-")
        datos["Minuto"] = payload.get("minuto", "-")
        datos["Cuotas"] = payload.get("cuotas", "- - -")
        datos["Stats"] = payload.get("stats", {})

    except Exception as e:
        print(f"Error procesando {id_partido}: {e}")

    return datos


# --- INTERFAZ DE USUARIO STREAMLIT ---
st.set_page_config(page_title="Monitor de Estadísticas en Vivo", layout="wide")
st.title("📊 Monitor de Estadísticas en Vivo")

if st.button("🔄 Ejecutar Escaneo Completo"):
    with st.spinner("Escaneando datos en directo..."):
        with sync_playwright() as p:
            # Configuración anti-detección básica para evitar bloqueos
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
                viewport={"width": 1280, "height": 800}
            )

            # Ocultar rastro de automatización
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)

            page = context.new_page()

            try:
                page.goto("https://www.flashscore.pe/", timeout=40000, wait_until="domcontentloaded")

                # Clic en "EN DIRECTO"
                btn_live = page.locator("//div[contains(@class, 'filters__text') and text()='EN DIRECTO']")
                btn_live.wait_for(timeout=15000)
                btn_live.click()
                time.sleep(3)

                # Obtener la lista de partidos en directo
                partidos_ids = page.evaluate('''() => {
                    const divs = Array.from(document.querySelectorAll("div[id^='g_1_']"));
                    return divs.map(d => {
                        const h = d.querySelector("div[class*='home'][class*='participant']");
                        const a = d.querySelector("div[class*='away'][class*='participant']");
                        return {
                            id: d.id.replace("g_1_", ""),
                            nombre: `${h ? h.innerText.trim() : 'Local'} vs ${a ? a.innerText.trim() : 'Visitante'}`
                        };
                    });
                }''')

                if partidos_ids:
                    res = []
                    limite = min(len(partidos_ids), 10)
                    progreso = st.progress(0)

                    # Reutilizar una sola pestaña dedicada al detalle para ahorrar RAM en Streamlit
                    detalle_page = context.new_page()

                    for i, item in enumerate(partidos_ids[:limite]):
                        data = extraer_datos_partido(detalle_page, item["id"])

                        fila = {
                            "Partido en Vivo": item["nombre"],
                            "Marcador": data["Marcador"],
                            "Cuotas": data["Cuotas"],
                            "Tiempo/Estado": data["Tiempo/Estado"],
                            "Minuto": data["Minuto"]
                        }
                        fila.update(data["Stats"])
                        res.append(fila)

                        progreso.progress((i + 1) / limite)

                    detalle_page.close()

                    df = pd.DataFrame(res).fillna("-")
                    st.dataframe(df, use_container_width=True)
                    st.balloons()
                else:
                    st.warning("No se encontraron partidos en directo actualmente.")

            except Exception as e:
                st.error(f"Error durante el escaneo: {e}")
            finally:
                browser.close()
