import numpy as np

name = "sinesquared"

Tex = r"A sin^2[(2\pi / 4T_{\pi}) \cdot x + \phi] + B"

def fit_function(x, A=1, tpi=1, phi=0, B=0):
    return A * np.sin(2 * np.pi * (1/(4*tpi)) * 1e6 * x + phi)**2 + B

def guess_parameters(xdata, ydata):
    B = np.min(ydata)
    A = np.max(ydata) - B
    x = np.array(xdata)
    y = np.array(ydata)
    f = np.fft.fftfreq(len(x), (x[1] - x[0]))  # This assumes uniform spacing
    F = abs(np.fft.fft(y))
    freq = abs(f[np.argmax(F[1:]) + 1])
    return A, 1 / (2.0 * freq * 1e-6), 0., B

