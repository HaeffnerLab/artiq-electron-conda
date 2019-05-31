import numpy as np

name = "sine"

Tex = r"A\cdot sin(2\pi\cdot freq[kHz]\cdot x+\phi) + B"

def fit_function(x, A=1, freq=5, phi=0, B=0):
    return A * np.sin(2 * np.pi * freq * 1e5 * x + phi) + B

def guess_parameters(xdata, ydata):
    B = np.min(ydata)
    A = np.max(ydata) - B
    x = np.array(xdata)
    y = np.array(ydata)
    f = np.fft.fftfreq(len(x), (x[1] - x[0]))  # This assumes uniform spacing
    F = abs(np.fft.fft(y))
    freq = abs(f[np.argmax(F[1:]) + 1])
    rel_diff = (ydata[0] - A / 2) / np.max(ydata)
    phase = - rel_diff * np.pi
    return A, freq * 1e-5, phase, B

