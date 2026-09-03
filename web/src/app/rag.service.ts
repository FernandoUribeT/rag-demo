/**
 * Cliente HTTP del servicio de RAG.
 *
 * Toda la comunicación con el backend vive aquí. El componente no conoce
 * rutas ni formas de la respuesta: pide y recibe tipos. Cuando cambie la API,
 * este archivo es el único que se toca.
 */

import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, catchError, throwError } from 'rxjs';

export interface Fuente {
  id: string;
  documento: string;
  similitud: number;
  extracto: string;
}

export interface Respuesta {
  texto: string;
  /** True cuando el sistema decidió no responder por falta de contexto. */
  abstuvo: boolean;
  fuentes: Fuente[];
}

export interface Salud {
  estado: string;
  fragmentos: number;
}

/** La URL vive en un solo lugar para que cambiarla no implique buscar por todo el código. */
export const API = 'http://127.0.0.1:8000';

@Injectable({ providedIn: 'root' })
export class RagService {
  private readonly http = inject(HttpClient);

  salud(): Observable<Salud> {
    return this.http.get<Salud>(`${API}/api/salud`).pipe(catchError(traducirError));
  }

  preguntar(pregunta: string, k = 4): Observable<Respuesta> {
    return this.http
      .post<Respuesta>(`${API}/api/preguntar`, { pregunta, k })
      .pipe(catchError(traducirError));
  }

  subirDocumento(nombre: string, contenido: string): Observable<{ clave: string }> {
    return this.http
      .post<{ clave: string }>(`${API}/api/documentos`, { nombre, contenido })
      .pipe(catchError(traducirError));
  }
}

/**
 * Convierte el error de HTTP en un mensaje que se le puede mostrar a alguien.
 *
 * El detalle técnico se queda en la consola. Enseñar un stack trace o el
 * cuerpo crudo de la respuesta en pantalla no ayuda a quien está usando la
 * aplicación, y puede filtrar información del servidor.
 */
function traducirError(error: HttpErrorResponse): Observable<never> {
  console.error('fallo la petición al servicio', error);

  if (error.status === 0) {
    return throwError(() => new Error('No se pudo contactar al servicio.'));
  }
  if (error.status === 422) {
    return throwError(() => new Error('La pregunta no es válida.'));
  }
  return throwError(() => new Error('El servicio respondió con un error.'));
}
