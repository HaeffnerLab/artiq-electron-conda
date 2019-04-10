import numpy as np

name = "sine"

Tex = r"A\cdot sin(\frac{2\pi}{T}\cdot x+\phi) + B"

def fit_function(x, A=1, T=5, phi=0, B=0):
    return A * np.sin(2 * np.pi / T * x + phi) + B
