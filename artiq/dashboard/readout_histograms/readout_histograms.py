import labrad
import asyncio
from PyQt5 import QtCore, QtGui, QtWidgets
from artiq import __artiq_dir__ as artiq_dir
from artiq.dashboard.readout_histograms import (pmt_readout_dock,
                                                camera_readout_dock)
from twisted.internet.defer import inlineCallbacks
from labrad.wrappers import connectAsync


parameterchangedID = 612512


class ReadoutHistograms(QtWidgets.QMainWindow):
    def __init__(self, acxn=None, smgr=None):
        self.acxn = acxn
        self.smgr = smgr
        QtWidgets.QMainWindow.__init__(self)
        qfm = QtGui.QFontMetrics(self.font())
        self.resize(140*qfm.averageCharWidth(), 38*qfm.lineSpacing())
        self.exit_request = asyncio.Event()
        self.add_docks(self.acxn)
        self.setup_listeners()

    def closeEvent(self, event):
        event.ignore()
        self.exit_request.set()

    def save_state(self):
        return {
            "state": bytes(self.saveState()),
            "geometry": bytes(self.saveGeometry())
        }

    def restore_state(self, state):
        self.restoreGeometry(QtCore.QByteArray(state["geometry"]))
        self.restoreState(QtCore.QByteArray(state["state"]))

    @inlineCallbacks
    def setup_listeners(self):
        context = yield self.acxn.context()
        p = yield self.acxn.get_server("ParameterVault")
        yield p.signal__parameter_change(parameterchangedID, context=context)
        yield p.addListener(listener=self.param_changed, source=None, 
                            ID=parameterchangedID, context=context)

    def add_docks(self, cxn):
        self.d_pmt = pmt_readout_dock.PMTReadoutDock(cxn)
        self.d_camera = camera_readout_dock.CameraReadoutDock(cxn)
        self.smgr.register(self.d_camera)
        self.addDockWidget(QtCore.Qt.TopDockWidgetArea, self.d_pmt)
        self.addDockWidget(QtCore.Qt.TopDockWidgetArea, self.d_camera)
        self.tabifyDockWidget(self.d_pmt, self.d_camera)
        self.setTabPosition(QtCore.Qt.TopDockWidgetArea,
                            QtWidgets.QTabWidget.North)
        self.d_pmt.show()
        self.d_pmt.raise_()

    @inlineCallbacks
    def param_changed(self, *args):
        # Should maybe do this in pmt_readout_dock code
        if "".join(args[1]) == "StateReadoutthreshold_list":
            d = self.d_pmt
            p = yield self.acxn.get_server("ParameterVault")
            lines = yield p.get_parameter(["StateReadout", "threshold_list"])
            slines = sorted(lines)
            if not list(slines) == list(lines):
                yield p.set_parameter(["StateReadout", "threshold_list", lines])
            d.number_lines = len(lines)
            for line in d.lines: 
                line.remove()
            d.lines = [d.ax.axvline(line, lw=3, color="r") for line in lines]
            d.n_thresholds.setValue(len(lines))
            d.curr_threshold.setMaximum(len(lines))
            d.canvas.draw()