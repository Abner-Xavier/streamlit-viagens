import json
from flask import Flask, render_template, request, Response
from flask_cors import CORS
from playwright.sync_api import sync_playwright
from datetime import datetime, timedelta
import re
import time
import random

app = Flask(__name__)
CORS(app)  # Libera o acesso para o frontend


# ==============================================================================
# 🏨 SCRAPER HOTELS
# ==============================================================================
def raspar_booking_master(page, data_str):
    quartos_encontrados = {}
    try:
        page.locator('button[aria-label="Dismiss"]').click(timeout=1500)
    except:
        pass

    try:
        page.wait_for_selector('#hprt-table', state='visible', timeout=10000)
    except:
        return []

    rows = page.locator('#hprt-table tbody tr').all()
    for row in rows:
        if not row.is_visible(): continue
        texto_bruto = row.inner_text()
        texto_limpo = " ".join(texto_bruto.split()).lower()
        if "not available" in texto_limpo: continue

        nome_el = row.locator('.hprt-roomtype-link, span.hprt-roomtype-icon-link').first
        if not nome_el.is_visible(): continue
        nome_item = nome_el.inner_text().strip()

        preco_el = row.locator('.bui-price-display__value, .prco-val').first
        preco = preco_el.inner_text().strip() if preco_el.is_visible() else "N/A"

        qtd_num = 10
        qtd_str = "9+"
        match = re.search(r'(?:have|only|restam|resta|só mais)\s+(\d+)\s+(?:left|restam|sobrando|room|quarto)',
                          texto_limpo)
        if match:
            qtd_num = int(match.group(1))
            qtd_str = str(qtd_num)

        if nome_item not in quartos_encontrados or qtd_num < quartos_encontrados[nome_item]['sort_val']:
            quartos_encontrados[nome_item] = {
                "item": nome_item, "qtd": qtd_str, "sort_val": qtd_num,
                "preco": preco, "extra": "-"
            }
            match_m2 = re.search(r'(\d+)\s*m²', texto_bruto)
            if match_m2: quartos_encontrados[nome_item]['extra'] = f"{match_m2.group(1)} m²"

    return list(quartos_encontrados.values())


# ==============================================================================
# ✈️ SCRAPER FLIGHTS
# ==============================================================================
def raspar_booking_flights(page, classe_rota_nome, airlines_filter=""):
    voos_encontrados = []

    try:
        page.wait_for_selector('div[id^="flight-card-"], aside[data-testid="no_direct_flights_banner"]', timeout=15000)
    except:
        return []

    cards = page.locator('div[id^="flight-card-"]').all()

    filters = [f.strip().lower() for f in airlines_filter.split(',')] if airlines_filter else []
    abbrev_map = {'aa': 'american', 'ba': 'british', 'ua': 'united', 'dl': 'delta', 'as': 'alaska', 'la': 'latam'}

    for card in cards:
        if not card.is_visible(): continue

        try:
            texto_card = card.inner_text().lower()

            if "1 stop" in texto_card or "2 stops" in texto_card or "conexão" in texto_card or "parada" in texto_card:
                continue

            cia = "Cia Desconhecida"
            logo_url = ""

            try:
                images = card.locator('img').all()
                for img in images:
                    src = img.get_attribute("src") or ""
                    alt = img.get_attribute("alt") or ""
                    if "logo" in src.lower() or "carrier" in src.lower() or "airlines" in src.lower() or ".png" in src.lower():
                        logo_url = src
                        if alt and len(alt) < 30 and "logo" not in alt.lower():
                            cia = alt.strip()
                        break
            except:
                pass

            if cia == "Cia Desconhecida" or "·" in cia or len(cia) > 25:
                if logo_url:
                    logo_str = logo_url.lower()
                    if "aa.png" in logo_str:
                        cia = "American Airlines"
                    elif "ba.png" in logo_str:
                        cia = "British Airways"
                    elif "ua.png" in logo_str:
                        cia = "United Airlines"
                    elif "dl.png" in logo_str:
                        cia = "Delta Air Lines"
                    elif "as.png" in logo_str:
                        cia = "Alaska Airlines"
                    elif "la.png" in logo_str or "jj.png" in logo_str:
                        cia = "LATAM Airlines"
                    elif "ac.png" in logo_str:
                        cia = "Air Canada"
                    elif "cm.png" in logo_str:
                        cia = "Copa Airlines"
                    elif "am.png" in logo_str:
                        cia = "Aeromexico"
                    elif "ad.png" in logo_str:
                        cia = "Azul"
                    elif "g3.png" in logo_str:
                        cia = "GOL"
                    elif "af.png" in logo_str:
                        cia = "Air France"
                    elif "kl.png" in logo_str:
                        cia = "KLM"

            if cia == "Cia Desconhecida":
                try:
                    cia_el = card.locator(
                        '[data-testid="flight_card_carrier_0"], xpath=.//div/div[1]/div[1]/div[2]/div[2]').first
                    if cia_el.is_visible():
                        cia_text = cia_el.inner_text().strip()
                        if not ("·" in cia_text or ":" in cia_text):
                            cia = cia_text
                except:
                    pass

            if cia == "Cia Desconhecida" or "·" in cia:
                for known_cia in ["American Airlines", "United Airlines", "Delta Air Lines", "British Airways", "LATAM",
                                  "Alaska Airlines", "GOL", "Copa Airlines", "Air Canada"]:
                    if known_cia.lower() in texto_card:
                        cia = known_cia
                        break

            if "·" in cia or ":" in cia or "->" in cia or "→" in cia or not cia:
                cia = "Cia Desconhecida"

            if filters:
                matched = False
                cia_lower = cia.lower()
                logo_lower = logo_url.lower()

                for f in filters:
                    mapped = abbrev_map.get(f, f)
                    if mapped in cia_lower or f in cia_lower or f"/{f}.png" in logo_lower or mapped in texto_card:
                        matched = True
                        if cia == "Cia Desconhecida":
                            reverse_map = {'american': 'American Airlines', 'british': 'British Airways',
                                           'united': 'United Airlines', 'delta': 'Delta Air Lines',
                                           'alaska': 'Alaska Airlines', 'latam': 'LATAM Airlines'}
                            cia = reverse_map.get(mapped, f.title())
                        break

                if not matched: continue

            preco = "N/A"
            try:
                el_preco = card.locator('[data-testid="upt_price"]').first
                if el_preco.is_visible(): preco = el_preco.inner_text().strip()
            except:
                pass

            if preco == "N/A":
                match_price = re.search(r'US\$\s*[\d,.]+', card.inner_text())
                if match_price: preco = match_price.group(0)

            try:
                tempos = card.locator('xpath=.//div[contains(text(), "AM") or contains(text(), "PM")]').all()
                hora_ida = tempos[0].inner_text().strip() if len(tempos) > 0 else "??"
                hora_chegada = tempos[1].inner_text().strip() if len(tempos) > 1 else "??"
            except:
                hora_ida, hora_chegada = "??", "??"

            duracao = "--"
            try:
                el_duracao = card.locator('[data-testid="flight_card_segment_duration_0"]').first
                if el_duracao.is_visible(): duracao = el_duracao.inner_text().strip()
            except:
                pass

            if duracao == "--":
                match_dur = re.search(r'\d{1,2}h\s*\d{1,2}m', card.inner_text())
                if match_dur: duracao = match_dur.group(0)

            voo_numero = ""
            try:
                html_card = card.inner_html()
                match_voo = re.search(r'\b(AA|BA|UA|DL|AS|LA|G3|CM|AC|KL|AF)\s*(-|&nbsp;)?\s*(\d{2,4})\b', html_card,
                                      re.IGNORECASE)
                if match_voo: voo_numero = f"{match_voo.group(1).upper()}{match_voo.group(3)}"
            except:
                pass

            nome_item = f"{cia} ({hora_ida})"

            voos_encontrados.append({
                "item": nome_item,
                "cia": cia,
                "logo": logo_url,
                "hora_ida": hora_ida,
                "hora_chegada": hora_chegada,
                "duracao": duracao,
                "preco": preco,
                "voo_num": voo_numero,
                "extra": f"{classe_rota_nome}"
            })

        except Exception as e:
            continue

    return voos_encontrados


# ==============================================================================
# MOTOR DE BUSCA
# ==============================================================================
def motor_busca_generator(dados):
    resultados = []
    modo = dados.get('modo', 'hotel')
    datas = dados.get('datas', [])
    adultos_hotel = str(dados.get('adultos', '2'))
    airlines_filter = dados.get('airlines', '')

    mapa_classe = {'M': 'ECONOMY', 'W': 'PREMIUM_ECONOMY', 'J': 'BUSINESS', 'F': 'FIRST'}
    rotas = []

    orig1, dest1 = dados.get('origem1', '').upper(), dados.get('destino1', '').upper()
    classe1_url = mapa_classe.get(dados.get('classe1', 'F'), 'FIRST')
    if orig1 and dest1: rotas.append((orig1, dest1, classe1_url))

    orig2, dest2 = dados.get('origem2', '').upper(), dados.get('destino2', '').upper()
    classe2_url = mapa_classe.get(dados.get('classe2', 'F'), 'FIRST')
    if orig2 and dest2: rotas.append((orig2, dest2, classe2_url))

    # ENVELOPE DE SEGURANÇA TRY...EXCEPT PARA O PLAYWRIGHT
    try:
        with sync_playwright() as p:
            yield f"data: {json.dumps({'status': 'info', 'msg': '🚀 Iniciando navegador c/ defesas Anti-Bot e forçando USD...'})}\n\n"

            # HEADLESS=TRUE PARA EVITAR CRASHES POR FALTA DE MONITOR (EX: WSL/DOCKER)
            browser = p.chromium.launch(headless=True,
                                        args=["--start-maximized", "--disable-blink-features=AutomationControlled"])

            context = browser.new_context(
                viewport={"width": 1366, "height": 768},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="en-US",
                timezone_id="America/New_York",
                geolocation={"longitude": -74.006, "latitude": 40.7128},
                permissions=["geolocation"]
            )
            page = context.new_page()

            page.route("**/*", lambda route: route.continue_() if "airlines" in route.request.url else (
                route.abort() if route.request.resource_type in ["image", "media"] else route.continue_()))

            for data in datas:
                dt = datetime.strptime(data, "%Y-%m-%d")
                s_in = dt.strftime("%Y-%m-%d")

                try:
                    if modo == 'hotel':
                        url_base = dados['url'].split("?")[0] if "?" in dados['url'] else dados['url']
                        s_out = (dt + timedelta(days=1)).strftime("%Y-%m-%d")
                        link = f"{url_base}?checkin={s_in}&checkout={s_out}&group_adults={adultos_hotel}&no_rooms=1&selected_currency=USD&currency=USD&lang=en-us"

                        yield f"data: {json.dumps({'status': 'info', 'msg': f'🏨 Mapeando Hotel: {s_in}'})}\n\n"
                        page.goto(link, timeout=60000, wait_until="domcontentloaded")
                        lista = raspar_booking_master(page, s_in)
                        resultados.append({"data": s_in, "itens": lista})

                    else:
                        pax_ranges = list(range(1, 10))
                        rotas_do_dia = []

                        for index_rota, (r_orig, r_dest, r_classe) in enumerate(rotas):
                            tag_rota = f"{r_orig} ➔ {r_dest} | {r_classe.title().replace('_', ' ')}"
                            voos_da_rota = {}

                            for pax in pax_ranges:
                                link = f"https://flights.booking.com/flights/{r_orig}.AIRPORT-{r_dest}.AIRPORT/?type=ONEWAY&adults={pax}&cabinClass={r_classe}&from={r_orig}.AIRPORT&to={r_dest}.AIRPORT&depart={s_in}&sort=BEST&locale=en-us&currency=USD&selected_currency=USD&stops=0"

                                filtro_str = airlines_filter if airlines_filter else "Todos"
                                msg_log = f"🛫 {s_in} | {r_orig}-{r_dest} | {pax} PAX (Filtro: {filtro_str})"
                                yield f"data: {json.dumps({'status': 'info', 'msg': msg_log})}\n\n"

                                page.goto(link, timeout=60000, wait_until="domcontentloaded")

                                try:
                                    page.wait_for_selector(
                                        'div[id^="flight-card-"], aside[data-testid="no_direct_flights_banner"], h2:has-text("0 flight options"), #px-captcha',
                                        timeout=15000)
                                except:
                                    pass

                                if page.locator(
                                        '#px-captcha, iframe[src*="captcha"], h2:has-text("Confirm you are human")').is_visible():
                                    yield f"data: {json.dumps({'status': 'error', 'msg': '⚠️ Bloqueio Detectado! Resolva o Captcha no navegador (Aguardando 60s)...'})}\n\n"
                                    try:
                                        page.wait_for_selector(
                                            'div[id^="flight-card-"], h2:has-text("0 flight options")', timeout=60000)
                                        yield f"data: {json.dumps({'status': 'info', 'msg': '✅ Captcha resolvido! Retomando coleta...'})}\n\n"
                                    except:
                                        yield f"data: {json.dumps({'status': 'error', 'msg': '❌ Captcha não resolvido a tempo. Pulando...'})}\n\n"
                                        break

                                time.sleep(random.uniform(1.0, 2.5))

                                try:
                                    page.locator('#onetrust-accept-btn-handler').click(timeout=1000)
                                except:
                                    pass

                                sem_voos = page.locator(
                                    'aside[data-testid="no_direct_flights_banner"], h2:has-text("0 flight options")').is_visible()
                                if sem_voos:
                                    yield f"data: {json.dumps({'status': 'info', 'msg': f'🛑 Sem voos diretos disponíveis. Puxando próximo trecho...'})}\n\n"
                                    break

                                lista_temp = raspar_booking_flights(page, tag_rota, airlines_filter)

                                for voo in lista_temp:
                                    nome = voo['item']
                                    if nome not in voos_da_rota:
                                        voo['sort_val'] = pax
                                        voos_da_rota[nome] = voo
                                    else:
                                        voos_da_rota[nome]['sort_val'] = pax

                            for voo in voos_da_rota.values():
                                voo['qtd'] = "≥ 9" if voo['sort_val'] == 9 else str(voo['sort_val'])

                            rotas_do_dia.append({
                                "id_trecho": index_rota,
                                "rota_tag": tag_rota,
                                "voos": list(voos_da_rota.values())
                            })

                        resultados.append({"data": s_in, "rotas": rotas_do_dia})

                except Exception as e:
                    yield f"data: {json.dumps({'status': 'error', 'msg': f'Erro em {s_in}: {str(e)}'})}\n\n"
                    resultados.append({"data": s_in, "rotas": []})

            browser.close()
            yield f"data: {json.dumps({'status': 'done', 'dados': resultados})}\n\n"

    # CAPTURA DE ERRO FATAL DO PLAYWRIGHT (PARA NÃO DERRUBAR O STREAM SILENCIOSAMENTE)
    except Exception as erro_fatal:
        mensagem_erro = str(erro_fatal)
        if "Executable doesn't exist" in mensagem_erro or "playwright install" in mensagem_erro:
            mensagem_erro = "Navegadores não instalados! Pare o servidor Python e rode o comando: playwright install"
        yield f"data: {json.dumps({'status': 'error', 'msg': f'💥 ERRO FATAL DO NAVEGADOR: {mensagem_erro}'})}\n\n"


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/buscar_stream', methods=['POST'])
def buscar_stream():
    return Response(motor_busca_generator(request.json), mimetype='text/event-stream')

# 🛑 MAKE SURE THIS IS FLUSH TO THE LEFT MARGIN!
if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5000, use_reloader=False)
