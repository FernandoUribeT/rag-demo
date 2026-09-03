"""Cola sobre RabbitMQ.

Implementa el protocolo `Cola` de ingesta.py contra un broker real. Toda la
lógica de ingesta se prueba contra `ColaEnMemoria`; esto es el adaptador.

La cola se declara durable y los mensajes persistentes: sin eso, reiniciar el
broker borra los trabajos pendientes, y un documento subido quedaría aceptado
pero nunca indexado — el peor de los fallos, porque es silencioso.
"""

from __future__ import annotations

COLA = "indexado"


class ColaRabbitMQ:
    """La librería se importa en el constructor para que el módulo se pueda
    importar donde `pika` no está instalado, que es el caso de CI."""

    def __init__(self, url: str = "amqp://guest:guest@127.0.0.1:5672/%2F") -> None:
        import pika  # noqa: PLC0415

        self._pika = pika
        self._conexion = pika.BlockingConnection(pika.URLParameters(url))
        self._canal = self._conexion.channel()
        self._canal.queue_declare(queue=COLA, durable=True)

    def publicar(self, mensaje: bytes) -> None:
        self._canal.basic_publish(
            exchange="",
            routing_key=COLA,
            body=mensaje,
            properties=self._pika.BasicProperties(delivery_mode=2),  # persistente
        )

    def consumir(self) -> bytes | None:
        """Toma un mensaje y lo confirma.

        Se confirma después de leerlo y antes de procesarlo, lo que asume que
        el procesamiento es idempotente — y lo es: la clave del documento
        incluye el hash de su contenido. Un diseño que no lo fuera tendría que
        confirmar después de indexar.
        """
        metodo, _, cuerpo = self._canal.basic_get(queue=COLA, auto_ack=False)
        if metodo is None:
            return None
        self._canal.basic_ack(metodo.delivery_tag)
        return cuerpo

    def cerrar(self) -> None:
        if self._conexion.is_open:
            self._conexion.close()
