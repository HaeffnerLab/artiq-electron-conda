#!/usr/bin/env python3

import numpy as np
import PyQt5  # make sure pyqtgraph imports Qt5
from PyQt5 import QtCore
import pyqtgraph

from artiq.applets.simple import TitleApplet


class PMTPlot(pyqtgraph.PlotWidget):
    def __init__(self, args):
        pyqtgraph.PlotWidget.__init__(self)
        self.args = args
        self.showGrid(x=True, y=True, alpha=0.75)
        self.setYRange(0, 20)
        legend = self.addLegend()
        legend.addItem(pyqtgraph.PlotDataItem(pen=pyqtgraph.mkPen((255, 0, 0), width=2)), 
                       "   866 ON")
        legend.addItem(pyqtgraph.PlotDataItem(pen=pyqtgraph.mkPen((0, 0, 255), width=2)), 
                       "   866 OFF")
        legend.addItem(pyqtgraph.PlotDataItem(pen=pyqtgraph.mkPen((0, 255, 0), width=2)), 
                       " Diff")
        self.autoscroll = True
        self.scene().sigMouseClicked.connect(self.mouse_clicked)

    def data_changed(self, data, mods, title):
        try:
            with_866_on = data[self.args.with_866_on][1]
            with_866_off = data[self.args.with_866_off][1]
            diff_counts = data[self.args.diff_counts][1]
            pulsed = data[self.args.pulsed][1][0]
        except KeyError:
            return
        x1 = np.arange(len(with_866_on))
        x2 = np.arange(len(with_866_off))
        x3 = np.arange(len(diff_counts))
        if pulsed:
            self.clear()
            self.plot(x1, with_866_on, pen=pyqtgraph.mkPen((255, 0, 0), width=2))
            self.plot(x2, with_866_off, pen=pyqtgraph.mkPen((0, 0, 255), width=2))
            self.plot(x3, diff_counts, pen=pyqtgraph.mkPen((0, 255, 0), width=2))
        else:
            self.clear()
            self.plot(x1, with_866_on, pen=pyqtgraph.mkPen((255, 0, 0), width=2))
        if self.autoscroll:
            self.enableAutoRange("x", True)
            self.setAutoPan(x=True)
        else:
            self.enableAutoRange("x", False)
            self.setAutoPan(x=False)
        self.setTitle(title)

    def mouse_clicked(self, ev):
        print(ev)
        # if (ev.button() == QtCore.Qt.LeftButton and
        #     ev.double()):
        if ev.double():
            self.autoscroll = not self.autoscroll

def main():
    applet = TitleApplet(PMTPlot)
    applet.add_dataset("with_866_on", "", required=False)
    applet.add_dataset("with_866_off", "", required=False)
    applet.add_dataset("diff_counts", "", required=False)
    applet.add_dataset("pulsed", "", required=False)
    applet.run()

if __name__ == "__main__":
    main()