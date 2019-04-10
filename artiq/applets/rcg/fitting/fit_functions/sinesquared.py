import numpy as np

name = "sine^2"

Tex = r"A sin^2(\frac{2\pi}{T}\cdot x + \phi) + B"

def fit_function(x, A=1, T=5, phi=0, B=0):
    return A * np.sin(2 * np.pi / T * x + phi)**2 + B
