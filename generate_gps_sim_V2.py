import requests
import datetime
import os
import subprocess
import shutil
import gzip
import sys # Importa sys para verificar a versão do Python e sair elegantemente

# --- CONFIGURAÇÕES GLOBAIS ---
# Definir um caminho padrão para o executável gps-sdr-sim.exe.
# Este é um bom lugar para começar a procurar. Se não for encontrado aqui, o script perguntará ao usuário.
# O 'r' antes da string é para tratar a string como "raw" e evitar problemas com barras invertidas.
DEFAULT_GPS_SDR_SIM_EXECUTABLE = r"C:\Users\Public\gps-sdr-sim-win\gps-sdr-sim.exe" # Um local comum e acessível para todos os usuários

# URL base para download dos arquivos de efemérides da NASA
NASA_CDDIS_URL = "https://cddis.nasa.gov/archive/gnss/data/daily/"

# Diretório de saída para arquivos temporários e gerados (.c8, .txt).
# Ele será criado na mesma pasta onde este script Python está sendo executado.
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gps_sim_output")

# Taxa de amostragem e frequência central para o HackRF (não mude, são padrões para GPS L1).
# Estes valores são fixos para a simulação de GPS L1.
SAMPLE_RATE = 2600000       # 2.6 MHz (taxa de amostragem em Hertz)
CENTER_FREQUENCY = 1575420000 # 1575.42 MHz (frequência central em Hertz para GPS L1)

# --- FUNÇÕES AUXILIARES ---

def get_day_of_year(date):
    """
    Calcula e retorna o dia do ano (1 a 366) para uma data específica.
    Usado para construir o nome do arquivo de efemérides da NASA.
    """
    return date.timetuple().tm_yday

def validate_path(prompt, default_path=None):
    """
    Solicita um caminho ao usuário, valida se o arquivo existe e é executável.
    Se um caminho padrão for fornecido, tenta usá-lo primeiro.
    """
    path = default_path
    if path and not os.path.exists(path):
        print(f"Atenção: O caminho padrão '{path}' não foi encontrado.")
        path = None # Se o padrão não existe, forçamos a entrada do usuário

    while not path or not os.path.exists(path) or not os.path.isfile(path) or not os.access(path, os.X_OK):
        if path: # Se o caminho não foi encontrado ou não é executável
            print(f"Erro: '{path}' não é um arquivo válido ou não é executável.")
        path = input(f"{prompt} (Ex: C:\\caminho\\para\\arquivo.exe): ").strip()
        # No Windows, os.access(path, os.X_OK) verifica se é executável.
        # Em alguns casos, pode ser necessário apenas verificar os.path.exists(path) e os.path.isfile(path)
        # e confiar que o .exe será executável.
    return path

def get_user_coordinates():
    """
    Solicita ao usuário as coordenadas de latitude, longitude e altitude.
    Valida as entradas para garantir que são números.
    """
    while True:
        try:
            latitude = float(input("Digite a Latitude (Ex: -22.9519 para o Cristo Redentor): "))
            longitude = float(input("Digite a Longitude (Ex: -43.2105 para o Cristo Redentor): "))
            altitude = float(input("Digite a Altitude em metros (Ex: 710 para o Cristo Redentor): "))
            return latitude, longitude, altitude
        except ValueError:
            print("Entrada inválida. Por favor, digite apenas números para latitude, longitude e altitude.")

def get_user_datetime():
    """
    Solicita ao usuário a data e hora para a simulação.
    Valida as entradas para garantir que são um formato de data/hora válido.
    """
    while True:
        date_str = input("Digite a data para a simulação (AAAA-MM-DD, Ex: 2025-06-05): ")
        time_str = input("Digite a hora para a simulação (HH:MM:SS, Ex: 10:00:00): ")
        try:
            # Tenta combinar e converter a string para um objeto datetime
            sim_datetime = datetime.datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")
            return sim_datetime
        except ValueError:
            print("Formato de data ou hora inválido. Por favor, use AAAA-MM-DD e HH:MM:SS.")

def download_ephemeris_file(target_date, output_path):
    """
    Baixa o arquivo de efemérides (Broadcast Ephemeris) da NASA para a data alvo.
    Tenta baixar o arquivo .n (não comprimido) primeiro.
    Se falhar, tenta o .n.Z (comprimido em gzip) e descompacta.
    """
    year = target_date.year
    day_of_year = get_day_of_year(target_date)

    # Formata o dia do ano com 3 dígitos (ex: 001, 155)
    day_str = f"{day_of_year:03d}"
    # Formata o ano com 2 dígitos (ex: 25 para 2025)
    year_short = str(year)[2:]

    # Constrói os nomes dos arquivos esperados (ex: brdc1550.25n)
    ephem_filename_n = f"brdc{day_str}0.{year_short}n"
    ephem_filename_n_gz = f"{ephem_filename_n}.Z" # Versão comprimida em .Z (gzip)

    # Constrói as URLs completas para os arquivos no servidor da NASA
    url_n = f"{NASA_CDDIS_URL}{year}/{day_str}/brdc/{ephem_filename_n}"
    url_n_gz = f"{NASA_CDDIS_URL}{year}/{day_str}/brdc/{ephem_filename_n_gz}"

    print(f"\nTentando baixar arquivo de efemérides (não comprimido): {url_n}")
    try:
        # Tenta baixar a versão não comprimida (.n)
        response = requests.get(url_n, stream=True)
        response.raise_for_status() # Lança um erro para status de erro (4xx, 5xx)
        with open(output_path, 'wb') as f:
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
            with gzip.open(gz_output_path, 'rb') as f_in:
                with open(output_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out) # Copia o conteúdo descompactado
            os.remove(gz_output_path) # Remove o arquivo .Z após descompactar
            print(f"Arquivo descompactado para: {output_path}")
            return output_path
        except requests.exceptions.RequestException as e_gz:
            print(f"Erro ao baixar {url_n_gz}: {e_gz}")
            print("Não foi possível baixar o arquivo de efemérides. Verifique sua conexão ou tente novamente mais tarde.")
            return None
        except Exception as e_unzip:
            print(f"Erro ao descompactar {gz_output_path}: {e_unzip}")
            return None

def generate_gps_file(gps_sdr_sim_exe_path, ephemeris_file_path, latitude, longitude, altitude, sim_datetime, output_filename_base):
    """
    Executa o programa gps-sdr-sim.exe para gerar o arquivo .c8 e cria o arquivo .txt.
    Inclui os parâmetros de latitude, longitude, altitude e tempo de simulação.
    """
    output_c8_path = os.path.join(OUTPUT_DIR, f"{output_filename_base}.c8")
    
    # Formato da data e hora para o parâmetro -t do gps-sdr-sim: AAAA/MM/DD,HH:MM:SS
    time_param = sim_datetime.strftime("%Y/%m/%d,%H:%M:%S")

    command = [
        gps_sdr_sim_exe_path,
        "-e", ephemeris_file_path,
        "-l", f"{latitude},{longitude},{altitude}",
        "-b", "8", # Bits por amostra (8 para HackRF)
        "-t", time_param, # Parâmetro de tempo de simulação
        "-o", output_c8_path
    ]

    print(f"\nGerando arquivo GPS simulado: {output_c8_path}")
    print(f"Executando comando: {' '.join(command)}")

    try:
        process = subprocess.run(command, capture_output=True, text=True, check=True)
        print("Saída do gps-sdr-sim:")
        print(process.stdout)
        if process.stderr:
            print("Erros (stderr) do gps-sdr-sim:")
            print(process.stderr)
        print(f"Arquivo .c8 gerado com sucesso: {output_c8_path}")
    except FileNotFoundError:
        print(f"ERRO: O executável do gps-sdr-sim não foi encontrado em {gps_sdr_sim_exe_path}.")
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

    # Gera o arquivo .txt de configuração para o PortaPack Mayhem
    output_txt_path = os.path.join(OUTPUT_DIR, f"{output_filename_base}.txt")
    with open(output_txt_path, 'w') as f:
        f.write(f"sample_rate={SAMPLE_RATE}\n")
        f.write(f"center_frequency={CENTER_FREQUENCY}\n")
    print(f"Arquivo .txt de configuração gerado: {output_txt_path}")

    return output_c8_path, output_txt_path

def find_sd_card_path():
    """
    Solicita ao usuário a letra da unidade do cartão SD para copiar os arquivos.
    No Windows, cartões SD aparecem como letras de unidade (ex: D:, E:).
    """
    print("\nPara copiar os arquivos para o cartão SD, preciso saber a letra da unidade.")
    print("Você pode verificar isso no 'Explorador de Arquivos' (Meu Computador/Este PC).")
    
    while True:
        sd_path_input = input("Digite a letra da unidade do cartão SD (Ex: D:): ").strip().upper()
        if len(sd_path_input) == 2 and sd_path_input[1] == ':' and sd_path_input[0].isalpha():
            sd_path = sd_path_input + os.sep # Adiciona a barra invertida para o caminho
            if os.path.exists(sd_path):
                print(f"Unidade '{sd_path_input}' encontrada.")
                return sd_path
            else:
                print(f"Erro: A unidade '{sd_path_input}' não parece existir ou não está acessível. Tente novamente.")
        else:
            print("Formato inválido. Por favor, digite apenas a letra da unidade seguida de dois pontos (Ex: D:).")

def copy_files_to_sd_card(c8_file, txt_file, sd_card_root_path):
    """
    Copia os arquivos .c8 e .txt para a pasta 'gps' no cartão SD.
    """
    gps_folder_on_sd = os.path.join(sd_card_root_path, "gps")
    
    print(f"\nVerificando caminho do cartão SD: {sd_card_root_path}")
    if not os.path.exists(sd_card_root_path):
        print(f"ERRO: O cartão SD não parece estar acessível em {sd_card_root_path}.")
        print("Certifique-se de que o cartão SD está conectado e o caminho está correto.")
        return False

    print(f"Criando pasta 'gps' no cartão SD: {gps_folder_on_sd} (se não existir)")
    os.makedirs(gps_folder_on_sd, exist_ok=True) 

    print(f"Copiando '{os.path.basename(c8_file)}' para '{gps_folder_on_sd}'")
    shutil.copy(c8_file, gps_folder_on_sd)
    print(f"Copiando '{os.path.basename(txt_file)}' para '{gps_folder_on_sd}'")
    shutil.copy(txt_file, gps_folder_on_sd)
    
    print("Arquivos copiados com sucesso para o cartão SD!")
    return True

# --- FUNÇÃO PRINCIPAL ---
def main():
    """
    Função principal que orquestra todo o processo de geração e cópia dos arquivos.
    """
    print("--- Início da Simulação GPS Automatizada no Windows ---")
    print("Este script irá gerar arquivos .c8 e .txt para seu PortaPack H2M com base nas suas entradas.")

    # 1. Verifica e obtém o caminho para o executável gps-sdr-sim.exe
    # Se o caminho padrão não funcionar, ele solicitará ao usuário.
    print("\nEtapa 1: Localizando o executável do gps-sdr-sim...")
    global GPS_SDR_SIM_EXECUTABLE # Permite modificar a variável global
    GPS_SDR_SIM_EXECUTABLE = validate_path(
        "Digite o caminho COMPLETO para o gps-sdr-sim.exe", 
        DEFAULT_GPS_SDR_SIM_EXECUTABLE
    )

    # 2. Solicita ao usuário as coordenadas da localização
    print("\nEtapa 2: Informe a localização que deseja simular.")
    latitude, longitude, altitude = get_user_coordinates()

    # 3. Solicita ao usuário a data e hora da simulação
    print("\nEtapa 3: Informe a data e hora de início da simulação.")
    sim_datetime = get_user_datetime()

    # 4. Cria o diretório de saída para arquivos temporários e gerados.
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"\nDiretório de trabalho para arquivos gerados: {OUTPUT_DIR}")

    # 5. Define o nome do arquivo de efemérides (brdcXXX0.YYn) com base na data da simulação.
    ephemeris_filename = f"brdc{get_day_of_year(sim_datetime):03d}0.{str(sim_datetime.year)[2:]}n"
    ephemeris_output_path = os.path.join(OUTPUT_DIR, ephemeris_filename)

    # 6. Baixa o arquivo de efemérides da NASA para a data informada.
    print("\nEtapa 4: Baixando arquivo de efemérides da NASA...")
    downloaded_ephem_file = download_ephemeris_file(sim_datetime, ephemeris_output_path)
    if not downloaded_ephem_file:
        print("Falha ao baixar o arquivo de efemérides. O script será encerrado.")
        sys.exit(1) # Sai com código de erro

    # 7. Define o nome base para os arquivos de saída .c8 e .txt.
    # O nome pode ser mais descritivo agora que a localização é dinâmica.
    output_filename_base = f"gps_sim_{latitude:.4f}_{longitude:.4f}_{sim_datetime.strftime('%Y%m%d_%H%M%S')}"

    # 8. Gera o arquivo .c8 e o arquivo .txt usando o gps-sdr-sim.exe.
    print("\nEtapa 5: Gerando arquivo GPS simulado (.c8 e .txt) com gps-sdr-sim...")
    generated_files = generate_gps_file(
        GPS_SDR_SIM_EXECUTABLE, 
        downloaded_ephem_file, 
        latitude, longitude, altitude, 
        sim_datetime, 
        output_filename_base
    )
    if not generated_files:
        print("Falha ao gerar os arquivos GPS simulados. O script será encerrado.")
        sys.exit(1) # Sai com código de erro

    c8_file, txt_file = generated_files

    # 9. Copia os arquivos gerados para o cartão SD do PortaPack.
    print("\nEtapa 6: Copiando arquivos para o cartão SD do PortaPack...")
    sd_card_path = find_sd_card_path()

    if not copy_files_to_sd_card(c8_file, txt_file, sd_card_path):
        print("\nOps! Não foi possível copiar os arquivos para o cartão SD automaticamente.")
        print(f"Por favor, copie os arquivos manualmente para a pasta 'gps' do seu cartão SD.")
        print(f"Os arquivos estão localizados em: {OUTPUT_DIR}")
        print(f"Arquivos a copiar: {os.path.basename(c8_file)} e {os.path.basename(txt_file)}")
        print("\nVerifique se o cartão SD está conectado e o caminho da unidade está correto!")
        # Não sai com erro fatal aqui, apenas instrui o usuário a fazer manualmente.

    print("\n--- Simulação GPS Automatizada Concluída! ---")
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


# Verifica se o script está sendo executado diretamente (não importado como módulo)
if __name__ == "__main__":
    main()