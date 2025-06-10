# Versão 1.3

import requests
import datetime
import os
import subprocess
import shutil
import zipfile # Para descompactar arquivos .zip se o .n.Z for um .zip (improvável, mas para robustez)
import gzip    # Para descompactar arquivos .gz (se o .n.Z for um .gz)

# --- CONFIGURAÇÕES GLOBAIS ---
# ONDE ESTÁ O EXECUTÁVEL gps-sdr-sim.exe NO SEU COMPUTADOR WINDOWS?
# EXTREMAMENTE IMPORTANTE: Mude este caminho para o local onde você descompactou o gps-sdr-sim-win.zip
# Exemplo: r"C:\Users\SeuUsuario\Documents\gps-sdr-sim-win\gps-sdr-sim.exe"
# O 'r' antes da string é para tratar a string como "raw" e evitar problemas com as barras invertidas.
GPS_SDR_SIM_EXECUTABLE = r"C:\Users\SeuUsuario\Documents\gps-sdr-sim-win\gps-sdr-sim.exe" 
# ^^^^^^^^^^^^^^^^^^^^^^^^^^^^  MUDE ISSO! ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

# URL base para download dos arquivos de efemérides da NASA
NASA_CDDIS_URL = "https://cddis.nasa.gov/archive/gnss/data/daily/"

# Local onde os arquivos de efemérides serão baixados temporariamente
# e onde os arquivos de saída .c8 e .txt serão gerados antes de mover
# Isso criará uma pasta "gps_sim_output" dentro da mesma pasta onde este script está.
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gps_sim_output")

# --- PARÂMETROS DA SIMULAÇÃO GPS ---
# Informe a localização desejada para a simulação.
# Exemplo: Cristo Redentor, Rio de Janeiro (usei a data de hoje para gerar um exemplo)
# Latitude: Norte é positivo, Sul é negativo.
# Longitude: Leste é positivo, Oeste é negativo.
# Altitude: Em metros.
TARGET_LATITUDE = -22.9519  # Ex: -22.9519 para o Cristo Redentor (ponto turístico)
TARGET_LONGITUDE = -43.2105 # Ex: -43.2105 para o Cristo Redentor (ponto turístico)
TARGET_ALTITUDE = 710      # Ex: 710 para o Cristo Redentor (altitude do pico em metros)

# Taxa de amostragem e frequência central para o HackRF (não mude, são padrões para GPS L1)
SAMPLE_RATE = 2600000       # 2.6 MHz (taxa de amostragem em Hertz)
CENTER_FREQUENCY = 1575420000 # 1575.42 MHz (frequência central em Hertz para GPS L1)

# --- FUNÇÕES DO SCRIPT ---

def get_day_of_year(date=None):
    """
    Calcula e retorna o dia do ano (1 a 366) para uma data específica ou a data atual.
    Usado para construir o nome do arquivo de efemérides da NASA.
    """
    if date is None:
        # Pega a data atual do sistema
        date = datetime.date.today()
    # Retorna o dia do ano (timetuple.tm_yday é o dia do ano)
    return date.timetuple().tm_yday

def download_ephemeris_file(output_path):
    """
    Baixa o arquivo de efemérides mais recente da NASA.
    Tenta baixar o arquivo .n (não comprimido) primeiro.
    Se falhar, tenta o .n.Z (comprimido em gzip) e descompacta.
    """
    today = datetime.date.today()
    year = today.year
    day_of_year = get_day_of_year(today)

    # Formata o dia do ano com 3 dígitos (ex: 001, 155)
    day_str = f"{day_of_year:03d}"
    # Formata o ano com 2 dígitos (ex: 25 para 2025)
    year_short = str(year)[2:]

    # Constrói os nomes dos arquivos esperados (ex: brdc1550.25n)
    ephem_filename_n = f"brdc{day_str}0.{year_short}n"
    ephem_filename_n_gz = f"{ephem_filename_n}.Z" # Versão comprimida em .Z (gzip)

    # Constrói as URLs completas para os arquivos
    url_n = f"{NASA_CDDIS_URL}{year}/{day_str}/brdc/{ephem_filename_n}"
    url_n_gz = f"{NASA_CDDIS_URL}{year}/{day_str}/brdc/{ephem_filename_n_gz}"

    print(f"Tentando baixar arquivo de efemérides (não comprimido): {url_n}")
    try:
        # Tenta baixar a versão não comprimida (.n)
        response = requests.get(url_n, stream=True)
        # Lança um erro se o status da resposta for 4xx (cliente) ou 5xx (servidor)
        response.raise_for_status() 
        with open(output_path, 'wb') as f:
            # Escreve o conteúdo baixado em blocos para evitar uso excessivo de memória
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"Arquivo de efemérides baixado com sucesso: {output_path}")
        return output_path
    except requests.exceptions.RequestException as e:
        print(f"Erro ao baixar {url_n}: {e}")
        print(f"Tentando baixar a versão comprimida (.Z): {url_n_gz}")
        try:
            # Tenta baixar a versão comprimida (.n.Z)
            response = requests.get(url_n_gz, stream=True)
            response.raise_for_status()
            gz_output_path = output_path + ".Z"
            with open(gz_output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            print(f"Arquivo comprimido baixado com sucesso: {gz_output_path}")

            # Descompactar o arquivo .Z (que é um gzip)
            print(f"Descompactando {gz_output_path}...")
            # Abre o arquivo .gz para leitura no modo binário
            with gzip.open(gz_output_path, 'rb') as f_in:
                # Abre o arquivo de saída (sem .Z) para escrita no modo binário
                with open(output_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out) # Copia o conteúdo descompactado
            os.remove(gz_output_path) # Remove o arquivo .Z após descompactar
            print(f"Arquivo descompactado para: {output_path}")
            return output_path
        except requests.exceptions.RequestException as e_gz:
            print(f"Erro ao baixar {url_n_gz}: {e_gz}")
            print("Não foi possível baixar o arquivo de efemérides. Verifique sua conexão ou tente novamente mais tarde.")
            return None
        except Exception as e_unzip: # Captura outros erros de descompactação
            print(f"Erro ao descompactar {gz_output_path}: {e_unzip}")
            return None

def generate_gps_file(ephemeris_file_path, output_filename_base):
    """
    Executa o programa gps-sdr-sim.exe para gerar o arquivo .c8 e cria o arquivo .txt.
    """
    # Define o caminho completo para o arquivo de saída .c8
    output_c8_path = os.path.join(OUTPUT_DIR, f"{output_filename_base}.c8")
    
    # Define os argumentos (parâmetros) para o gps-sdr-sim.exe
    # -e: caminho para o arquivo de efemérides (.n)
    # -l: latitude,longitude,altitude (separados por vírgula)
    # -b: profundidade de bits (8 bits é o padrão e recomendado para HackRF)
    # -o: caminho para o arquivo de saída .c8
    command = [
        GPS_SDR_SIM_EXECUTABLE = r"F:\GPS_Simulator_Python\gps-sdr-sim_.exe",
        "-e", ephemeris_file_path,
        "-l", f"{TARGET_LATITUDE},{TARGET_LONGITUDE},{TARGET_ALTITUDE}",
        "-b", "8",
        "-o", output_c8_path
    ]

    print(f"\nGerando arquivo GPS simulado: {output_c8_path}")
    print(f"Executando comando: {' '.join(command)}")

    try:
        # Executa o comando no sistema operacional.
        # capture_output=True: captura o que o programa imprime na tela (stdout e stderr).
        # text=True: decodifica a saída como texto (não binário).
        # check=True: se o comando retornar um erro (código de saída diferente de 0), levanta uma exceção.
        process = subprocess.run(command, capture_output=True, text=True, check=True)
        print("Saída do gps-sdr-sim:")
        print(process.stdout) # Imprime o que o programa imprimiu normalmente
        if process.stderr:
            print("Erros (stderr) do gps-sdr-sim:")
            print(process.stderr) # Imprime mensagens de erro do programa
        print(f"Arquivo .c8 gerado com sucesso: {output_c8_path}")
    except FileNotFoundError:
        print(f"ERRO: O executável do gps-sdr-sim não foi encontrado em {GPS_SDR_SIM_EXECUTABLE}.")
        print("Verifique se o caminho no script está correto e se o arquivo 'gps-sdr-sim.exe' existe.")
        return None
    except subprocess.CalledProcessError as e:
        print(f"ERRO ao executar gps-sdr-sim. Código de saída: {e.returncode}")
        print(f"Erro de saída (stderr): {e.stderr}")
        print("Verifique se os parâmetros estão corretos ou se o arquivo .n foi baixado sem problemas.")
        return None
    except Exception as e:
        print(f"Ocorreu um erro inesperado ao executar gps-sdr-sim: {e}")
        return None

    # Gera o arquivo .txt de configuração.
    # Este arquivo é lido pelo firmware Mayhem no PortaPack para saber a taxa de amostragem e frequência.
    output_txt_path = os.path.join(OUTPUT_DIR, f"{output_filename_base}.txt")
    with open(output_txt_path, 'w') as f:
        f.write(f"sample_rate={SAMPLE_RATE}\n")
        f.write(f"center_frequency={CENTER_FREQUENCY}\n")
    print(f"Arquivo .txt de configuração gerado: {output_txt_path}")

    return output_c8_path, output_txt_path

def find_sd_card_path():
    """
    Tenta encontrar automaticamente o caminho do cartão SD.
    No Windows, cartões SD aparecem como letras de unidade (ex: D:, E:).
    Esta função é uma tentativa e pode precisar de ajuste manual.
    """
    print("\nTentando encontrar o caminho do cartão SD automaticamente...")
    drives = ['%s:' % d for d in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ']
    
    for drive in drives:
        # Verifica se o drive existe e se parece ser um dispositivo removível
        # (e não uma unidade de disco rígido principal)
        # Mais complexo de fazer de forma robusta apenas com os.path
        # Uma heurística simples é procurar por pastas com "gps" dentro ou ver se o nome do volume sugere PortaPack.
        
        # O ideal seria um driver ou ferramenta mais avançada para listar discos removíveis.
        # Para simplificar, esta função retorna uma instrução para o usuário.
        pass # Não faz nada aqui, apenas para demonstração

    print("Não foi possível detectar automaticamente o cartão SD.")
    print("Por favor, insira a letra da unidade do seu cartão SD (ex: D:, E:) abaixo:")
    sd_path = input("Letra da unidade do cartão SD (ex: D:): ")
    # Verifica se o caminho termina com uma barra
    if not sd_path.endswith(os.sep):
        sd_path += os.sep
    return sd_path

def copy_files_to_sd_card(c8_file, txt_file, sd_card_root_path):
    """
    Copia os arquivos .c8 e .txt para a pasta 'gps' no cartão SD.
    """
    # Constrói o caminho completo para a pasta 'gps' no cartão SD
    gps_folder_on_sd = os.path.join(sd_card_root_path, "gps")
    
    print(f"\nVerificando caminho do cartão SD: {sd_card_root_path}")
    if not os.path.exists(sd_card_root_path):
        print(f"ERRO: O cartão SD não parece estar acessível em {sd_card_root_path}.")
        print("Certifique-se de que o cartão SD está conectado e o caminho está correto.")
        return False

    print(f"Criando pasta 'gps' no cartão SD: {gps_folder_on_sd} (se não existir)")
    # os.makedirs(..., exist_ok=True) cria a pasta se ela não existir.
    # Se ela já existir, não faz nada e não dá erro.
    os.makedirs(gps_folder_on_sd, exist_ok=True) 

    print(f"Copiando {os.path.basename(c8_file)} para {gps_folder_on_sd}")
    # shutil.copy copia o arquivo de origem para o destino.
    shutil.copy(c8_file, gps_folder_on_sd)
    print(f"Copiando {os.path.basename(txt_file)} para {gps_folder_on_sd}")
    shutil.copy(txt_file, gps_folder_on_sd)
    
    print("Arquivos copiados com sucesso para o cartão SD!")
    return True

# --- FUNÇÃO PRINCIPAL ---
def main():
    """
    Função principal que orquestra todo o processo de geração e cópia dos arquivos.
    """
    print("--- Início da Simulação GPS Automatizada no Windows ---")

    # 1. Cria o diretório de saída para arquivos temporários, se não existir.
    # Todos os arquivos gerados (efemérides, .c8, .txt) ficarão aqui antes de serem copiados para o SD.
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"Diretório de trabalho para arquivos gerados: {OUTPUT_DIR}")

    # 2. Define o nome base do arquivo de efemérides (ex: brdc1550.25n)
    # Isso é baseado na data atual para buscar o arquivo correto da NASA.
    ephemeris_filename = f"brdc{get_day_of_year():03d}0.{str(datetime.date.today().year)[2:]}n"
    ephemeris_output_path = os.path.join(OUTPUT_DIR, ephemeris_filename)

    # 3. Baixa o arquivo de efemérides da NASA.
    print("\nEtapa 1: Baixando arquivo de efemérides da NASA...")
    downloaded_ephem_file = download_ephemeris_file(ephemeris_output_path)
    if not downloaded_ephem_file:
        print("Falha ao baixar o arquivo de efemérides. O script será encerrado.")
        return # Encerra o script se o download falhar

    # 4. Define o nome base para os arquivos de saída .c8 e .txt que serão gerados.
    output_filename_base = "gps_sim_generado_hackrf" # Nome amigável para seus arquivos de simulação

    # 5. Gera o arquivo .c8 e o arquivo .txt usando o gps-sdr-sim.exe.
    print("\nEtapa 2: Gerando arquivo GPS simulado (.c8 e .txt)...")
    generated_files = generate_gps_file(downloaded_ephem_file, output_filename_base)
    if not generated_files:
        print("Falha ao gerar os arquivos GPS simulados. O script será encerrado.")
        return # Encerra o script se a geração falhar

    c8_file, txt_file = generated_files

    # 6. Copia os arquivos gerados para o cartão SD do PortaPack.
    print("\nEtapa 3: Copiando arquivos para o cartão SD do PortaPack...")
    # Aqui, o script vai pedir para você inserir a letra da unidade do cartão SD.
    # É o método mais confiável no Windows, pois a detecção automática pode ser complexa.
    sd_card_path = find_sd_card_path()

    if not copy_files_to_sd_card(c8_file, txt_file, sd_card_path):
        print("\nOps! Não foi possível copiar os arquivos para o cartão SD automaticamente.")
        print(f"Por favor, copie os arquivos manualmente para a pasta 'gps' do seu cartão SD.")
        print(f"Os arquivos estão localizados em: {OUTPUT_DIR}")
        print(f"Arquivos a copiar: {os.path.basename(c8_file)} e {os.path.basename(txt_file)}")
        return # Encerra o script com instruções de cópia manual se a cópia automática falhar

    print("\n--- Simulação GPS Automatizada Concluída! ---")
    print("Os arquivos necessários foram gerados e copiados para o cartão SD.")
    print("Próximo passo: Remova o cartão SD do computador COM SEGURANÇA.")
    print("Insira-o no PortaPack H2M e siga os passos para iniciar a simulação no dispositivo.")
    print(f"Localização que será simulada: Lat={TARGET_LATITUDE}, Lon={TARGET_LONGITUDE}, Alt={TARGET_ALTITUDE}m")

# Verifica se o script está sendo executado diretamente (não importado como módulo)
if __name__ == "__main__":
    main()