import cv2
import threading
import requests
import time
import sys
import numpy as np

# Configuración de comunicación y frecuencia
CLOUD_URL = "http://localhost:8000/detect"
SEND_INTERVAL_SEC = 1.0

# Traducción de etiquetas del modelo a términos de usuario
DISPLAY_LABELS = {
    "A factory worker focused on working at the desk": "Enfocado",
    "A factory worker distracted looking at a mobile phone": "Usando Celular",
    "A factory worker sleeping on the desk": "Durmiendo",
    "A factory worker drinking water from a glass": "Bebiendo Agua"
}

# Definición de paleta de colores en formato BGR
COLOR_SAFE = (144, 238, 144)      
COLOR_ALERT = (80, 80, 255)       
COLOR_WAIT = (180, 180, 180)      
COLOR_BG = (30, 30, 30)           
COLOR_TEXT = (245, 245, 245)      
COLOR_BAR_BG = (80, 80, 80)       

class AttentionMonitor:
    """
    Gestiona la captura de video, la comunicación con la API de detección
    y la renderización de la interfaz de usuario en tiempo real.
    """
    def __init__(self):
        # Variables de control de estado interno
        self.current_alarm = False
        self.current_action = "N/A"
        self.current_scores = {}
        self.is_connecting = False
        self.server_offline = False

    def send_frame_to_cloud(self, frame_bytes):
        """
        Realiza el envío asíncrono del frame comprimido al servidor.
        Actualiza los estados de alarma y confianza basados en la respuesta JSON.
        """
        try:
            self.is_connecting = True
            files = {'file': ('frame.jpg', frame_bytes, 'image/jpeg')}
            
            response = requests.post(CLOUD_URL, files=files, timeout=5)
            response.raise_for_status()
            data = response.json()
            
            # Registro en consola para integración con sistemas externos o logs
            if data.get("alarm") and not self.current_alarm:
                print("\n" + "="*60)
                print("SISTEMA DE DETENCION DE MAQUINARIA ACTIVADO")
                print(f"Causa: {data.get('action_detected')}")
                print(f"Confianza: {data.get('confidence_score')*100:.2f}%")
                print("="*60 + "\n")
                
            self.current_alarm = data.get("alarm", False)
            self.current_action = data.get("action_detected", "N/A")
            self.current_scores = data.get("all_scores", {})
            self.server_offline = False
            
        except requests.exceptions.RequestException as e:
            self.server_offline = True
            self.current_alarm = False
            print(f"Fallo de conexión con Cloud API: {e}")
        finally:
            self.is_connecting = False

    def draw_hud(self, frame):
        """
        Renderiza la interfaz gráfica (Heads-Up Display) sobre el frame.
        Incluye paneles laterales, indicadores de estado y barras de probabilidad.
        """
        h, w, _ = frame.shape
        overlay = frame.copy()
        
        # Selección de color y texto según el estado actual del sistema
        if self.server_offline or (self.is_connecting and not self.current_scores):
            status_text = "CONECTANDO AL SERVIDOR..."
            main_color = COLOR_WAIT
        elif self.current_alarm:
            action_es = DISPLAY_LABELS.get(self.current_action, self.current_action).upper()
            status_text = f"ALERTA: {action_es}"
            main_color = COLOR_ALERT
        else:
            status_text = "SEGURO - TRABAJADOR ENFOCADO"
            main_color = COLOR_SAFE

        # Dibujo del panel lateral con transparencia mediante mezcla de imágenes
        panel_width = 380
        cv2.rectangle(overlay, (0, 0), (panel_width, h), COLOR_BG, -1)
        
        alpha = 0.85
        cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)

        # Cabecera de estado principal
        cv2.rectangle(frame, (0, 0), (panel_width, 60), main_color, -1)
        
        # Uso de LINE_AA para renderizado suavizado de tipografía
        cv2.putText(frame, status_text, (15, 38), cv2.FONT_HERSHEY_DUPLEX, 0.6, (0, 0, 0), 1, cv2.LINE_AA)
        cv2.rectangle(frame, (0, 0), (w, h), main_color, 3)

        # Renderizado de barras de nivel para cada categoría detectada
        if self.current_scores:
            cv2.putText(frame, "NIVEL DE ATENCION:", (15, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLOR_WAIT, 1, cv2.LINE_AA)
            
            y_offset = 130
            for raw_label, score in self.current_scores.items():
                label_es = DISPLAY_LABELS.get(raw_label, "Otro")
                
                cv2.putText(frame, f"{label_es}", (15, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLOR_TEXT, 1, cv2.LINE_AA)
                
                # Dibujo de la barra de fondo y la barra de progreso proporcional al score
                bar_x, bar_w, bar_h = 15, 250, 8
                cv2.rectangle(frame, (bar_x, y_offset + 10), (bar_x + bar_w, y_offset + 10 + bar_h), COLOR_BAR_BG, -1)
                
                fill_w = int(bar_w * score)
                bar_color = main_color if raw_label == self.current_action else COLOR_WAIT
                cv2.rectangle(frame, (bar_x, y_offset + 10), (bar_x + fill_w, y_offset + 10 + bar_h), bar_color, -1)
                
                cv2.putText(frame, f"{score*100:.1f}%", (bar_x + bar_w + 15, y_offset + 19), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLOR_TEXT, 1, cv2.LINE_AA)
                
                y_offset += 50

    def run(self):
        """
        Ciclo principal de captura y procesamiento.
        Configura el hardware de entrada y gestiona los hilos de red.
        """
        # Para linux usar cv2.CAP_V4L2
        # Para windows usar cv2.CAP_DSHOW
        # Para mac usar cv2.CAP_AVFOUNDATION
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW) 
        
        if not cap.isOpened():
            print("Error: Fallo al inicializar el dispositivo de captura.")
            sys.exit(1)

        # Configuración de resolución nativa para relación de aspecto 16:9
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

        last_send_time = 0
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            # Inversión de imagen para visualización natural del usuario
            frame = cv2.flip(frame, 1)
                
            current_time = time.time()
            
            # Control de frecuencia de muestreo asíncrono
            if (current_time - last_send_time) >= SEND_INTERVAL_SEC:
                if not self.is_connecting:
                    # Codificación en JPEG para reducir el ancho de banda necesario
                    _, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                    
                    thread = threading.Thread(target=self.send_frame_to_cloud, args=(buffer.tobytes(),))
                    thread.daemon = True
                    thread.start()
                    
                    last_send_time = current_time

            self.draw_hud(frame)
            cv2.imshow('Edge Client - Monitor de Atencion', frame)
            
            # Cierre de aplicación mediante interrupción de teclado
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    monitor = AttentionMonitor()
    monitor.run()