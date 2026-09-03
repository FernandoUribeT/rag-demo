/**
 * Interfaz de consulta.
 *
 * El estado se maneja con signals: `consultando` y `error` existen porque una
 * llamada de red puede estar en curso o haber fallado, y la interfaz tiene que
 * decirlo. Una pantalla que solo contempla el caso exitoso deja al usuario sin
 * saber si el sistema está pensando o se rompió.
 */

import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { RagService, Respuesta } from './rag.service';

@Component({
  imports: [FormsModule],
  selector: 'app-root',
  styleUrl: './app.css',
  templateUrl: './app.html',
})
export class App {
  private readonly rag = inject(RagService);

  readonly pregunta = signal('');
  readonly respuesta = signal<Respuesta | null>(null);
  readonly consultando = signal(false);
  readonly error = signal<string | null>(null);

  /** Evita mandar una consulta vacía o disparar dos a la vez con doble clic. */
  readonly puedeConsultar = computed(
    () => this.pregunta().trim().length > 0 && !this.consultando(),
  );

  consultar(): void {
    if (!this.puedeConsultar()) {
      return;
    }

    this.consultando.set(true);
    this.error.set(null);
    // Se limpia la respuesta anterior: dejarla en pantalla junto a la nueva
    // haría que el usuario no sepa cuál corresponde a qué pregunta.
    this.respuesta.set(null);

    this.rag.preguntar(this.pregunta().trim()).subscribe({
      next: (respuesta) => {
        this.respuesta.set(respuesta);
        this.consultando.set(false);
      },
      error: (fallo: Error) => {
        this.error.set(fallo.message);
        this.consultando.set(false);
      },
    });
  }
}
