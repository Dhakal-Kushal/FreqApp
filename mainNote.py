import numpy as np
import aubio
import pyaudio
import time

RATE = 44100
CHUNK = 4096
FORMAT = pyaudio.paInt16
CHANNELS = 1

p = pyaudio.PyAudio()
stream = p.open(format=FORMAT, channels=CHANNELS, input=True,
                frames_per_buffer=CHUNK, rate=RATE)

pitch_o = aubio.pitch("yin", buf_size=CHUNK, hop_size=CHUNK, samplerate=RATE)
pitch_o.set_unit("Hz")
pitch_o.set_silence(-40)

print("Starting stream...")

try:    
    last_time = 0
    while True:
        data = stream.read(CHUNK, exception_on_overflow=False)
        samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / np.iinfo(np.int16).max

        volume = np.sqrt(np.mean(samples ** 2))
        pitch = pitch_o(samples)[0]

        if pitch > 0 and volume > 0.1:
            note = aubio.freq2note(pitch)
            now = time.time()
            if now - last_time > 0.1:
                print(f"{note} ({pitch:.2f} Hz)")
                last_time = now

except KeyboardInterrupt:
    print("Ending stream...")

finally:
    stream.stop_stream()
    stream.close()
    p.terminate()
