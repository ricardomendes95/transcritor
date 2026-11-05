#!/usr/bin/env python3
"""Interface gráfica para o transcritor de áudio (pt-BR), usando CustomTkinter.

Uso:
    python transcrever_gui.py
"""

import ctypes
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
from tkinterdnd2 import DND_FILES, TkinterDnD

import transcrever as core


def caminho_recurso(rel: str) -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / rel


COR_FUNDO = "#11131A"
COR_PAINEL = "#171A24"
COR_CARTAO = "#1F2330"
COR_CAMPO = "#151823"
COR_ACENTO = "#7C5CFC"
COR_ACENTO_HOVER = "#6A49EB"
COR_CIANO = "#22D3EE"
COR_SUCESSO = "#2DD4BF"
COR_ERRO = "#FB7185"
COR_TEXTO = "#E8EAF2"
COR_TEXTO_SEC = "#9AA0B4"
COR_BOTAO_SEC = "#2A2F42"
COR_BOTAO_SEC_HOVER = "#363C54"

FONTE = "Segoe UI"
FONTE_LOG = "Consolas"

GLOSSARIO_MODELOS = {
    "tiny": (
        "Mais rápido, menor qualidade.",
        "Modelo minúsculo (~75 MB). Usa pouquíssima RAM/VRAM e roda quase instantaneamente, "
        "mas erra bastante em português, principalmente com sotaques, ruído de fundo ou fala rápida. "
        "Só recomendado para testes rápidos ou áudios muito simples.",
    ),
    "base": (
        "Rápido, qualidade básica.",
        "Um pouco maior que o tiny (~145 MB). Ainda é rápido e leve, com qualidade um pouco melhor, "
        "mas continua abaixo do ideal para transcrições que precisam de fidelidade.",
    ),
    "small": (
        "Boa qualidade, leve.",
        "Modelo intermediário (~500 MB, ~1 GB de VRAM). Boa relação entre velocidade e qualidade para "
        "português. Ótima escolha em máquinas com pouca VRAM ou para transcrições rápidas de rascunho.",
    ),
    "medium": (
        "Muito boa qualidade (padrão recomendado).",
        "Modelo padrão deste script (~1,5 GB, ~2-3 GB de VRAM). Equilíbrio muito bom entre qualidade e "
        "velocidade em português. Recomendado para a maioria dos áudios, inclusive os mais longos.",
    ),
    "large-v2": (
        "Excelente qualidade, mais pesado.",
        "Modelo grande, anterior ao large-v3 (~3 GB, 8+ GB de VRAM recomendados). Qualidade muito alta, "
        "porém mais lento e pesado. Prefira o large-v3 ou o large-v3-turbo, que são mais recentes.",
    ),
    "large-v3": (
        "Excelente qualidade, o mais pesado.",
        "Modelo grande mais recente (~3 GB, 8-10 GB de VRAM recomendados). A melhor qualidade disponível, "
        "mas exige GPU com bastante VRAM; em GPUs de 4 GB (como a desta máquina) pode não caber ou ficar "
        "lento. Considere large-v3-turbo como alternativa mais leve com qualidade parecida.",
    ),
    "large-v3-turbo": (
        "Excelente qualidade, mais leve que o large-v3.",
        "Versão otimizada do large-v3 (~1,6 GB, cabe em ~3-4 GB de VRAM). Qualidade muito próxima do "
        "large-v3 com bem mais velocidade e menos consumo de memória. Boa escolha em GPUs de 4 GB.",
    ),
    "distil-large-v3": (
        "Qualidade próxima do large, mais rápido.",
        "Versão destilada (comprimida) do large-v3, focada em velocidade mantendo qualidade próxima do "
        "original. Consome menos recursos que o large-v3 completo, mas pode perder um pouco de precisão "
        "em nuances específicas do português.",
    ),
}

GLOSSARIO_DEVICES = {
    "auto": (
        "Escolhe GPU automaticamente, senão usa CPU.",
        "O script detecta se há uma GPU NVIDIA com CUDA/cuDNN disponíveis e usa a GPU automaticamente. "
        "Se não encontrar, cai para CPU e avisa no log. Recomendado para a maioria dos usos.",
    ),
    "cuda": (
        "Força o uso da GPU NVIDIA.",
        "Usa a GPU NVIDIA via CUDA, muito mais rápido que CPU (nesta máquina, ~3x mais rápido no modelo "
        "medium). Requer GPU NVIDIA com drivers e bibliotecas cuBLAS/cuDNN instaladas — se não estiverem "
        "disponíveis, o script explica o motivo em vez de travar.",
    ),
    "cpu": (
        "Força o uso do processador (sem GPU).",
        "Usa apenas a CPU. Funciona em qualquer computador, mas é bem mais lento que GPU, especialmente "
        "com modelos medium/large. Útil se a GPU estiver sendo usada por outro programa (jogo, outra IA) "
        "ou se não houver GPU NVIDIA disponível.",
    ),
}


ROTULOS_STATUS = {
    "aguardando": ("Aguardando", COR_TEXTO_SEC),
    "transcrevendo": ("Transcrevendo", COR_CIANO),
    "concluido": ("Concluído", COR_SUCESSO),
    "erro": ("Erro", COR_ERRO),
    "cancelado": ("Cancelado", COR_TEXTO_SEC),
}


@dataclass(eq=False)
class ItemFila:
    audio: Path
    status: str = "aguardando"
    saida: Path | None = None
    erro: str = ""
    lbl_status: ctk.CTkLabel | None = None


@dataclass(eq=False)
class Documento:
    """Uma aba do preview. `texto` guarda as edições enquanto outra aba está aberta."""

    caminho: Path
    texto_salvo: str
    texto: str
    editado: bool = False


class JanelaPrincipal(ctk.CTk, TkinterDnD.DnDWrapper):
    """Janela do CustomTkinter com o suporte a arrastar e soltar do tkdnd."""


class TranscritorGUI:
    def __init__(self, root: ctk.CTk) -> None:
        self.root = root
        self.root.title("Transcritor de Áudio e Vídeo (pt-BR)")

        self.pasta_destino = tk.StringVar()
        self.modelo = tk.StringVar(value=core.MODELO_PADRAO)
        self.device = tk.StringVar(value="auto")
        self.timestamps = tk.BooleanVar(value=False)
        self.usar_vad = tk.BooleanVar(value=False)
        self.gerar_srt = tk.BooleanVar(value=False)
        self.pausa_paragrafo = tk.DoubleVar(value=core.PAUSA_PARAGRAFO_PADRAO)
        self.status = tk.StringVar(value="Pronto.")
        self.percentual = tk.StringVar(value="")

        self.fila = queue.Queue()
        self.em_execucao = False
        self._inicio_execucao = 0.0
        self._progresso_determinado = False
        self.itens: list[ItemFila] = []
        self._trava_itens = threading.Lock()  # protege self.itens entre a UI e a thread de trabalho
        self._cancelar = threading.Event()
        self._encerrados_rodada = 0
        self._sucessos_rodada = 0
        self.documentos: list[Documento] = []
        self.doc_atual: Documento | None = None
        self._logo = None

        self._montar_layout()
        self.root.protocol("WM_DELETE_WINDOW", self._fechar)
        self._ativar_arrastar_e_soltar()
        self.root.after(100, self._processar_fila)

    # ------------------------------------------------------------------ UI

    def _cartao(self, pai, titulo: str) -> ctk.CTkFrame:
        cartao = ctk.CTkFrame(pai, fg_color=COR_CARTAO, corner_radius=14)
        cartao.pack(fill="x", padx=6, pady=(0, 12))
        cartao.columnconfigure(0, weight=1)
        ctk.CTkLabel(
            cartao, text=titulo, font=(FONTE, 14, "bold"), text_color=COR_CIANO, anchor="w"
        ).grid(row=0, column=0, columnspan=2, sticky="ew", padx=14, pady=(12, 4))
        return cartao

    def _montar_layout(self) -> None:
        self.root.configure(fg_color=COR_FUNDO)
        self.root.columnconfigure(0, weight=0, minsize=400)
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)

        esquerda = ctk.CTkFrame(self.root, fg_color=COR_PAINEL, corner_radius=0, width=400)
        esquerda.grid(row=0, column=0, sticky="nsew")
        esquerda.grid_propagate(False)
        esquerda.columnconfigure(0, weight=1)
        esquerda.rowconfigure(1, weight=1)

        self._montar_cabecalho(esquerda)

        rolagem = ctk.CTkScrollableFrame(
            esquerda, fg_color="transparent", corner_radius=0,
            scrollbar_button_color=COR_BOTAO_SEC, scrollbar_button_hover_color=COR_ACENTO,
        )
        rolagem.grid(row=1, column=0, sticky="nsew", padx=(10, 4), pady=(0, 4))
        self._montar_arquivos(rolagem)
        self._montar_opcoes(rolagem)

        self._montar_rodape(esquerda)

        direita = ctk.CTkFrame(self.root, fg_color="transparent")
        direita.grid(row=0, column=1, sticky="nsew", padx=18, pady=18)
        direita.columnconfigure(0, weight=1)
        direita.rowconfigure(1, weight=1)
        self._montar_direita(direita)

    def _montar_cabecalho(self, pai) -> None:
        cab = ctk.CTkFrame(pai, fg_color="transparent")
        cab.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 12))
        coluna_texto = 0
        icone = caminho_recurso("assets/icone.png")
        if icone.exists():
            try:
                from PIL import Image

                imagem = Image.open(icone)
                self._logo = ctk.CTkImage(light_image=imagem, dark_image=imagem, size=(40, 40))
                ctk.CTkLabel(cab, image=self._logo, text="").grid(row=0, column=0, rowspan=2, padx=(0, 12))
                coluna_texto = 1
            except Exception:
                self._logo = None
        ctk.CTkLabel(
            cab, text="Transcritor", font=(FONTE, 22, "bold"), text_color=COR_TEXTO, anchor="w"
        ).grid(row=0, column=coluna_texto, sticky="w")
        ctk.CTkLabel(
            cab, text="Áudio e vídeo para texto, em português", font=(FONTE, 12),
            text_color=COR_TEXTO_SEC, anchor="w",
        ).grid(row=1, column=coluna_texto, sticky="w")

    def _montar_arquivos(self, pai) -> None:
        cartao = self._cartao(pai, "Arquivos")

        area_soltar = ctk.CTkFrame(
            cartao, fg_color=COR_CAMPO, border_color=COR_ACENTO, border_width=1, corner_radius=10
        )
        area_soltar.grid(row=1, column=0, columnspan=2, sticky="ew", padx=14, pady=(2, 10))
        area_soltar.columnconfigure(0, weight=1)
        ctk.CTkLabel(
            area_soltar, text="Arraste áudios, vídeos ou pastas para a janela", font=(FONTE, 12),
            text_color=COR_TEXTO_SEC,
        ).grid(row=0, column=0, padx=10, pady=(10, 4))
        ctk.CTkButton(
            area_soltar, text="Selecionar arquivos", width=140, height=30, corner_radius=8, font=(FONTE, 12),
            fg_color=COR_BOTAO_SEC, hover_color=COR_BOTAO_SEC_HOVER, text_color=COR_TEXTO,
            command=self._escolher_audios,
        ).grid(row=1, column=0, pady=(0, 10))

        self.frame_fila = ctk.CTkFrame(cartao, fg_color="transparent")
        self.frame_fila.grid(row=2, column=0, columnspan=2, sticky="ew", padx=14, pady=(0, 8))
        self.frame_fila.columnconfigure(0, weight=1)
        self.frame_fila.grid_remove()

        ctk.CTkLabel(
            cartao, text="Pasta de destino (vazio = mesma pasta de cada arquivo)", font=(FONTE, 12),
            text_color=COR_TEXTO_SEC, anchor="w",
        ).grid(row=3, column=0, columnspan=2, sticky="ew", padx=14)
        ctk.CTkEntry(
            cartao, textvariable=self.pasta_destino, fg_color=COR_CAMPO, border_color=COR_BOTAO_SEC,
            text_color=COR_TEXTO, corner_radius=8, height=32, font=(FONTE, 12),
        ).grid(row=4, column=0, sticky="ew", padx=(14, 6), pady=(2, 14))
        ctk.CTkButton(
            cartao, text="Escolher", width=84, height=32, corner_radius=8, font=(FONTE, 12),
            fg_color=COR_BOTAO_SEC, hover_color=COR_BOTAO_SEC_HOVER, text_color=COR_TEXTO,
            command=self._escolher_pasta,
        ).grid(row=4, column=1, padx=(0, 14), pady=(2, 14))

    def _renderizar_fila(self) -> None:
        for widget in self.frame_fila.winfo_children():
            widget.destroy()
        if not self.itens:
            self.frame_fila.grid_remove()
            return
        self.frame_fila.grid()

        for linha, item in enumerate(self.itens):
            nome = item.audio.name
            nome = nome if len(nome) <= 30 else nome[:27] + "..."
            lbl_nome = ctk.CTkLabel(
                self.frame_fila, text=nome, font=(FONTE, 12), text_color=COR_TEXTO, anchor="w", height=24
            )
            lbl_nome.grid(row=linha, column=0, sticky="ew")
            lbl_nome.bind("<Button-1>", lambda _e, i=item: self._abrir_item(i))
            item.lbl_status = ctk.CTkLabel(self.frame_fila, text="", font=(FONTE, 11), anchor="e", height=24)
            item.lbl_status.grid(row=linha, column=1, sticky="e", padx=(8, 4))
            item.lbl_status.bind("<Button-1>", lambda _e, i=item: self._abrir_item(i))
            ctk.CTkButton(
                self.frame_fila, text="×", width=24, height=24, corner_radius=12, font=(FONTE, 13),
                fg_color="transparent", hover_color=COR_BOTAO_SEC, text_color=COR_TEXTO_SEC,
                command=lambda i=item: self._remover_item(i),
            ).grid(row=linha, column=2)
            self._atualizar_item(item)

        ctk.CTkButton(
            self.frame_fila, text="Limpar lista", width=84, height=26, corner_radius=8, font=(FONTE, 11),
            fg_color="transparent", hover_color=COR_BOTAO_SEC, text_color=COR_TEXTO_SEC,
            command=self._limpar_fila,
        ).grid(row=len(self.itens), column=0, columnspan=3, sticky="e", pady=(4, 0))

    def _atualizar_item(self, item: ItemFila) -> None:
        if item.lbl_status is not None:
            texto, cor = ROTULOS_STATUS[item.status]
            item.lbl_status.configure(text=texto, text_color=cor)

    def _linha_menu(self, cartao, linha: int, rotulo: str, variavel, valores, foco: str, descricao_var) -> None:
        ctk.CTkLabel(
            cartao, text=rotulo, font=(FONTE, 12), text_color=COR_TEXTO_SEC, anchor="w"
        ).grid(row=linha, column=0, columnspan=2, sticky="ew", padx=14)
        menu = ctk.CTkOptionMenu(
            cartao, variable=variavel, values=valores, height=32, corner_radius=8, font=(FONTE, 12),
            dropdown_font=(FONTE, 12), fg_color=COR_CAMPO, button_color=COR_ACENTO,
            button_hover_color=COR_ACENTO_HOVER, dropdown_fg_color=COR_CARTAO,
            dropdown_hover_color=COR_ACENTO, text_color=COR_TEXTO, dropdown_text_color=COR_TEXTO,
        )
        menu.grid(row=linha + 1, column=0, sticky="ew", padx=(14, 6), pady=(2, 2))
        ctk.CTkButton(
            cartao, text="?", width=32, height=32, corner_radius=16, font=(FONTE, 13, "bold"),
            fg_color=COR_BOTAO_SEC, hover_color=COR_CIANO, text_color=COR_TEXTO,
            command=lambda: self._abrir_glossario(foco),
        ).grid(row=linha + 1, column=1, padx=(0, 14), pady=(2, 2))
        ctk.CTkLabel(
            cartao, textvariable=descricao_var, font=(FONTE, 11), text_color=COR_TEXTO_SEC,
            wraplength=300, justify="left", anchor="w",
        ).grid(row=linha + 2, column=0, columnspan=2, sticky="ew", padx=14, pady=(0, 10))

    def _montar_opcoes(self, pai) -> None:
        cartao = self._cartao(pai, "Opções")
        self.descricao_modelo = tk.StringVar()
        self.descricao_device = tk.StringVar()

        self._linha_menu(
            cartao, 1, "Modelo", self.modelo, sorted(core.MODELOS_VALIDOS), "modelo", self.descricao_modelo
        )
        self._linha_menu(
            cartao, 4, "Dispositivo", self.device, ["auto", "cuda", "cpu"], "device", self.descricao_device
        )
        self.modelo.trace_add("write", self._atualizar_descricoes)
        self.device.trace_add("write", self._atualizar_descricoes)
        self._atualizar_descricoes()

        estilo_switch = dict(
            font=(FONTE, 12), text_color=COR_TEXTO, progress_color=COR_ACENTO,
            button_color=COR_TEXTO, button_hover_color="#FFFFFF", fg_color=COR_BOTAO_SEC,
        )
        ctk.CTkSwitch(
            cartao, text="Incluir timestamps [HH:MM:SS]", variable=self.timestamps, **estilo_switch
        ).grid(row=7, column=0, columnspan=2, sticky="w", padx=14, pady=(2, 8))
        ctk.CTkSwitch(
            cartao, text="Gerar legenda .srt", variable=self.gerar_srt, **estilo_switch
        ).grid(row=8, column=0, columnspan=2, sticky="w", padx=14, pady=(0, 8))
        ctk.CTkSwitch(
            cartao, text="Filtrar silêncio (VAD)", variable=self.usar_vad, **estilo_switch
        ).grid(row=9, column=0, columnspan=2, sticky="w", padx=14, pady=(0, 2))
        ctk.CTkLabel(
            cartao, text="Pode cortar trechos com música de fundo.", font=(FONTE, 11),
            text_color=COR_TEXTO_SEC, anchor="w",
        ).grid(row=10, column=0, columnspan=2, sticky="ew", padx=14, pady=(0, 10))

        linha_pausa = ctk.CTkFrame(cartao, fg_color="transparent")
        linha_pausa.grid(row=11, column=0, columnspan=2, sticky="ew", padx=14)
        linha_pausa.columnconfigure(0, weight=1)
        ctk.CTkLabel(
            linha_pausa, text="Pausa para novo parágrafo", font=(FONTE, 12), text_color=COR_TEXTO_SEC, anchor="w"
        ).grid(row=0, column=0, sticky="w")
        self.lbl_pausa = ctk.CTkLabel(
            linha_pausa, text="", font=(FONTE, 12, "bold"), text_color=COR_CIANO, anchor="e"
        )
        self.lbl_pausa.grid(row=0, column=1, sticky="e")
        self.slider_pausa = ctk.CTkSlider(
            cartao, from_=0, to=10, number_of_steps=20, variable=self.pausa_paragrafo,
            progress_color=COR_ACENTO, button_color=COR_CIANO, button_hover_color="#67E8F9",
            fg_color=COR_BOTAO_SEC, command=self._atualizar_rotulo_pausa,
        )
        self.slider_pausa.grid(row=12, column=0, columnspan=2, sticky="ew", padx=14, pady=(6, 14))
        self._atualizar_rotulo_pausa()

    def _montar_rodape(self, pai) -> None:
        rodape = ctk.CTkFrame(pai, fg_color=COR_CARTAO, corner_radius=14)
        rodape.grid(row=2, column=0, sticky="ew", padx=16, pady=(4, 16))
        rodape.columnconfigure(0, weight=1)

        self.btn_transcrever = ctk.CTkButton(
            rodape, text="Transcrever", height=48, corner_radius=12, font=(FONTE, 16, "bold"),
            fg_color=COR_ACENTO, hover_color=COR_ACENTO_HOVER, text_color="#FFFFFF",
            text_color_disabled="#C9C2F5", command=self._acao_principal,
        )
        self.btn_transcrever.grid(row=0, column=0, columnspan=2, sticky="ew", padx=14, pady=(14, 10))

        self.progress = ctk.CTkProgressBar(
            rodape, height=10, corner_radius=5, progress_color=COR_CIANO, fg_color=COR_BOTAO_SEC
        )
        self.progress.grid(row=1, column=0, columnspan=2, sticky="ew", padx=14, pady=(0, 8))
        self.progress.set(0)

        self.lbl_status = ctk.CTkLabel(
            rodape, textvariable=self.status, font=(FONTE, 12), text_color=COR_TEXTO_SEC,
            anchor="w", wraplength=270, justify="left",
        )
        self.lbl_status.grid(row=2, column=0, sticky="w", padx=(14, 4), pady=(0, 12))
        ctk.CTkLabel(
            rodape, textvariable=self.percentual, font=(FONTE, 12, "bold"), text_color=COR_CIANO, anchor="e"
        ).grid(row=2, column=1, sticky="e", padx=(4, 14), pady=(0, 12))

    def _montar_direita(self, pai) -> None:
        self.abas = ctk.CTkSegmentedButton(
            pai, values=["Transcrição", "Log"], command=self._trocar_aba, font=(FONTE, 13, "bold"),
            height=34, corner_radius=10, fg_color=COR_CARTAO, selected_color=COR_ACENTO,
            selected_hover_color=COR_ACENTO_HOVER, unselected_color=COR_CARTAO,
            unselected_hover_color=COR_BOTAO_SEC, text_color=COR_TEXTO,
        )
        self.abas.grid(row=0, column=0, sticky="w", pady=(0, 12))

        area = ctk.CTkFrame(pai, fg_color=COR_CARTAO, corner_radius=14)
        area.grid(row=1, column=0, sticky="nsew")
        area.columnconfigure(0, weight=1)
        area.rowconfigure(0, weight=1)

        # Aba Transcrição
        self.frame_transcricao = ctk.CTkFrame(area, fg_color="transparent")
        self.frame_transcricao.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        self.frame_transcricao.columnconfigure(0, weight=1)
        self.frame_transcricao.rowconfigure(1, weight=1)

        self.barra_abas = ctk.CTkScrollableFrame(
            self.frame_transcricao, orientation="horizontal", height=34, fg_color="transparent",
            corner_radius=0, scrollbar_button_color=COR_BOTAO_SEC, scrollbar_button_hover_color=COR_ACENTO,
        )
        self.barra_abas.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.barra_abas.grid_remove()

        self.txt_preview = ctk.CTkTextbox(
            self.frame_transcricao, wrap="word", undo=True, fg_color=COR_CAMPO, text_color=COR_TEXTO,
            font=(FONTE, 13), corner_radius=10, border_width=0, state="disabled",
            scrollbar_button_color=COR_BOTAO_SEC, scrollbar_button_hover_color=COR_ACENTO,
        )
        self.txt_preview.grid(row=1, column=0, sticky="nsew")
        self.txt_preview.bind("<<Modified>>", self._ao_modificar, add="+")
        self.txt_preview.bind("<Control-s>", self._salvar_atalho, add="+")
        self.lbl_vazio = ctk.CTkLabel(
            self.frame_transcricao, text="A transcrição aparecerá aqui", font=(FONTE, 14),
            text_color=COR_TEXTO_SEC, fg_color=COR_CAMPO,
        )
        self.lbl_vazio.place(in_=self.txt_preview, relx=0.5, rely=0.5, anchor="center")

        barra = ctk.CTkFrame(self.frame_transcricao, fg_color="transparent")
        barra.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        barra.columnconfigure(4, weight=1)
        self.btn_copiar = ctk.CTkButton(
            barra, text="Copiar texto", width=110, height=34, corner_radius=8, font=(FONTE, 12, "bold"),
            fg_color=COR_ACENTO, hover_color=COR_ACENTO_HOVER, text_color="#FFFFFF",
            command=self._copiar, state="disabled",
        )
        self.btn_copiar.grid(row=0, column=0, padx=(0, 8))
        self.btn_salvar = ctk.CTkButton(
            barra, text="Salvar alterações", width=130, height=34, corner_radius=8, font=(FONTE, 12),
            fg_color=COR_BOTAO_SEC, hover_color=COR_BOTAO_SEC_HOVER, text_color=COR_TEXTO,
            command=self._salvar, state="disabled",
        )
        self.btn_salvar.grid(row=0, column=1, padx=(0, 8))
        self.btn_abrir = ctk.CTkButton(
            barra, text="Abrir local do arquivo", width=150, height=34, corner_radius=8, font=(FONTE, 12),
            fg_color=COR_BOTAO_SEC, hover_color=COR_BOTAO_SEC_HOVER, text_color=COR_TEXTO,
            command=self._abrir_local, state="disabled",
        )
        self.btn_abrir.grid(row=0, column=2, padx=(0, 12))
        self.lbl_nao_salvo = ctk.CTkLabel(
            barra, text="", font=(FONTE, 12, "bold"), text_color=COR_ERRO
        )
        self.lbl_nao_salvo.grid(row=0, column=3, sticky="w")
        self.lbl_palavras = ctk.CTkLabel(
            barra, text="0 palavras", font=(FONTE, 12), text_color=COR_TEXTO_SEC, anchor="e"
        )
        self.lbl_palavras.grid(row=0, column=4, sticky="e")

        # Aba Log
        self.frame_log = ctk.CTkFrame(area, fg_color="transparent")
        self.frame_log.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        self.frame_log.columnconfigure(0, weight=1)
        self.frame_log.rowconfigure(0, weight=1)
        self.txt_log = ctk.CTkTextbox(
            self.frame_log, wrap="word", fg_color=COR_CAMPO, text_color=COR_TEXTO,
            font=(FONTE_LOG, 12), corner_radius=10, border_width=0, state="disabled",
            scrollbar_button_color=COR_BOTAO_SEC, scrollbar_button_hover_color=COR_ACENTO,
        )
        self.txt_log.grid(row=0, column=0, sticky="nsew")

        self.abas.set("Transcrição")
        self._trocar_aba("Transcrição")

    def _trocar_aba(self, aba: str) -> None:
        if aba == "Log":
            self.frame_log.tkraise()
        else:
            self.frame_transcricao.tkraise()
        self.abas.set(aba)

    # ------------------------------------------------------------- ajuda

    def _atualizar_rotulo_pausa(self, *_args) -> None:
        try:
            valor = float(self.pausa_paragrafo.get())
        except (tk.TclError, ValueError):
            valor = core.PAUSA_PARAGRAFO_PADRAO
        self.lbl_pausa.configure(text=f"{valor:.1f} s".replace(".", ","))

    def _atualizar_descricoes(self, *_args) -> None:
        resumo_modelo, _ = GLOSSARIO_MODELOS.get(self.modelo.get(), ("", ""))
        resumo_device, _ = GLOSSARIO_DEVICES.get(self.device.get(), ("", ""))
        self.descricao_modelo.set(resumo_modelo)
        self.descricao_device.set(resumo_device)

    def _aplicar_icone(self, janela) -> None:
        icone = caminho_recurso("assets/icone.ico")
        if icone.exists():
            try:
                janela.iconbitmap(str(icone))
            except tk.TclError:
                pass

    def _abrir_glossario(self, foco: str) -> None:
        janela = ctk.CTkToplevel(self.root, fg_color=COR_FUNDO)
        janela.title("Guia de ajuda - Modelos e dispositivos")
        janela.geometry("640x520")
        janela.transient(self.root)
        janela.after(250, lambda: self._aplicar_icone(janela))

        janela.columnconfigure(0, weight=1)
        janela.rowconfigure(0, weight=1)
        texto = ctk.CTkTextbox(
            janela, wrap="word", fg_color=COR_CARTAO, text_color=COR_TEXTO, font=(FONTE, 13),
            corner_radius=12, scrollbar_button_color=COR_BOTAO_SEC, scrollbar_button_hover_color=COR_ACENTO,
        )
        texto.grid(row=0, column=0, sticky="nsew", padx=14, pady=(14, 8))

        # CTkTextbox.tag_config não aceita a opção "font": só cor e espaçamento.
        texto.tag_config("titulo", foreground=COR_CIANO, spacing1=10, spacing3=2)
        texto.tag_config("item", foreground=COR_TEXTO, spacing1=6, spacing3=2)
        texto.tag_config("atual", foreground=COR_SUCESSO, spacing1=6, spacing3=2)
        texto.tag_config("corpo", foreground=COR_TEXTO_SEC, spacing3=6)

        texto.insert("end", "Modelos Whisper disponíveis\n", "titulo")
        for nome in sorted(GLOSSARIO_MODELOS):
            resumo, detalhe = GLOSSARIO_MODELOS[nome]
            marcador = " (selecionado)" if nome == self.modelo.get() else ""
            tag = "atual" if nome == self.modelo.get() else "item"
            texto.insert("end", f"\n{nome}{marcador} — {resumo}\n", tag)
            texto.insert("end", f"{detalhe}\n", "corpo")

        texto.insert("end", "\nDispositivos de processamento\n", "titulo")
        for nome in ("auto", "cuda", "cpu"):
            resumo, detalhe = GLOSSARIO_DEVICES[nome]
            marcador = " (selecionado)" if nome == self.device.get() else ""
            tag = "atual" if nome == self.device.get() else "item"
            texto.insert("end", f"\n{nome}{marcador} — {resumo}\n", tag)
            texto.insert("end", f"{detalhe}\n", "corpo")

        texto.configure(state="disabled")
        ctk.CTkButton(
            janela, text="Fechar", width=110, height=34, corner_radius=8, font=(FONTE, 12, "bold"),
            fg_color=COR_ACENTO, hover_color=COR_ACENTO_HOVER, command=janela.destroy,
        ).grid(row=1, column=0, pady=(0, 14))

        if foco == "device":
            texto.see("end")
        else:
            texto.see("1.0")
        janela.after(100, janela.focus_force)

    # ------------------------------------------------------------- eventos

    def _ativar_arrastar_e_soltar(self) -> None:
        # Registrado na janela: o tkdnd sobe dos widgets filhos até ela.
        try:
            self.root.TkdndVersion = TkinterDnD._require(self.root)
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind("<<Drop>>", self._ao_soltar)
        except (tk.TclError, RuntimeError) as e:
            self._log(f"[AVISO] Arrastar e soltar indisponível: {e}")

    def _ao_soltar(self, evento) -> None:
        self._adicionar_arquivos(self.root.tk.splitlist(evento.data))

    def _escolher_audios(self) -> None:
        todas = " ".join(f"*{e}" for e in sorted(core.FORMATOS_SUPORTADOS))
        audio = " ".join(f"*{e}" for e in sorted(core.FORMATOS_AUDIO))
        video = " ".join(f"*{e}" for e in sorted(core.FORMATOS_VIDEO))
        caminhos = filedialog.askopenfilenames(
            title="Selecionar arquivos de áudio ou vídeo",
            filetypes=[
                ("Áudio e vídeo", todas),
                ("Arquivos de áudio", audio),
                ("Arquivos de vídeo", video),
                ("Todos os arquivos", "*.*"),
            ],
        )
        if caminhos:
            self._adicionar_arquivos(caminhos)

    def _adicionar_arquivos(self, caminhos) -> None:
        candidatos: list[Path] = []
        for caminho in map(Path, caminhos):
            candidatos += sorted(caminho.iterdir()) if caminho.is_dir() else [caminho]
        ignorados = 0
        with self._trava_itens:
            existentes = {item.audio for item in self.itens}
            for caminho in candidatos:
                caminho = caminho.resolve()
                if not caminho.is_file() or caminho.suffix.lower() not in core.FORMATOS_SUPORTADOS:
                    ignorados += 1
                elif caminho not in existentes:
                    existentes.add(caminho)
                    self.itens.append(ItemFila(caminho))
        self._renderizar_fila()
        if ignorados and not self.em_execucao:
            self._definir_status(f"{ignorados} item(ns) ignorado(s): formato não suportado.", COR_ERRO)

    def _remover_item(self, item: ItemFila) -> None:
        if item.status == "transcrevendo":
            return
        with self._trava_itens:
            if item in self.itens:
                self.itens.remove(item)
        self._renderizar_fila()

    def _limpar_fila(self) -> None:
        with self._trava_itens:
            self.itens = [item for item in self.itens if item.status == "transcrevendo"]
        self._renderizar_fila()

    def _abrir_item(self, item: ItemFila) -> None:
        if item.status == "erro":
            self._trocar_aba("Log")
        elif item.status == "concluido":
            self._abrir_documento(item.saida)

    def _escolher_pasta(self) -> None:
        pasta = filedialog.askdirectory(title="Pasta de destino das transcrições")
        if pasta:
            self.pasta_destino.set(pasta)

    def _acao_principal(self) -> None:
        if self.em_execucao:
            self._cancelar.set()
            self.btn_transcrever.configure(state="disabled", text="Cancelando...")
            self._definir_status("Cancelando no próximo trecho...", COR_TEXTO_SEC)
        else:
            self._iniciar()

    def _iniciar(self) -> None:
        with self._trava_itens:
            for item in self.itens:
                if item.status in ("erro", "cancelado"):
                    item.status = "aguardando"
                    item.saida = None
                    self._atualizar_item(item)
            tem_pendentes = any(item.status == "aguardando" for item in self.itens)
        if not tem_pendentes:
            messagebox.showerror("Nenhum arquivo na fila", "Adicione um arquivo de áudio ou vídeo antes de transcrever.")
            return

        pasta = self.pasta_destino.get().strip()
        try:
            pausa_paragrafo = float(self.pausa_paragrafo.get())
        except (tk.TclError, ValueError):
            pausa_paragrafo = core.PAUSA_PARAGRAFO_PADRAO
            self.pausa_paragrafo.set(pausa_paragrafo)

        self._limpar_log()
        self._trocar_aba("Log")
        self.em_execucao = True
        self._cancelar.clear()
        self._encerrados_rodada = 0
        self._sucessos_rodada = 0
        self.btn_transcrever.configure(text="Cancelar", fg_color=COR_ERRO, hover_color=COR_ERRO)
        self._definir_status("Carregando modelo...", COR_TEXTO_SEC)
        self.percentual.set("")
        self._progresso_determinado = False
        self.progress.configure(mode="indeterminate", progress_color=COR_CIANO)
        self.progress.start()
        self._inicio_execucao = time.time()

        thread = threading.Thread(
            target=self._executar_fila,
            args=(
                Path(pasta).expanduser().resolve() if pasta else None, self.modelo.get(), self.device.get(),
                self.timestamps.get(), pausa_paragrafo, self.usar_vad.get(), self.gerar_srt.get(),
            ),
            daemon=True,
        )
        thread.start()

    def _definir_status(self, texto: str, cor: str) -> None:
        self.status.set(texto)
        self.lbl_status.configure(text_color=cor)

    # ------------------------------------------------------ thread de trabalho

    def _proximo_item(self, pasta: Path | None) -> ItemFila | None:
        """Reserva o próximo item pendente e define um destino que não colida com
        outro item da fila (ex.: aula.mp3 e aula.mp4 na mesma pasta)."""
        with self._trava_itens:
            item = next((i for i in self.itens if i.status == "aguardando"), None)
            if item is None:
                return None
            item.status = "transcrevendo"
            base = pasta if pasta is not None else item.audio.parent
            ocupados = {i.saida for i in self.itens if i.saida is not None}
            destino = base / f"{item.audio.stem}.txt"
            contador = 2
            while destino in ocupados:
                destino = base / f"{item.audio.stem} ({contador}).txt"
                contador += 1
            item.saida = destino
            return item

    def _executar_fila(
        self, pasta: Path | None, modelo: str, device: str, timestamps: bool,
        pausa_paragrafo: float, usar_vad: bool, gerar_srt: bool,
    ) -> None:
        def log(msg: str) -> None:
            self.fila.put(("log", str(msg)))

        def progresso(fracao: float) -> None:
            self.fila.put(("progress", fracao))

        try:
            core.verificar_ffmpeg()
            modelo_carregado = core.carregar_modelo(modelo, device, log=log)
            while not self._cancelar.is_set():
                item = self._proximo_item(pasta)
                if item is None:
                    break
                self.fila.put(("inicio", item))
                try:
                    core.verificar_arquivo(item.audio)
                    core.transcrever(
                        item.audio,
                        modelo,
                        device,
                        timestamps,
                        caminho_saida=item.saida,
                        log=log,
                        progresso=progresso,
                        pausa_paragrafo=pausa_paragrafo,
                        usar_vad=usar_vad,
                        gerar_srt=gerar_srt,
                        cancelar=self._cancelar,
                        modelo_carregado=modelo_carregado,
                    )
                    self.fila.put(("sucesso", item))
                except core.TranscricaoCancelada:
                    self.fila.put(("cancelado", item))
                except core.ErroTranscricao as e:
                    self.fila.put(("erro_item", (item, str(e))))
                except Exception as e:
                    self.fila.put(("erro_item", (item, f"Erro inesperado: {e}")))
        except core.ErroTranscricao as e:
            self.fila.put(("erro", str(e)))
        except Exception as e:
            self.fila.put(("erro", f"Erro inesperado: {e}"))
        finally:
            self.fila.put(("fim", None))

    # -------------------------------------------------------- fila -> UI

    def _processar_fila(self) -> None:
        try:
            while True:
                tipo, valor = self.fila.get_nowait()
                if tipo == "log":
                    self._log(valor)
                elif tipo == "inicio":
                    self._iniciar_item(valor)
                elif tipo == "progress":
                    self._atualizar_progresso(float(valor))
                elif tipo == "sucesso":
                    self._log(f"\nConcluído! Arquivo salvo em:\n{valor.saida}\n")
                    self._sucessos_rodada += 1
                    self._encerrar_item(valor, "concluido")
                    # Só a primeira da rodada ganha foco, para não trocar a aba de quem está lendo.
                    focar = self.doc_atual is None or (self._sucessos_rodada == 1 and not self.doc_atual.editado)
                    self._abrir_documento(valor.saida, focar=focar)
                elif tipo == "cancelado":
                    self._log(f"\nCancelado: {valor.audio.name}")
                    self._encerrar_item(valor, "cancelado")
                elif tipo == "erro_item":
                    item, mensagem = valor
                    item.erro = mensagem
                    self._log(f"\n[ERRO] {item.audio.name}: {mensagem}\n")
                    self._encerrar_item(item, "erro")
                elif tipo == "erro":
                    self._log(f"\n[ERRO] {valor}")
                    self._trocar_aba("Log")
                    messagebox.showerror("Erro na transcrição", valor)
                elif tipo == "fim":
                    self._concluir_rodada()
        except queue.Empty:
            pass
        self.root.after(100, self._processar_fila)

    def _iniciar_item(self, item: ItemFila) -> None:
        self._atualizar_item(item)
        if not self._cancelar.is_set():
            atual = self._encerrados_rodada + 1
            total = self._encerrados_rodada + self._restantes()
            self._definir_status(f"Transcrevendo {atual} de {total}: {item.audio.name}", COR_TEXTO_SEC)

    def _restantes(self) -> int:
        with self._trava_itens:
            return sum(1 for item in self.itens if item.status in ("aguardando", "transcrevendo"))

    def _atualizar_progresso(self, fracao: float) -> None:
        if not self._progresso_determinado:
            self._progresso_determinado = True
            self.progress.stop()
            self.progress.configure(mode="determinate")
        total = self._encerrados_rodada + self._restantes()
        geral = (self._encerrados_rodada + max(0.0, min(1.0, fracao))) / max(total, 1)
        self.progress.set(geral)
        self.percentual.set(f"{geral * 100:.0f}%")

    def _encerrar_item(self, item: ItemFila, status: str) -> None:
        item.status = status
        self._encerrados_rodada += 1
        self._atualizar_item(item)

    def _concluir_rodada(self) -> None:
        self.em_execucao = False
        self.btn_transcrever.configure(
            state="normal", text="Transcrever", fg_color=COR_ACENTO, hover_color=COR_ACENTO_HOVER
        )
        with self._trava_itens:
            falhas = [item for item in self.itens if item.status == "erro"]
        duracao = core.formatar_duracao(time.time() - self._inicio_execucao)

        if self._cancelar.is_set():
            self._finalizar_progresso(0)
            self._definir_status("Cancelado.", COR_TEXTO_SEC)
        elif falhas:
            self._finalizar_progresso(0)
            self._definir_status(f"{self._sucessos_rodada} concluído(s), {len(falhas)} com erro.", COR_ERRO)
            self._trocar_aba("Log")
            detalhes = "\n\n".join(f"{item.audio.name}:\n{item.erro}" for item in falhas[:3])
            messagebox.showerror("Erro na transcrição", detalhes)
        elif self._sucessos_rodada:
            self._finalizar_progresso(100)
            self.progress.configure(progress_color=COR_SUCESSO)
            self._definir_status(f"Concluído em {duracao}", COR_SUCESSO)
        else:
            self._finalizar_progresso(0)
            self._definir_status("Erro.", COR_ERRO)

    def _finalizar_progresso(self, percentual: int) -> None:
        self.progress.stop()
        self.progress.configure(mode="determinate")
        self._progresso_determinado = True
        self.progress.set(percentual / 100)
        self.percentual.set(f"{percentual}%" if percentual else "")

    def _log(self, msg: str) -> None:
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", msg + "\n")
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")

    def _limpar_log(self) -> None:
        self.txt_log.configure(state="normal")
        self.txt_log.delete("1.0", "end")
        self.txt_log.configure(state="disabled")

    # ------------------------------------------------------------ preview

    def _texto_atual(self) -> str:
        return self.txt_preview.get("1.0", "end-1c")

    def _sincronizar_doc(self) -> None:
        if self.doc_atual is not None:
            self.doc_atual.texto = self._texto_atual()
            self.doc_atual.editado = self.doc_atual.texto != self.doc_atual.texto_salvo

    def _definir_conteudo(self, texto: str, estado: str) -> None:
        self.txt_preview.configure(state="normal")
        self.txt_preview.delete("1.0", "end")
        self.txt_preview.insert("1.0", texto)
        self.txt_preview.edit_reset()
        self.txt_preview.edit_modified(False)
        self.txt_preview.configure(state=estado)

    def _limpar_preview(self) -> None:
        self.doc_atual = None
        self._definir_conteudo("", "disabled")
        for botao in (self.btn_copiar, self.btn_salvar, self.btn_abrir):
            botao.configure(state="disabled")
        self.btn_copiar.configure(text="Copiar texto")
        self.lbl_vazio.place(in_=self.txt_preview, relx=0.5, rely=0.5, anchor="center")
        self.lbl_nao_salvo.configure(text="")
        self.lbl_palavras.configure(text="0 palavras")

    def _mostrar_documento(self, doc: Documento) -> None:
        self._sincronizar_doc()
        self.doc_atual = doc
        self.lbl_vazio.place_forget()
        self._definir_conteudo(doc.texto, "normal")
        for botao in (self.btn_copiar, self.btn_salvar, self.btn_abrir):
            botao.configure(state="normal")
        self._atualizar_indicadores()
        self._renderizar_abas()

    def _abrir_documento(self, caminho: Path, focar: bool = True) -> None:
        try:
            texto = caminho.read_text(encoding="utf-8")
        except OSError as e:
            self._log(f"[AVISO] Não foi possível carregar a transcrição: {e}")
            return

        self._sincronizar_doc()
        doc = next((d for d in self.documentos if d.caminho == caminho), None)
        if doc is None:
            doc = Documento(caminho, texto, texto)
            self.documentos.append(doc)
        elif texto != doc.texto_salvo:
            # O arquivo mudou (nova transcrição): sem edições, a aba acompanha; com edições, elas ficam.
            if not doc.editado:
                doc.texto = texto
            doc.texto_salvo = texto
            doc.editado = doc.texto != texto
            if doc is self.doc_atual:
                self._mostrar_documento(doc)

        if focar:
            if doc is not self.doc_atual:
                self._mostrar_documento(doc)
            self._trocar_aba("Transcrição")
        else:
            self._renderizar_abas()

    def _fechar_documento(self, doc: Documento) -> None:
        self._sincronizar_doc()
        if doc.editado and not messagebox.askyesno(
            "Edições não salvas", f"{doc.caminho.name} tem edições não salvas. Deseja fechar a aba e descartá-las?"
        ):
            return
        indice = self.documentos.index(doc)
        self.documentos.remove(doc)
        if doc is self.doc_atual:
            self.doc_atual = None
            if self.documentos:
                self._mostrar_documento(self.documentos[min(indice, len(self.documentos) - 1)])
            else:
                self._limpar_preview()
        self._renderizar_abas()

    def _renderizar_abas(self) -> None:
        for widget in self.barra_abas.winfo_children():
            widget.destroy()
        if not self.documentos:
            self.barra_abas.grid_remove()
            return
        self.barra_abas.grid()

        for coluna, doc in enumerate(self.documentos):
            ativa = doc is self.doc_atual
            nome = doc.caminho.stem
            nome = nome if len(nome) <= 22 else nome[:19] + "..."
            cor = COR_ACENTO if ativa else COR_BOTAO_SEC
            hover = COR_ACENTO_HOVER if ativa else COR_BOTAO_SEC_HOVER
            aba = ctk.CTkFrame(self.barra_abas, fg_color=cor, corner_radius=8)
            aba.grid(row=0, column=coluna, padx=(0, 6))
            ctk.CTkButton(
                aba, text=("• " if doc.editado else "") + nome, height=28, width=60, corner_radius=8,
                font=(FONTE, 12, "bold" if ativa else "normal"), fg_color=cor, hover_color=hover,
                text_color="#FFFFFF" if ativa else COR_TEXTO,
                command=lambda d=doc: self._selecionar_aba(d),
            ).grid(row=0, column=0, padx=(2, 0), pady=2)
            ctk.CTkButton(
                aba, text="×", height=28, width=24, corner_radius=8, font=(FONTE, 13), fg_color=cor,
                hover_color=hover, text_color="#FFFFFF" if ativa else COR_TEXTO_SEC,
                command=lambda d=doc: self._fechar_documento(d),
            ).grid(row=0, column=1, padx=(0, 2), pady=2)

    def _selecionar_aba(self, doc: Documento) -> None:
        if doc is not self.doc_atual:
            self._mostrar_documento(doc)

    def _atualizar_indicadores(self) -> None:
        palavras = len(self._texto_atual().split())
        self.lbl_palavras.configure(text=f"{palavras} palavra" + ("" if palavras == 1 else "s"))
        editado = self.doc_atual is not None and self._texto_atual() != self.doc_atual.texto_salvo
        self.lbl_nao_salvo.configure(text="Edições não salvas" if editado else "")
        if self.doc_atual is not None and editado != self.doc_atual.editado:
            self.doc_atual.editado = editado
            self._renderizar_abas()

    def _ao_modificar(self, _evento=None) -> None:
        try:
            if self.doc_atual is not None:
                self._atualizar_indicadores()
        finally:
            self.txt_preview.edit_modified(False)

    def _copiar(self) -> None:
        texto = self.txt_preview.get("1.0", "end-1c")
        self.root.clipboard_clear()
        self.root.clipboard_append(texto)
        self.root.update()
        self.btn_copiar.configure(text="Copiado!")
        self.root.after(1500, lambda: self.btn_copiar.configure(text="Copiar texto"))

    def _salvar_atalho(self, _evento=None) -> str:
        self._salvar()
        return "break"

    def _salvar(self) -> None:
        doc = self.doc_atual
        if doc is None:
            return
        texto = self._texto_atual()
        try:
            doc.caminho.write_text(texto, encoding="utf-8")
        except OSError as e:
            messagebox.showerror("Erro ao salvar", f"Não foi possível salvar o arquivo:\n{e}")
            return
        doc.texto = doc.texto_salvo = texto
        self._atualizar_indicadores()

    def _abrir_local(self) -> None:
        if self.doc_atual is None or not self.doc_atual.caminho.exists():
            messagebox.showerror("Arquivo não encontrado", "O arquivo da transcrição não existe mais.")
            return
        # O explorer retorna código 1 mesmo com sucesso: nunca usar check=True.
        subprocess.Popen(["explorer", "/select,", str(self.doc_atual.caminho)])

    def _fechar(self) -> None:
        if self.em_execucao and not messagebox.askyesno(
            "Transcrição em andamento", "Há uma transcrição em andamento. Deseja fechar e interrompê-la?"
        ):
            return
        self._sincronizar_doc()
        editados = [doc.caminho.name for doc in self.documentos if doc.editado]
        if editados and not messagebox.askyesno(
            "Edições não salvas",
            "Há edições não salvas em:\n" + "\n".join(editados) + "\n\nDeseja fechar mesmo assim e descartá-las?",
        ):
            return
        self.root.destroy()


def main() -> None:
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("RicardoMendes.Transcritor")
        except Exception:
            pass

    # App sem console: o tqdm do download de modelos falha se stdout/stderr forem None.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")

    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    ctk.set_appearance_mode("dark")

    root = JanelaPrincipal(fg_color=COR_FUNDO)
    escala = root.winfo_fpixels("1i") / 96
    altura = min(760, int(root.winfo_screenheight() / escala) - 90)
    root.geometry(f"1120x{altura}")
    root.minsize(940, min(600, altura))

    app = TranscritorGUI(root)
    root.after(300, lambda: app._aplicar_icone(root))
    root.mainloop()


if __name__ == "__main__":
    main()
