import numpy as np

name = "lorentzian"

Tex = r"\frac{A}{(x-x_0)^2 + \gamma^2/4}"

def fit_function(x, A=1, x0=0, gamma=1):
    return A * (gamma / 2) / ((x - x0)**2 + (gamma/2)**2)

def guess_parameters(xdata, ydata):
    A = np.max(ydata)
    x0 = xdata[np.argmax(ydata)]
    std = np.std(ydata)
    gamma = np.abs(xdata[np.argmin(ydata - std)] - x0)
    return A, x0, gamma
