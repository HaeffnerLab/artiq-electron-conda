import numpy as np

name = "Gaussian"

Tex = r"A\cdot exp[-(x-x_0)^2/2\sigma^2]"

def fit_function(x, A=.5, x0=0, sigma=1):
    return A * np.exp(-(x - x0)**2 / (2 * sigma**2))
