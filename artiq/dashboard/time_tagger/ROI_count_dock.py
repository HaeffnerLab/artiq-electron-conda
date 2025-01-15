import labrad
import logging
import asyncio
import os
from artiq import __artiq_dir__ as artiq_dir
from PyQt5 import QtCore, QtGui, QtWidgets
from TimeTagger import createTimeTagger, Counter, \
                       Countrate, Histogram, LOW, \
                       HIGH, freeTimeTagger, scanTimeTagger, \
                       ConstantFractionDiscriminator
import numpy as np
import datetime
import tqdm
from time import sleep
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
import matplotlib.pyplot as plt

#import logging
#logger = logging.getLogger(__name__)

#laser_room_ip = "192.168.169.49"
#SIGNALID = 270835


class ROICountDock(QtWidgets.QDockWidget):
    def __init__(self, tagger):
        super().__init__()
        self.setup_layout()
        self.tagger = tagger
        self.continue_plotting = False
    
    
    def setup_layout(self):
        layout = QtWidgets.QVBoxLayout()
        self.fig = Figure()
        self.canvas = FigureCanvas(self.fig)
        self.canvas.setParent(self)
        self.axes = self.fig.add_subplot(111)
        self.mpl_toolbar = NavigationToolbar(self.canvas, self)
        #self.test_plot(self.axes)
        self.axes.set_title('ROI Count', fontsize = 22)
        self.axes.set_xlabel('Time (ms)')
        #self.axes.legend(loc = 'best')
        self.fig.tight_layout()
        layout.addWidget(self.mpl_toolbar)
        layout.addWidget(self.canvas)
        self.setLayout(layout)

    def start_plot(self):
        self.continue_plotting = True
        self.step = [0]
        self.x_so_far = []
        while self.continue_plotting:
            self.loop_plot()
            sleep(1e-3)
    
    def continue_plot(self):
        self.continue_plotting = True
        while self.continue_plotting:
            self.loop_plot()
            sleep(1e-3)

    def end_plot(self):
        self.continue_plotting = False
        
    def loop_plot(self):
        ax = self.axes
        x = np.random.random(1)
        self.x_so_far.append(x)
        ax.clear()
        self.test_plot()
        ax.legend(loc='upper right')
        interval = 100
        ax.set_xbound(max(max(self.step)-interval, 0), max(self.step))
        ax.set_title('ROI Count', fontsize = 22)
        ax.set_xlabel('Time (ms)')
        self.fig.canvas.draw_idle()
        self.fig.canvas.flush_events()
        self.step += [self.step[-1]+1]
    
    def test_plot(self):
        self.axes.plot(self.step, self.x_so_far, label='Test Data')

    