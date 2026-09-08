<!-- synced-from: 001f660e6b3b12e52d59a05745ec46d94188f664 -->
# framesig

**Español** · [English](README.md)

**Encuentra *cuándo* pasa algo en pantalla — en cualquier vídeo, de cualquier juego o fuente — por su firma de píxeles.**

![Python](https://img.shields.io/badge/python-3.9%2B-blue) ![License: MIT](https://img.shields.io/badge/license-MIT-green) ![Tests](https://img.shields.io/badge/tests-88%20passing-brightgreen)

framesig no sabe qué aspecto tiene una «baja» ni una «pantalla de muerte» — y no le hace falta. Describes un evento como **una región del fotograma + una firma de color o brillo** en unas pocas líneas de YAML, y framesig recorre el vídeo y te devuelve las **marcas de tiempo** donde aparece esa firma. Un destello rojo en el HUD, una fila coloreada del registro de bajas, un fundido a negro, un corte seco — la misma configuración diminuta, sin modelo, sin entrenamiento y sin código específico por juego.

> **Nota sobre el idioma.** Este README está en las dos lenguas. El resto de la documentación y los comentarios del código están en inglés.

---

## Por qué sirve

- **Agnóstico de la fuente.** Sólo razona sobre píxeles dentro de un rectángulo, nunca sobre el juego. La misma herramienta vale para League, CS, una presentación o unas cámaras de seguridad.
- **Declarativo.** Los eventos viven en YAML, no en código. Cambias una región o un umbral y vuelves a lanzarlo — sin recompilar y sin volver a escanear (ver la caché abajo).
- **Barato de reajustar.** Escanear el vídeo es la parte cara; framesig cachea las puntuaciones crudas por fotograma, así que cambiar un umbral es *instantáneo*.
- **Demostración autocontenida.** `framesig demo` genera su propio clip de prueba con ffmpeg, lo escanea y dibuja el resultado — sin vídeos ni modelos que descargar.

## Qué trae

- Cuatro detectores incorporados: `channel_dominance`, `color_fraction`, `brightness`, `scene_change`.
- Regiones en fracciones independientes de la resolución (o en píxeles absolutos).
- Submuestreo de fotogramas a un ritmo configurable, por velocidad.
- Eventos en JSON, con instante de pico, puntuación de pico y media, duración y número de muestras por evento.
- **Caché de puntuaciones** en disco, con una clave tal que cambiar un umbral reutiliza el escaneo, y cambiar un detector lo invalida.
- Un dibujante de líneas temporales hecho con OpenCV puro (sin depender de matplotlib).
- API de Python limpia y un CLI `framesig`.

## Instalación

framesig sólo necesita `numpy`, `opencv-python-headless` y `PyYAML`. (`ffmpeg` en el `PATH` es opcional: se usa únicamente para *generar* el clip de muestra en `gen-sample` / `demo`; escanear vídeos reales no lo necesita.)

```bash
pip install framesig
```

## Inicio rápido

Genera un clip sintético, escanéalo y dibuja las detecciones en un solo comando:

```console
$ framesig demo
[1/3] rendering synthetic clip with ffmpeg...
[2/3] scanning for pixel signatures...
sample.mp4  640x360  15.0s  150 samples @ 10.0 fps  (scan)
7 event(s) across 4 signature(s)
  death_screen: 2
    [  2.00s ->   2.40s]  peak 1.00 @   2.00s  (5 samples)
  ...
```

Cada evento cae exactamente donde se pintó en el clip — dos destellos de muerte, tres filas de registro de bajas, un destello blanco y un corte de escena.

## Uso

### CLI

```console
$ framesig scan sample.mp4 -c examples/flash.yaml -o events.json
sample.mp4  640x360  15.0s  150 samples @ 10.0 fps  (scan)
```

Si lo vuelves a lanzar, el escaneo sale de la caché — fíjate en la etiqueta `(cache)`.

Opciones útiles: `--sample-fps N` (cambia el ritmo de muestreo), `--no-cache`, `--chart timeline.png`, `-q`.

### Configuración

Una firma es un **detector** aplicado a una **región**, más las reglas para convertir la línea temporal de puntuaciones en eventos discretos:

```yaml
sample_fps: 10                       # analiza ~10 fotogramas por segundo de vídeo
cache_dir: .framesig_cache           # opcional

regions:                             # los límites son fracciones del fotograma por defecto
  hud_top:    { x: 0.00, y: 0.00, w: 1.00, h: 0.55 }
  kill_feed:  { x: 0.08, y: 0.74, w: 0.84, h: 0.18 }
  minimap:    { x: 1500, y: 800, w: 400, h: 250, unit: pixels }   # píxeles absolutos

signatures:
  - name: death_screen
    region: hud_top
    detector: channel_dominance      # «rojo relativo», robusto a la compresión
    params: { channel: red, gain: 2.0 }
    threshold: 0.30                  # puntuación >= 0.30 cuenta como activa
    min_duration: 0.15               # descarta parpadeos de menos de 0,15 s
    merge_gap: 0.25                  # une intermitencias separadas por menos de 0,25 s
```

Ver [`examples/flash.yaml`](examples/flash.yaml) para la configuración completa de cuatro firmas.

### API de Python

```python
from framesig import load_config, scan_video, detect_all

config = load_config("examples/flash.yaml")
result = scan_video("sample.mp4", config)      # las puntuaciones se cachean en disco
events = detect_all(config, result)            # aplicar umbrales sale gratis

for nombre, evs in events.items():
    for e in evs:
        print(f"{nombre}: {e.peak_t:.2f}s (puntuación {e.peak_score:.2f})")
```

## Detectores

| detector | mide | bueno para | parámetros clave |
|---|---|---|---|
| `channel_dominance` | cuánto gana un canal BGR a los otros dos | destellos rojos de muerte o baja; aguanta la compresión e ignora el brillo | `channel`, `gain` |
| `color_fraction` | fracción de píxeles dentro de uno o varios rangos HSV | elementos de HUD con color (registro de bajas, banners de objetivo) | `hsv_low/high`, `hsv_low2/high2` |
| `brightness` | luminancia media | destellos blancos (`invert: false`), fundidos a negro (`invert: true`) | `invert` |
| `scene_change` | diferencia absoluta media con el fotograma muestreado anterior | cortes secos, transiciones grandes | — |

`framesig detectors` los lista en tiempo de ejecución.

## Cómo funciona

1. **Muestrear.** El escáner recorre el vídeo una vez y se queda con unos `sample_fps` fotogramas por segundo.
2. **Puntuar.** Cada firma recorta su región y le pide a su detector un número en `[0, 1]`.
3. **Cachear.** Esas líneas de puntuación se escriben en `.framesig_cache/`, con una clave que resume el vídeo **y** la parte de la configuración que afecta a la puntuación (ritmo de muestreo, regiones, parámetros del detector) — pero **no** los umbrales. Así, reajustar un umbral es un acierto de caché; cambiar un detector la invalida sin que te enteres.
4. **Detectar.** El umbral convierte cada línea en eventos: las muestras activas consecutivas forman una racha, las rachas cercanas se unen (`merge_gap`), y las demasiado cortas se descartan (`min_duration`).

## Pruebas

```console
$ pytest
88 passed
```

La batería incluye una prueba de punta a punta que genera el clip sintético con ffmpeg y comprueba que framesig recupera **exactamente** los eventos que se pintaron en él, en las marcas de tiempo correctas — más pruebas unitarias de cada detector, la lógica de eventos, la validación de configuración, los caminos de error del escáner y la caché.

## Herramientas hermanas

framesig es una de un conjunto de herramientas pequeñas y con pocas dependencias que construyo y mantengo en abierto — utilidades concretas que hacen bien un trabajo y convierten entradas desordenadas en salidas limpias y estructuradas:

- [The GEO Handbook](https://github.com/ferinazumaDEV/generative-engine-optimization-handbook) — la referencia abierta sobre conseguir que los motores de respuesta de IA te citen.
- [typedout](https://github.com/ferinazumaDEV/typedout) — salida estructurada fiable de OpenAI y Anthropic, con interfaz de proveedor para añadir otros.
- [politeclient](https://github.com/ferinazumaDEV/politeclient) — un cliente HTTP cuidadoso y bien educado para Python: reintentos con espera, límite de ritmo por host, caché y paginación.
- [scaffld](https://github.com/ferinazumaDEV/scaffld) — genera proyectos Python completos (pruebas, CI, pre-commit, licencia) desde plantillas, con interfaz de terminal.
- Web y publicaciones: [zentimes.es](https://zentimes.es).

De [ferinazumaDEV](https://github.com/ferinazumaDEV).

## Licencia

MIT — ver [LICENSE](LICENSE).

---

<sub>Hecho por Fernando ([@ferinazumaDEV](https://github.com/ferinazumaDEV)).</sub>
