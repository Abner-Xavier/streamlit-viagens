async def buscar_booking(hotel_nome, checkin, checkout):
    async with async_playwright() as p:
        # Lançamos o navegador com flags para evitar detecção
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        
        # Criamos um contexto com Headers de um navegador real
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            extra_http_headers={
                "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
                "Referer": "https://www.google.com/"
            },
            viewport={"width": 1280, "height": 800}
        )
        page = await context.new_page()

        # URL com parâmetro para evitar redirecionamentos chatos
        url = (
            f"https://www.booking.com/searchresults.pt-br.html?"
            f"ss={hotel_nome.replace(' ', '+')}&"
            f"checkin={checkin}&"
            f"checkout={checkout}&"
            f"group_adults=2&no_rooms=1&group_children=0&selected_currency=BRL"
        )

        try:
            # Aumentamos o timeout para 90 segundos
            await page.goto(url, wait_until="networkidle", timeout=90000)
            
            # Pequena espera para carregar preços dinâmicos
            await asyncio.sleep(5) 

            # Tentamos encontrar o card usando seletores variados
            card = await page.wait_for_selector('[data-testid="property-card"]', timeout=15000)
            
            if card:
                nome = await page.locator('[data-testid="title"]').first.inner_text()
                preco = await page.locator('[data-testid="price-and-discounted-price"]').first.inner_text()
                
                return {"status": "sucesso", "hotel": nome, "preco": preco, "url": url}
            
        except Exception as e:
            # Tira um print para você ver o que o robô está vendo (ajuda a identificar CAPTCHA)
            await page.screenshot(path="debug_screen.png")
            return {"status": "erro", "mensagem": f"O site não respondeu como esperado. Verifique o print de debug abaixo."}
        finally:
            await browser.close()
