"""Janelinha para transcrever e traduzir um video do YouTube.

    pythonw.exe -m app.gui

Usa Tkinter, que ja vem com o Python -- sem dependencia extra e sem servidor
rodando por tras: chama o pipeline direto.
"""

import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from . import config, pipeline, translators

TITULO = "legextrac"
FUNDO = "#1e1e2e"
FUNDO_CAMPO = "#2a2a3c"
TEXTO = "#e6e6f0"
TEXTO_FRACO = "#9a9ab0"
DESTAQUE = "#7aa2f7"
ERRO = "#f7768e"
SUCESSO = "#9ece6a"


def abrir_pasta(arquivo: Path) -> None:
    """Abre o Explorer com o arquivo ja selecionado."""
    try:
        # /select, precisa do caminho colado na virgula, sem espaco.
        subprocess.run(["explorer", f"/select,{arquivo}"], check=False)
    except OSError:
        subprocess.run(["explorer", str(arquivo.parent)], check=False)


class Janela:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.fila: queue.Queue[tuple[str, object]] = queue.Queue()
        self.trabalhando = False
        self.arquivo: Path | None = None

        root.title(TITULO)
        root.configure(bg=FUNDO)
        root.resizable(False, False)
        self._centralizar(460, 250)

        icone = Path(__file__).resolve().parent.parent / "assets" / "legextrac.ico"
        if icone.exists():
            try:
                root.iconbitmap(str(icone))
            except tk.TclError:
                pass

        moldura = tk.Frame(root, bg=FUNDO, padx=22, pady=18)
        moldura.pack(fill="both", expand=True)

        tk.Label(
            moldura,
            text="Link do vídeo no YouTube",
            bg=FUNDO,
            fg=TEXTO_FRACO,
            font=("Segoe UI", 9),
            anchor="w",
        ).pack(fill="x")

        self.entrada = tk.Entry(
            moldura,
            bg=FUNDO_CAMPO,
            fg=TEXTO,
            insertbackground=TEXTO,
            relief="flat",
            font=("Segoe UI", 11),
            highlightthickness=1,
            highlightbackground="#3b3b52",
            highlightcolor=DESTAQUE,
        )
        self.entrada.pack(fill="x", ipady=8, pady=(4, 14))
        self.entrada.focus_set()

        self.botao = tk.Button(
            moldura,
            text="TRANSCREVER",
            command=self.iniciar,
            bg=DESTAQUE,
            fg="#1a1a26",
            activebackground="#94b8ff",
            activeforeground="#1a1a26",
            relief="flat",
            font=("Segoe UI", 10, "bold"),
            cursor="hand2",
            borderwidth=0,
        )
        self.botao.pack(fill="x", ipady=9)

        self.barra = ttk.Progressbar(moldura, mode="indeterminate")

        self.status = tk.Label(
            moldura,
            text="",
            bg=FUNDO,
            fg=TEXTO_FRACO,
            font=("Segoe UI", 9),
            wraplength=400,
            justify="left",
            anchor="w",
        )
        self.status.pack(fill="x", pady=(12, 0))

        root.bind("<Return>", lambda _: self.iniciar())
        root.bind("<Escape>", lambda _: root.destroy())

        self._colar_do_clipboard()
        self._checar_configuracao()
        self.root.after(100, self._consumir_fila)

    # -- montagem ----------------------------------------------------------

    def _centralizar(self, largura: int, altura: int) -> None:
        x = (self.root.winfo_screenwidth() - largura) // 2
        y = (self.root.winfo_screenheight() - altura) // 3
        self.root.geometry(f"{largura}x{altura}+{x}+{y}")

    def _colar_do_clipboard(self) -> None:
        """Se voce copiou o link antes de abrir o app, ja vem preenchido."""
        try:
            texto = self.root.clipboard_get().strip()
        except tk.TclError:
            return
        if "youtube.com/" in texto or "youtu.be/" in texto:
            self.entrada.insert(0, texto)
            self.entrada.select_range(0, "end")

    def _checar_configuracao(self) -> None:
        if not translators.is_configured():
            self._status(
                f"Sem chave do {config.TRANSLATOR}: o texto sai no idioma original.",
                TEXTO_FRACO,
            )

    # -- estado ------------------------------------------------------------

    def _status(self, texto: str, cor: str = TEXTO_FRACO) -> None:
        self.status.config(text=texto, fg=cor)

    def iniciar(self) -> None:
        if self.trabalhando:
            return

        url = self.entrada.get().strip()
        if not url:
            self._status("Cole o link do vídeo primeiro.", ERRO)
            return

        # Segundo clique depois de pronto: abre a pasta em vez de reprocessar.
        if self.arquivo and self.botao.cget("text") == "ABRIR PASTA":
            abrir_pasta(self.arquivo)
            return

        self.trabalhando = True
        self.arquivo = None
        self.botao.config(text="TRANSCREVENDO...", state="disabled", bg="#3b3b52", fg=TEXTO_FRACO)
        self.barra.pack(fill="x", pady=(12, 0))
        self.barra.start(12)
        self._status("Começando...", TEXTO_FRACO)

        threading.Thread(target=self._trabalhar, args=(url,), daemon=True).start()

    def _trabalhar(self, url: str) -> None:
        """Roda fora da thread da interface, senao a janela congela."""
        try:
            resultado = pipeline.processar(
                url=url,
                progresso=lambda m: self.fila.put(("status", m)),
            )
            self.fila.put(("pronto", resultado))
        except pipeline.PipelineError as exc:
            self.fila.put(("erro", str(exc)))
        except Exception as exc:  # rede caiu, disco cheio, o que for
            self.fila.put(("erro", f"Erro inesperado: {exc}"))

    def _consumir_fila(self) -> None:
        """Tkinter so pode ser tocado pela thread principal; a fila faz a ponte."""
        try:
            while True:
                tipo, carga = self.fila.get_nowait()
                if tipo == "status":
                    self._status(str(carga))
                elif tipo == "pronto":
                    self._terminar(carga)
                elif tipo == "erro":
                    self._falhar(str(carga))
        except queue.Empty:
            pass
        self.root.after(100, self._consumir_fila)

    def _parar_barra(self) -> None:
        self.barra.stop()
        self.barra.pack_forget()
        self.trabalhando = False

    def _terminar(self, resultado) -> None:
        self._parar_barra()
        self.arquivo = resultado.saved_to

        idioma = resultado.source_language
        if resultado.translated:
            resumo = f"Pronto: {len(resultado.snippets)} frases traduzidas de {idioma}."
        else:
            resumo = resultado.note or f"Pronto: {len(resultado.snippets)} frases em {idioma}."

        self._status(f"{resumo}\n{resultado.saved_to}", SUCESSO)
        self.botao.config(text="ABRIR PASTA", state="normal", bg=SUCESSO, fg="#1a1a26")

        if self.arquivo:
            abrir_pasta(self.arquivo)

    def _falhar(self, mensagem: str) -> None:
        self._parar_barra()
        self._status(mensagem, ERRO)
        self.botao.config(text="TRANSCREVER", state="normal", bg=DESTAQUE, fg="#1a1a26")


def main() -> int:
    root = tk.Tk()
    try:
        # Sem isso a janela fica borrada em tela com escala acima de 100%.
        from ctypes import windll

        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    Janela(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
