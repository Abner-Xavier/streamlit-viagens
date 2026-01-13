import time
import csv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def iniciar_driver():
    """Configura o navegador Chrome para automação."""
    chrome_options = Options()
    # chrome_options.add_argument("--headless") # Retire o comentário para não ver o navegador abrindo
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    # Tenta evitar detecção de bot
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def buscar_voos(origem, destino, data_ida):
    driver = iniciar_driver()
    
    # URL formatada do Google Flights
    url = f"https://www.google.com/travel/flights?q=Flights%20to%20{destino}%20from%20{origem}%20on%20{data_ida}"
    print(f"Acessando: {url}")
    
    driver.get(url)
    
    # Espera para carregar e para você resolver CAPTCHA manualmente se aparecer
    time.sleep(5) 
    
    # Tenta clicar no botão "Concluído" de cookies se aparecer (ajuste conforme necessário)
    try:
        botoes = driver.find_elements(By.TAG_NAME, "button")
        for btn in botoes:
            if "Aceitar" in btn.text or "Accept" in btn.text:
                btn.click()
                break
    except:
        pass

    print("Carregando lista de voos...")
    
    # Rola a página para carregar mais resultados
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(3)

    voos_encontrados = []

    try:
        # O Google muda essas classes constantemente.
        # Uma estratégia mais segura é buscar pelos elementos de lista (role="listitem")
        # dentro da área principal de resultados.
        
        # Localiza a lista de melhores voos e outros voos
        # A classe .pIav2d geralmente envolve o cartão do voo, mas é volátil.
        # Vamos usar XPATH genérico para tentar pegar os cartões.
        flight_cards = driver.find_elements(By.XPATH, "//div[@class='pIav2d']") 
        
        if not flight_cards:
            print("Tentando seletor alternativo...")
            flight_cards = driver.find_elements(By.CSS_SELECTOR, ".pIav2d")

        print(f"Encontrados {len(flight_cards)} possíveis voos. Extraindo dados...")

        for card in flight_cards:
            try:
                # Texto cru do cartão contém quase tudo (quebras de linha separam os dados)
                texto_cartao = card.text.split('\n')
                
                # A estrutura do texto geralmente é:
                # [Horario, Empresa, Duração, Aeroportos, Paradas, Preço, ..., Assentos(opcional)]
                
                # Tentativa de extração baseada em estrutura comum (pode variar)
                horario_partida = ""
                duracao = ""
                preco = ""
                empresa = ""
                assentos = "Não informado" # Padrão
                
                # Busca por elementos específicos via ARIA-LABEL para ser mais robusto
                # Aria-labels são usados para leitores de tela e mudam menos que classes CSS
                
                # Exemplo de extração por texto cru (método fallback)
                for linha in texto_cartao:
                    if "h " in linha and "m" in linha and len(linha) < 10: # Ex: 13 h 5 m
                        duracao = linha
                    if "R$" in linha or "US$" in linha:
                        preco = linha
                    if "restam" in linha.lower() or "left" in linha.lower():
                        assentos = linha # Ex: "Restam 2 lugares"

                # Tentar pegar a empresa aérea (geralmente as primeiras linhas)
                if len(texto_cartao) > 2:
                    empresa = texto_cartao[1] if ":" not in texto_cartao[1] else texto_cartao[0]

                if preco: # Só adiciona se achou preço
                    voo = {
                        "Origem": origem,
                        "Destino": destino,
                        "Empresa": empresa,
                        "Duração": duracao,
                        "Preço": preco,
                        "Assentos": assentos
                    }
                    voos_encontrados.append(voo)
                    print(f"Extraído: {empresa} - {preco}")
            
            except Exception as e:
                continue

    except Exception as e:
        print(f"Erro ao processar dados: {e}")
    
    driver.quit()
    return voos_encontrados

def salvar_csv(dados):
    if not dados:
        print("Nenhum dado para salvar.")
        return

    keys = dados[0].keys()
    with open('voos_google.csv', 'w', newline='', encoding='utf-8') as output_file:
        dict_writer = csv.DictWriter(output_file, fieldnames=keys)
        dict_writer.writeheader()
        dict_writer.writerows(dados)
    print("Arquivo 'voos_google.csv' salvo com sucesso!")

# --- CONFIGURAÇÃO DA BUSCA ---
if __name__ == "__main__":
    ORIGEM = "GRU"       # Código IATA (São Paulo)
    DESTINO = "JFK"      # Código IATA (Nova York)
    DATA = "2026-01-17"  # Formato YYYY-MM-DD
    
    dados = buscar_voos(ORIGEM, DESTINO, DATA)
    salvar_csv(dados)
