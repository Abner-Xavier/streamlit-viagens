import asyncio
import re
from playwright.async_api import async_playwright
import pandas as pd
from datetime import datetime, timedelta
from playwright_stealth import stealth # Importação simplificada
import csv

# --- CONFIGURAÇÕES GLOBAIS ---
STAYS_COMPLETES = [
    {
        "name": "Grand Hyatt Istanbul",
        "url": "https://www.booking.com/hotel/tr/grand-hyatt-istanbul.html",
        "start": "2026-01-10",
        "end": "2026-01-13",
    },
]

OUTPUT_FILENAME = "hoteis_pernoite_suites.csv"
SELECTOR_TIMEOUT = 30000 

# --- FUNÇÕES AUXILIARES ---

def clean_text(text):
    if not text: return ""
    return re.sub(r'\s+', ' ', text.replace('\n', ' ')).strip()

def extract_price(text):
    if not text: return None
    match = re.search(r"([\d,]+(?:\.\d{1,2})?)", text.replace('USD', '').replace('€', '').replace('$', ''))
    return float(match.group(1).replace(",", "")) if match else None

def extract_area(text):
    """
    Melhoria na extração de área: busca por padrões comuns de m2.
    """
    if not text: return None
    # Procura por "30 m²" ou "30 sq m" ou "30 square meters"
    match = re.search(r"(\d+)\s*(?:m²|sq m|sq metre|sq meter|square meter)", text, re.IGNORECASE)
    return int(match.group(1)) if match else None

# --- SCRAPER ---

async def scrape_detailed_data(browser, hotel_name, hotel_url, checkin, checkout):
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
    page = await context.new_page()
    await stealth(page)

    url = f"{hotel_url}?checkin={checkin}&checkout={checkout}&selected_currency=USD&lang=en-us&group_adults=2&no_rooms=1"
    
    print(f"🏨 Buscando: {hotel_name} | {checkin}")
    
    try:
        await page.goto(url, timeout=60000, wait_until="domcontentloaded")
        
        # Espera a tabela de quartos carregar
        await page.wait_for_selector(".hprt-roomtype-link", timeout=SELECTOR_TIMEOUT)
        
        # O SEGREDO PARA A ÁREA: Muitas vezes a área está em um elemento oculto ou em 
        # tooltips. Vamos capturar o texto de toda a célula do tipo de quarto.
        rows = await page.query_selector_all("tr.hprt-table-row")
        extracted_data = []
        
        # Variáveis de controle para linhas que mesclam células (rowspan)
        last_room_name = "Desconhecido"
        last_room_area = None

        for row in rows:
            # 1. Tenta capturar Nome e Área (presentes apenas na primeira linha de cada bloco de quarto)
            room_link = await row.query_selector(".hprt-roomtype-link")
            if room_link:
                last_room_name = clean_text(await room_link.inner_text())
                
                # BUSCA AMPLIADA PELA ÁREA: Olhamos para a célula pai que contém o link do quarto
                # Geralmente a área fica em um <span> ou <div> próximo ao nome
                room_cell = await row.query_selector("td.hprt-table-cell-roomtype")
                if room_cell:
                    cell_text = await room_cell.inner_text()
                    last_room_area = extract_area(cell_text)

            # 2. Captura de Preço
            price_el = await row.query_selector(".bui-price-display__value, .prco-val-actual-color")
            price = extract_price(await price_el.inner_text()) if price_el else None

            # 3. PRECISÃO NA QUANTIDADE: 
            # Verificamos o select e pegamos o valor máximo da última opção
            qty_available = 0
            select_el = await row.query_selector("select.hprt-nos-select")
            if select_el:
                options = await select_el.query_selector_all("option")
                if options:
                    # O Booking costuma ter a última opção como o limite disponível
                    last_opt_val = await options[-1].get_attribute("value")
                    try:
                        qty_available = int(last_opt_val)
                    except:
                        qty_available = 0

            # Só adiciona se for suíte (conforme seu pedido anterior) e tiver preço
            if "suite" in last_room_name.lower() and price:
                extracted_data.append({
                    "Hotel_Name": hotel_name,
                    "Checkin": checkin,
                    "Checkout": checkout,
                    "Room_Name": last_room_name,
                    "Area_m2": last_room_area,
                    "Price_USD": price,
                    "Qty_Available": qty_available
                })
        
        await context.close()
        return extracted_data
    except Exception as e:
        print(f"⚠️ Erro no pernoite {checkin}: {e}")
        await context.close()
        return []

# --- EXECUÇÃO PRINCIPAL ---

async def run():
    # ... (mesma lógica de geração de pernoites do seu código)
    from datetime import datetime, timedelta
    overnights = []
    for stay in STAYS_COMPLETES:
        start = datetime.strptime(stay["start"], "%Y-%m-%d")
        end = datetime.strptime(stay["end"], "%Y-%m-%d")
        while start < end:
            nxt = start + timedelta(days=1)
            overnights.append({"name": stay["name"], "url": stay["url"], "checkin": start.strftime("%Y-%m-%d"), "checkout": nxt.strftime("%Y-%m-%d")})
            start = nxt

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        all_rows = []

        for o in overnights:
            data = await scrape_detailed_data(browser, o["name"], o["url"], o["checkin"], o["checkout"])
            all_rows.extend(data)
            await asyncio.sleep(2)

        await browser.close()

    if all_rows:
        df = pd.DataFrame(all_rows)
        # Preenchimento de área para garantir que linhas sem o dado capturem da anterior do mesmo grupo
        df['Area_m2'] = df.groupby('Room_Name')['Area_m2'].ffill().bfill()
        
        print("\n✅ DADOS CONSOLIDADOS:")
        print(df.to_string(index=False))
        df.to_csv(OUTPUT_FILENAME, index=False, sep=";", encoding="utf-8-sig")

if __name__ == "__main__":
    asyncio.run(run())
