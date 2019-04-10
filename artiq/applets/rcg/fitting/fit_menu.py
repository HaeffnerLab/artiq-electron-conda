import inspect
import numpy as np
from PyQt5 import QtWidgets, QtGui, QtCore
import matplotlib as mpl
from matplotlib.backends.backend_agg import FigureCanvasAgg
from artiq.applets.rcg.fitting.fit_functions import *
from artiq.applets.rcg.fitting.fit_functions import __all__ as fit_functions
from functools import partial
from artiq.applets.rcg.tree_item import treeItem


class fitMenu(QtWidgets.QWidget):
    def __init__(self, name, title, data, graph):
        QtWidgets.QWidget.__init__(self)
        self.x, self.y = data; self.graph = graph
        for f in fit_functions:
            fit_function = globals()[f]
            try:
                ffname = fit_function.name
                self.model = fit_function.fit_function
            except AttributeError:
                continue
            if ffname == name:
                self.fit_function = fit_function.fit_function
                self.Tex = fit_function.Tex
                argspec = inspect.getfullargspec(self.model)
                args = argspec.args[1:]
                p0 = argspec.defaults
                break
        else:
            return
        self.plot_item = None
        self.color = next(self.graph.color_chooser)
        self.xrange = np.linspace(self.x[0], self.x[-1], 10000)
        self.p0 = []
        self.title = "FIT:  {}".format(title)
        self.setWindowTitle(self.title)

        layout = QtWidgets.QVBoxLayout()
        self.tw = QtWidgets.QTreeWidget()
        self.tw.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.tw.setIndentation(0)
        self.tw.setHeaderLabels(["", "Parameter", "Guess", "Fit Value"])
        self.tw.setColumnWidth(0, 25)
        self.tw.setAlternatingRowColors(True)
        
        for i, arg in enumerate(args):
            child = QtWidgets.QTreeWidgetItem(["", arg, "", ""])
            child.setTextAlignment(1, QtCore.Qt.AlignHCenter)
            self.tw.addTopLevelItem(child)
            checkbox = QtWidgets.QCheckBox()
            checkbox.setCheckState(2)
            self.tw.setItemWidget(child, 0, checkbox)
            guess = QtWidgets.QDoubleSpinBox()
            guess.setMaximum(1e10)
            guess.setMinimum(-1e10)
            if p0 is not None:
                val = p0[i] if p0[i] is not None else 0
            else:
                val = 0
            guess.setValue(val)
            self.p0.append(val)
            if val != 0:
                guess.setSingleStep(abs(val) / 100)
            guess.setAlignment(QtCore.Qt.AlignHCenter)
            self.tw.setItemWidget(child, 2, guess)
            lineedit = QtWidgets.QLineEdit()
            lineedit.setEnabled(False)
            self.tw.setItemWidget(child, 4, lineedit)
            guess.valueChanged.connect(self.on_spinbox_changed)

        model_label = QtWidgets.QLabel("")
        model_label.setAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignVCenter)
        try:
            Tex = self.mathTex_to_QPixmap(r"${}$".format(self.Tex), 15)
            model_label.setPixmap(Tex)
        except:
            pass
        
        manual_button = QtWidgets.QPushButton("Manual")
        manual_button.released.connect(self.on_manual_button_released)
        manual_button.setCheckable(False)
        fit_button = QtWidgets.QPushButton("Fit")
        fit_button.released.connect(self.on_fit_button_released)
        fit_button.setCheckable(False)
        sublayout = QtWidgets.QHBoxLayout()
        sublayout.addWidget(manual_button)
        sublayout.addWidget(fit_button)
        
        layout.addWidget(model_label)
        layout.addWidget(self.tw)
        layout.addLayout(sublayout)
        self.setLayout(layout)
        self.setMinimumWidth(500)

    def on_spinbox_changed(self):
        sender = self.sender()
        step = sender.value() / 100
        if step < .001: 
        sender.setSingleStep(sender.value() / 100)
        self.on_manual_button_released()

    def on_manual_button_released(self):
        self.p0 = [self.tw.itemWidget(self.tw.topLevelItem(i), 2).value() 
                                    for i in range(self.tw.topLevelItemCount())]
        try:
            y = self.fit_function(self.xrange, *self.p0)
        except:
            print("oops")
            return
        if self.plot_item is not None:
            self.graph.remove_curve(curve=self.plot_item)
            del self.plot_item
        
        self.plot_item = treeItem(self.graph, self.title, self.xrange, y, self.graph.pg, self.color, False)
        self.graph.tw.addTopLevelItem(self.plot_item)

    def on_fit_button_released(self):
        pass

    def mathTex_to_QPixmap(self, mathTex, fs):
        #https://stackoverflow.com/questions/32035251/displaying-latex-in-pyqt-pyside-qtablewidget
        #---- set up a mpl figure instance ----
        fig = mpl.figure.Figure()
        fig.patch.set_facecolor('none')
        fig.set_canvas(FigureCanvasAgg(fig))
        renderer = fig.canvas.get_renderer()

        #---- plot the mathTex expression ----
        ax = fig.add_axes([0, 0, 1, 1])
        ax.axis('off')
        ax.patch.set_facecolor('none')
        t = ax.text(0, 0, mathTex, ha='left', va='bottom', fontsize=fs)

        #---- fit figure size to text artist ----
        fwidth, fheight = fig.get_size_inches()
        fig_bbox = fig.get_window_extent(renderer)
        text_bbox = t.get_window_extent(renderer)

        tight_fwidth = text_bbox.width * fwidth / fig_bbox.width
        tight_fheight = text_bbox.height * fheight / fig_bbox.height

        fig.set_size_inches(tight_fwidth, tight_fheight)

        #---- convert mpl figure to QPixmap ----
        buf, size = fig.canvas.print_to_buffer()
        qimage = QtGui.QImage.rgbSwapped(QtGui.QImage(buf, size[0], size[1],
                                                    QtGui.QImage.Format_ARGB32))
        qpixmap = QtGui.QPixmap(qimage)

        return qpixmap