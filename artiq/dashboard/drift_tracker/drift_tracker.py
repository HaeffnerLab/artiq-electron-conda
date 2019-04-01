import labrad
import logging
import csv
from datetime import datetime
from labrad.wrappers import connectAsync
from labrad.units import WithUnit as U
import os
import asyncio
import time
import numpy as np
from PyQt5 import QtCore, QtGui, QtWidgets
from artiq import __artiq_dir__ as artiq_dir
from artiq.dashboard.drift_tracker.linecenter_tracker import LinecenterTracker
from artiq.dashboard.drift_tracker.spectrum import Spectrum
import artiq.dashboard.drift_tracker.drift_tracker_config as c
import artiq.dashboard.drift_tracker.client_config as cl
from artiq.dashboard.drift_tracker.drift_tracker_control_widget import DriftTrackerControl
from twisted.internet.defer import inlineCallbacks


global_address = "192.168.169.49"
password = "lab"
colors = c.default_color_cycle[0 : len(cl.client_list)]
logger = logging.getLogger(__name__)


class DriftTracker(QtWidgets.QMainWindow):
    signalpoo = QtCore.pyqtSignal([list])
    def __init__(self, acxn):
        QtWidgets.QMainWindow.__init__(self)
        self.acxn = acxn
        qfm = QtGui.QFontMetrics(self.font())
        self.resize(140 * qfm.averageCharWidth(), 38 * qfm.lineSpacing())
        self.exit_request = asyncio.Event()
        self.setObjectName("DriftTracker")
        self.clipboard = None
        self.signalpoo.connect(self.update_spectrum)
        self.signalpoo.connect(self.update_listing)
        self.setup_background()
        self.add_docks()
        now = datetime.now()
        self.path = (os.path.expanduser("~") + 
                     "/data/drift_tracker/" + now.strftime("%Y"))
        os.makedirs(self.path, exist_ok=True)
        self.subscribed = False
        try:
            self.connect()
            self.connect_dt_control_widget()
            self.initialize_layout()
            self.update_show = QtCore.QTimer()
            self.update_show.timeout.connect(self.readout_update)
            self.update_show.start(c.show_rate * 1e3)
        except:
            logger.error("failed in initialization", exc_info=True)
            self.setDisabled(True) 
        
    def closeEvent(self, event):
        event.ignore()
        self.exit_request.set()

    def save_state(self):
        lcc = self.d_control
        return {"state": bytes(self.saveState()),
                "geometry": bytes(self.saveGeometry()),
                "remove_line_center": lcc.remove_line_center_count.value(), 
                "remove_b": lcc.remove_B_count.value(),
                "b_input": lcc.Bfield_entry.value(),
                "lc_input": lcc.linecenter_entry.value(),
                "carrier1": lcc.entry_table.cellWidget(0, 1).value(),
                "carrier2": lcc.entry_table.cellWidget(1, 1).value(),
                "globlist": {client: lcc.client_checkbox[client].isChecked() 
                            for client in cl.client_list},
                "durationglob": lcc.track_global_line_center_duration.value(),
                "durationloc": lcc.track_line_center_duration.value(),
                "tracking_duration_b": lcc.track_B_duration.value(),
                "current_tab": lcc.tabs.currentIndex()}

    def restore_state(self, state):
        lcc = self.d_control
        self.restoreGeometry(QtCore.QByteArray(state["geometry"]))
        self.restoreState(QtCore.QByteArray(state["state"]))
        lcc.remove_B_count.setValue(int(state["remove_b"]))
        lcc.remove_line_center_count.setValue(int(state["remove_line_center"]))
        lcc.Bfield_entry.setValue(float(state["b_input"]))
        lcc.linecenter_entry.setValue(float(state["lc_input"]))
        lcc.entry_table.cellWidget(0, 1).setValue(float(state["carrier1"]))
        lcc.entry_table.cellWidget(1, 1).setValue(float(state["carrier2"]))
        for client in cl.client_list:
            try:
                # maybe config has changed
                lcc.client_checkbox[client].setChecked(state["globlist"][client])
            except:
                pass
        lcc.track_global_line_center_duration.setValue(int(state["durationglob"]))
        lcc.track_line_center_duration.setValue(int(state["durationloc"]))
        lcc.track_B_duration.setValue(int(state["tracking_duration_b"]))
        lcc.tabs.setCurrentIndex(int(state["current_tab"]))      

    def setup_background(self):
        pass
        # mdi_area = MdiArea()
        # mdi_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        # mdi_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        # mdi_area.setMinimumSize(0, 0)  # doesn't work
        # self.setCentralWidget(mdi_area)
    
    def add_docks(self):
        self.d_linecentertracker = LinecenterTracker()
        self.addDockWidget(QtCore.Qt.TopDockWidgetArea, 
                           self.d_linecentertracker)
        self.d_spectrum = Spectrum()
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea,
                           self.d_spectrum)
        self.d_control = DriftTrackerControl()
        self.addDockWidget(QtCore.Qt.LeftDockWidgetArea,
                           self.d_control)

    def initialize_layout(self):
        lcc = self.d_control
        global global_address
        global password
        with (labrad.connection(global_address, 
                                password=password,
                                tls_mode="off")) as cxn:
            try:
                server = cxn.sd_tracker_global
            except:
                logger.error("SD tracker not initially connected")
                self.setDisabled(True)
                return
            transitions = server.get_transition_names()
            lcc.entry_table.fill_out(transitions)
            duration_B, duration_line_center = server.history_duration_local(cl.client_name)
            lcc.track_B_duration.blockSignals(True)
            lcc.track_line_center_duration.blockSignals(True)
            lcc.track_B_duration.setValue(duration_B["min"])
            lcc.track_line_center_duration.setValue(duration_line_center["min"])
            lcc.track_B_duration.blockSignals(False)
            lcc.track_line_center_duration.blockSignals(False)
            duration_line_center_global = server.history_duration_global_line_center(cl.client_name)
            lcc.track_global_line_center_duration.blockSignals(True)
            lcc.track_global_line_center_duration.setValue(duration_line_center_global["min"])
            lcc.track_global_line_center_duration.blockSignals(False)
            bool_keep_last_point = server.bool_keep_last_point(cl.client_name)
            lcc.bool_keep_last_button.set_value_no_signal(bool_keep_last_point)
            global_or_local = server.bool_global(cl.client_name)
            global_fit_list = server.get_global_fit_list(cl.client_name)
            lcc.global_checkbox.set_value_no_signal(self.global_or_local)
            lcc.global_checkbox.setChecked(False)
            if global_or_local:
                lcc.track_global_line_center_duration.blockSignals(True)
                lcc.track_global_line_center_duration.setEnabled(True)
                lcc.track_global_line_center_duration.blockSignals(False)
                for name in global_fit_list:
                    lcc.client_checkbox[name].blockSignals(True)
                    lcc.client_checkbox[name].setChecked(True)
                    lcc.client_checkbox[name].blockSignals(False)
            else:
                lcc.track_global_line_center_duration.blockSignals(True)
                lcc.track_global_line_center_duration.setEnabled(False)
                lcc.track_global_line_center_duration.blockSignals(False)
                for client in cl.client_list:
                    if client == cl.client_name:
                        lcc.client_checkbox[client].blockSignals(True)
                        lcc.client_checkbox[client].setChecked(True)
                        lcc.client_checkbox[client].setEnabled(False)
                        lcc.client_checkbox[client].blockSignals(False)
                    else:
                        lcc.client_checkbox[client].blockSignals(True)
                        lcc.client_checkbox[client].setEnabled(False)
                        lcc.client_checkbox[client].setChecked(False)
                        lcc.client_checkbox[client].blockSignals(False)
            self.on_new_fit(None, None)
    
    def connect_dt_control_widget(self):
        # Should probably just do all of this sort of stuff inside of the 
        # individual dock's code.
        lcc = self.d_control
        lcc.remove_B_button.clicked.connect(self.on_remove_B)
        lcc.remove_line_center_button.clicked.connect(self.on_remove_line_center)
        lcc.remove_all_B_and_lines_button.clicked.connect(self.on_remove_all_B_and_line_centers)
        lcc.entry_button.clicked.connect(self.on_entry)
        lcc.entry_line1_button.clicked.connect(self.on_entry_line1)
        lcc.entry_line2_button.clicked.connect(self.on_entry_line2)
        lcc.entry_Bfield_and_center_button.clicked.connect(self.on_entry_Bfield_and_center)
        lcc.entry_Bfield_button.clicked.connect(self.on_entry_Bfield)
        lcc.entry_center_button.clicked.connect(self.on_entry_center)
        lcc.track_B_duration.valueChanged.connect(self.on_new_B_track_duration)
        lcc.track_line_center_duration.valueChanged.connect(self.on_new_line_center_track_duration)
        lcc.track_global_line_center_duration.valueChanged.connect(self.on_new_global_line_center_track_duration)
        lcc.copy_clipboard_button.pressed.connect(self.do_copy_info_to_clipboard)
        lcc.global_checkbox.toggled.connect(self.global_or_local)
        for client in cl.client_list:
            lcc.client_checkbox[client].stateChanged.connect(self.on_new_fit_global)
        lcc.bool_keep_last_button.toggled.connect(self.bool_keep_last_point)

    @inlineCallbacks
    def on_remove_B(self, x):
        server = yield self.acxn.get_server("SD Tracker Global")
        to_remove = self.d_control.remove_B_count.value()
        yield server.remove_b_measurement(to_remove, cl.client_name)

    @inlineCallbacks
    def on_remove_line_center(self, *params):
        server = yield self.acxn.get_server("SD Tracker Global")
        to_remove = self.d_control.remove_line_center_count.value()
        try:
            yield server.remove_line_center_measurement(to_remove, cl.client_name)
        except:
            logger.warning("Issue removing line center point: ", exc_info=True)

    @inlineCallbacks
    def on_remove_all_B_and_line_centers(self, *params):
        server = yield self.acxn.get_server("SD Tracker Global")
        yield server.remove_all_measurements(cl.client_name)

    @inlineCallbacks
    def on_entry(self, *params):
        server = yield self.acxn.get_server("SD Tracker Global")
        info = self.d_control.entry_table.get_info()
        with_units = [(name, U(val, "MHz")) for name, val in info]
        try:
            yield server.set_measurements(with_units, cl.client_name)
            b_field = yield server.get_last_b_field_local(cl.client_name)
            line_center = yield server.get_last_line_center_local(cl.client_name)
            self.d_control.Bfield_entry.setValue(b_field * 1e3)
            self.d_control.linecenter_entry.setValue(line_center * 1e3)
        except:
            logger.warning("Issue entering lines: ", exc_info=True)

    @inlineCallbacks
    def on_entry_line1(self, *params):
        server = yield self.acxn.get_server("SD Tracker Global")
        info = self.d_control.entry_table.get_info()
        with_units = [(name, U(val, "MHz")) for name, val in info]
        with_units = [with_units[0]]
        try:
            yield server.set_measurements_with_one_line(with_units, cl.client_name)
        except:
            logger.warning("Issue entering line 1: ", exc_info=True)

    @inlineCallbacks
    def on_entry_line2(self, *params):
        server = yield self.acxn.get_server("SD Tracker Global")
        info = self.d_control.entry_table.get_info()
        with_units = [(name, U(val, "MHz")) for name, val in info]
        with_units = [with_units[1]]
        try:
            yield server.set_measurements_with_one_line(with_units, cl.client_name)
        except:
            logger.warning("Issue entering line 2: ", exc_info=True)
    
    @inlineCallbacks
    def on_entry_Bfield_and_center(self, *params):
        lcc = self.d_control
        server = yield self.acxn.get_server("SD Tracker Global")
        B_with_units = U(lcc.Bfield_entry.value() / 1e3, "gauss")
        f_with_units = U(lcc.linecenter_entry.value() / 1e3, "MHz")
        hlp1 = [("Bfield", B_with_units)]
        hlp2 = [("line_center", f_with_units)] # workaround, needs fixing
        try:
            yield server.set_measurements_with_bfield_and_line_center(hlp1, hlp2, 
                                                                      cl.client_name)
            # get the currently chosen lines
            hlp = yield server.get_lines_from_bfield_and_center(B_with_units, f_with_units)
            hlp = dict(hlp)
            # e.g. [('S-1/2D-3/2', -14.3), ('S-1/2D-5/2', -19.3)]
            line_info = lcc.entry_table.get_info()
            for k in range(len(line_info)):
                # get the current line from the server
                new_freq = hlp[line_info[k][0]]
                lcc.entry_table.cellWidget(k, 1).setValue(new_freq[new_freq.units])                
        except:
            logger.warning("Issue entering linecenter and bfield: ", exc_info=True)

    @inlineCallbacks
    def on_entry_Bfield(self, *params):
        server = yield self.acxn.get_server("SD Tracker Global")
        B_with_units = U(self.d_control.Bfield_entry.value() / 1e3, "gauss")
        hlp1 = [("Bfield", B_with_units)]
        try:
            yield server.set_measurements_with_bfield(hlp1, cl.client_name)
        except:
            logger.warning("Issue entering bfield: ", exc_info=True)

    @inlineCallbacks
    def on_entry_center(self, *params):
        server = yield self.acxn.get_server("SD Tracker Global")
        f_with_units = U(self.d_control.linecenter_entry.value() / 1e3, "MHz")
        hlp2 = [("line_center", f_with_units)]
        try:
            yield server.set_measurements_with_line_center(hlp2, cl.client_name)
        except:
            logger.warning("Issue entering linecenter: ", exc_info=True)

    @inlineCallbacks
    def on_new_B_track_duration(self, value):
        server = yield self.acxn.get_server("SD Tracker Global")
        rate_B = U(value, "min")
        rate_line_center = U(self.d_control.track_line_center_duration.value(), "min")
        yield server.history_duration_local(cl.client_name, (rate_B, rate_line_center))
    
    @inlineCallbacks
    def on_new_line_center_track_duration(self, value):
        server = yield self.acxn.get_server("SD Tracker Global")
        rate_line_center = U(value, "min")
        rate_B = U(self.d_control.track_B_duration.value(), "min")
        yield server.history_duration_local(cl.client_name, (rate_B, rate_line_center))

    @inlineCallbacks
    def on_new_global_line_center_track_duration(self, value):
        server = yield self.acxn.get_server("SD Tracker Global")
        rate_global_line_center = U(value, "min")
        yield server.history_duration_global_line_center(cl.client_name, 
                                                         rate_global_line_center)

    @inlineCallbacks
    def do_copy_info_to_clipboard(self):
        try:
            server = yield self.acxn.get_server("SD Tracker Global")
            lines = yield server.get_current_lines(cl.client_name)
            b_history, center_history = yield server.get_fit_history(cl.client_name)
            b_value =  b_history[-1][1]
            center_value = center_history[-1][1]
        except:
            logger.warning("Issue copyin to clipboard: ", exc_info=True)
            yield print("Issue copyin to clipboard")
        else:
            date = time.strftime("%m/%d/%Y")
            d = dict(lines)
            text = (
            "| {0} || {1:.4f} MHz || {2:.4f} MHz || {3:.4f} MHz ||" 
              "{4:.4f} MHz || {5:.4f} G || comment").format(date, d["S+1/2D-3/2"]["MHz"], 
                                                                  d["S-1/2D-5/2"]["MHz"], 
                                                                  d["S-1/2D-1/2"]["MHz"], 
                                                                  center_value["MHz"], 
                                                                  b_value["gauss"])
            if self.clipboard is not None:
                self.clipboard.setText(text)

    @inlineCallbacks
    def global_or_local(self, toggled):
        server = yield self.acxn.get_server("SD Tracker Global")
        lcc = self.d_control
        if bool(toggled):
            yield server.bool_global(cl.client_name, True)
            for client in cl.client_list:
                lcc.client_checkbox[client].setEnabled(True)
            lcc.track_global_line_center_duration.setEnabled(True)
        else:
            yield server.bool_global(cl.client_name, False)
            for client in cl.client_list:
                lcc.client_checkbox[client].setChecked(False)
                lcc.client_checkbox[client].setEnabled(False)
            lcc.client_checkbox[cl.client_name].setChecked(True)
            lcc.track_global_line_center_duration.setEnabled(False)
        self.on_new_fit_global()

    @inlineCallbacks
    def on_new_fit_global(self, *params):
        server = yield self.acxn.get_server("SD Tracker Global")
        fit_list = []
        for client in cl.client_list:
            if self.d_control.client_checkbox[client].isChecked():
                fit_list.append(client)
        yield server.set_global_fit_list(cl.client_name, fit_list)

    @inlineCallbacks
    def bool_keep_last_point(self, toggled):
        server = yield self.acxn.get_server("SD Tracker Global")
        yield server.bool_keep_last_point(cl.client_name, toggled)

    @inlineCallbacks
    def connect(self):
        yield self.setup_listeners()
        self.subscribed = True
        yield self.acxn.add_on_connect("SD Tracker Global", self.connectypoo)
        yield self.acxn.add_on_disconnect("SD Tracker Global", self.disconnectypoo)

    @inlineCallbacks
    def connectypoo(self, *args):
        self.setDisabled(False)
        global global_address
        global password
        try:
            yield self.setup_listeners()
        except:
            yield self.setDisabled(True)

    def disconnectypoo(self, *args):
        self.setDisabled(True)
            
    @inlineCallbacks
    def setup_listeners(self):
        try:
            server = yield self.acxn.get_server("SD Tracker Global")
            yield server.signal__new_fit(c.ID)
            yield server.signal__new_save_lattice(c.ID + 1)
            yield server.addListener(listener=self.on_new_fit, source=None, ID=c.ID)
            yield server.addListener(listener=self.on_new_save, source=None, ID=c.ID + 1)
        except:
            pass
        
    def on_new_fit(self, x, y, *args):
        self.update_lines()
        self.update_fit()

    @inlineCallbacks
    def on_new_save(self, x, y, *args):
        lcc = self.d_control
        try:
            server = yield self.acxn.get_server("SD Tracker Global")
        except:
            logger.warning("Failed on_new_save: ", exc_info=True)
        t = time.time()
        dt = datetime.now().strftime("%m%d")
        datafile = os.path.join(self.path, dt + ".csv")
        line_center = None
        b_field = None
        if y == "linecenter_bfield":
            b_field = yield server.get_last_b_field_local(cl.client_name)
            line_center = yield server.get_last_line_center_local(cl.client_name)
            lcc.Bfield_entry.setValue(b_field * 1.0e3)
            lcc.linecenter_entry.setValue(line_center * 1.0e3)
        elif y == "bfield":
            b_field = yield server.get_last_b_field_local(cl.client_name)
            lcc.Bfield_entry.setValue(b_field * 1.0e3)
        elif y == "linecenter":
            line_center = yield server.get_last_line_center_local(cl.client_name)
            lcc.linecenter_entry.setValue(line_center * 1.0e3)
        with open(datafile, "a+") as f:
                    fwriter = csv.writer(f)
                    fwriter.writerow([t, line_center, b_field])

    @inlineCallbacks
    def update_lines(self):
        try:
            server = yield self.acxn.get_server("SD Tracker Global")
            lines = yield server.get_current_lines(cl.client_name)
        except:
            logger.info("No lines")
            self.signalpoo.emit([])
        else:
            self.signalpoo.emit(lines)
    
    @inlineCallbacks
    def update_fit(self):
        try:
            server = yield self.acxn.get_server("SD Tracker Global")
            lct = self.d_linecentertracker
            history_B = yield server.get_fit_history(cl.client_name)
            history_B = history_B[0]
            excluded_B = yield server.get_excluded_points(cl.client_name)
            excluded_B = excluded_B[0]
            history_line_center = dict.fromkeys(cl.client_list)
            excluded_line_center = dict.fromkeys(cl.client_list)
            for client in cl.client_list:
                history_line_center[client] = yield server.get_fit_history(client)
                history_line_center[client] = history_line_center[client][1]
                excluded_line_center[client] = yield server.get_excluded_points(client)
                excluded_line_center[client] = excluded_line_center[client][1]
            fit_b = yield server.get_fit_parameters_local("bfield", cl.client_name)
            fit_f = yield server.get_fit_line_center(cl.client_name)
        except :
            logger.warning("Failed to update the fit", exc_info=True)
        else:
            inunits_b = [(t["min"], b["mgauss"]) for (t, b) in history_B]
            inunits_b_nofit = [(t["min"], b["mgauss"]) for (t, b) in excluded_B]
            inunits_f = dict.fromkeys(cl.client_list)
            inunits_f_nofit = dict.fromkeys(cl.client_list)
            for client in cl.client_list:
                inunits_f[client] = [(t["min"], freq["kHz"]) 
                                        for (t, freq) in history_line_center[client]]
                inunits_f_nofit[client] = [(t["min"], freq["kHz"]) 
                                            for (t, freq) in excluded_line_center[client]]
            yield self.update_track((inunits_f, inunits_f_nofit), 
                                    lct.line_drift, lct.line_drift_lines)
            yield self.update_track((inunits_b, inunits_b_nofit), 
                                    lct.b_drift, lct.b_drift_lines)          
            self.plot_fit_f(fit_f)
            self.plot_fit_b(fit_b)

    def update_listing(self, lines):
        lcc = self.d_control
        if not lines:
            lcc.copy_clipboard_button.setEnabled(False)
            lcc.frequency_table.setRowCount(0)
        else:
            listing = [(c.favorites.get(line, line), freq) for line,freq in lines]
            zeeman = self.calc_zeeman(listing)
            listing.append(zeeman)
            lcc.copy_clipboard_button.setEnabled(True)
            lcc.frequency_table.fill_out_widget(listing)

    def update_spectrum(self, lines):
        # clear all lines by removing them from the self.spectral_lines list
        lcs = self.d_spectrum
        for _ in range(len(lcs.spectral_lines)):
            lcs.spectral_lines.pop().remove()
        lcs.spec_canvas.draw()
        # sort by frequency to add them in the right order
        if not lines:
            lcs.spec_canvas.draw()
        else:
            srt = sorted(lines, key=lambda x: x[1])
            num = len(srt)
            for i, (linename, freq) in enumerate(srt):
                line = lcs.spec.axvline(freq["MHz"], linewidth=1, ymin=0, ymax=1)
                lcs.spectral_lines.append(line)
                # check to see if linename in the favorites dictionary, 
                # if not use the linename for display
                display_name = c.favorites.get(linename, linename)
                label = lcs.spec.annotate(display_name, xy=(freq["MHz"], 
                                          .9 - i * .7 / num), xycoords="data", 
                                          fontsize=13)
                lcs.spectral_lines.append(label)
            lcs.spec.set_xlim(left=srt[0][1]["MHz"] - 1, right=srt[-1][1]["MHz"] + 1)
            lcs.spec_canvas.draw()

    def plot_fit_b(self, p):
        lct = self.d_linecentertracker
        for _ in range(len(lct.b_drift_fit_line)):
            lct.b_drift_fit_line.pop().remove()
        for _ in range(len(lct.b_drift_twin_lines)):
            lct.b_drift_twin_lines.pop().remove()
        if not p is None:
            xmin, xmax = lct.b_drift.get_xlim()
            xmin -= 10
            xmax += 10
            points = 1000        
            x = np.linspace(xmin, xmax, points) 
            y = 1000 * np.polyval(p, 60 * x)
            frequency_scale = 1.4  # KHz / mgauss
            l = lct.b_drift.plot(x, y, "-r")[0]
            twin = lct.b_drift_twin.plot(x, frequency_scale * y, alpha=0)[0]
            lct.b_drift_twin_lines.append(twin)
            label = lct.b_drift.annotate("Slope {0:.1f} microgauss/sec".format(10**6 * p[-2]), 
                                         xy=(.3, .8), xycoords="axes fraction", 
                                         fontsize=13)
            lct.b_drift_fit_line.append(label)
            lct.b_drift_fit_line.append(l)
        lct.drift_canvas.draw()
    
    def plot_fit_f(self, p):
        lct = self.d_linecentertracker
        for _ in range(len(lct.line_drift_fit_line)):
            lct.line_drift_fit_line.pop().remove()
        if not p is None:
            xmin, xmax = lct.line_drift.get_xlim()
            xmin-= 10
            xmax+= 10
            points = 1000
            x = np.linspace(xmin, xmax, points) 
            y = 1000 * np.polyval(p, 60 * x)
            l = lct.line_drift.plot(x, y, "-r")[0]
            label = lct.line_drift.annotate("Slope {0:.1f} Hz/sec".format(10**6 * p[-2]), 
                                             xy=(.3, .8), xycoords="axes fraction", 
                                             fontsize=13)
            lct.line_drift_fit_line.append(l)
            lct.line_drift_fit_line.append(label)
        lct.drift_canvas.draw()

    @inlineCallbacks
    def readout_update(self):
        try:
            server = yield self.acxn.get_server("SD Tracker Global")
            center = yield server.get_current_center(cl.client_name)
            self.d_control.current_line_center.setText("%.8f MHz"%center["MHz"])
        except:
            logger.warning("Failure in readout_update: ", exc_info=True)
            yield self.d_control.current_line_center.setText("Error")
        try:
            B = yield server.get_current_b_local(cl.client_name)
            self.d_control.current_B.setText("%.8f gauss"%B["gauss"])
        except:
            logger.warning("Failure in readout_update: ", exc_info=True)
            yield self.d_control.current_B.setText("Error")
        try:
            time = yield server.get_current_time()
            self.d_control.current_time.setText("%.2f min"%time["min"])
        except:
            logger.warning("Failure in readout_update: ", exc_info=True)
            yield self.d_control.current_time.setText("Error")
    
    @inlineCallbacks
    def update_track(self, meas, axes, lines):
        # clear all current lines
        for _ in range(len(lines)):
            lines.pop().remove()
        global colors
        fitted = meas[0]
        not_fitted = meas[1]
        lct = self.d_linecentertracker
        lcc = self.d_control
        if ((type(fitted) and type(not_fitted)) != dict and 
            (type(fitted) and type(not_fitted)) != list):
            raise Exception("Data type should be dict or list")
        
        if type(fitted) is dict:
            x_all = np.array([])
            y_all = np.array([])
            for client, clr in zip(cl.client_list, colors):
                x = np.array([m[0] for m in fitted[client]])
                y = np.array([m[1] for m in fitted[client]])
                xnofit = np.array([m[0] for m in not_fitted[client]])
                ynofit = np.array([m[1] for m in not_fitted[client]])
                line = axes.plot(x, y, "*", color=clr, label=client)[0]
                line_nofit = axes.plot(xnofit, ynofit, "o", color=clr, label="{} (nofit)".format(client))[0]
                lines.append(line)
                lines.append(line_nofit)
                x_all = np.append(x_all, x)
                y_all = np.append(y_all, y)
            try:
                last = y_all[np.where(x_all == x_all.max())][0]
            except:
                logger.warning("Issue in update_track", exc_info=True)
            else:
                label = axes.annotate("Last Global Point: {0:.2f} {1}".format(last, axes.get_ylabel()), 
                                      xy=(.3, .9), xycoords="axes fraction", fontsize=13)
                lines.append(label)
            legend = axes.legend(loc=1)
            lines.append(legend)
            server = yield self.acxn.get_server("SD Tracker Global")
            if lcc.global_checkbox.isChecked():
                try:
                    fit_data = yield server.get_line_center_global_fit_data(cl.client_name)
                    fit_data = [(t["min"], freq["kHz"]) for (t, freq) in fit_data]
                    x_fit_data = np.array([m[0] for m in fit_data])
                    y_fit_data = np.array([m[1] for m in fit_data])
                    xmin = np.amin(x_fit_data)
                    xmax = np.amax(x_fit_data)
                    ymin = np.amin(y_fit_data)
                    ymax = np.amax(y_fit_data)
                except ValueError:
                    logger.warning("ValueError", exc_info=True)
                    return
            else:
                try:
                    xmin = np.amin(np.array([m[0] for m in fitted[cl.client_name]]))
                    xmax = np.amax(np.array([m[0] for m in fitted[cl.client_name]]))
                    ymin = np.amin(np.array([m[1] for m in fitted[cl.client_name]]))
                    ymax = np.amax(np.array([m[1] for m in fitted[cl.client_name]]))
                except:
                    logger.warning("ValueError", exc_info=True)
                    return

            if xmin == xmax:
                xlims = [xmin - 5, xmax + 5]
                ylims = [ymin - 2, ymax + 2]
            else:
                xspan = xmax - xmin
                yspan = ymax - ymin
                xlims = [xmin - .25 * xspan, xmax + .5 * xspan]
                ylims = [ymin - .5 * yspan, ymax + 0.5 * yspan]
            axes.set_xlim(xlims)
            axes.set_ylim(ylims)
            lct.drift_canvas.draw()

        if type(fitted) is list:
            x = np.array([m[0] for m in fitted])
            y = np.array([m[1] for m in fitted])
            xnofit = np.array([m[0] for m in not_fitted])
            ynofit = np.array([m[1] for m in not_fitted])
            # annotate the last point
            try:
                last = y[-1]
            except IndexError:
                logger.warning("IndexError", exc_info=True)
            else:
                label = axes.annotate("Last Point: {0:.2f} {1}".format(last, axes.get_ylabel()), xy=(.3, .9), 
                                      xycoords="axes fraction", fontsize=13)
                lines.append(label)
            line = axes.plot(x, y, "*", color=colors[cl.client_list.index(cl.client_name)], label=cl.client_name)[0]
            line_nofit = axes.plot(xnofit, ynofit, "o", color=colors[cl.client_list.index(cl.client_name)], 
                                   label="{} (nofit)".format(cl.client_name))[0]
            legend = axes.legend()
            lines.append(line)
            lines.append(line_nofit)
            lines.append(legend)
            #set window limits
            try:
                xmin = np.amin(x)
                xmax = np.amax(x)
                ymin = np.amin(y)
                ymax = np.amax(y)
            except ValueError:
                logger.warning("ValueError", exc_info=True)
                return

            if xmin == xmax:
                xlims = [xmin - 5, xmax + 5]
                ylims = [ymin - 2, ymax + 2]
            else:
                xspan = xmax - xmin
                yspan = ymax - ymin
                xlims = [xmin - .25 * xspan, xmax + .5 * xspan]
                ylims = [ymin - .5 * yspan, ymax + .5 * yspan]
            axes.set_xlim(xlims)
            axes.set_ylim(ylims)
            lct.drift_canvas.draw()

    def calc_zeeman(self, listing):
    	line1 = "S+1/2D+1/2"
    	line2 = "S-1/2D+1/2"
    	for line, freq in listing:
    		if line == line1:
    			freq1 = freq["MHz"]
    		if line == line2:
    			freq2 = freq["MHz"]
    	zeeman = ("Zeeman Splitting", U(-freq1 + freq2, "MHz"))
    	return zeeman


class MdiArea(QtWidgets.QMdiArea):
    # redundant
    def __init__(self):
        QtWidgets.QMdiArea.__init__(self)
        self.pixmap = QtGui.QPixmap(os.path.join(
            artiq_dir, "gui", "logo_ver.svg"))

    def paintEvent(self, event):
        QtWidgets.QMdiArea.paintEvent(self, event)
        painter = QtGui.QPainter(self.viewport())
        x = (self.width() - self.pixmap.width())//2
        y = (self.height() - self.pixmap.height())//2
        painter.setOpacity(1)
        painter.drawPixmap(x, y, self.pixmap)
