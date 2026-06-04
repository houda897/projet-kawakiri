from __future__ import annotations

from typing import Any, Protocol


class DbClient(Protocol):
    """
    Minimal database interface used by engines.

    Keeping this protocol small makes the engines easy to test with mocks.
    """

    def query(self, sql: str, parameters: dict | None = None) -> Any: ...

    def command(self, sql: str, parameters: dict | None = None) -> Any: ...

    def insert(
        self,
        table: str,
        data: list,
        column_names: list[str] | None = None,
    ) -> Any: ...
