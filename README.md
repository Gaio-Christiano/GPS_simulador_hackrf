# Simulador de GPS com gps-sdr-sim + HackRF

Este projeto permite simular sinais de GPS com base em efemérides reais (RINEX) utilizando o programa `gps-sdr-sim` e um HackRF. Ele automatiza o processo de download das efemérides, geração dos dados simulados (`.c8`) e pode ser integrado com o HackRF para transmitir o sinal.

##É para fins de estudos

## 📦 Requisitos

- Python 3.7+
- Sistema operacional Linux (preferencialmente Ubuntu/Debian)
- Dispositivo HackRF
- gps-sdr-sim compilado (`gps-sdr-sim/gps-sdr-sim`)

### Bibliotecas Python necessárias

Instale com:

```bash
pip install requests tqdm


Este repositório contém um script em Python para gerar sinais simulados de GPS utilizando o executável [`gps-sdr-sim`](https://github.com/osqzss/gps-sdr-sim) e o dispositivo SDR [HackRF One](https://greatscottgadgets.com/hackrf/). É ideal para fins de estudo, análise e testes de equipamentos receptores de GPS em ambientes controlados.

## Funcionalidades

- Download automático de efemérides (arquivos .n/.Z) da NASA.
- Permite configurar coordenadas (latitude, longitude, altitude).
- Permite escolher data e hora da simulação.
- Gera arquivos binários `.c8` prontos para transmissão via HackRF.
- Criação de arquivos de configuração compatíveis com PortaPack Mayhem.

## Pré-requisitos

- Python 3.6+
- `gps-sdr-sim.exe` disponível localmente (especifique o caminho).
- HackRF One com firmware atualizado.
- (Opcional) PortaPack com firmware Mayhem.

## Execução

1. Execute o script:
```bash
python simulador_gps.py

Siga as instruções interativas para gerar os arquivos .c8.

Observações
⚠️ Este projeto é para fins educacionais. A transmissão de sinais GPS falsos é ilegal em muitos países. Utilize apenas em ambientes controlados e com permissões apropriadas.

Licença
MIT


---

### Como adicionar e subir o `README.md`:

```bash
echo "# Simulador de Sinal GPS para HackRF" > README.md
# (Cole o restante do conteúdo depois de abrir com o editor ou usando echo múltiplas vezes)

git add README.md
git commit -m "Cria README com instruções e descrição do projeto"
git push origin main
=======
# GPS_simulador_hackrf
Programa para simular sinal de GPS (gerar os arquivos pro hackrf) para estudos de prevenção de ataque de simulação de gps.
