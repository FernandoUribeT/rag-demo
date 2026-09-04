"""Saldo de créditos para indexar documentos.

Indexar cuesta cómputo: trocear y vectorizar un documento largo son cientos de
llamadas al modelo. Cobrarlo por créditos mantiene el costo ligado al uso.

Este módulo no sabe nada de Stripe ni de HTTP. Recibe "se pagó esto" y "se
consumió aquello", y su único trabajo es que las cuentas cuadren. Por eso se
puede probar entero sin red.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class SaldoInsuficiente(RuntimeError):
    """No hay créditos para cubrir la operación."""


@dataclass(frozen=True)
class Otorgamiento:
    """Créditos concedidos por un pago concreto."""

    cliente: str
    creditos: int
    evento_id: str


class LibroDeCreditos(Protocol):
    def saldo(self, cliente: str) -> int: ...

    def otorgar(self, otorgamiento: Otorgamiento) -> bool:
        """Devuelve True si se aplicó; False si el evento ya se había aplicado."""
        ...

    def consumir(self, cliente: str, creditos: int) -> int: ...


@dataclass
class LibroEnMemoria:
    """Implementación de referencia; también es la que usan las pruebas."""

    _saldos: dict[str, int] = field(default_factory=dict)
    _eventos_aplicados: set[str] = field(default_factory=set)

    def saldo(self, cliente: str) -> int:
        return self._saldos.get(cliente, 0)

    def otorgar(self, otorgamiento: Otorgamiento) -> bool:
        """Aplica un pago una sola vez, sin importar cuántas veces llegue.

        Stripe reintenta un webhook hasta que responde 2xx, y puede entregar el
        mismo evento más de una vez por diseño. Sin esta guarda, un reintento
        regala créditos: el usuario paga una vez y recibe dos veces.

        La clave de idempotencia es el id del evento de Stripe, que es estable
        entre reintentos.
        """
        if otorgamiento.creditos <= 0:
            raise ValueError("los créditos otorgados deben ser positivos")
        if not otorgamiento.evento_id:
            raise ValueError("el otorgamiento necesita un id de evento")

        if otorgamiento.evento_id in self._eventos_aplicados:
            return False

        self._eventos_aplicados.add(otorgamiento.evento_id)
        self._saldos[otorgamiento.cliente] = (
            self.saldo(otorgamiento.cliente) + otorgamiento.creditos
        )
        return True

    def consumir(self, cliente: str, creditos: int) -> int:
        """Descuenta créditos y devuelve el saldo restante."""
        if creditos <= 0:
            raise ValueError("los créditos consumidos deben ser positivos")

        actual = self.saldo(cliente)
        if actual < creditos:
            raise SaldoInsuficiente(
                f"el cliente tiene {actual} créditos y la operación cuesta {creditos}"
            )

        self._saldos[cliente] = actual - creditos
        return self._saldos[cliente]
