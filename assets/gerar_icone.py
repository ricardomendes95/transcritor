"""Gera assets/icone.ico e assets/icone.png a partir de um desenho a 1024px."""
from pathlib import Path

from PIL import Image, ImageDraw

PASTA = Path(__file__).resolve().parent
TAM = 1024
ROXO = (124, 92, 252)
CIANO = (34, 211, 238)


def gradiente(tam):
    # Gradiente diagonal: gera uma faixa 1D e a estica na diagonal.
    img = Image.new("RGB", (tam, tam))
    px = img.load()
    for y in range(tam):
        for x in range(tam):
            t = (x + y) / (2 * (tam - 1))
            px[x, y] = tuple(round(a + (b - a) * t) for a, b in zip(ROXO, CIANO))
    return img


def desenhar():
    margem, raio = 24, 220
    mascara = Image.new("L", (TAM, TAM), 0)
    ImageDraw.Draw(mascara).rounded_rectangle(
        (margem, margem, TAM - margem - 1, TAM - margem - 1), radius=raio, fill=255
    )
    base = gradiente(TAM).convert("RGBA")
    base.putalpha(mascara)

    d = ImageDraw.Draw(base)
    branco = (255, 255, 255, 255)

    # Sete barras verticais (ondas sonoras), centralizadas em y=400.
    alturas = [140, 260, 380, 480, 380, 260, 140]
    largura, espaco = 72, 52
    total = 7 * largura + 6 * espaco
    x = (TAM - total) // 2
    centro_y = 400
    for h in alturas:
        d.rounded_rectangle(
            (x, centro_y - h // 2, x + largura, centro_y + h // 2),
            radius=largura // 2, fill=branco,
        )
        x += largura + espaco

    # Duas linhas de "texto" embaixo.
    for y, comprimento in ((700, 560), (820, 360)):
        x0 = (TAM - 560) // 2
        d.rounded_rectangle((x0, y, x0 + comprimento, y + 60), radius=30, fill=branco)
    return base


def main():
    img = desenhar()
    img.resize((256, 256), Image.LANCZOS).save(PASTA / "icone.png")
    img.save(
        PASTA / "icone.ico",
        format="ICO",
        sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)],
    )


if __name__ == "__main__":
    main()
