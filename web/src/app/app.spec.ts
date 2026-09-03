/**
 * Pruebas del componente.
 *
 * Se sustituye RagService por un doble: el componente se prueba por su
 * comportamiento visible -que deshabilite el boton, que muestre el error, que
 * pinte las fuentes- sin depender de HTTP ni del backend.
 */

import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Observable, of, throwError } from 'rxjs';

import { App } from './app';
import { RagService, Respuesta } from './rag.service';

const RESPUESTA: Respuesta = {
  texto: 'Se requiere para traslados por vía pública. [carta-porte#0]',
  abstuvo: false,
  fuentes: [
    {
      id: 'carta-porte#0',
      documento: 'carta-porte',
      similitud: 0.82,
      extracto: 'El complemento Carta Porte ampara el traslado...',
    },
  ],
};

const ABSTENCION: Respuesta = {
  texto: 'No encontré información sobre eso en los documentos disponibles.',
  abstuvo: true,
  fuentes: [],
};

class RagFalso {
  respuesta: Observable<Respuesta> = of(RESPUESTA);
  preguntasRecibidas: string[] = [];

  preguntar(pregunta: string): Observable<Respuesta> {
    this.preguntasRecibidas.push(pregunta);
    return this.respuesta;
  }
}

describe('App', () => {
  let fixture: ComponentFixture<App>;
  let componente: App;
  let rag: RagFalso;

  beforeEach(async () => {
    rag = new RagFalso();
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [{ provide: RagService, useValue: rag }],
    }).compileComponents();

    fixture = TestBed.createComponent(App);
    componente = fixture.componentInstance;
    fixture.detectChanges();
  });

  function texto(): string {
    return (fixture.nativeElement as HTMLElement).textContent ?? '';
  }

  it('se crea', () => {
    expect(componente).toBeTruthy();
  });

  it('no permite consultar con la pregunta vacía', () => {
    expect(componente.puedeConsultar()).toBe(false);
  });

  it('no permite consultar con solo espacios', () => {
    componente.pregunta.set('   ');
    expect(componente.puedeConsultar()).toBe(false);
  });

  it('permite consultar con una pregunta escrita', () => {
    componente.pregunta.set('carta porte');
    expect(componente.puedeConsultar()).toBe(true);
  });

  it('recorta los espacios antes de mandar la pregunta', () => {
    componente.pregunta.set('  carta porte  ');
    componente.consultar();
    expect(rag.preguntasRecibidas).toEqual(['carta porte']);
  });

  it('no manda nada si la pregunta está vacía', () => {
    componente.consultar();
    expect(rag.preguntasRecibidas).toEqual([]);
  });

  it('muestra la respuesta y sus fuentes', () => {
    componente.pregunta.set('carta porte');
    componente.consultar();
    fixture.detectChanges();

    expect(texto()).toContain('traslados por vía pública');
    expect(texto()).toContain('carta-porte#0');
    expect(texto()).toContain('0.82');
  });

  it('avisa explícitamente cuando el sistema se abstuvo', () => {
    rag.respuesta = of(ABSTENCION);
    componente.pregunta.set('receta de pizza');
    componente.consultar();
    fixture.detectChanges();

    expect(texto()).toContain('No encontré información');
    expect(texto()).toContain('por encima del umbral');
  });

  it('muestra el error cuando el servicio falla', () => {
    rag.respuesta = throwError(() => new Error('No se pudo contactar al servicio.'));
    componente.pregunta.set('algo');
    componente.consultar();
    fixture.detectChanges();

    expect(texto()).toContain('No se pudo contactar');
  });

  it('limpia la respuesta anterior antes de consultar de nuevo', () => {
    componente.pregunta.set('carta porte');
    componente.consultar();

    rag.respuesta = throwError(() => new Error('falló'));
    componente.consultar();
    fixture.detectChanges();

    // La respuesta vieja no debe quedarse junto al mensaje de error.
    expect(texto()).not.toContain('traslados por vía pública');
  });

  it('deja de marcar consultando cuando termina', () => {
    componente.pregunta.set('carta porte');
    componente.consultar();
    expect(componente.consultando()).toBe(false);
  });
});
