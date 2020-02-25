import numpy as np

name = "exponential_decay"

Tex = r"(A - B)\cdot exp[-t/T] + B"

def fit_function(x, A=1, T=1, B=1):
    return (A-B) * np.exp(-x/T) + B
