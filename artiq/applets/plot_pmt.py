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
        self.curves = {}
        self.showGrid(x=True, y=True, alpha=0.75)
        self.setYRange(0, 1000)

        self.pens = {"with_866_on":  pyqtgraph.mkPen((255, 0, 0), width=2),
                     "with_866_off": pyqtgraph.mkPen((0, 0, 255), width=2),
                     "diff_counts":  pyqtgraph.mkPen((0, 255, 0), width=2)}

        legend = self.addLegend()
        legend.addItem(pyqtgraph.PlotDataItem(pen=self.pens["with_866_on"]),  "   866 ON")
        legend.addItem(pyqtgraph.PlotDataItem(pen=self.pens["with_866_off"]), "   866 OFF")
        legend.addItem(pyqtgraph.PlotDataItem(pen=self.pens["diff_counts"]),  " Diff")

        self.autoscroll = True
        self.setLimits(yMin=0, xMin=0)
        self.disableAutoRange()
        self.scene().sigMouseClicked.connect(self.mouse_clicked)

    def data_changed(self, data, mods, title):
        self.disableAutoRange()
        raw_data = {}
        try:
            raw_data["with_866_on"] = data[self.args.with_866_on][1][1:]
            raw_data["with_866_off"] = data[self.args.with_866_off][1][1:]
            raw_data["diff_counts"] = data[self.args.diff_counts][1][1:]
            pulsed = data[self.args.pulsed][1][0]
        except KeyError:
            return

        pens = self.pens
        brushes = {"with_866_on":  pyqtgraph.mkBrush((255,0,0,75)) if pulsed else pyqtgraph.mkBrush((255,0,0,100)),
                   "with_866_off": pyqtgraph.mkBrush((0,0,255,75)),
                   "diff_counts":  pyqtgraph.mkBrush((0,255,0,75))}

        data_points_per_curve = 1000

        # we want to plot specifically in this order: with_866_on, diff_counts, with_866_off
        # so that the brushes look nice visually
        for curve_name in ["with_866_on", "diff_counts", "with_866_off"]:
            if not curve_name in raw_data.keys():
                continue

            data_to_plot = raw_data[curve_name]            
            num_points = len(data_to_plot)
            if num_points == 0:
                continue

            x = np.arange(num_points)
            num_curves_needed = (num_points // data_points_per_curve) + 1

            if not curve_name in self.curves.keys():
                self.curves[curve_name] = []

            num_curves_now = len(self.curves[curve_name])
            if num_curves_needed < num_curves_now:
                # if we have more curves than necessary, we must have restarted the dataset,
                # so remove all curves and start over
                for curve in self.curves[curve_name]:
                    self.removeItem(curve)
                self.curves[curve_name] = []
                num_curves_now = 0
            else:
                # otherwise, let's remove the latest one (in case it needs to be updated)
                if num_curves_now > 0:
                    latest_curve = self.curves[curve_name][-1]
                    self.removeItem(latest_curve)
                    self.curves[curve_name].pop(-1)
                    num_curves_now -= 1

            # now let's plot all the curves that haven't already been plotted
            for curve_index in range(num_curves_now, num_curves_needed):
                x_start = curve_index * data_points_per_curve
                x_end = min(num_points, x_start + data_points_per_curve + 1)
                self.curves[curve_name].append(self.plot(
                    x[x_start:x_end], data_to_plot[x_start:x_end],
                    pen=pens[curve_name], brush=brushes[curve_name], fillLevel=0))

        if self.autoscroll:
            (xmin_cur, xmax_cur), _ = self.viewRange()
            max_x = 0
            for curve_name in self.curves.keys():
                for curve in self.curves[curve_name]:
                    localxmax = curve.dataBounds(0)[-1]
                    try:
                        if localxmax > max_x:
                            max_x = localxmax
                    except TypeError:
                        continue
            window_width = xmax_cur - xmin_cur
            if max_x > xmin_cur + window_width:
                shift = (xmax_cur - xmin_cur) / 2
                xmin = xmin_cur + shift
                xmax = xmax_cur + shift
                limits = [xmin, xmax]
                self.setXRange(*limits)
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