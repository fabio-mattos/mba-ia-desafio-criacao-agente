"""Serializa um Event do ADK para JSON, com o conteudo completo do evento."""

from __future__ import annotations

from google.adk.events.event import Event


def evento_para_json(evento: Event) -> dict:
    return evento.model_dump(mode="json", exclude_none=True)
