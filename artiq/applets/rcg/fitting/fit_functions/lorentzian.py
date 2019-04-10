import numpy as np

name = "Lorentzian"

Tex = r"\frac{A}{(x-x_0)^2 + \gamma^2/4}"

def fit_function(x, A=1, x0=0, gamma=1):
    return A / ((x - x0)**2 + (gamma/2)**2)
