# Transcritor de Áudio e Vídeo para Texto (pt-BR)

## ⬇️ Baixar para Windows

**[Baixar o Transcritor v1.0.0 para Windows 64 bits (.zip, 1,35 GB)](https://github.com/ricardomendes95/transcritor/releases/latest/download/Transcritor-v1.0.0-windows-x64.zip)**

1. Extraia a pasta inteira do `.zip`.
2. Instale o FFmpeg, que é obrigatório: `winget install Gyan.FFmpeg`.
3. Abra `Transcritor.exe`.

O Windows SmartScreen pode alertar porque o app não é assinado: clique em "Mais informações" e "Executar assim mesmo". Veja todas as versões em [Releases](https://github.com/ricardomendes95/transcritor/releases).

Transcrição de áudio ou vídeo para texto 100% local, usando [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (Whisper otimizado com CTranslate2). Nenhum áudio é enviado para serviços externos.

Formatos de áudio aceitos: `.ogg`, `.mp3`, `.wav`, `.m4a`, `.flac`, `.aac`, `.wma`, `.opus`.
Formatos de vídeo aceitos: `.mp4`, `.mkv`, `.webm`, `.avi`, `.mov`, `.wmv`, `.flv`, `.m4v`, `.3gp`, `.mpg`, `.mpeg` (o FFmpeg extrai a trilha de áudio automaticamente, sem precisar converter antes).

Testado neste projeto com: Python 3.11, Windows 11, GPU NVIDIA RTX 3050 Laptop (4 GB VRAM).

## Instalar a partir do código (Windows)

Com Python 3.11, FFmpeg e Git instalados (seções 1 e 2):

```powershell
git clone https://github.com/ricardomendes95/transcritor.git
cd transcritor
python -m venv venv
venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
.\build.bat
```

O programa fica em `dist\Transcritor\Transcritor.exe`. A instalação baixa cerca de 3 GB de dependências, e o modelo escolhido é baixado na primeira transcrição.

## Estrutura

```
transcritor/
├── transcrever.py         # motor de transcrição e linha de comando
├── transcrever_gui.py     # interface gráfica
├── transcrever.bat        # transcreve o arquivo arrastado sobre ele
├── transcrever_gui.bat    # abre a interface usando o venv
├── build.bat              # gera o .exe
├── transcritor.spec       # configuração do PyInstaller
├── requirements.txt
├── requirements-build.txt
├── assets/                # ícones
└── README.md
```

O `.txt` gerado é salvo **na mesma pasta do áudio de origem**, exceto se você usar `--saida` ou "Pasta de destino" na interface.

## 1. Instalar o Python

Baixe o Python 3.11 (recomendado) em https://www.python.org/downloads/ e marque a opção **"Add python.exe to PATH"** durante a instalação.

Confirme no terminal:

```powershell
python --version
```

## 2. Instalar o FFmpeg no Windows

Forma mais simples, via `winget`:

```powershell
winget install Gyan.FFmpeg
```

Feche e reabra o terminal, depois confirme:

```powershell
ffmpeg -version
```

Se `winget` não estiver disponível, baixe o build em https://www.gyan.dev/ffmpeg/builds/ (essentials build), extraia e adicione a pasta `bin` ao PATH do Windows.

## 3. Criar o ambiente virtual

Baixe o projeto e crie o ambiente dentro da pasta dele:

```powershell
git clone https://github.com/ricardomendes95/transcritor.git
cd transcritor
python -m venv venv
venv\Scripts\activate
```

Você verá `(venv)` no início do prompt quando estiver ativo.

## 4. Instalar as dependências

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Isso instala `faster-whisper`, `ctranslate2==4.4.0` (combinação estável e testada com CUDA 12), as bibliotecas de CUDA e, para a interface gráfica, `customtkinter`, `pillow` e `tkinterdnd2`.

## 5. Usar GPU NVIDIA (CUDA) — opcional, mas recomendado

O CTranslate2 (motor por trás do faster-whisper) precisa das bibliotecas **cuBLAS** e **cuDNN** do CUDA 12 em tempo de execução. Elas já vêm no `requirements.txt` (cerca de 2 GB), sem precisar instalar o CUDA Toolkit completo, e o script ajusta o PATH sozinho. No macOS elas não são instaladas, pois não há CUDA.

Requisitos:
- Driver NVIDIA atualizado (o driver já detectado nesta máquina, 581.57, é compatível com CUDA 12).
- GPU com pelo menos ~4 GB de VRAM livres para os modelos `small`/`medium`. Para `large-v3` completo, considere 8+ GB; use `large-v3-turbo` se quiser qualidade próxima do `large` com menos VRAM.

Se o CUDA não for detectado, o script avisa claramente e sugere usar `--device cpu`.

## 6. Usar CPU (sem GPU)

Não é necessário nenhum passo extra. Basta rodar com `--device cpu` (ou deixar `--device auto`, que cai para CPU automaticamente se não houver CUDA disponível). CPU é mais lento, especialmente em modelos `medium`/`large`.

## 7. Como executar

Ativando o ambiente virtual primeiro:

```powershell
venv\Scripts\activate
```

### Exemplo básico (usa modelo `medium`, escolhe GPU/CPU automaticamente)

```powershell
python transcrever.py "C:\audios\reuniao.mp3"
```

### Especificando modelo e dispositivo

```powershell
python transcrever.py "C:\audios\reuniao.mp3" --model large-v3-turbo --device cuda
```

```powershell
python transcrever.py "C:\audios\reuniao.mp3" --model small --device cpu
```

### Gerando TXT com timestamps

```powershell
python transcrever.py "C:\audios\reuniao.mp3" --timestamps
```

Saída, por exemplo:

```
[00:00:03] Bom dia, tudo bem?
[00:00:08] Eu queria conversar com você sobre...
```

## Interface gráfica (selecionar áudio e destino visualmente)

Além da linha de comando, há uma interface gráfica em CustomTkinter (tema escuro) para selecionar o áudio, escolher onde salvar o `.txt`, o modelo e o dispositivo, e acompanhar o progresso.

Com o ambiente virtual ativado (para desenvolvimento):

```powershell
python transcrever_gui.py
```

Ou dando duplo clique em `transcrever_gui.bat` (não precisa ativar o venv manualmente; continua funcionando para desenvolvimento).

Na janela: arraste áudios, vídeos ou pastas para qualquer ponto da janela (ou clique em "Selecionar arquivos"), escolha modelo/dispositivo e clique em "Transcrever". Os arquivos são processados em fila, reaproveitando o modelo carregado, e novos arquivos podem ser adicionados durante a execução. Por padrão, cada `.txt` fica na mesma pasta do arquivo de origem; "Pasta de destino" muda isso para todos.

- **Cancelar**: o botão "Transcrever" vira "Cancelar" durante a execução. O arquivo atual é interrompido no próximo trecho, sem gravar nada, e os demais continuam na fila. O carregamento ou download do modelo não é interrompido no meio: o cancelamento vale quando ele termina.
- **Gerar legenda .srt**: grava também uma legenda ao lado do `.txt` (na linha de comando, use `--srt`).
- Clique em um item concluído para abrir a aba dele; em um item com erro, para ver o log.

Depois de transcrever, o texto aparece na aba "Transcrição" dentro do próprio app, onde pode ser editado. Cada arquivo abre sua própria aba: a troca entre abas mantém as edições, um ponto (•) marca a aba com edições não salvas, e o desfazer (Ctrl+Z) não sobrevive à troca. Há três botões, que valem para a aba atual:
- **Copiar texto**: copia o texto com as edições, sem precisar salvar.
- **Salvar alterações** (ou Ctrl+S): grava as edições no TXT gerado.
- **Abrir local do arquivo**: abre o Explorer com o arquivo selecionado.

### Usar como programa nativo (.exe)

Rodar `build.bat` gera `dist\Transcritor\Transcritor.exe`, com ícone e sem depender do venv para executar. A pasta inteira `dist\Transcritor` precisa ficar junta, pois contém as DLLs de CUDA (cerca de 2 GB). O FFmpeg continua sendo necessário no PATH, e os modelos continuam no cache do Hugging Face.

## Escolha de modelo

| Modelo            | Qualidade pt-BR | VRAM aprox. (float16) | Velocidade | Quando usar |
|-------------------|-----------------|------------------------|------------|-------------|
| `small`           | Boa             | ~1 GB                  | Rápida     | Testes rápidos, GPUs com pouca VRAM |
| `medium` (padrão) | Muito boa       | ~2-3 GB                | Média      | Melhor equilíbrio para a maioria dos casos |
| `large-v3-turbo`  | Excelente       | ~3-4 GB                | Rápida     | Qualidade alta cabendo em GPUs de 4 GB, como a desta máquina |
| `large-v3`        | Excelente       | ~8-10 GB               | Lenta      | Só se houver VRAM sobrando (8+ GB) |

O modelo é baixado do Hugging Face na primeira vez em que é usado e fica em cache para as próximas.

Com uma RTX 3050 de 4 GB, `medium` e `large-v3-turbo` são as opções mais seguras. `large-v3` completo tende a estourar a VRAM disponível.

## Escolher entre CPU e GPU

- `--device auto` (padrão): usa GPU se o CTranslate2 detectar CUDA disponível; senão cai para CPU e avisa no terminal.
- `--device cuda`: força GPU; se CUDA não estiver disponível/configurado, o script explica o motivo em vez de travar com erro confuso.
- `--device cpu`: força CPU, útil para não competir por VRAM com outros programas (jogos, outras IAs) ou em máquinas sem GPU NVIDIA.

## Uso simplificado: arrastar o áudio para o script

No Windows, crie um atalho para arrastar arquivos direto sobre ele. Duas opções:

**Opção A — arquivo `.bat` (mais simples):**

O projeto já inclui `transcrever.bat`, com este conteúdo:

```bat
@echo off
call "%~dp0venv\Scripts\activate.bat"
python "%~dp0transcrever.py" %1
pause
```

Depois, basta arrastar um arquivo de áudio e soltar sobre `transcrever.bat` no Explorer. O terminal abre, mostra o progresso e mantém a janela aberta no final (`pause`) para você ver o resultado.

**Opção B — atalho na área de trabalho:**

Clique com o botão direito em `transcrever.bat` → "Criar atalho" → mova o atalho para a Área de Trabalho. Agora você pode arrastar áudios direto para esse atalho.

## Tratamento de erros

O script identifica e explica, sem travar de forma confusa:

- arquivo inexistente ou formato não suportado;
- FFmpeg ausente no PATH;
- CUDA indisponível quando `--device cuda` é forçado;
- memória insuficiente (RAM ou VRAM) durante carregamento ou transcrição;
- falha ao baixar/carregar o modelo;
- erros inesperados durante a transcrição.

## Sobre fidelidade da transcrição

O script usa `temperature=0.0` e `condition_on_previous_text=False` para reduzir alucinações (o modelo "inventar" palavras). O filtro de VAD, que pula trechos de silêncio, vem desligado por padrão porque pode cortar fala com música de fundo; ative-o com `--vad` ou pela opção na interface.

## Licença

[MIT](LICENSE).
