#!/usr/bin/env python3

import numpy as np
import PyQt5  # make sure pyqtgraph imports Qt5
import pyqtgraph
from PyQt5 import QtCore

from artiq.applets.simple import TitleApplet


class PMTPlot(pyqtgraph.PlotWidget):
    def __init__(self, args):
        pyqtgraph.PlotWidget.__init__(self)
        self.args = args
        self.showGrid(x=True, y=True, alpha=0.75)
        self.setYRange(0, 1000)
        legend = self.addLegend()
        legend.addItem(pyqtgraph.PlotDataItem(pen=pyqtgraph.mkPen((255, 0, 0), width=2)), 
                       "   866 ON")
        legend.addItem(pyqtgraph.PlotDataItem(pen=pyqtgraph.mkPen((0, 0, 255), width=2)), 
                       "   866 OFF")
        legend.addItem(pyqtgraph.PlotDataItem(pen=pyqtgraph.mkPen((0, 255, 0), width=2)), 
                       " Diff")
        self.autoscroll = True
        self.setLimits(yMin=0, xMin=0)
        self.disableAutoRange()
        self.curves = []
        self.scene().sigMouseClicked.connect(self.mouse_clicked)

    def data_changed(self, data, mods, title):
        try:
            with_866_on = data[self.args.with_866_on][1][1:]
            with_866_off = data[self.args.with_866_off][1][1:]
            diff_counts = data[self.args.diff_counts][1][1:]
            pulsed = data[self.args.pulsed][1][0]
        except KeyError:
            return
        x1 = np.arange(len(with_866_on))
        x2 = np.arange(len(with_866_off))
        x3 = np.arange(len(diff_counts))
        self.clear()
        if pulsed:
            self.curves.append(self.plot(x1, with_866_on, 
                  pen=pyqtgraph.mkPen((255, 0, 0), width=2), 
                  brush=pyqtgraph.mkBrush((255,0,0,100)), fillLevel=0))
            self.curves.append(self.plot(x2, with_866_off, 
                  pen=pyqtgraph.mkPen((0, 0, 255), width=2),
                  brush=pyqtgraph.mkBrush((0,0,255,100)), fillLevel=0))
            self.curves.append(self.plot(x3, diff_counts, 
                  pen=pyqtgraph.mkPen((0, 255, 0), width=2),
                  brush=pyqtgraph.mkBrush((0,255,0,100)), fillLevel=0))
        else:
            self.curves.append(self.plot(x1, with_866_on, 
                  pen=pyqtgraph.mkPen((255, 0, 0), width=2), fillLevel=0, brush=pyqtgraph.mkBrush((255,0,0,100))))
        if self.autoscroll:
            try:
                (xmin_cur, xmax_cur), (ymin_cur, ymax_cur) = self.viewRange()
                max_x = 0
                for curve in self.curves:
                    localxmax = curve.dataBounds(0)[-1]
                    if localxmax > max_x:
                        max_x = localxmax
                window_width = xmax_cur - xmin_cur
                if max_x > xmin_cur + window_width:
                    shift = (xmax_cur - xmin_cur) / 2
                    xmin = xmin_cur + shift
                    xmax = xmax_cur + shift
                    limits = [xmin, xmax]
                    self.setXRange(*limits)
            except TypeError:
                pass
            finally:
                self.setTitle(title)
        
    def mouse_clicked(self, ev):
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