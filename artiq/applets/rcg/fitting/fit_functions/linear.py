import numpy as np
name = "linear"

Tex = "m\cdot x+b"

def fit_function(x, m=0, b=0):
    return  m * x + b

def guess_parameters(xdata, ydata):
    xdiffs = []
    ydiffs = []
    for i in range(len(xdata)):
        try:
            xdiffs.append(xdata[i + 1] - xdata[i])
            ydiffs.append(ydata[i + 1] - ydata[i])
        except:
            continue
    x_mean = np.mean(xdiffs)
    y_mean = np.mean(ydiffs)
    m = y_mean / x_mean
    b = ydata[0] - m * xdata[0]
    return m, b
