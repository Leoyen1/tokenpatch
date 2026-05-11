from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Todo:
    id: int
    title: str
    completed: bool = False


def list_todos(todos: list[Todo]) -> list[Todo]:
    return list(todos)

