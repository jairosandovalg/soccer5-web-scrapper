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
        # Usar networkidle o al menos asegurar carga tras domcontentloaded
        page.goto(url_partido, timeout=30000, wait_until="domcontentloaded")

        # 1. Esperar encabezado básico
        try:
            page.wait_for_selector("div.detailScore__wrapper", timeout=6000)
        except Exception:
            pass

        # 2. Asegurar que estamos en la pestaña ESTADÍSTICAS
        tab_stats = page.locator('a[data-analytics-alias="match-statistics"], a[role="tab"]:has-text("Estadísticas")')
        if tab_stats.count() > 0:
            try:
                clases = tab_stats.first.get_attribute("class") or ""
                if "active" not in clases:
                    tab_stats.first.click(force=True)
            except Exception:
                pass

        # Esperar a que al menos un grupo de estadísticas o mensaje aparezca
        try:
            page.wait_for_selector('[data-testid="statGroup"], [data-testid="wcl-statistics"], .section--teamStats', timeout=5000)
        except Exception:
            pass

        soup = BeautifulSoup(page.content(), "html.parser")

        # Marcador y tiempos
        score = soup.select_one("div.detailScore__wrapper")
        if score:
            datos_partido["Marcador"] = score.get_text(separator=" ", strip=True)

        status = soup.select_one("span.fixedHeaderDuel__detailStatus")
        if status:
            datos_partido["Tiempo/Estado"] = status.get_text(strip=True)

        minuto = soup.select_one("span.eventTime")
        if minuto:
            datos_partido["Minuto"] = minuto.get_text(strip=True)

        # 3. EXTRACCIÓN TOTAL DE ESTADÍSTICAS (Agnóstica del tab 74, 12 o 13)
        # Seleccionamos el bloque contenedor de estadísticas o el cuerpo completo si no hay wrapper específico
        contenedor = (
            soup.select_one('div.tabContent__match-statistics') or 
            soup.select_one('div.section--teamStats') or 
            soup
        )

        # A) Filas clásicas (data-testid="wcl-statistics")
        for fila in contenedor.select('[data-testid="wcl-statistics"]'):
            # Nombre de la estadística
            nombre_elem = (
                fila.select_one('[class*="wcl-name_"]') or
                fila.select_one('[class*="wcl-label_"]') or
                fila.select_one('[data-testid*="category"]')
            )
            # Valores (primer valor = Local, último valor = Visitante)
            vals = fila.select('[class*="wcl-value_"]')
            
            if nombre_elem and len(vals) >= 2:
                nombre = nombre_elem.get_text(strip=True)
                val_l = vals[0].get_text(strip=True)
                val_v = vals[-1].get_text(strip=True)
                if nombre:
                    datos_partido["Stats"][f"{nombre} (L)"] = val_l
                    datos_partido["Stats"][f"{nombre} (V)"] = val_v

        # B) Barras de remates y tiros al arco (wcl-shotOnTargetStats_)
        for shot_bar in contenedor.select('[class*="wcl-shotOnTargetStats_"]'):
            label_el = shot_bar.select_one('[class*="wcl-label_"]')
            vals = shot_bar.select('[class*="wcl-value_"]')
            if label_el and len(vals) >= 2:
                nombre = label_el.get_text(strip=True)
                datos_partido["Stats"][f"{nombre} (L)"] = vals[0].get_text(strip=True)
                datos_partido["Stats"][f"{nombre} (V)"] = vals[-1].get_text(strip=True)

        # C) Badges de incidentes con iconos SVG (Córneres, Tarjetas)
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

        # D) Extracción universal de respaldo (cualquier fila de 3 elementos: Valor - Etiqueta - Valor)
        for row in contenedor.select('[class*="wcl-labelRow_"]'):
            vals = row.select('[class*="wcl-value_"]')
            lbl = row.select_one('[class*="wcl-name_"]') or row.select_one('[class*="wcl-label_"]')
            if lbl and len(vals) >= 2:
                nombre = lbl.get_text(strip=True)
                key_l = f"{nombre} (L)"
                if key_l not in datos_partido["Stats"]:
                    datos_partido["Stats"][key_l] = vals[0].get_text(strip=True)
                    datos_partido["Stats"][f"{nombre} (V)"] = vals[-1].get_text(strip=True)

        # 4. EXTRACCIÓN DE CUOTAS (Sin romper la vista)
        # Intentar leer cuotas del DOM actual
        c1 = soup.select_one('[data-analytics-element="ODDS_COMPARISONS_ODD_CELL_1"] [data-testid="wcl-oddsValue"]')
        cx = soup.select_one('[data-analytics-element="ODDS_COMPARISONS_ODD_CELL_2"] [data-testid="wcl-oddsValue"]')
        c2 = soup.select_one('[data-analytics-element="ODDS_COMPARISONS_ODD_CELL_3"] [data-testid="wcl-oddsValue"]')

        if c1 and cx and c2:
            datos_partido["Cuotas"] = f"1:{c1.get_text(strip=True)} X:{cx.get_text(strip=True)} 2:{c2.get_text(strip=True)}"
        else:
            # Si no estaban visibles, buscar en cualquier celda de cuotas presente
            raw_odds = [o.get_text(strip=True) for o in soup.select('[data-testid="wcl-oddsValue"]') if o.get_text(strip=True)]
            if len(raw_odds) >= 3:
                datos_partido["Cuotas"] = f"1:{raw_odds[0]} X:{raw_odds[1]} 2:{raw_odds[2]}"

    except Exception as e:
        print(f"Error procesando {url_partido}: {e}")
    finally:
        if page:
            page.close()

    return datos_partido
