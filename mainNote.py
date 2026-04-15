import numpy as np
import parselmouth
import pyaudio
import time
import threading
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from collections import deque
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
import math
import csv
import sys

RATE = 44100
CHUNK = 2048
FORMAT = pyaudio.paInt16
CHANNELS = 1
INT16_MAX = np.iinfo(np.int16).max
PITCH_WINDOW_SAMPLES = int(RATE * 0.2)

NOTES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

SCALES = {
    "Chromatic": list(range(12)),
    "Major":     [0, 2, 4, 5, 7, 9, 11],
    "Minor":     [0, 2, 3, 5, 7, 8, 10],
    "Pentatonic":[0, 2, 4, 7, 9],
    "Blues":     [0, 3, 5, 6, 7, 10],
}
KEYS = NOTES

data_lock = threading.Lock()
_stop_event = threading.Event()
_stop_event.set()
_listener_thread = None

exit_app = False
is_listening = False

live_app_state = {
    "key": "C",
    "scale": "Chromatic"
}

_ui_queue: queue.Queue = queue.Queue(maxsize=1)

MAX_POINTS = 200

pitch_data   = deque([0.0] * MAX_POINTS, maxlen=MAX_POINTS)
time_data    = deque([-(MAX_POINTS - i) * 0.1 for i in range(MAX_POINTS)], maxlen=MAX_POINTS)
color_data   = deque(['#4a90d9'] * MAX_POINTS, maxlen=MAX_POINTS)
note_history = deque(maxlen=50)
session_log  = []

start_time     = None
plot_update_id = None
p              = None 

def freq_to_midi(freq):
    if freq <= 0:
        return None
    try:
        return 69 + 12 * math.log2(freq / 440.0)
    except ValueError:
        return None

def freq2note(freq):
    if freq <= 0:
        return ""
    midi = freq_to_midi(freq)
    if midi is None:
        return ""
    note_idx = int(round(midi)) % 12
    octave   = int(round(midi)) // 12 - 1
    return f"{NOTES[note_idx]}{octave}"

def cents_deviation(freq):
    midi = freq_to_midi(freq)
    if midi is None:
        return 0.0
    return (midi - round(midi)) * 100

def note_in_scale(note_name, key, scale_name):
    if scale_name == "Chromatic":
        return True
    root_note = note_name.rstrip('0123456789')
    root_idx  = NOTES.index(root_note) if root_note in NOTES else -1
    key_idx   = NOTES.index(key)       if key       in NOTES else  0
    offset    = (root_idx - key_idx) % 12
    return offset in SCALES.get(scale_name, list(range(12)))

def cents_color(cents):
    a = abs(cents)
    if a < 10: return '#2ecc71'
    if a < 25: return '#f39c12'
    return '#e74c3c'

# Update live dictionary safely from the main Tkinter thread
def sync_ui_state(*args):
    live_app_state["key"] = selected_key.get()
    live_app_state["scale"] = selected_scale.get()

def listen(stop_flag, volume_threshold, debounce_time):
    global start_time

    try:
        s = p.open(
            format=FORMAT, channels=CHANNELS,
            input=True, frames_per_buffer=CHUNK, rate=RATE,
        )
    except Exception:
        root.after(0, lambda: status_label.config(text="✗ No mic found", fg='#e74c3c'))
        return

    start_time     = time.time()
    last_note_time = 0.0
    audio_buffer   = np.zeros(PITCH_WINDOW_SAMPLES, dtype=np.float32)

    while not stop_flag.is_set() and not exit_app:
        try:
            raw = s.read(CHUNK, exception_on_overflow=False)
        except Exception:
            break

        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / INT16_MAX
        volume  = float(np.sqrt(np.mean(samples ** 2)))
        now     = time.time()
        elapsed = now - start_time

        audio_buffer = np.roll(audio_buffer, -len(samples))
        audio_buffer[-len(samples):] = samples

        pitch = 0.0
        if volume > volume_threshold:
            try:
                sound     = parselmouth.Sound(audio_buffer, sampling_frequency=RATE)
                pitch_obj = sound.to_pitch(pitch_floor=60.0, pitch_ceiling=3000.0)
                vals      = pitch_obj.selected_array['frequency']
                valid     = vals[vals > 0]
                if len(valid):
                    pitch = float(np.median(valid))
            except Exception:
                pass

        with data_lock:
            time_data.append(elapsed)

            if 0 < pitch < 5000:
                note  = freq2note(pitch)
                cents = cents_deviation(pitch)
                color = cents_color(cents)
                pitch_data.append(pitch)
                color_data.append(color)

                if now - last_note_time > debounce_time:
                    last_note_time = now
                    
                    key      = live_app_state["key"]
                    scale    = live_app_state["scale"]
                    in_scale = note_in_scale(note, key, scale)

                    note_history.appendleft({
                        "note":     note,
                        "hz":       f"{pitch:.2f} Hz",
                        "cents":    f"{cents:+.1f}¢",
                        "color":    color,
                        "in_scale": in_scale,
                    })
                    
                    session_log.append({
                        "time":  round(elapsed, 3),
                        "note":  note,
                        "hz":    round(pitch, 2),
                        "cents": round(cents, 1),
                    })

                    payload = {
                        "note":       note,
                        "hz":         f"{pitch:.2f} Hz",
                        "cents_text": f"{cents:+.1f}¢",
                        "color":      color,
                        "in_scale":   in_scale,
                        "cents_val":  cents,
                    }
                    try:
                        _ui_queue.put_nowait(payload)
                    except queue.Full:
                        try: _ui_queue.get_nowait()
                        except queue.Empty: pass
                        try: _ui_queue.put_nowait(payload)
                        except queue.Full: pass
            else:
                pitch_data.append(0.0)
                color_data.append('#4a90d9')

    try:
        s.stop_stream()
        s.close()
    except Exception:
        pass

def poll_ui_queue():
    if not exit_app:
        if is_listening:
            try:
                payload = _ui_queue.get_nowait()
                ui_update(
                    payload["note"], payload["hz"], payload["cents_text"],
                    payload["color"], payload["in_scale"], payload["cents_val"],
                )
            except queue.Empty:
                pass
        
        # Tkinter loop handling text/labels at ~30 FPS
        root.after(33, poll_ui_queue)

def ui_update(note_text, hz_text, cents_text, color, in_scale, cents_val):
    note_label.config(text=note_text, fg=color)
    hz_label.config(text=hz_text)
    cents_label.config(text=cents_text, fg=color)
    warning = "" if in_scale else f"⚠ Not in {selected_key.get()} {selected_scale.get()}"
    scale_warn_label.config(text=warning)
    update_needle(cents_val)
    update_history()

def periodic_plot_update():
    global plot_update_id
    if not exit_app:
        if is_listening:
            update_plot()
            
        # Tkinter loop scheduling Matplotlib redraws at ~10 FPS
        plot_update_id = root.after(100, periodic_plot_update)

def update_needle(cents):
    needle_canvas.delete("needle")
    cx, cy, r = 150, 120, 90
    cents  = max(-50.0, min(50.0, cents))
    angle_rad = math.radians(90 + (cents / 50) * 60)
    x2 = cx + r * math.cos(math.pi - angle_rad)
    y2 = cy - r * math.sin(math.pi - angle_rad)
    color = cents_color(cents)
    needle_canvas.create_line(cx, cy, x2, y2, fill=color, width=3, tags="needle")
    needle_canvas.create_oval(cx-5, cy-5, cx+5, cy+5, fill=color, tags="needle")

def draw_tuner_arc():
    needle_canvas.delete("arc_base")
    cx, cy, r = 150, 120, 90
    needle_canvas.create_arc(
        cx-r, cy-r, cx+r, cy+r,
        start=30, extent=120,
        outline='#555', width=2, style='arc', tags="arc_base",
    )
    for mark, lbl in [(-50, "-50¢"), (-25, "-25¢"), (0, "0"), (25, "+25¢"), (50, "+50¢")]:
        a  = math.radians(90 + (mark / 50) * 60)
        mx = cx + (r + 12) * math.cos(math.pi - a)
        my = cy - (r + 12) * math.sin(math.pi - a)
        needle_canvas.create_text(mx, my, text=lbl, font=("Courier", 7),
                                  fill='#888', tags="arc_base")

def update_plot():
    with data_lock:
        pd_list = list(pitch_data)
        td_list = list(time_data)
        cd_list = list(color_data)

    # Fast Matplotlib optimization: Remove only the plotted line instead of ax.cla()
    while ax.lines:
        ax.lines[0].remove()

    for i in range(1, len(pd_list)):
        if pd_list[i] > 0 and pd_list[i-1] > 0:
            ax.plot(
                [td_list[i-1], td_list[i]],
                [pd_list[i-1], pd_list[i]],
                color=cd_list[i], linewidth=1.5,
            )

    valid = [v for v in pd_list if v > 0]
    ymax  = max(500.0, max(valid) * 1.2) if valid else 500.0
    
    xmin, xmax = td_list[0], td_list[-1]
    
    ax.set_xlim(xmin, xmax if xmax > xmin else xmin + 1.0)
    ax.set_ylim(0, ymax)
    canvas.draw()

def update_history():
    history_listbox.delete(0, tk.END)
    with data_lock:
        entries = list(note_history)
    for entry in entries:
        flag    = "" if entry["in_scale"] else " ⚠"
        display = f"{entry['note']:>4}  {entry['hz']:>12}  {entry['cents']:>8}{flag}"
        history_listbox.insert(tk.END, display)
        history_listbox.itemconfig(tk.END, fg=entry["color"])

def start_listening():
    global _listener_thread, _stop_event, start_time, is_listening

    if _listener_thread is not None and _listener_thread.is_alive():
        _stop_event.set()
        _listener_thread.join(timeout=2.0)
        if _listener_thread.is_alive():
            status_label.config(text="⚠ Thread stuck — try again", fg='#e74c3c')
            return

    with data_lock:
        pitch_data.clear()
        time_data.clear()
        color_data.clear()
        note_history.clear()
        
        pitch_data.extend([0.0] * MAX_POINTS)
        time_data.extend([-(MAX_POINTS - i) * 0.1 for i in range(MAX_POINTS)])
        color_data.extend(['#4a90d9'] * MAX_POINTS)
    
    start_time = None

    while not _ui_queue.empty():
        try: _ui_queue.get_nowait()
        except queue.Empty: break

    volume_threshold = volume_var.get()
    debounce_time    = debounce_var.get()

    _stop_event = threading.Event()
    _listener_thread = threading.Thread(
        target=listen,
        args=(_stop_event, volume_threshold, debounce_time),
        daemon=True,
    )
    _listener_thread.start()

    is_listening = True
    status_label.config(text="● Listening", fg='#2ecc71')

def stop_listening():
    global is_listening
    is_listening = False
    _stop_event.set()
    status_label.config(text="■ Stopped", fg='#e74c3c')

def clear_session_log():
    if messagebox.askyesno("Clear Data", "Are you sure you want to clear the export log?"):
        session_log.clear()
        messagebox.showinfo("Cleared", "Session log cleared.")

def export_session():
    if not session_log:
        messagebox.showinfo("Export", "No data to export.")
        return
    path = filedialog.asksaveasfilename(
        defaultextension=".csv",
        filetypes=[("CSV files", "*.csv")],
        title="Save Session Log",
    )
    if not path:
        return
    with open(path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=["time", "note", "hz", "cents"])
        writer.writeheader()
        writer.writerows(session_log)
    messagebox.showinfo("Export", f"Session saved to:\n{path}")

def on_closing():
    global exit_app
    exit_app = True
    _stop_event.set()

    if plot_update_id is not None:
        try: root.after_cancel(plot_update_id)
        except Exception: pass

    if _listener_thread is not None:
        _listener_thread.join(timeout=1.5)

    if p is not None:
        p.terminate()
        
    plt.close('all')
    root.quit()
    root.destroy()

if __name__ == "__main__":
    p = pyaudio.PyAudio()

    root = tk.Tk()
    root.title("Note Detector Pro")
    root.configure(bg='#1a1a2e')
    root.geometry("980x760")

    volume_var     = tk.DoubleVar(value=0.01)
    debounce_var   = tk.DoubleVar(value=0.05)
    selected_key   = tk.StringVar(value="C")
    selected_scale = tk.StringVar(value="Chromatic")
    
    selected_key.trace_add("write", sync_ui_state)
    selected_scale.trace_add("write", sync_ui_state)

    header_frame = tk.Frame(root, bg='#1a1a2e')
    header_frame.pack(fill='x', padx=20, pady=(15, 0))

    tk.Label(header_frame, text="NOTE DETECTOR PRO", font=("Courier", 13, "bold"),
             bg='#1a1a2e', fg='#888').pack(side='left')

    status_label = tk.Label(header_frame, text="■ Idle", font=("Courier", 12),
                            bg='#1a1a2e', fg='#888')
    status_label.pack(side='right')

    main_frame = tk.Frame(root, bg='#1a1a2e')
    main_frame.pack(fill='both', expand=True, padx=20, pady=10)

    left_panel = tk.Frame(main_frame, bg='#16213e', relief='flat', bd=0)
    left_panel.pack(side='left', fill='y', padx=(0, 10), ipadx=10, ipady=10)

    note_label = tk.Label(left_panel, text="—", font=("Courier", 72, "bold"),
                          bg='#16213e', fg='#4a90d9', width=4)
    note_label.pack(pady=(20, 0))

    hz_label = tk.Label(left_panel, text="— Hz", font=("Courier", 14),
                        bg='#16213e', fg='#aaa')
    hz_label.pack()

    cents_label = tk.Label(left_panel, text="±0.0¢", font=("Courier", 18, "bold"),
                           bg='#16213e', fg='#2ecc71')
    cents_label.pack(pady=(0, 5))

    scale_warn_label = tk.Label(left_panel, text="", font=("Courier", 10),
                                 bg='#16213e', fg='#e67e22')
    scale_warn_label.pack()

    needle_canvas = tk.Canvas(left_panel, width=300, height=140,
                              bg='#16213e', highlightthickness=0)
    needle_canvas.pack(pady=10)
    draw_tuner_arc()
    update_needle(0)

    controls_frame = tk.Frame(left_panel, bg='#16213e')
    controls_frame.pack(pady=10, padx=10, fill='x')

    tk.Label(controls_frame, text="Volume Threshold", font=("Courier", 9),
             bg='#16213e', fg='#888').pack(anchor='w')
    tk.Scale(controls_frame, variable=volume_var, from_=0.001, to=0.1,
             resolution=0.001, orient='horizontal', bg='#16213e',
             fg='#aaa', troughcolor='#0f3460', highlightthickness=0,
             length=220).pack()

    tk.Label(controls_frame, text="Debounce (s)", font=("Courier", 9),
             bg='#16213e', fg='#888').pack(anchor='w')
    tk.Scale(controls_frame, variable=debounce_var, from_=0.01, to=0.3,
             resolution=0.01, orient='horizontal', bg='#16213e',
             fg='#aaa', troughcolor='#0f3460', highlightthickness=0,
             length=220).pack()

    scale_frame = tk.Frame(controls_frame, bg='#16213e')
    scale_frame.pack(fill='x', pady=(8, 0))

    tk.Label(scale_frame, text="Key",   font=("Courier", 9), bg='#16213e', fg='#888').grid(row=0, column=0, sticky='w')
    ttk.Combobox(scale_frame, textvariable=selected_key,   values=KEYS,
                 width=5,  state='readonly').grid(row=0, column=1, padx=5)
    tk.Label(scale_frame, text="Scale", font=("Courier", 9), bg='#16213e', fg='#888').grid(row=0, column=2, sticky='w')
    ttk.Combobox(scale_frame, textvariable=selected_scale, values=list(SCALES.keys()),
                 width=10, state='readonly').grid(row=0, column=3, padx=5)

    btn_frame = tk.Frame(left_panel, bg='#16213e')
    btn_frame.pack(pady=10)

    tk.Button(btn_frame, text="START",  command=start_listening,
              font=("Courier", 11, "bold"), bg='#0f3460', fg='#2ecc71',
              activebackground='#0f3460', relief='flat', padx=15, pady=6).grid(row=0, column=0, padx=3)
    tk.Button(btn_frame, text="STOP",   command=stop_listening,
              font=("Courier", 11, "bold"), bg='#0f3460', fg='#e74c3c',
              activebackground='#0f3460', relief='flat', padx=15, pady=6).grid(row=0, column=1, padx=3)
    tk.Button(btn_frame, text="EXPORT", command=export_session,
              font=("Courier", 11, "bold"), bg='#0f3460', fg='#f39c12',
              activebackground='#0f3460', relief='flat', padx=15, pady=6).grid(row=0, column=2, padx=3)
    
    tk.Button(btn_frame, text="CLR LOG", command=clear_session_log,
              font=("Courier", 9, "bold"), bg='#0f1b35', fg='#888',
              activebackground='#0f3460', relief='flat', padx=5, pady=8).grid(row=0, column=3, padx=3)

    right_panel = tk.Frame(main_frame, bg='#1a1a2e')
    right_panel.pack(side='left', fill='both', expand=True)

    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(7, 3))
    fig.patch.set_facecolor('#16213e')
    ax.set_facecolor('#0f1b35')
    ax.set_title("Pitch over Time", color='#888', fontsize=10, fontfamily='monospace')
    ax.set_xlabel("Time (s)", color='#666', fontsize=8)
    ax.set_ylabel("Frequency (Hz)", color='#666', fontsize=8)
    ax.tick_params(colors='#555')
    for spine in ax.spines.values():
        spine.set_edgecolor('#333')
    ax.set_ylim(0, 500)
    ax.set_xlim(0, 10)
    plt.tight_layout()

    canvas = FigureCanvasTkAgg(fig, master=right_panel)
    canvas.get_tk_widget().pack(fill='x')

    hist_frame = tk.Frame(right_panel, bg='#16213e')
    hist_frame.pack(fill='both', expand=True, pady=(10, 0))

    tk.Label(hist_frame, text="NOTE HISTORY", font=("Courier", 9, "bold"),
             bg='#16213e', fg='#555').pack(anchor='w', padx=10, pady=(6, 0))
    tk.Label(hist_frame, text=f"{'NOTE':>4}  {'FREQUENCY':>12}  {'CENTS':>8}",
             font=("Courier", 9), bg='#16213e', fg='#444').pack(anchor='w', padx=10)

    hist_list_frame = tk.Frame(hist_frame, bg='#16213e')
    hist_list_frame.pack(fill='both', expand=True, padx=10, pady=(0, 10))

    history_listbox = tk.Listbox(hist_list_frame, font=("Courier", 10), bg='#0f1b35',
                                  fg='#aaa', selectbackground='#0f3460',
                                  relief='flat', borderwidth=0,
                                  highlightthickness=0, height=12)
    history_listbox.pack(side='left', fill='both', expand=True)

    scrollbar = tk.Scrollbar(hist_list_frame, orient='vertical', command=history_listbox.yview)
    scrollbar.pack(side='right', fill='y')
    history_listbox.config(yscrollcommand=scrollbar.set)

    root.protocol("WM_DELETE_WINDOW", on_closing)

    plot_update_id = root.after(100, periodic_plot_update)
    poll_ui_queue()

    root.mainloop()