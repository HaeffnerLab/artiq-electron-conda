import numpy as np

name = "gaussian_sinequad"

Tex = r"0.25 A [1 + exp[- (x-x0) / \tau \cdot 10^{-6})^2/2] [-2 cos[2 (2\pi / 4T_{\pi}) \cdot (x-x0) + \phi] + cos[2 (2\pi / 4T_{\pi}) \cdot (x-x0) + \phi]^2] + B"

def fit_function(x, A=1, x0=0, tau=1, tpi=1, phi=0, B=0):
    return 0.5 * A * (1 - (2 * np.exp(-((x-x0)**2)/2/(tau*1e-6)**2) * np.cos(2*2 * np.pi * (1/(4*tpi)) * 1e6 * (x-x0) + phi)- np.exp(-((x-x0)**2)/(tau*1e-6)**2) * np.cos(2*2 * np.pi * (1/(4*tpi)) * 1e6 * (x-x0) + phi)**2)) + B

def guess_parameters(xdata, ydata):
    B = 0#np.min(ydata)
    A = 0.5#np.max(ydata) - B
    x = np.array(xdata)
    x0 = 0.
    y = np.array(ydata)
    f = np.fft.fftfreq(len(x), (x[1] - x[0]))  # This assumes uniform spacing
    F = abs(np.fft.fft(y))
    freq = abs(f[np.argmax(F[1:]) + 1])
    tau = np.max(xdata) * 0.5 * 1e6
    return A, x0, tau, 1 / (2.0 * freq * 1e-6), 0., B
