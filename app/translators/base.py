"""Contrato comum entre os provedores de traducao."""


class TranslationError(Exception):
    """Falha esperada ao traduzir (mensagem exibivel ao usuario)."""
