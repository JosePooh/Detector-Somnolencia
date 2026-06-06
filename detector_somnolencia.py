import cv2
import mediapipe as mp
import numpy as np
import pygame
import time
import math
import os
import pyttsx3
from datetime import datetime
import tkinter as tk
from tkinter import messagebox
import requests
from io import BytesIO

API_URL = "http://127.0.0.1:5000"

# ==========================
# CONFIGURACIÓN
# ==========================

EAR_UMBRAL = 0.23
MAR_UMBRAL = 0.60
TIEMPO_OJOS_CERRADOS = 2
TIEMPO_BOSTEZO = 1.5
TIEMPO_SIN_ROSTRO = 3

# ==========================
# AUDIO
# ==========================

pygame.mixer.init()

try:
    alarma = pygame.mixer.Sound("alarma.mp3")
except:
    alarma = None

alarma_activa = False

voz = pyttsx3.init()
voz.setProperty("rate", 150)

ultima_voz = 0

# ==========================
# MEDIAPIPE
# ==========================

mp_face_mesh = mp.solutions.face_mesh

face_mesh = mp_face_mesh.FaceMesh(
    max_num_faces=1,
    refine_landmarks=True,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5
)

# ==========================
# PUNTOS FACIALES
# ==========================

OJO_IZQ = [33, 160, 158, 133, 153, 144]
OJO_DER = [362, 385, 387, 263, 373, 380]
BOCA = [13, 14, 78, 308]

FRENTE = 10
MENTON = 152


# ==========================
# FUNCIONES
# ==========================
def dibujar_alerta_evidencia(frame, mensaje):
    frame_alerta = frame.copy()

    cv2.putText(
        frame_alerta,
        mensaje,
        (40, 90),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.2,
        (0, 0, 255),
        3
    )

    return frame_alerta

def distancia(p1, p2):
    return np.linalg.norm(np.array(p1) - np.array(p2))


def calcular_ear(puntos_ojo):
    A = distancia(puntos_ojo[1], puntos_ojo[5])
    B = distancia(puntos_ojo[2], puntos_ojo[4])
    C = distancia(puntos_ojo[0], puntos_ojo[3])
    return (A + B) / (2.0 * C)


def calcular_mar(puntos_boca):
    vertical = distancia(puntos_boca[0], puntos_boca[1])
    horizontal = distancia(puntos_boca[2], puntos_boca[3])
    return vertical / horizontal


def calcular_inclinacion(p_frente, p_menton):
    dx = p_menton[0] - p_frente[0]
    dy = p_menton[1] - p_frente[1]
    return math.degrees(math.atan2(dx, dy))


def activar_alarma():
    global alarma_activa

    if alarma and not alarma_activa:
        alarma.play(-1)
        alarma_activa = True


def detener_alarma():
    global alarma_activa

    if alarma and alarma_activa:
        alarma.stop()
        alarma_activa = False


def hablar(texto):
    global ultima_voz

    ahora = time.time()

    if ahora - ultima_voz > 5:
        voz.say(texto)
        voz.runAndWait()
        ultima_voz = ahora


def registrar_alerta(tipo_alerta, nivel):
    try:
        response = requests.post(
            f"{API_URL}/api/registrar-alerta",
            json={
                "dni": dni_conductor,
                "conductor": nombre_conductor,
                "tipo_alerta": tipo_alerta,
                "nivel_cansancio": nivel
            },
            timeout=10
        )

        data = response.json()

        if not data.get("ok"):
            print("Error registrando alerta:", data.get("mensaje"))

    except Exception as e:
        print("No se pudo registrar alerta en API:", e)

def guardar_evidencia(frame, tipo_alerta):
    try:
        ok, buffer = cv2.imencode(".jpg", frame)

        if not ok:
            print("No se pudo convertir la imagen.")
            return

        archivos = {
            "imagen": (
                "evidencia.jpg",
                BytesIO(buffer.tobytes()),
                "image/jpeg"
            )
        }

        datos = {
            "dni": dni_conductor,
            "tipo_alerta": tipo_alerta
        }

        response = requests.post(
            f"{API_URL}/api/subir-evidencia",
            data=datos,
            files=archivos,
            timeout=15
        )

        data = response.json()

        if not data.get("ok"):
            print("Error subiendo evidencia:", data.get("mensaje"))

    except Exception as e:
        print("No se pudo subir evidencia:", e)
    
def dibujar_barra(frame, nivel):
    x, y = 20, 190
    ancho = 300
    alto = 25

    relleno = int((nivel / 100) * ancho)

    cv2.rectangle(frame, (x, y), (x + ancho, y + alto), (255, 255, 255), 2)

    color = (0, 255, 0)

    if nivel >= 60:
        color = (0, 255, 255)

    if nivel >= 80:
        color = (0, 0, 255)

    cv2.rectangle(frame, (x, y), (x + relleno, y + alto), color, -1)

    cv2.putText(frame, f"{nivel}%", (x + ancho + 10, y + 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)


# ==========================
# VARIABLES
# ==========================

tiempo_inicio_ojos = None
tiempo_inicio_bostezo = None
tiempo_sin_rostro = None

nivel_cansancio = 0
nivel_maximo = 0

alertas_ojos = 0
alertas_bostezos = 0
alertas_cabeza = 0
alertas_sin_rostro = 0

tiempo_inicio_programa = time.time()

ultimo_registro = 0

def login_conductor():
    datos = {}

    ventana = tk.Tk()
    ventana.title("Acceso de Conductor")
    ventana.geometry("460x470")
    ventana.resizable(False, False)

    modo = tk.StringVar(value="login")

    frame = tk.Frame(ventana)
    frame.pack(fill="both", expand=True)

    def limpiar():
        for widget in frame.winfo_children():
            widget.destroy()

    def mostrar_login():
        limpiar()
        modo.set("login")

        tk.Label(frame, text="Sistema de Detección de Somnolencia",
                 font=("Arial", 15, "bold")).pack(pady=20)

        tk.Label(frame, text="Iniciar Sesión", font=("Arial", 13, "bold")).pack(pady=10)

        tk.Label(frame, text="Correo").pack()
        entrada_correo = tk.Entry(frame, width=40)
        entrada_correo.pack(pady=5)

        tk.Label(frame, text="Contraseña / DNI").pack()
        entrada_dni = tk.Entry(frame, width=40, show="*")
        entrada_dni.pack(pady=5)

        def iniciar_sesion():
            correo = entrada_correo.get().strip()
            dni = entrada_dni.get().strip()

            try:
                response = requests.post(
                    f"{API_URL}/api/login-conductor",
                    json={
                        "correo": correo,
                        "dni": dni
                    },
                    timeout=10
                )

                data = response.json()

                if data.get("ok"):
                    conductor = data["conductor"]
                    datos.update(conductor)

                    messagebox.showinfo(
                        "Correcto",
                        f"Bienvenido {conductor['nombre']}"
                    )

                    ventana.destroy()
                    return

                messagebox.showerror(
                    "Error",
                    data.get("mensaje", "Correo o DNI incorrecto.")
                )

            except Exception as e:
                messagebox.showerror(
                    "Error",
                    f"No se pudo conectar con el servidor:\n{e}"
                )

        tk.Button(
            frame,
            text="Iniciar monitoreo",
            width=25,
            height=2,
            bg="#1f6feb",
            fg="white",
            command=iniciar_sesion
        ).pack(pady=20)

        tk.Button(
            frame,
            text="Registrar conductor",
            width=25,
            command=mostrar_registro
        ).pack(pady=5)

    def mostrar_registro():
        limpiar()
        modo.set("registro")

        tk.Label(frame, text="Sistema de Detección de Somnolencia",
                 font=("Arial", 15, "bold")).pack(pady=15)

        tk.Label(frame, text="Registro de Conductor", font=("Arial", 13, "bold")).pack(pady=5)

        tk.Label(frame, text="Nombre del conductor").pack()
        entrada_nombre = tk.Entry(frame, width=40)
        entrada_nombre.pack(pady=5)

        tk.Label(frame, text="DNI / Código de conductor").pack()
        entrada_dni = tk.Entry(frame, width=40)
        entrada_dni.pack(pady=5)

        tk.Label(frame, text="Correo").pack()
        entrada_correo = tk.Entry(frame, width=40)
        entrada_correo.pack(pady=5)

        tk.Label(frame, text="Teléfono").pack()
        entrada_telefono = tk.Entry(frame, width=40)
        entrada_telefono.pack(pady=5)

        def registrar():
            nombre = entrada_nombre.get().strip()
            dni = entrada_dni.get().strip()
            correo = entrada_correo.get().strip()
            telefono = entrada_telefono.get().strip()

            if not nombre or not dni or not correo or not telefono:
                messagebox.showerror("Error", "Completa todos los campos.")
                return

            if not dni.isdigit() or len(dni) != 8:
                messagebox.showerror("Error", "El DNI debe tener 8 dígitos.")
                return

            try:

                response = requests.post(
                    f"{API_URL}/api/registrar-conductor",
                    json={
                        "nombre": nombre,
                        "dni": dni,
                        "correo": correo,
                        "telefono": telefono
                    },
                    timeout=10
                )

                data = response.json()

                if not data["ok"]:
                    messagebox.showerror(
                        "Error",
                        data["mensaje"]
                    )
                    return

                conductor = {
                    "nombre": nombre,
                    "dni": dni,
                    "correo": correo,
                    "telefono": telefono
                }

                datos.update(conductor)

            except Exception as e:

                messagebox.showerror(
                    "Error",
                    f"No se pudo conectar al servidor\n{e}"
                )

            messagebox.showinfo(
                "Correcto",
                "Conductor registrado correctamente.\nTu contraseña será tu DNI."
            )

            ventana.destroy()

        tk.Button(
            frame,
            text="Registrar e iniciar monitoreo",
            width=25,
            height=2,
            bg="#1f6feb",
            fg="white",
            command=registrar
        ).pack(pady=20)

        tk.Button(
            frame,
            text="Volver a iniciar sesión",
            width=25,
            command=mostrar_login
        ).pack(pady=5)

    mostrar_login()
    ventana.mainloop()

    if not datos:
        exit()

    return datos

conductor_actual = login_conductor()
dni_conductor = conductor_actual["dni"]
nombre_conductor = conductor_actual["nombre"]

# ==========================
# CÁMARA
# ==========================

cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("No se pudo abrir la cámara.")
    exit()

print("Sistema iniciado.")
print("Presiona Q para salir.")
print("Presiona C para calibrar ojos abiertos.")

while True:
    ret, frame = cap.read()

    if not ret:
        break

    frame = cv2.flip(frame, 1)
    h, w, _ = frame.shape

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    resultado = face_mesh.process(rgb)

    alerta = False
    tipo_alerta = ""
    mensaje_alerta = ""

    if resultado.multi_face_landmarks:
        tiempo_sin_rostro = None

        rostro = resultado.multi_face_landmarks[0]
        puntos = rostro.landmark

        def obtener_punto(indice):
            return int(puntos[indice].x * w), int(puntos[indice].y * h)

        puntos_ojo_izq = [obtener_punto(i) for i in OJO_IZQ]
        puntos_ojo_der = [obtener_punto(i) for i in OJO_DER]
        puntos_boca = [obtener_punto(i) for i in BOCA]

        p_frente = obtener_punto(FRENTE)
        p_menton = obtener_punto(MENTON)

        ear_izq = calcular_ear(puntos_ojo_izq)
        ear_der = calcular_ear(puntos_ojo_der)
        ear_promedio = (ear_izq + ear_der) / 2

        mar = calcular_mar(puntos_boca)
        inclinacion = calcular_inclinacion(p_frente, p_menton)

        # Ojos cerrados
        if ear_promedio < EAR_UMBRAL:
            if tiempo_inicio_ojos is None:
                tiempo_inicio_ojos = time.time()

            if time.time() - tiempo_inicio_ojos >= TIEMPO_OJOS_CERRADOS:
                alerta = True
                tipo_alerta = "OJOS_CERRADOS"
                mensaje_alerta = "ALERTA: OJOS CERRADOS"
                nivel_cansancio += 3
                alertas_ojos += 1
        else:
            tiempo_inicio_ojos = None
            nivel_cansancio -= 1

        # Bostezo
        if mar > MAR_UMBRAL:
            if tiempo_inicio_bostezo is None:
                tiempo_inicio_bostezo = time.time()

            if time.time() - tiempo_inicio_bostezo >= TIEMPO_BOSTEZO:
                alerta = True
                tipo_alerta = "BOSTEZO"
                mensaje_alerta = "ALERTA: BOSTEZO DETECTADO"
                nivel_cansancio += 2
                alertas_bostezos += 1
        else:
            tiempo_inicio_bostezo = None

        # Cabeza inclinada
        if abs(inclinacion) > 25:
            alerta = True
            tipo_alerta = "CABEZA_INCLINADA"
            mensaje_alerta = "ALERTA: CABEZA INCLINADA"
            nivel_cansancio += 2
            alertas_cabeza += 1

        nivel_cansancio = max(0, min(nivel_cansancio, 100))
        nivel_maximo = max(nivel_maximo, nivel_cansancio)

        if nivel_cansancio < 30:
            estado = "NORMAL"
        elif nivel_cansancio < 60:
            estado = "CANSANCIO LEVE"
        elif nivel_cansancio < 80:
            estado = "RIESGO MODERADO"
        else:
            estado = "SOMNOLENCIA CRITICA"

        if alerta:
            activar_alarma()

            if time.time() - ultimo_registro > 5:
                registrar_alerta(tipo_alerta, nivel_cansancio)

                frame_evidencia = dibujar_alerta_evidencia(
                    frame,
                    mensaje_alerta
                )

                guardar_evidencia(
                    frame_evidencia,
                    tipo_alerta
                )

                if tipo_alerta == "OJOS_CERRADOS":
                    hablar("Alerta, ojos cerrados detectados")

                elif tipo_alerta == "BOSTEZO":
                    hablar("Alerta, bostezo detectado")

                elif tipo_alerta == "CABEZA_INCLINADA":
                    hablar("Alerta, cabeza inclinada detectada")

                ultimo_registro = time.time()

        else:
            detener_alarma()

        # Dibujar puntos
        for p in puntos_ojo_izq + puntos_ojo_der:
            cv2.circle(frame, p, 2, (0, 255, 0), -1)

        for p in puntos_boca:
            cv2.circle(frame, p, 3, (255, 0, 0), -1)

        cv2.putText(frame, f"EAR Ojos: {ear_promedio:.2f}", (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        cv2.putText(frame, f"MAR Boca: {mar:.2f}", (20, 70),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        cv2.putText(frame, f"Inclinacion: {inclinacion:.2f}", (20, 100),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        cv2.putText(frame, f"Estado: {estado}", (20, 140),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

        dibujar_barra(frame, nivel_cansancio)

        if alerta:
            cv2.putText(frame, mensaje_alerta, (40, 260),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 3)

    else:
        if tiempo_sin_rostro is None:
            tiempo_sin_rostro = time.time()

        tiempo_ausente = time.time() - tiempo_sin_rostro

        if tiempo_ausente >= TIEMPO_SIN_ROSTRO:
            alerta = True
            tipo_alerta = "SIN_ROSTRO"
            mensaje_alerta = "ALERTA: CONDUCTOR NO DETECTADO"
            nivel_cansancio += 2
            nivel_cansancio = min(nivel_cansancio, 100)
            nivel_maximo = max(nivel_maximo, nivel_cansancio)
            alertas_sin_rostro += 1

            activar_alarma()

            cv2.putText(frame, mensaje_alerta, (40, 130),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 3)

            if time.time() - ultimo_registro > 5:
                registrar_alerta(tipo_alerta, nivel_cansancio)
                frame_evidencia = dibujar_alerta_evidencia(frame, mensaje_alerta)
                guardar_evidencia(frame_evidencia, tipo_alerta)
                hablar("Alerta, conductor no detectado")
                ultimo_registro = time.time()
        else:
            detener_alarma()

    dibujar_barra(frame, nivel_cansancio)

    cv2.putText(frame, "Q: Salir | C: Calibrar", (20, h - 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

    cv2.imshow("Sistema Inteligente - Detector de Somnolencia", frame)

    tecla = cv2.waitKey(1) & 0xFF

    if tecla == ord("q") or tecla == 27:
        break

    if tecla == ord("c") and resultado.multi_face_landmarks:
        EAR_UMBRAL = ear_promedio * 0.75
        print(f"Nuevo umbral EAR calibrado: {EAR_UMBRAL:.2f}")
        hablar("Calibración realizada correctamente")

# ==========================
# CIERRE Y ESTADÍSTICAS
# ==========================

cap.release()
cv2.destroyAllWindows()
detener_alarma()

tiempo_total = time.time() - tiempo_inicio_programa
minutos = int(tiempo_total // 60)
segundos = int(tiempo_total % 60)

print("\n========== ESTADÍSTICAS FINALES ==========")
print(f"Tiempo total monitoreado: {minutos} min {segundos} seg")
print(f"Alertas por ojos cerrados: {alertas_ojos}")
print(f"Alertas por bostezos: {alertas_bostezos}")
print(f"Alertas por cabeza inclinada: {alertas_cabeza}")
print(f"Alertas por conductor no detectado: {alertas_sin_rostro}")
print(f"Nivel máximo de cansancio: {nivel_maximo}%")
print("Evidencias almacenadas en Supabase Storage")
print("==========================================")