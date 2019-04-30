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
        self.current_curve_x_start = {}
        self.current_curve_point_count = {}
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
        self.getPlotItem().setClipToView(True)

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

        for curve_name in ["with_866_on", "diff_counts", "with_866_off"]:
            if not curve_name in raw_data.keys():
                continue

            data_to_plot = raw_data[curve_name]
            num_points = len(data_to_plot)

            if not curve_name in self.curves.keys():
                self.curves[curve_name] = []

            if not curve_name in self.current_curve_point_count.keys():
                self.current_curve_point_count[curve_name] = 0

            if not curve_name in self.current_curve_x_start.keys():
                self.current_curve_x_start[curve_name] = 0

            if num_points == self.current_curve_point_count[curve_name]:
                # nothing new to plot for this curve
                continue
            if num_points < self.current_curve_point_count[curve_name]:
                # if this dataset has fewer points than the current curve, the dataset
                # must have been restarted, so we will simply begin a new curve.
                # update the x_start value for the new curve
                self.current_curve_x_start[curve_name] += self.current_curve_point_count[curve_name]
            else:
                # we have more points, so the current curve needs to be updated.
                # remove the current curve so that we will recreate it.
                num_curves_now = len(self.curves[curve_name])
                if num_curves_now > 0:
                    latest_curve = self.curves[curve_name][-1]
                    self.removeItem(latest_curve)
                    self.curves[curve_name].pop(-1)
                    num_curves_now -= 1

            self.current_curve_point_count[curve_name] = num_points

            x_start = self.current_curve_x_start[curve_name]
            x_end = x_start + num_points
            x = np.arange(x_start, x_end)
            self.curves[curve_name].append(self.plot(
                x, data_to_plot,
                pen=self.pens[curve_name], fillLevel=0))

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