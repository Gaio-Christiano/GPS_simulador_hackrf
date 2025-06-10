import requests # Importa a biblioteca 'requests' para fazer requisições HTTP (usada para baixar arquivos da internet).
import datetime # Importa a biblioteca 'datetime' para trabalhar com datas e horas.
import os # Importa a biblioteca 'os' para interagir com o sistema operacional (caminhos de arquivos, diretórios, etc.).
import subprocess # Importa a biblioteca 'subprocess' para executar comandos externos (como o programa gps-sdr-sim.exe).
import shutil # Importa a biblioteca 'shutil' para operações de alto nível em arquivos e coleções de arquivos (copiar, mover).
import gzip # Importa a biblioteca 'gzip' para descompactar arquivos gzip (arquivos .gz ou .Z da NASA).
import sys # Importa a biblioteca 'sys' para interagir com o interpretador Python (ex: sair do script em caso de erro).

# --- CONFIGURAÇÕES GLOBAIS ---
# Definir um caminho padrão para o executável gps-sdr-sim.exe.
# Este é um bom lugar para o script tentar encontrar o executável primeiro.
# Se o executável não for encontrado neste caminho padrão, o script perguntará ao usuário.
# O 'r' antes da string é para tratá-la como "raw" e evitar problemas com barras invertidas em caminhos do Windows.
DEFAULT_GPS_SDR_SIM_EXECUTABLE = r"C:\Users\Public\gps-sdr-sim-win\gps-sdr-sim.exe" # Um local comum e acessível para todos os usuários.

# URL base para download dos arquivos de efemérides da NASA (dados dos satélites GPS).
# ATENÇÃO: O CDDIS da NASA agora exige autenticação (login/senha) para downloads.
# O download direto via requests pode falhar e baixar uma página de erro HTML.
# O script tentará baixar, mas, se falhar, pedirá o arquivo manualmente.
NASA_CDDIS_URL = "https://cddis.nasa.gov/archive/gnss/data/daily/"

# Diretório de saída para arquivos temporários e gerados (.c8, .txt).
# os.path.dirname(os.path.abspath(__file__)) obtém o diretório onde este script Python está.
# os.path.join() constrói o caminho completo para a subpasta "gps_sim_output".
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gps_sim_output")


# Taxa de amostragem e frequência central para o HackRF (hardware SDR).
# Estes valores são fixos para a simulação de GPS L1 e não devem ser alterados,
# pois são padrões da especificação do sinal GPS.
SAMPLE_RATE = 2600000        # 2.6 MHz (taxa de amostragem em Hertz)
CENTER_FREQUENCY = 1575420000 # 1575.42 MHz (frequência central em Hertz para GPS L1)

# Tamanho mínimo esperado para um arquivo de efemérides válido em KB.
# Arquivos de 11KB geralmente indicam uma página de erro ou redirecionamento.
MIN_EPHEMERIS_FILE_SIZE_KB = 100 # Um arquivo válido geralmente tem mais de 100 KB.

# --- FUNÇÕES AUXILIARES ---

def get_day_of_year(date):
    """
    Calcula e retorna o dia do ano (um número de 1 a 366) para uma data específica.
    Ex: 1º de janeiro é o dia 1, 31 de dezembro é o dia 365 (ou 366 em ano bissexto).
    Este valor é usado para construir o nome do arquivo de efemérides da NASA.
    """
    return date.timetuple().tm_yday # Retorna o dia do ano do objeto datetime.

def validate_path(prompt, default_path=None):
    """
    Solicita um caminho de arquivo ao usuário, valida se o arquivo existe e é executável.
    Se um 'default_path' (caminho padrão) for fornecido, a função tenta usá-lo primeiro.
    Se o caminho não for válido, ela continua pedindo ao usuário até que um caminho válido seja inserido.
    """
    path = default_path # Começa com o caminho padrão.
    if path and not os.path.exists(path): # Se um caminho padrão foi dado, mas não existe...
        print(f"Atenção: O caminho padrão '{path}' não foi encontrado.") # Avisa que o padrão não foi achado.
        path = None # Define 'path' como None para forçar a entrada do usuário.

    # Loop que continua enquanto o caminho não for válido.
    while not path or not os.path.exists(path) or not os.path.isfile(path) or not os.access(path, os.X_OK):
        if path: # Se 'path' tem um valor (ou seja, não é a primeira iteração ou o padrão falhou)...
            print(f"Erro: '{path}' não é um arquivo válido ou não é executável.") # Informa o erro específico.
        # Pede ao usuário para digitar o caminho completo. .strip() remove espaços extras.
        path = input(f"{prompt} (Ex: C:\\caminho\\para\\arquivo.exe): ").strip()
        # No Windows, os.access(path, os.X_OK) verifica se é executável.
        # Em alguns casos, pode ser necessário apenas verificar os.path.exists(path) e os.path.isfile(path)
        # e confiar que o .exe será executável, mas a verificação de X_OK é mais robusta.
    return path # Retorna o caminho validado.

def get_user_coordinates():
    """
    Solicita ao usuário as coordenadas de latitude, longitude e altitude para a simulação.
    Valida as entradas para garantir que são números e lida com a substituição de vírgulas por pontos
    para permitir a conversão correta para números de ponto flutuante (float).
    """
    while True: # Loop contínuo até que entradas válidas sejam fornecidas.
        try:
            # Pede a latitude e substitui vírgulas por pontos (se houver).
            latitude_str = input("Digite a Latitude (Ex: -22.9519 para o Cristo Redentor): ").replace(',', '.')
            # Pede a longitude e substitui vírgulas por pontos.
            longitude_str = input("Digite a Longitude (Ex: -43.2105 para o Cristo Redentor): ").replace(',', '.')
            # Pede a altitude e substitui vírgulas por pontos.
            altitude_str = input("Digite a Altitude em metros (Ex: 710 para o Cristo Redentor): ").replace(',', '.')

            # Tenta converter as strings para números de ponto flutuante.
            latitude = float(latitude_str)
            longitude = float(longitude_str)
            altitude = float(altitude_str)
            return latitude, longitude, altitude # Retorna as coordenadas se a conversão for bem-sucedida.
        except ValueError: # Captura o erro se a conversão para float falhar (entrada não numérica).
            print("Entrada inválida. Por favor, digite apenas números para latitude, longitude e altitude.")
            print("Use ponto (.) como separador decimal, não vírgula (,).") # Instrução clara sobre o separador.

def get_user_datetime():
    """
    Solicita ao usuário a data e hora de início da simulação.
    Valida as entradas para garantir que estão em um formato de data/hora válido (AAAA-MM-DD HH:MM:SS).
    """
    while True: # Loop contínuo até que entradas válidas sejam fornecidas.
        date_str = input("Digite a data para a simulação (AAAA-MM-DD, Ex: 2025-06-05): ") # Pede a data.
        time_str = input("Digite a hora para a simulação (HH:MM:SS, Ex: 10:00:00): ") # Pede a hora.
        try:
            # Tenta combinar as strings de data e hora e convertê-las para um objeto datetime.
            sim_datetime = datetime.datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")
            return sim_datetime # Retorna o objeto datetime se a conversão for bem-sucedida.
        except ValueError: # Captura o erro se o formato da data ou hora estiver incorreto.
            print("Formato de data ou hora inválido. Por favor, use AAAA-MM-DD e HH:MM:SS.")

def download_ephemeris_file(target_date, output_path):
    """
    Tenta baixar o arquivo de efemérides (Broadcast Ephemeris) da NASA para a data alvo.
    Esta função tenta baixar diferentes formatos de arquivos de efemérides em uma ordem específica:
    1. Arquivo .n (não comprimido)
    2. Arquivo .gz (comprimido em gzip, o mais comum atualmente)
    3. Arquivo .Z (comprimido em LZW, um formato mais antigo, mas ainda pode existir)
    Se um arquivo compactado for baixado, ele será descompactado.
    Retorna o caminho completo do arquivo de efemérides baixado/descompactado ou None em caso de falha,
    especialmente se o arquivo baixado for muito pequeno (indicando uma página de erro).
    """
    year = target_date.year # Obtém o ano da data alvo.
    day_of_year = get_day_of_year(target_date) # Obtém o dia do ano da data alvo.

    # Formata o dia do ano com 3 dígitos (ex: 001, 155), preenchendo com zeros à esquerda.
    day_str = f"{day_of_year:03d}"
    # Formata o ano com 2 dígitos (ex: 25 para 2025).
    year_short = str(year)[2:]

    # Constrói os nomes dos arquivos esperados com base no padrão da NASA (ex: brdc1610.25n).
    ephem_filename_n = f"brdc{day_str}0.{year_short}n"
    ephem_filename_n_gz = f"{ephem_filename_n}.gz" # Versão comprimida em .gz (gzip).
    ephem_filename_n_Z = f"{ephem_filename_n}.Z"   # Versão comprimida em .Z (LZW).

    # Constrói as URLs completas para os diferentes formatos de arquivos no servidor da NASA.
    url_n = f"{NASA_CDDIS_URL}{year}/{day_str}/brdc/{ephem_filename_n}"
    url_n_gz = f"{NASA_CDDIS_URL}{year}/{day_str}/brdc/{ephem_filename_n_gz}"
    url_n_Z = f"{NASA_CDDIS_URL}{year}/{day_str}/brdc/{ephem_filename_n_Z}"

    # Lista de URLs a tentar baixar, em ordem de preferência (não compactado, depois .gz, depois .Z).
    urls_to_try = [url_n, url_n_gz, url_n_Z]
    # Dicionário que mapeia a URL para o caminho temporário onde o arquivo será salvo.
    temp_paths = {
        url_n: output_path, # Se for .n, o caminho final é o mesmo.
        url_n_gz: output_path + ".gz", # Se for .gz, adiciona .gz ao nome.
        url_n_Z: output_path + ".Z"   # Se for .Z, adiciona .Z ao nome.
    }

    download_successful = False # Flag para controlar se o download foi bem-sucedido.
    downloaded_temp_path = None # Variável para armazenar o caminho do arquivo baixado temporariamente.
    
    print("\nEtapa 4: Baixando arquivo de efemérides da NASA...") # Mensagem informativa para o usuário.
    print("Atenção: O site CDDIS da NASA (cddis.nasa.gov) agora requer login/senha.")
    print("O download automático pode falhar e baixar uma página HTML de erro de 11KB.")
    print("Se o download automático falhar, você será solicitado a fornecer o arquivo manualmente.")

    # Loop através das URLs tentando baixar o arquivo.
    for url in urls_to_try:
        print(f"Tentando baixar: {url}") # Mostra qual URL está sendo tentada.
        try:
            response = requests.get(url, stream=True, timeout=15)
            response.raise_for_status() # Lança uma exceção HTTPError se o status da resposta for 4xx ou 5xx (erro).

            downloaded_temp_path = temp_paths[url]
            with open(downloaded_temp_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            # Verifica o tamanho do arquivo baixado. Se for muito pequeno, é provável que seja uma página de erro.
            file_size_kb = os.path.getsize(downloaded_temp_path) / 1024
            if file_size_kb < MIN_EPHEMERIS_FILE_SIZE_KB:
                print(f"Aviso: Arquivo baixado '{os.path.basename(downloaded_temp_path)}' tem apenas {file_size_kb:.2f} KB.")
                print("Isso geralmente indica que o download falhou e o que foi baixado é uma página de erro/login.")
                os.remove(downloaded_temp_path) # Remove o arquivo inválido.
                download_successful = False # Marca como falha.
                continue # Tenta a próxima URL.
            
            print(f"Download bruto concluído: {downloaded_temp_path} ({file_size_kb:.2f} KB)")
            download_successful = True
            break
        except requests.exceptions.RequestException as e:
            print(f"Erro ao baixar {url}: {e}")
            download_successful = False
            if downloaded_temp_path and os.path.exists(downloaded_temp_path):
                os.remove(downloaded_temp_path) # Limpa qualquer arquivo parcial/inválido.
            continue # Tenta a próxima URL.

    if not download_successful or not downloaded_temp_path:
        print("Não foi possível baixar o arquivo de efemérides automaticamente de nenhuma URL ou o arquivo é inválido.")
        return None

    # Tenta descompactar o arquivo se ele tiver uma extensão de compressão (.gz ou .Z).
    if downloaded_temp_path.lower().endswith('.gz') or downloaded_temp_path.lower().endswith('.Z'):
        print(f"Descompactando {downloaded_temp_path} para {output_path}...")
        try:
            with gzip.open(downloaded_temp_path, 'rb') as f_in:
                with open(output_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            os.remove(downloaded_temp_path)
            print(f"Arquivo de efemérides descompactado com sucesso: {output_path}")
            return output_path

        except requests.exceptions.RequestException as e_gz:
            print(f"Erro ao baixar {url_n_gz}: {e_gz}")
            print("Não foi possível baixar o arquivo de efemérides automaticamente.")
            return None
        except Exception as e_unzip:
            print(f"Erro ao descompactar {downloaded_temp_path}: {e_unzip}")
            print("O arquivo baixado pode estar corrompido ou não é um gzip válido.")
            if os.path.exists(output_path):
                os.remove(output_path)
            return None
    else:
        print(f"Arquivo de efemérides baixado e pronto: {output_path}")
        return output_path

def get_manual_ephemeris_file():
    """
    Solicita ao usuário o caminho para um arquivo de efemérides baixado manualmente.
    Valida se o arquivo existe e tem a extensão .n ou .rnx (comum para arquivos de efemérides RINEX).
    Permite ao usuário continuar mesmo com uma extensão diferente, mas com aviso.
    """
    print("\n--- Download automático falhou. Por favor, forneça o arquivo manualmente. ---")
    print("Você pode baixar arquivos de efemérides de fontes como:")
    print(" - NASA CDDIS (cddis.nasa.gov): requer registro e login. Procure por 'GNSS Data' -> 'Daily' -> 'yyyy' -> 'ddd' -> 'brdc'.")
    print(" - IGS (ftp.igs.org): também pode ser uma fonte, mas verifique os requisitos de acesso.")
    print(" - Use um navegador web para baixar o arquivo mais recente (ex: brdcJJJ0.YYn ou brdcJJJ0.YYn.gz) para a data desejada.")
    print("Lembre-se de DESCOMPACTAR arquivos .gz ou .Z para .n antes de usar aqui.")
    
    while True:
        manual_path = input("Digite o caminho COMPLETO para o arquivo de efemérides (.n ou .rnx) que você baixou manualmente (Ex: C:\\caminho\\para\\brdc1520.25n): ").strip()
        
        if not os.path.exists(manual_path):
            print(f"Erro: O arquivo '{manual_path}' não foi encontrado.")
            continue
        
        if not os.path.isfile(manual_path):
            print(f"Erro: '{manual_path}' não é um arquivo válido.")
            continue

        # Verifica o tamanho do arquivo manual para garantir que não é um arquivo "vazio" ou corrompido.
        file_size_kb = os.path.getsize(manual_path) / 1024
        if file_size_kb < MIN_EPHEMERIS_FILE_SIZE_KB:
            print(f"Aviso: O arquivo selecionado '{os.path.basename(manual_path)}' tem apenas {file_size_kb:.2f} KB.")
            print("Este tamanho é incomum para um arquivo de efemérides válido. Ele pode estar corrompido ou ser um erro.")
            confirm = input("Deseja continuar com este arquivo mesmo assim? (s/n): ").lower()
            if confirm != 's':
                continue

        if not (manual_path.lower().endswith('.n') or manual_path.lower().endswith('.rnx')):
            print("Atenção: O arquivo não tem a extensão .n ou .rnx. Certifique-se de que é um arquivo de efemérides válido.")
            confirm = input("Deseja continuar com este arquivo? (s/n): ").lower()
            if confirm != 's':
                continue
        
        print(f"Arquivo de efemérides manual selecionado: {manual_path}")
        return manual_path

def get_manual_ephemeris_file():
    """
    Solicita ao usuário o caminho para um arquivo de efemérides baixado manualmente.
    Valida se o arquivo existe e tem a extensão .n (ou .rnx).
    """
    while True:
        manual_path = input("\nO download automático falhou. Por favor, digite o caminho COMPLETO do arquivo de efemérides (.n ou .rnx) que você baixou manualmente (Ex: C:\\caminho\\para\\brdc1520.25n): ").strip()
        
        if not os.path.exists(manual_path):
            print(f"Erro: O arquivo '{manual_path}' não foi encontrado.")
            continue
        
        if not os.path.isfile(manual_path):
            print(f"Erro: '{manual_path}' não é um arquivo válido.")
            continue

        # Verifica se a extensão é .n ou .rnx (comum para arquivos de efemérides)
        if not (manual_path.lower().endswith('.n') or manual_path.lower().endswith('.rnx')):
            print("Atenção: O arquivo não tem a extensão .n ou .rnx. Certifique-se de que é um arquivo de efemérides válido.")
            # Permite ao usuário continuar, mas avisa. Pode ser um arquivo RInex com outra extensão.
            confirm = input("Deseja continuar com este arquivo? (s/n): ").lower()
            if confirm != 's':
                continue
        
        print(f"Arquivo de efemérides manual selecionado: {manual_path}")
        return manual_path

def generate_gps_file(gps_sdr_sim_exe_path, ephemeris_file_path, latitude, longitude, altitude, sim_datetime, output_filename_base):
    """
    Executa o programa gps-sdr-sim.exe para gerar o arquivo de simulação GPS (.c8)
    e cria o arquivo de configuração (.txt) para o PortaPack H2M.
    Inclui todos os parâmetros necessários: caminho do executável, arquivo de efemérides,
    latitude, longitude, altitude e tempo de início da simulação.
    """
    # Constrói o caminho completo para o arquivo .c8 de saída.
    output_c8_path = os.path.join(OUTPUT_DIR, f"{output_filename_base}.c8")
    
    # Formata a data e hora para o parâmetro '-t' do gps-sdr-sim: AAAA/MM/DD,HH:MM:SS.
    time_param = sim_datetime.strftime("%Y/%m/%d,%H:%M:%S")

    # Lista de argumentos que serão passados para o gps-sdr-sim.exe.
    command = [
        gps_sdr_sim_exe_path, # Caminho para o executável gps-sdr-sim.
        "-e", ephemeris_file_path, # Parâmetro para o arquivo de efemérides.
        "-l", f"{latitude},{longitude},{altitude}", # Parâmetro de localização (latitude, longitude, altitude).
        "-b", "8", # Parâmetro para bits por amostra (8 bits para HackRF).
        "-t", time_param, # Parâmetro de tempo de início da simulação.
        "-o", output_c8_path # Parâmetro para o arquivo de saída (.c8).
    ]

    print(f"\nGerando arquivo GPS simulado: {output_c8_path}") # Informa o nome do arquivo a ser gerado.
    print(f"Executando comando: {' '.join(command)}") # Exibe o comando completo que será executado.

    try:
        process = subprocess.run(command, capture_output=True, text=True, check=True, timeout=300) 
        print("Saída do gps-sdr-sim:") # Exibe a saída padrão do gps-sdr-sim (geralmente progresso).

        print(process.stdout)
        if process.stderr: # Se houver saída de erro (stderr)...
            print("Erros (stderr) do gps-sdr-sim:") # Exibe os erros do gps-sdr-sim.
            print(process.stderr)
        print(f"Arquivo .c8 gerado com sucesso: {output_c8_path}") # Confirma o sucesso da geração do .c8.
    except FileNotFoundError: # Captura o erro se o executável do gps-sdr-sim não for encontrado.
        print(f"ERRO: O executável do gps-sdr-sim não foi encontrado em {gps_sdr_sim_exe_path}.")
        print("Verifique se o caminho no script está correto e se o arquivo 'gps-sdr-sim.exe' existe.")
        return None # Retorna None indicando falha.
    except subprocess.CalledProcessError as e: # Captura o erro se o gps-sdr-sim retornar um código de saída diferente de zero.
        print(f"ERRO ao executar gps-sdr-sim. Código de saída: {e.returncode}") # Mostra o código de erro.
        print(f"Erro de saída (stderr): {e.stderr}") # Mostra a mensagem de erro (se houver) do stderr.
        print("Isso pode indicar um problema com o arquivo de efemérides ou com os parâmetros. ")
        print("Verifique se o arquivo .n foi baixado/fornecido corretamente e não está corrompido.")
        print("Para depuração, tente executar o gps-sdr-sim manualmente com os mesmos parâmetros no terminal.")
        return None # Retorna None indicando falha.
    except subprocess.TimeoutExpired: # Captura o erro se o gps-sdr-sim exceder o tempo limite de execução.
        print(f"ERRO: O gps-sdr-sim não respondeu dentro do tempo limite de 300 segundos.")
        print("A simulação pode ser muito longa ou o programa travou. Tente diminuir a duração da simulação.")
        return None # Retorna None indicando falha.
    except Exception as e: # Captura qualquer outra exceção inesperada.
        print(f"Ocorreu um erro inesperado ao executar gps-sdr-sim: {e}")
        return None # Retorna None indicando falha.

    # Gera o arquivo .txt de configuração para o PortaPack Mayhem.
    output_txt_path = os.path.join(OUTPUT_DIR, f"{output_filename_base}.txt") # Caminho completo para o arquivo .txt.
    with open(output_txt_path, 'w') as f: # Abre o arquivo em modo de escrita de texto.
        f.write(f"sample_rate={SAMPLE_RATE}\n") # Escreve a taxa de amostragem.
        f.write(f"center_frequency={CENTER_FREQUENCY}\n") # Escreve a frequência central.
    print(f"Arquivo .txt de configuração gerado: {output_txt_path}") # Confirma a geração do .txt.

    return output_c8_path, output_txt_path # Retorna os caminhos dos arquivos .c8 e .txt gerados.

def find_sd_card_path():
    """
    Solicita ao usuário a letra da unidade do cartão SD para copiar os arquivos.
    No Windows, cartões SD aparecem como letras de unidade (ex: D:, E:).
    Valida se a entrada é um formato de letra de unidade e se a unidade existe.
    """
    print("\nPara copiar os arquivos para o cartão SD, preciso saber a letra da unidade.")
    print("Você pode verificar isso no 'Explorador de Arquivos' (Meu Computador/Este PC).")
    
    while True: # Loop contínuo até que um caminho válido seja fornecido.
        # Pede a letra da unidade, remove espaços e converte para maiúsculas.
        sd_path_input = input("Digite a letra da unidade do cartão SD (Ex: D:): ").strip().upper()
        # Verifica se a entrada tem 2 caracteres, o segundo é ':' e o primeiro é uma letra.
        if len(sd_path_input) == 2 and sd_path_input[1] == ':' and sd_path_input[0].isalpha():
            sd_path = sd_path_input + os.sep # Adiciona a barra invertida para completar o caminho (Ex: D:\).
            if os.path.exists(sd_path): # Verifica se o caminho da unidade realmente existe.
                print(f"Unidade '{sd_path_input}' encontrada.") # Confirma que a unidade foi encontrada.
                return sd_path # Retorna o caminho da unidade.
            else:
                print(f"Erro: A unidade '{sd_path_input}' não parece existir ou não está acessível. Tente novamente.")
        else:
            print("Formato inválido. Por favor, digite apenas a letra da unidade seguida de dois pontos (Ex: D:).")

def copy_files_to_sd_card(c8_file, txt_file, sd_card_root_path):
    """
    Copia os arquivos .c8 e .txt gerados para a pasta 'gps' dentro do cartão SD.
    Cria a pasta 'gps' se ela ainda não existir no cartão SD.
    """
    # Constrói o caminho completo para a pasta 'gps' no cartão SD.
    gps_folder_on_sd = os.path.join(sd_card_root_path, "gps")
    
    print(f"\nVerificando caminho do cartão SD: {sd_card_root_path}") # Informa o caminho do SD.
    if not os.path.exists(sd_card_root_path): # Verifica se o caminho raiz do SD existe.
        print(f"ERRO: O cartão SD não parece estar acessível em {sd_card_root_path}.")
        print("Certifique-se de que o cartão SD está conectado e o caminho está correto.")
        return False # Retorna False indicando falha.

    print(f"Criando pasta 'gps' no cartão SD: {gps_folder_on_sd} (se não existir)") # Informa sobre a criação da pasta.
    os.makedirs(gps_folder_on_sd, exist_ok=True) # Cria a pasta 'gps' no SD. 'exist_ok=True' evita erro se já existir.

    print(f"Copiando '{os.path.basename(c8_file)}' para '{gps_folder_on_sd}'") # Informa qual arquivo está sendo copiado.
    try:
        shutil.copy(c8_file, gps_folder_on_sd) # Copia o arquivo .c8.
        print(f"Copiando '{os.path.basename(txt_file)}' para '{gps_folder_on_sd}'") # Informa qual arquivo está sendo copiado.
        shutil.copy(txt_file, gps_folder_on_sd) # Copia o arquivo .txt.
        print("Arquivos copiados com sucesso para o cartão SD!") # Mensagem de sucesso.
        return True # Retorna True indicando sucesso.
    except Exception as e: # Captura qualquer erro durante a cópia dos arquivos.
        print(f"ERRO ao copiar arquivos para o cartão SD: {e}")
        print("Verifique as permissões de escrita no cartão SD.")
        return False # Retorna False indicando falha.

    print(f"Copiando '{os.path.basename(c8_file)}' para '{gps_folder_on_sd}'")
    try:
        shutil.copy(c8_file, gps_folder_on_sd)
        print(f"Copiando '{os.path.basename(txt_file)}' para '{gps_folder_on_sd}'")
        shutil.copy(txt_file, gps_folder_on_sd)
        print("Arquivos copiados com sucesso para o cartão SD!")
        return True
    except Exception as e:
        print(f"ERRO ao copiar arquivos para o cartão SD: {e}")
        print("Verifique as permissões de escrita no cartão SD.")
        return False


# --- FUNÇÃO PRINCIPAL ---
def main():
    """
    Função principal que orquestra todo o processo de geração do sinal GPS simulado e cópia dos arquivos.
    Ela guia o usuário através das etapas necessárias e gerencia as chamadas às outras funções.
    """

    print("--- Início da Simulação GPS Automatizada no Windows ---") # Mensagem de início do script.
    print("Este script é para **fins de estudo e proteção contra simulação de GPS**.") # Aviso legal/educacional.
    print("Ele irá gerar arquivos .c8 e .txt para seu PortaPack H2M com base nas suas entradas.") # Explicação do que o script faz.

    # 1. Verifica e obtém o caminho para o executável gps-sdr-sim.exe.
    # Se o caminho padrão não funcionar, ele solicitará ao usuário.
    print("\nEtapa 1: Localizando o executável do gps-sdr-sim...")
    global GPS_SDR_SIM_EXECUTABLE # Declara que estamos modificando a variável global.
    GPS_SDR_SIM_EXECUTABLE = validate_path( # Chama a função para validar o caminho do executável.
        "Digite o caminho COMPLETO para o gps-sdr-sim.exe", 
        DEFAULT_GPS_SDR_SIM_EXECUTABLE # Passa o caminho padrão.
    )

    # 2. Solicita ao usuário as coordenadas da localização a ser simulada.
    print("\nEtapa 2: Informe a localização que deseja simular.")
    latitude, longitude, altitude = get_user_coordinates() # Chama a função para obter as coordenadas.

    # 3. Solicita ao usuário a data e hora de início da simulação.
    print("\nEtapa 3: Informe a data e hora de início da simulação.")
    sim_datetime = get_user_datetime() # Chama a função para obter a data e hora.

    # 4. Cria o diretório de saída para arquivos temporários e gerados (.c8, .txt).
    os.makedirs(OUTPUT_DIR, exist_ok=True) # Cria o diretório se ele não existir.
    print(f"\nDiretório de trabalho para arquivos gerados: {OUTPUT_DIR}") # Informa o diretório de saída.

    # 5. Define o nome do arquivo de efemérides (ex: brdcXXX0.YYn) com base na data da simulação.
    ephemeris_filename = f"brdc{get_day_of_year(sim_datetime):03d}0.{str(sim_datetime.year)[2:]}n"
    ephemeris_output_path = os.path.join(OUTPUT_DIR, ephemeris_filename) # Caminho completo para o arquivo de efemérides.

    # 6. Baixa o arquivo de efemérides da NASA para a data informada ou pede ao usuário para fornecê-lo.
    downloaded_ephem_file = download_ephemeris_file(sim_datetime, ephemeris_output_path) # Tenta baixar o arquivo.
    
    if not downloaded_ephem_file: # Se o download automático falhar (função retornou None ou arquivo inválido)...
        print("\nO download automático do arquivo de efemérides falhou ou o arquivo baixado é inválido.")
        # Pede ao usuário para fornecer o caminho do arquivo manualmente.
        downloaded_ephem_file = get_manual_ephemeris_file()
        
        if not downloaded_ephem_file: # Se mesmo a entrada manual falhar...
            print("Nenhum arquivo de efemérides foi fornecido. O script será encerrado.")
            sys.exit(1) # Sai do script com um código de erro.

    # 7. Define o nome base para os arquivos de saída .c8 e .txt.
    # O nome é mais descritivo agora, incluindo localização e data/hora.
    output_filename_base = f"gps_sim_{latitude:.4f}_{longitude:.4f}_{sim_datetime.strftime('%Y%m%d_%H%M%S')}"

    # 8. Gera o arquivo .c8 (sinal GPS simulado) e o arquivo .txt (configuração) usando o gps-sdr-sim.exe.
    print("\nEtapa 5: Gerando arquivo GPS simulado (.c8 e .txt) com gps-sdr-sim...")
    generated_files = generate_gps_file( # Chama a função para gerar os arquivos.
        GPS_SDR_SIM_EXECUTABLE, 

        downloaded_ephem_file, # Usa o arquivo de efemérides que foi baixado ou fornecido manualmente.
        latitude, longitude, altitude, 
        sim_datetime, 
        output_filename_base
    )
    if not generated_files: # Se a geração dos arquivos falhar...
        print("Falha ao gerar os arquivos GPS simulados. O script será encerrado.")
        sys.exit(1) # Sai do script com um código de erro.

    c8_file, txt_file = generated_files # Desempacota os arquivos gerados.

    # 9. Copia os arquivos gerados para o cartão SD do PortaPack H2M.
    print("\nEtapa 6: Copiando arquivos para o cartão SD do PortaPack...")
    sd_card_path = find_sd_card_path() # Obtém o caminho do cartão SD.

    # Tenta copiar os arquivos para o cartão SD. Se falhar, instrui o usuário a fazer manualmente.
    if not copy_files_to_sd_card(c8_file, txt_file, sd_card_path):
        print("\nOps! Não foi possível copiar os arquivos para o cartão SD automaticamente.")
        print(f"Por favor, copie os arquivos manualmente para a pasta 'gps' do seu cartão SD.")
        print(f"Os arquivos estão localizados em: {OUTPUT_DIR}")
        print(f"Arquivos a copiar: {os.path.basename(c8_file)} e {os.path.basename(txt_file)}")
        print("\nVerifique se o cartão SD está conectado e o caminho da unidade está correto!")
        # Não sai com erro fatal aqui, apenas instrui o usuário a fazer manualmente,
        # pois a geração dos arquivos já foi concluída.

    print("\n--- Simulação GPS Automatizada Concluída! ---") # Mensagem de conclusão.
    print("Os arquivos necessários foram gerados e, se possível, copiados para o cartão SD.")
    print("\nPróximo passo CRÍTICO: Remova o cartão SD do computador COM SEGURANÇA (use 'Ejetar').")
    print("Em seguida, insira-o no PortaPack H2M e siga os passos no dispositivo:")
    print("1. Ligue o PortaPack.")
    print("2. Navegue para 'Transmit' -> 'GPS Sim'.")
    print(f"3. Selecione 'Load file' e escolha '{output_filename_base}.c8' (localizado na pasta 'gps').")
    print("4. Ajuste o 'TX Gain' com cautela (comece em 0 dB).")
    print("5. Pressione 'Start' para iniciar a transmissão.")
    print(f"\nLocalização que será simulada: Latitude={latitude}, Longitude={longitude}, Altitude={altitude}m")
    print(f"Data e Hora de simulação: {sim_datetime.strftime('%Y-%m-%d %H:%M:%S')}")


# Verifica se o script está sendo executado diretamente (ou seja, não foi importado como um módulo em outro script).
# Isso garante que a função main() seja chamada apenas quando o script é executado por si só.
if __name__ == "__main__":
    main() # Chama a função principal para iniciar a execução do script.