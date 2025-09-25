import numpy as np
import aubio
import pyaudio
import time
import threading
import tkinter as tk
from collections import deque
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
import sys

RATE = 44100
CHUNK = 4096
FORMAT = pyaudio.paInt16
CHANNELS = 1

p = pyaudio.PyAudio()
stream = None

pitch_o = aubio.pitch("yin", buf_size=CHUNK, hop_size=CHUNK, samplerate=RATE)
pitch_o.set_unit("Hz")
pitch_o.set_silence(-40)

listening = False
exit_app = False

MAX_POINTS = 200
pitch_data = deque([0]*MAX_POINTS, maxlen=MAX_POINTS)
time_data = deque(np.linspace(-MAX_POINTS/10, 0, MAX_POINTS), maxlen=MAX_POINTS)  # time axis

def listen():
    global stream, listening, exit_app
    if stream is None:
        stream = p.open(format=FORMAT, channels=CHANNELS, input=True,
                        frames_per_buffer=CHUNK, rate=RATE)
    last_time = 0
    while listening and not exit_app:
        try:
            data = stream.read(CHUNK, exception_on_overflow=False)
        except Exception:
            continue
        samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / np.iinfo(np.int16).max

        volume = np.sqrt(np.mean(samples ** 2))
        pitch = pitch_o(samples)[0]

        if pitch > 0 and volume > 0.02 and pitch < 5000:
            try:
                note = aubio.freq2note(pitch)
            except ValueError:
                continue
            now = time.time()
            if now - last_time > 0.05:
                note_label.config(text=f"{note} ({pitch:.2f} Hz)")
                pitch_data.append(pitch)
                time_data.append(time_data[-1]+0.1)
                update_plot()
                last_time = now


def update_plot():
    line.set_data(time_data, pitch_data)
    ax.set_xlim(time_data[0], time_data[-1])
    ax.set_ylim(0, max(500, max(pitch_data)*1.2))
    canvas.draw()

def start_listening():
    global listening
    if not listening:
        listening = True
        threading.Thread(target=listen, daemon=True).start()
        status_label.config(text="Listening...")

def stop_listening():
    global listening
    listening = False
    status_label.config(text="Stopped")

def on_closing():
    global exit_app
    exit_app = True
    stop_listening()
    root.update() 
    if stream is not None:
        stream.stop_stream()
        stream.close()
    p.terminate()
    root.destroy()
    sys.exit()

# GUI setup
root = tk.Tk()
root.title("Real-time Note Detector with Graph")

note_label = tk.Label(root, text="Press Start", font=("Helvetica", 32))
note_label.pack(pady=20)

status_label = tk.Label(root, text="Idle", font=("Helvetica", 14))
status_label.pack(pady=5)

start_button = tk.Button(root, text="Start Listening", command=start_listening)
start_button.pack(pady=5)

stop_button = tk.Button(root, text="Stop Listening", command=stop_listening)
stop_button.pack(pady=5)

# Matplotlib figure for graph
fig, ax = plt.subplots(figsize=(8, 3))
line, = ax.plot(time_data, pitch_data, color='blue')
ax.set_title("Pitch over Time")
ax.set_xlabel("Time (s)")
ax.set_ylabel("Frequency (Hz)")
ax.set_ylim(0, 500)
ax.set_xlim(time_data[0], time_data[-1])
plt.tight_layout()

canvas = FigureCanvasTkAgg(fig, master=root)
canvas.get_tk_widget().pack()

root.protocol("WM_DELETE_WINDOW", on_closing)

root.mainloop()
