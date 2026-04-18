# Edge Client: Nodo de Ingestión y Telemetría Visual

Este directorio contiene la implementación del nodo local (Edge). Su propósito en la arquitectura del sistema es actuar como un cliente ligero encargado de la captura de hardware (video), compresión de *frames*, comunicación asíncrona con el servidor de inferencia, y el renderizado en tiempo real de los resultados telemétricos sin bloquear el hilo principal de ejecución.

## Arquitectura y Tecnologías

El cliente está optimizado para consumir un mínimo de recursos locales, delegando el cómputo pesado a la nube.

* **OpenCV (`cv2`):** Interfaz a nivel de sistema para la captura del *stream* de video en hardware (cámara web) y manipulación de matrices de píxeles para el renderizado del *Heads-Up Display* (HUD).
* **Concurrencia (`threading`):** Desacoplamiento del I/O de red respecto al bucle principal de renderizado de video, garantizando una tasa de fotogramas (FPS) fluida y evitando el *thread blocking*.
* **HTTP Client (`requests`):** Capa de transporte para la transmisión de binarios (`image/jpeg`) hacia la API REST del Cloud Server.
* **NumPy:** Procesamiento vectorial estricto para operaciones de fusión de imágenes (Alpha Blending) en la interfaz gráfica.

---

## Implementación Base

### 1. Gestión de Estado (`AttentionMonitor`)
Para prevenir condiciones de carrera (*race conditions*) derivadas de la arquitectura multihilo, el estado de la aplicación se encapsula dentro de la clase `AttentionMonitor`. Esta clase maneja el ciclo de vida de la conexión, el estado de las alarmas locales y la caché de los últimos resultados procesados por la API.

### 2. Transmisión Asíncrona (Non-Blocking I/O)
El desafío principal en el procesamiento de video en red es la latencia de las peticiones HTTP. Para evitar la caída de *frames*, el envío de la carga útil se realiza aislando la petición en un hilo demonio (`daemon thread`), controlado por un temporizador de muestreo.

```python
# Muestreo de frames basado en SEND_INTERVAL_SEC
if (current_time - last_send_time) >= SEND_INTERVAL_SEC:
    if not self.is_connecting:
        # Compresión en memoria para optimización de ancho de banda (JPEG 80%)
        _, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        
        # Despacho de la petición de red en un hilo secundario
        thread = threading.Thread(target=self.send_frame_to_cloud, args=(buffer.tobytes(),))
        thread.daemon = True 
        thread.start()
```

### 3. Renderizado de Interfaz No Obstructiva (Alpha Blending)
Para mantener la visibilidad total del área de trabajo, los paneles de telemetría se renderizan mediante fusión alfa (`cv2.addWeighted`). Se generan máscaras y *overlays* que posteriormente se calculan sobre la matriz original del *frame*.

```python
panel_width = 380
# Se genera una matriz idéntica al frame para el cálculo del overlay
cv2.rectangle(overlay, (0, 0), (panel_width, h), COLOR_BG, -1)

# Fusión matricial: 85% de opacidad para el frame original, 15% para el panel de telemetría
alpha = 0.85
cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)
```

### 4. Controlador de Actuadores (Simulación IoT)
Al recibir una respuesta estructurada del Cloud Server donde el *flag* `is_alarm` se evalúa como `True`, el bucle principal modifica el mapeo de colores de la interfaz a `COLOR_ALERT` y detona la rutina de señalización a nivel de consola (simulando una interrupción por puerto Serial/GPIO hacia los relés de la maquinaria).

```python
if data.get("alarm") is True:
    print("[CRITICAL] SISTEMA DE DETENCIÓN DE MAQUINARIA ACTIVADO")
    print(f"[LOG] Causa detectada: {data.get('action_detected')}")
```

---

## Entorno y Ejecución

**1. Dependencias**
Instalar los paquetes requeridos en el entorno local:
```bash
pip install -r requirements.txt
```

**2. Configuración de Red**
Verificar que la variable de entorno o constante de URL en `monitor.py` apunte al host correcto del Cloud Server (ej. `http://localhost:8000/detect` o la IP de la instancia EC2).

**3. Ejecución del Nodo**
Iniciar el script principal. El sistema solicitará permisos a nivel de sistema operativo para acceder al periférico de captura de video.
```bash
python monitor.py
```
*(Los logs de latencia, red y simulación de actuadores se imprimirán en *stdout* en tiempo real).*