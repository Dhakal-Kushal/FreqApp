import numpy as np
import aubio
import pyaudio
import time
import threading
import tkinter as tk

# Audio setup
RATE = 44100
CHUNK = 4096
FORMAT = pyaudio.paInt16
CHANNELS = 1

p = pyaudio.PyAudio()
stream = None

pitch_o = aubio.pitch("yin", buf_size=CHUNK, hop_size=CHUNK, samplerate=RATE)
pitch_o.set_unit("Hz")
pitch_o.set_silence(-40)

listening = False  # Flag to control the listening thread

# Function to detect pitch
def listen():
    global stream, listening
    if stream is None:
        stream = p.open(format=FORMAT, channels=CHANNELS, input=True,
                        frames_per_buffer=CHUNK, rate=RATE)
    last_time = 0
    while listening:
        data = stream.read(CHUNK, exception_on_overflow=False)
        samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / np.iinfo(np.int16).max

        volume = np.sqrt(np.mean(samples ** 2))
        pitch = pitch_o(samples)[0]

        if pitch > 0 and volume > 0.05:
            note = aubio.freq2note(pitch)
            now = time.time()
            if now - last_time > 0.1:
                note_label.config(text=f"{note} ({pitch:.2f} Hz)")
                last_time = now

# Start listening thread
def start_listening():
    global listening
    if not listening:
        listening = True
        threading.Thread(target=listen, daemon=True).start()
        status_label.config(text="Listening...")

# Stop listening
def stop_listening():
    global listening
    listening = False
    status_label.config(text="Stopped")

# GUI setup
root = tk.Tk()
root.title("Real-time Note Detector")

note_label = tk.Label(root, text="Press Start", font=("Helvetica", 32))
note_label.pack(pady=20)

status_label = tk.Label(root, text="Idle", font=("Helvetica", 14))
status_label.pack(pady=5)

start_button = tk.Button(root, text="Start Listening", command=start_listening)
start_button.pack(pady=10)

stop_button = tk.Button(root, text="Stop Listening", command=stop_listening)
stop_button.pack(pady=10)

root.protocol("WM_DELETE_WINDOW", lambda: (stop_listening(), root.destroy()))

root.mainloop()

# Cleanup audio
if stream is not None:
    stream.stop_stream()
    stream.close()
p.terminate()
