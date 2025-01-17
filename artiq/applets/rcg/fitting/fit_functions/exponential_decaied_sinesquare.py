import numpy as np

name = "exponential_decaied_sinesquare"

Tex = r"0.5 A [1 + exp[- x / \tau] cos[2 (2\pi / 4T_{\pi}) \cdot x + \phi]] + B"

def fit_function(x, A=1, tau=1, tpi=1, phi=0, B=0):
    return 0.5 * A * (1 -  np.exp(-1e6 * x/tau) * np.cos(2*2 * np.pi * (1/(4*tpi)) * 1e6 * x + phi)) + B

def guess_parameters(xdata, ydata):
    B = np.min(ydata)
    A = np.max(ydata) - B
    x = np.array(xdata)
    y = np.array(ydata)
    f = np.fft.fftfreq(len(x), (x[1] - x[0]))  # This assumes uniform spacing
    F = abs(np.fft.fft(y))
    freq = abs(f[np.argmax(F[1:]) + 1])
    tau = np.max(xdata) * 0.5
    return A, tau, 1 / (2.0 * freq * 1e-6), 0., B
