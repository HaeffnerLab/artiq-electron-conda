name = "linear"

Tex = "m\cdot x+b"

def fit_function(x, m=0, b=0):
    return  m * x + b

def guess_parameters(xdata, ydata):
    diffs = []
    for i in range(len(xdata)):
        try:
            diffs.append(xdata[i + 1] - xdata[i])
        except:
            continue
    m = np.mean(diffs)
    b = ydata[0] = m * xdata[0]
    return m, b
