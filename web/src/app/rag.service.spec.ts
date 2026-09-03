/**
 * Pruebas del cliente HTTP.
 *
 * HttpTestingController intercepta las peticiones: no sale ninguna a la red.
 * Se verifica qué se mandó y cómo se interpreta lo que vuelve, incluidos los
 * errores, que es donde suele estar el defecto.
 */

import { HttpErrorResponse, provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { firstValueFrom } from 'rxjs';

import { API, RagService, Respuesta } from './rag.service';

describe('RagService', () => {
  let service: RagService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(RagService);
    http = TestBed.inject(HttpTestingController);
  });

  // Falla la prueba si quedó alguna petición sin atender: así se detecta una
  // llamada de más que nadie esperaba.
  afterEach(() => http.verify());

  it('manda la pregunta y la k al endpoint correcto', () => {
    service.preguntar('¿cuándo se requiere Carta Porte?', 3).subscribe();

    const peticion = http.expectOne(`${API}/api/preguntar`);
    expect(peticion.request.method).toBe('POST');
    expect(peticion.request.body).toEqual({
      pregunta: '¿cuándo se requiere Carta Porte?',
      k: 3,
    });
    peticion.flush({ texto: '', abstuvo: true, fuentes: [] });
  });

  it('usa k = 4 cuando no se especifica', () => {
    service.preguntar('algo').subscribe();

    const peticion = http.expectOne(`${API}/api/preguntar`);
    expect(peticion.request.body.k).toBe(4);
    peticion.flush({ texto: '', abstuvo: true, fuentes: [] });
  });

  it('entrega la respuesta con sus fuentes', async () => {
    const esperada: Respuesta = {
      texto: 'Se requiere para traslados por vía pública. [carta-porte#0]',
      abstuvo: false,
      fuentes: [
        {
          id: 'carta-porte#0',
          documento: 'carta-porte',
          similitud: 0.82,
          extracto: 'El complemento Carta Porte...',
        },
      ],
    };

    const recibida = firstValueFrom(service.preguntar('carta porte'));
    http.expectOne(`${API}/api/preguntar`).flush(esperada);

    expect(await recibida).toEqual(esperada);
  });

  it('conserva la abstención cuando el servicio no encontró contexto', async () => {
    const recibida = firstValueFrom(service.preguntar('receta de pizza'));
    http.expectOne(`${API}/api/preguntar`).flush({
      texto: 'No encontré información sobre eso en los documentos disponibles.',
      abstuvo: true,
      fuentes: [],
    });

    const respuesta = await recibida;
    expect(respuesta.abstuvo).toBe(true);
    expect(respuesta.fuentes).toEqual([]);
  });

  it('avisa cuando el servicio no responde', async () => {
    const recibida = firstValueFrom(service.preguntar('algo'));
    http
      .expectOne(`${API}/api/preguntar`)
      .error(new ProgressEvent('error'), { status: 0, statusText: '' });

    await expect(recibida).rejects.toThrow('No se pudo contactar');
  });

  it('traduce un 422 a un mensaje sobre la pregunta', async () => {
    const recibida = firstValueFrom(service.preguntar('  '));
    http
      .expectOne(`${API}/api/preguntar`)
      .flush({ detail: 'vacía' }, { status: 422, statusText: 'Unprocessable' });

    await expect(recibida).rejects.toThrow('no es válida');
  });

  it('no filtra el detalle técnico del servidor al mensaje visible', async () => {
    const recibida = firstValueFrom(service.preguntar('algo'));
    http
      .expectOne(`${API}/api/preguntar`)
      .flush({ detail: 'Traceback: línea 42 de /srv/app/interno.py' },
             { status: 500, statusText: 'Server Error' });

    await expect(recibida).rejects.not.toThrow('Traceback');
  });

  it('consulta la salud del servicio', async () => {
    const recibida = firstValueFrom(service.salud());

    const peticion = http.expectOne(`${API}/api/salud`);
    expect(peticion.request.method).toBe('GET');
    peticion.flush({ estado: 'ok', fragmentos: 12 });

    expect((await recibida).fragmentos).toBe(12);
  });

  it('sube un documento con su nombre y contenido', () => {
    service.subirDocumento('nuevo', 'Un texto.').subscribe();

    const peticion = http.expectOne(`${API}/api/documentos`);
    expect(peticion.request.body).toEqual({ nombre: 'nuevo', contenido: 'Un texto.' });
    peticion.flush({ clave: 'nuevo/abc123', estado: 'encolado' });
  });
});
