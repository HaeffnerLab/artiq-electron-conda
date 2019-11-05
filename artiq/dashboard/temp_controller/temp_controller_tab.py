import logging
import asyncio
import labrad
from tc4820 import *
from datetime import datetime
from artiq.dashboard.parameter_editor import ParameterEditorDock
from PyQt5 import QtCore, QtGui, QtWidgets, Qt
from matplotlib.backends.backend_qt5agg import (NavigationToolbar2QT,
                                                FigureCanvasQTAgg)
import matplotlib.dates as mdates
from matplotlib.figure import Figure


logger = logging.getLogger(__name__)


class TempControllerTab(QtWidgets.QDockWidget):
    def __init__(self):
        QtWidgets.QDockWidget.__init__(self, "Temperature Controller")
        self.setObjectName("Temperature Controller")
        self.setFeatures(QtWidgets.QDockWidget.DockWidgetMovable |
                         QtWidgets.QDockWidget.DockWidgetFloatable)
        self.main_widget = QtWidgets.QWidget()
        self.setWidget(self.main_widget)
        try:
            self.device1 = device("/dev/ttyUSB0")
        except:
            self.device1 = None
        try:
            self.device2 = device("/dev/ttyUSB1")
        except:
            self.device2 = None
        try:
            self.cxn = labrad.connect()
        except:
            logger.warning("Temp controller failed to connect to labrad.", exc_info=True)
            self.setDisabled(True)
        self.make_GUI()
        self.readout_timer = QtCore.QTimer()
        self.readout_timer.timeout.connect(self.update_readout)
        self.readout_timer.start(1000)
        # Change to async at some point
        self.control_timer = QtCore.QTimer()
        self.control_timer.timeout.connect(self.update_control)
        self.control_timer.start(1000)

        self.time = []
        self.temp1 = []
        self.temp2 = []

    def make_GUI(self):
        layout = QtWidgets.QGridLayout()

        self.fig  = Figure()
        self.fig.patch.set_facecolor((.97, .96, .96))
        self.canvas = FigureCanvasQTAgg(self.fig)
        self.canvas.setParent(self)
        self.ax = self.fig.add_subplot(111)
        self.ax.xaxis_date()
        self.ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
        self.ax.set_facecolor((.97,.96,.96))
        self.ax.tick_params(top=False, bottom=False, left=False, right=False, 
                            labeltop=True, labelbottom=True, labelleft=True, labelright=True)
        self.mpl_toolbar = NavigationToolbar2QT(self.canvas, self)
        self.fig.tight_layout()
        self.canvas.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                                  QtWidgets.QSizePolicy.Expanding)
        self.ax.tick_params(axis="both", direction="in")

        self.fig2  = Figure()
        self.fig2.patch.set_facecolor((.97, .96, .96))
        self.canvas2 = FigureCanvasQTAgg(self.fig2)
        self.canvas2.setParent(self)
        self.ax2 = self.fig2.add_subplot(111)
        self.ax2.set_facecolor((.97,.96,.96))
        self.ax2.tick_params(top=False, bottom=False, left=False, right=False, 
                            labeltop=True, labelbottom=True, labelleft=True, labelright=True)
        self.mpl_toolbar2 = NavigationToolbar2QT(self.canvas, self)
        self.fig2.tight_layout()
        self.canvas2.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                                  QtWidgets.QSizePolicy.Expanding)
        self.ax2.tick_params(axis="both", direction="in")

        myFont = QtGui.QFont()
        myFont.setBold(True)
        label1 = QtWidgets.QLabel("Amplifier (TempControl1)")
        label1.setAlignment(Qt.Qt.AlignCenter)
        label1.setFont(myFont)
        layout.addWidget(label1, 1, 0, 1, 1)
        layout.addWidget(self.canvas, 2, 0, 5, 1)
        label2 = QtWidgets.QLabel("Resonator (TempControl2)")
        label2.setAlignment(Qt.Qt.AlignCenter)
        label2.setFont(myFont)
        layout.addWidget(label2, 7, 0, 1, 1)
        layout.addWidget(self.canvas2, 8, 0, 5, 1)
        layout.setColumnStretch(0, 3)

        try:
            cxn = labrad.connect()
            p = cxn.parametervault
        except:
            pass
        accessed_params = set()
        parameters = p.get_parameter_names("TempControl1")
        for parameter in parameters:
            accessed_params.update({"TempControl1." + parameter})
        parameters = p.get_parameter_names("TempControl2")
        for parameter in parameters:
            accessed_params.update({"TempControl2." + parameter})

        d_accessed_parameter_editor = ParameterEditorDock(
                acxn=None,
                name="Controller Options",
                accessed_params=accessed_params
            )
        d_accessed_parameter_editor.setFeatures(QtGui.QDockWidget.NoDockWidgetFeatures)
        d_accessed_parameter_editor.setTitleBarWidget(QtGui.QWidget())
        d_accessed_parameter_editor.table.setMaximumWidth(390)
        label3 = QtWidgets.QLabel("Output Power (Tempcontrol1)")
        label3.setFont(myFont)
        label3.setAlignment(Qt.Qt.AlignHCenter)
        layout.addWidget(label3, 1, 1)
        self.output1 = QtWidgets.QLCDNumber()
        self.output1.setSegmentStyle(2)
        self.output1.display(0)
        self.output1.setDigitCount(4)
        self.output1.setStyleSheet("background-color: lightGray;"
                                        "color: green;")
        layout.addWidget(self.output1, 2, 1)
        self.clear_button1 = QtWidgets.QPushButton("Clear Plot 1")
        self.clear_button1.clicked[bool].connect(self.clear_plot1)
        layout.addWidget(self.clear_button1, 3, 1)
        layout.addWidget(d_accessed_parameter_editor, 4, 1, 6, 1)
        label4 = QtWidgets.QLabel("Output Power (Tempcontrol2)")
        label4.setFont(myFont)
        label4.setAlignment(Qt.Qt.AlignHCenter)
        layout.addWidget(label4, 10, 1)
        self.output2 = QtWidgets.QLCDNumber()
        self.output2.setSegmentStyle(2)
        self.output2.display(0)
        self.output2.setDigitCount(4)
        self.output2.setStyleSheet("background-color: lightGray;"
                                        "color: green;")
        layout.addWidget(self.output2, 11, 1)
        self.clear_button2 = QtWidgets.QPushButton("Clear Plot 2")
        self.clear_button2.clicked[bool].connect(self.clear_plot2)
        layout.addWidget(self.clear_button2, 12, 1)
        layout.setColumnStretch(1, 1)
        self.main_widget.setLayout(layout)

    def update_readout(self):
        try:
            self.time.append(datetime.now())
        except:
            return
        if self.device1 is not None:
            self.temp1.append(self.device1.get_temp())
            self.ax.plot(self.time, self.temp1, color="C0")
            self.canvas.draw()
        if self.device2 is not None:
            self.temp2.append(self.device2.get_temp())
            self.ax2.plot(self.time, self.temp2, color="C0")
            self.canvas2.draw()

    def update_control(self):
        p = self.cxn.parametervault
        if self.device1 is not None:
            set_temp = float(p.get_parameter("TempControl1", "set_temp"))
            self.device1.set_set_temp(set_temp)
            try:
                self.set1.remove()
            except:
                pass
            self.set1 = self.ax.axhline(y=set_temp, color="C1", linestyle="--")
            self.device1.set_Pgain(float(p.get_parameter("TempControl1", "P_bandwidth")))
            self.device1.set_Igain(float(p.get_parameter("TempControl1", "I_gain")))
            self.device1.set_Dgain(float(p.get_parameter("TempControl1", "D_gain")))
            self.device1.set_alarm1_deadband(float(p.get_parameter("TempControl1", "alarm_deadband")))
            self.device1.set_alarm1_high(int(p.get_parameter("TempControl1", "alarm_high")))
            self.device1.set_alarm1_low(int(p.get_parameter("TempControl1", "alarm_low")))
            self.device1.set_analog_multiplier(float(p.get_parameter("TempControl1", "analog_multiplier")))
            self.device1.set_control_mode(p.get_parameter("TempControl1", "mode"))
            self.device1.set_offset(int(p.get_parameter("TempControl1", "offset")))
            self.device1.set_sensor_type(p.get_parameter("TempControl1", "sensor_type"))
            if p.get_parameter("TempControl1", "output"):
                output = "on"
            else:
                output = "off"
            self.device1.set_output_enable(output)
            if p.get_parameter("TempControl1", "alarm_latch"):
                alarm = "on"
                alarm_latch = 1
            else:
                alarm = "off"
                alarm_latch = 0
            self.device1.set_alarm_latch_function(alarm_latch)
            self.device1.set_alarm1(alarm)
            self.device1.set_alarm2("off")
            poutput = float(self.device1.get_power_output())
            if poutput >= 0 and poutput <= 1:
                self.output1.display(poutput * 100)
        if self.device2 is not None:
            set_temp = float(p.get_parameter("TempControl2", "set_temp"))
            self.device2.set_set_temp(set_temp)
            try:
                self.set2.remove()
            except:
                pass
            self.set2 = self.ax.axhline(y=set_temp, color="C1", linestyle="--")
            self.device2.set_Pgain(float(p.get_parameter("TempControl2", "P_bandwidth")))
            self.device2.set_Igain(float(p.get_parameter("TempControl2", "I_gain")))
            self.device2.set_Dgain(float(p.get_parameter("TempControl2", "D_gain")))
            self.device2.set_alarm1_deadband(float(p.get_parameter("TempControl2", "alarm_deadband")))
            self.device2.set_alarm1_high(int(p.get_parameter("TempControl2", "alarm_high")))
            self.device2.set_alarm1_low(int(p.get_parameter("TempControl2", "alarm_low")))
            self.device2.set_analog_multiplier(float(p.get_parameter("TempControl2", "analog_multiplier")))
            self.device2.set_control_mode(p.get_parameter("TempControl2", "mode"))
            self.device2.set_offset(int(p.get_parameter("TempControl2", "offset")))
            self.device2.set_sensor_type(p.get_parameter("TempControl2", "sensor_type"))
            if p.get_parameter("TempControl2", "output"):
                output = "on"
            else:
                output = "off"
            self.device2.set_output_enable(output)
            if p.get_parameter("TempControl2", "alarm_latch"):
                alarm = "on"
                alarm_latch = 1
            else:
                alarm = "off"
                alarm_latch = 0
            self.device2.set_alarm_latch_function(alarm_latch)
            self.device2.set_alarm1(alarm)
            self.device2.set_alarm2("off")
            poutput = float(self.device2.get_power_output())
            if poutput >= 0 and poutput <= 1:
                self.output2.display(poutput * 100)

    def clear_plot1(self):
        self.time = []
        self.temp1 = []
        self.ax.plot([], [])
        self.ax.axes.cla()
        self.canvas.draw()

    def clear_plot2(self):
        self.time = []
        self.temp2 = []
        self.ax2.plot([], [])
        self.ax2.axes.cla()
        self.canvas2.draw()