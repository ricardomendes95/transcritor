#!/usr/bin/env python3
"""Transcritor de áudio e vídeo para texto em português (pt-BR) usando faster-whisper.

O FFmpeg extrai a trilha de áudio diretamente de arquivos de vídeo (mp4, mkv etc.),
então basta apontar o caminho do vídeo normalmente, sem conversão manual.

Uso:
    python transcrever.py "C:\\audios\\audio de dani.ogg"
    python transcrever.py audio.mp3 --model medium --device cuda
    python transcrever.py video.mp4 --timestamps
"""

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# No Windows, criar o cache de modelos exige privilégio de symlink (Modo de
# Desenvolvedor ou administrador); sem isso, o download falha com WinError 1314.
# Desabilitar symlinks faz o huggingface_hub copiar os arquivos normalmente.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

FORMATOS_AUDIO = {
    ".ogg", ".mp3", ".wav", ".m4a", ".flac", ".aac", ".wma", ".opus",
}

FORMATOS_VIDEO = {
    ".mp4", ".mkv", ".webm", ".avi", ".mov", ".wmv", ".flv", ".m4v", ".3gp", ".mpg", ".mpeg",
}

FORMATOS_SUPORTADOS = FORMATOS_AUDIO | FORMATOS_VIDEO

MODELOS_VALIDOS = {
    "tiny", "base", "small", "medium",
    "large-v2", "large-v3", "large-v3-turbo", "distil-large-v3",
}

MODELO_PADRAO = "medium"

# Modelos que o faster-whisper 1.0.3 não conhece pelo nome: precisam do repositório no Hub.
REPOSITORIOS_MODELOS = {
    "large-v3-turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
}


class ErroTranscricao(Exception):
    """Erro esperado (arquivo inválido, FFmpeg ausente, CUDA indisponível etc.),
    com mensagem pronta para exibir ao usuário no CLI ou na GUI."""


class TranscricaoCancelada(ErroTranscricao):
    """O usuário cancelou a transcrição; nenhum arquivo foi gravado."""


def erro(msg: str) -> None:
    raise ErroTranscricao(msg)


def verificar_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        erro(
            "FFmpeg não foi encontrado no PATH do sistema.\n"
            "faster-whisper depende do FFmpeg para decodificar áudio.\n\n"
            "Como instalar no Windows:\n"
            "  1. winget install Gyan.FFmpeg\n"
            "     (ou baixe em https://www.gyan.dev/ffmpeg/builds/ e adicione o bin/ ao PATH)\n"
            "  2. Feche e reabra o terminal após instalar.\n"
            "  3. Confirme com: ffmpeg -version"
        )


def verificar_arquivo(caminho: Path) -> None:
    if not caminho.exists():
        erro(f"Arquivo não encontrado: {caminho}")
    if not caminho.is_file():
        erro(f"O caminho informado não é um arquivo: {caminho}")
    if caminho.suffix.lower() not in FORMATOS_SUPORTADOS:
        audio = ", ".join(sorted(FORMATOS_AUDIO))
        video = ", ".join(sorted(FORMATOS_VIDEO))
        erro(
            f"Formato '{caminho.suffix}' não suportado.\n"
            f"Áudio aceito: {audio}\n"
            f"Vídeo aceito: {video}"
        )


def preparar_path_bibliotecas_cuda() -> None:
    """Registra os diretórios das DLLs de cublas/cudnn instaladas via pip (pacotes
    nvidia-*), caso existam, para que o CTranslate2 consiga localizá-las em tempo
    de execução (necessário via os.add_dll_directory desde o Python 3.8 no Windows,
    já que o PATH sozinho não é mais suficiente para o carregador de DLLs)."""
    import os
    import site

    if getattr(sys, "frozen", False):
        # No .exe do PyInstaller, as DLLs ficam na pasta extraída do pacote.
        diretorios_base = [sys._MEIPASS]
    else:
        diretorios_base = list(site.getsitepackages())
        venv_site = Path(sys.prefix) / "Lib" / "site-packages"
        diretorios_base.append(str(venv_site))

    for base in diretorios_base:
        nvidia_dir = Path(base) / "nvidia"
        if not nvidia_dir.is_dir():
            continue
        for sub in nvidia_dir.glob("*/bin"):
            caminho = str(sub)
            os.environ["PATH"] = caminho + ";" + os.environ["PATH"]
            if hasattr(os, "add_dll_directory"):
                try:
                    os.add_dll_directory(caminho)
                except OSError:
                    pass


def cudnn_disponivel() -> bool:
    """Testa se as DLLs de cuDNN necessárias pelo CTranslate2 estão localizáveis."""
    import ctypes

    for nome_dll in ("cudnn_ops_infer64_8.dll", "cudnn_ops_infer64_9.dll", "cublas64_12.dll"):
        try:
            ctypes.WinDLL(nome_dll)
            return True
        except OSError:
            continue
    return False


def resolver_device_e_compute(device_solicitado: str, log=print) -> tuple[str, str]:
    """Retorna (device, compute_type) validando disponibilidade de CUDA."""
    print = log  # noqa: A001
    if device_solicitado == "cpu":
        return "cpu", "int8"

    preparar_path_bibliotecas_cuda()

    # device_solicitado == "cuda" ou "auto"
    cuda_disponivel = False
    try:
        import ctranslate2
        cuda_disponivel = ctranslate2.get_cuda_device_count() > 0
    except Exception:
        cuda_disponivel = False

    mensagem_instalacao = (
        "Bibliotecas cuBLAS/cuDNN do CUDA 12 não foram encontradas.\n"
        "Instale-as com:\n"
        "  pip install nvidia-cublas-cu12 nvidia-cudnn-cu12==8.9.6.50\n"
        "e execute o script novamente (o PATH é ajustado automaticamente)."
    )

    if cuda_disponivel and not cudnn_disponivel():
        if device_solicitado == "cuda":
            erro(
                "GPU NVIDIA detectada, mas o CTranslate2 não conseguiu localizar as "
                "bibliotecas cuDNN/cuBLAS necessárias.\n\n" + mensagem_instalacao
            )
        print(f"[AVISO] {mensagem_instalacao}\n[AVISO] Usando CPU (mais lento).")
        return "cpu", "int8"

    if cuda_disponivel:
        return "cuda", "float16"

    if device_solicitado == "cuda":
        erro(
            "CUDA foi solicitado (--device cuda) mas nenhuma GPU NVIDIA compatível "
            "foi detectada pelo CTranslate2.\n\n"
            "Possíveis causas:\n"
            "  - Driver NVIDIA desatualizado ou ausente.\n"
            "  - Sem GPU NVIDIA na máquina.\n"
            "  - Biblioteca cuDNN/cuBLAS do CUDA não instalada (veja o README.md).\n\n"
            "Use --device cpu para rodar sem GPU, ou --device auto para escolha automática."
        )

    print("[AVISO] CUDA não detectado. Usando CPU (mais lento).")
    return "cpu", "int8"


def formatar_timestamp(segundos: float) -> str:
    h = int(segundos // 3600)
    m = int((segundos % 3600) // 60)
    s = int(segundos % 60)
    return f"[{h:02d}:{m:02d}:{s:02d}]"


def formatar_duracao(segundos: float) -> str:
    m = int(segundos // 60)
    s = segundos % 60
    return f"{m}m{s:05.2f}s"


def formatar_tempo_srt(segundos: float) -> str:
    total_ms = round(segundos * 1000)
    h, resto = divmod(total_ms, 3_600_000)
    m, resto = divmod(resto, 60_000)
    s, ms = divmod(resto, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def montar_srt(segmentos: list[tuple[float, float, str]]) -> str:
    """Monta o conteúdo de uma legenda .srt a partir de (início, fim, texto)."""
    return "\n".join(
        f"{i}\n{formatar_tempo_srt(inicio)} --> {formatar_tempo_srt(fim)}\n{texto}\n"
        for i, (inicio, fim, texto) in enumerate(segmentos, start=1)
    )


PAUSA_PARAGRAFO_PADRAO = 1.5  # segundos de silêncio entre falas para iniciar um novo parágrafo


def carregar_modelo(modelo: str, device: str, log=print) -> tuple:
    """Carrega o modelo e retorna (model, device, compute_type), para que uma fila de
    arquivos reaproveite o mesmo modelo em vez de recarregá-lo a cada arquivo."""
    from faster_whisper import WhisperModel

    print = log  # noqa: A001 - dentro desta função, log substitui o print padrão

    device_resolvido, compute_type = resolver_device_e_compute(device, log=log)

    print("\nCarregando modelo (o download ocorre apenas na primeira execução)...")
    try:
        model = WhisperModel(
            REPOSITORIOS_MODELOS.get(modelo, modelo), device=device_resolvido, compute_type=compute_type
        )
    except ValueError as e:
        erro(f"Falha ao carregar o modelo '{modelo}': {e}")
    except RuntimeError as e:
        msg = str(e).lower()
        if "out of memory" in msg or "cuda" in msg and "memory" in msg:
            erro(
                f"Memória insuficiente na GPU para o modelo '{modelo}'.\n"
                "Tente um modelo menor (--model small ou --model medium) "
                "ou rode em CPU (--device cpu)."
            )
        erro(f"Falha ao carregar o modelo: {e}")
    except Exception as e:
        erro(f"Não foi possível carregar/baixar o modelo '{modelo}': {e}")

    return model, device_resolvido, compute_type


def transcrever(
    caminho_audio: Path,
    modelo: str,
    device: str,
    incluir_timestamps: bool,
    caminho_saida: Path | None = None,
    log=print,
    progresso=None,
    pausa_paragrafo: float = PAUSA_PARAGRAFO_PADRAO,
    usar_vad: bool = False,
    gerar_srt: bool = False,
    cancelar=None,
    modelo_carregado: tuple | None = None,
) -> Path:
    """Executa a transcrição. `log` recebe linhas de texto (para redirecionar a saída
    a uma GUI, por exemplo). `progresso`, se informado, é chamado com uma fração
    de 0.0 a 1.0 conforme o áudio é processado. `cancelar`, se informado, é um
    threading.Event verificado a cada trecho; quando acionado, levanta
    TranscricaoCancelada sem gravar nada. `modelo_carregado` é o retorno de
    carregar_modelo. Com `gerar_srt`, grava também um .srt ao lado do .txt.
    Retorna o caminho do .txt gerado."""
    print = log  # noqa: A001 - dentro desta função, log substitui o print padrão

    if modelo_carregado is None:
        modelo_carregado = carregar_modelo(modelo, device, log=log)
    model, device_resolvido, compute_type = modelo_carregado

    print("=" * 60)
    print(f"Arquivo:    {caminho_audio.name}")
    print(f"Modelo:     {modelo}")
    print(f"Dispositivo:{' ' + device_resolvido} ({compute_type})")
    print(f"Idioma:     pt (português do Brasil)")
    print("=" * 60)

    print("Modelo carregado. Iniciando transcrição...\n")

    inicio = time.time()
    try:
        segments, info = model.transcribe(
            str(caminho_audio),
            language="pt",
            task="transcribe",
            beam_size=5,
            temperature=0.0,
            condition_on_previous_text=False,
            vad_filter=usar_vad,
            vad_parameters={"min_silence_duration_ms": 500} if usar_vad else None,
        )
    except RuntimeError as e:
        msg = str(e).lower()
        if "out of memory" in msg:
            erro(
                "Memória insuficiente durante a transcrição.\n"
                "Tente um modelo menor ou rode em CPU (--device cpu)."
            )
        erro(f"Erro durante a transcrição: {e}")
    except Exception as e:
        erro(f"Erro durante a transcrição: {e}")

    print(f"Idioma detectado: {info.language} (confiança: {info.language_probability:.2f})")
    print(f"Duração do áudio: {formatar_duracao(info.duration)}\n")

    segmentos_coletados = []  # (inicio, fim, texto)
    ultimo_print = time.time()
    duracao_total = info.duration or 1.0
    for segment in segments:
        if cancelar is not None and cancelar.is_set():
            raise TranscricaoCancelada("Transcrição cancelada.")

        texto = segment.text.strip()
        if not texto:
            continue
        segmentos_coletados.append((segment.start, segment.end, texto))

        if progresso is not None:
            progresso(min(segment.end / duracao_total, 1.0))

        if time.time() - ultimo_print > 1.0:
            print(f"  ... processando até {formatar_timestamp(segment.end)}")
            ultimo_print = time.time()

    fim = time.time()

    if not segmentos_coletados:
        erro("Nenhum segmento de fala foi reconhecido no áudio.")

    # Agrupa os segmentos em parágrafos: uma pausa de fala >= pausa_paragrafo
    # segundos inicia um parágrafo novo, o que evita que a transcrição toda
    # saia em uma única linha corrida.
    limiar_paragrafo = pausa_paragrafo if pausa_paragrafo > 0 else float("inf")
    paragrafos: list[list[tuple[float, str]]] = []
    paragrafo_atual: list[tuple[float, str]] = []
    fim_segmento_anterior = None
    for inicio_seg, fim_segmento, texto in segmentos_coletados:
        if fim_segmento_anterior is not None and (inicio_seg - fim_segmento_anterior) >= limiar_paragrafo:
            if paragrafo_atual:
                paragrafos.append(paragrafo_atual)
            paragrafo_atual = []
        paragrafo_atual.append((inicio_seg, texto))
        fim_segmento_anterior = fim_segmento
    if paragrafo_atual:
        paragrafos.append(paragrafo_atual)

    if incluir_timestamps:
        blocos = [
            "\n".join(f"{formatar_timestamp(inicio_seg)} {texto}" for inicio_seg, texto in paragrafo)
            for paragrafo in paragrafos
        ]
    else:
        blocos = [" ".join(texto for _, texto in paragrafo).strip() for paragrafo in paragrafos]

    texto_final = "\n\n".join(blocos) + "\n"

    caminho_txt = caminho_saida if caminho_saida is not None else caminho_audio.with_suffix(".txt")
    caminho_txt.parent.mkdir(parents=True, exist_ok=True)
    caminho_txt.write_text(texto_final, encoding="utf-8")
    if gerar_srt:
        caminho_txt.with_suffix(".srt").write_text(montar_srt(segmentos_coletados), encoding="utf-8")

    if progresso is not None:
        progresso(1.0)

    print("\n" + "=" * 60)
    print(f"Transcrição concluída em {formatar_duracao(fim - inicio)}")
    print(f"Arquivo gerado: {caminho_txt}")
    if gerar_srt:
        print(f"Legenda gerada: {caminho_txt.with_suffix('.srt')}")
    print("=" * 60)

    return caminho_txt


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="transcrever.py",
        description="Transcreve arquivos de áudio para texto em português (pt-BR) usando faster-whisper, 100% local.",
    )
    parser.add_argument("audio", type=str, help="Caminho do arquivo de áudio ou vídeo a transcrever.")
    parser.add_argument(
        "--model",
        type=str,
        default=MODELO_PADRAO,
        choices=sorted(MODELOS_VALIDOS),
        help=f"Modelo Whisper a usar (padrão: {MODELO_PADRAO}).",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="auto",
        choices=["auto", "cuda", "cpu"],
        help="Dispositivo de processamento (padrão: auto).",
    )
    parser.add_argument(
        "--timestamps",
        action="store_true",
        help="Inclui marcações de tempo [HH:MM:SS] no TXT gerado.",
    )
    parser.add_argument(
        "--srt",
        action="store_true",
        help="Gera também uma legenda .srt ao lado do TXT.",
    )
    parser.add_argument(
        "--saida",
        type=str,
        default=None,
        help="Caminho do .txt de destino (padrão: mesma pasta e nome do áudio).",
    )
    parser.add_argument(
        "--vad",
        action="store_true",
        help=(
            "Ativa o filtro de detecção de voz (VAD) para pular trechos de silêncio. "
            "Desativado por padrão: em alguns vídeos/áudios com música de fundo, o VAD "
            "classifica trechos sem fala clara como silêncio e corta o resto da transcrição."
        ),
    )
    parser.add_argument(
        "--pausa-paragrafo",
        type=float,
        default=PAUSA_PARAGRAFO_PADRAO,
        help=(
            "Duração mínima de silêncio (em segundos) para iniciar um novo parágrafo "
            f"no TXT (padrão: {PAUSA_PARAGRAFO_PADRAO}). Use 0 para desativar a quebra "
            "em parágrafos e manter o texto corrido em uma única linha."
        ),
    )

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)

    args = parser.parse_args()

    caminho_audio = Path(args.audio).expanduser().resolve()
    caminho_saida = Path(args.saida).expanduser().resolve() if args.saida else None

    try:
        verificar_ffmpeg()
        verificar_arquivo(caminho_audio)
        transcrever(
            caminho_audio,
            args.model,
            args.device,
            args.timestamps,
            caminho_saida=caminho_saida,
            pausa_paragrafo=args.pausa_paragrafo,
            usar_vad=args.vad,
            gerar_srt=args.srt,
        )
    except ErroTranscricao as e:
        print(f"\n[ERRO] {e}\n", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[Cancelado pelo usuário]")
        sys.exit(130)
