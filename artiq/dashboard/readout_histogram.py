import labrad
import asyncio
from PyQt5 import QtCore, QtGui, QtWidgets
from artiq import __artiq_dir__ as artiq_dir
from artiq.dashboard import (pmt_readout_dock,
                             camera_readout_dock)
from twisted.internet.defer import inlineCallbacks
from labrad.wrappers import connectAsync


parameterchangedID = 612512


class ReadoutHistogram(QtWidgets.QMainWindow):
    def __init__(self):
        QtWidgets.QMainWindow.__init__(self)
        qfm = QtGui.QFontMetrics(self.font())
        self.resize(140*qfm.averageCharWidth(), 38*qfm.lineSpacing())
        self.exit_request = asyncio.Event()
        try:
            self.cxn = labrad.connect()
        except Exception as e:
            print("Failed on readout_histogram connect: ", e)
            self.setDisabled(True)
        self.setup_background()
        self.add_docks(self.cxn)
        self.connect()

    def closeEvent(self, event):
        event.ignore()
        self.exit_request.set()

    def save_state(self):
        pass

    def restore_state(self):
        pass

    def setup_background(self):
        pass

    @inlineCallbacks
    def connect(self):
        try:
            self.acxn = yield connectAsync()
        except Exception as e:
            print("Failed on readout_histogram connect: ", e)
            self.setDisabled(True)
        yield self.setup_listeners()
        yield self.acxn.manager.subscribe_to_named_message("Server Connect", 
                                                           987111321, True)
        yield self.acxn.manager.subscribe_to_named_message("Server Disconnect", 
                                                           987111322, True)
        yield self.acxn.manager.addListener(listener=self.connectypoo, 
                                            source=None, ID=987111321)
        yield self.acxn.manager.addListener(listener=self.disconnectypoo, 
                                            source=None, ID=987111322)

    @inlineCallbacks
    def setup_listeners(self):
        try:
            del self.acxn
            self.acxn = yield connectAsync()
        except Exception as e:
            print("109323083: ", e)
        yield self.acxn.parametervault.signal__parameter_change(parameterchangedID)
        yield self.acxn.parametervault.addListener(listener=self.param_changed, 
                                                   source=None, ID=parameterchangedID)

    @inlineCallbacks
    def connectypoo(self, *args):
        if args[1][1] == "ParameterVault":
            self.setDisabled(False)
            yield self.setup_listeners()

    def disconnectypoo(self, *args):
        if args[1][1] == "ParameterVault":
            self.setDisabled(True)

    def add_docks(self, cxn):
        self.d_pmt = pmt_readout_dock.PMTReadoutDock(cxn)
        self.d_camera = camera_readout_dock.CameraReadoutDock(cxn)
        self.addDockWidget(QtCore.Qt.TopDockWidgetArea, self.d_pmt)
        self.addDockWidget(QtCore.Qt.TopDockWidgetArea, self.d_camera)
        self.tabifyDockWidget(self.d_pmt, self.d_camera)
        self.setTabPosition(QtCore.Qt.TopDockWidgetArea,
                            QtWidgets.QTabWidget.North)

    @inlineCallbacks
    def param_changed(self, *args):
        # Should prob do this in pmt_readout_dock code
        if "".join(args[1]) == "StateReadoutthreshold_list":
            d = self.d_pmt
            p = self.acxn.parametervault
            lines = yield p.get_parameter(["StateReadout", "threshold_list"])
            lines = lines[1]
            lines.sort()
            yield p.set_parameter(["StateReadout", "threshold_list", lines])
            d.number_lines = len(lines)
            for line in d.lines: 
                line.remove()
            d.lines = [d.ax.axvline(line, lw=3, color="r") for line in lines]
            d.n_thresholds.setValue(len(lines))
            d.curr_threshold.setMaximum(len(lines))
            d.canvas.draw()