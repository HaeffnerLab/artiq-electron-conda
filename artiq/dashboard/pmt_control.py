import labrad
from labrad.units import WithUnit as U
import logging
from PyQt5 import QtCore, QtWidgets, QtGui
from artiq.gui.tools import LayoutWidget
from artiq.protocols.pc_rpc import Client


logger = logging.getLogger(__name__)


class PMTControlDock(QtWidgets.QDockWidget):
    def __init__(self, main_window, exp_manager):
        QtWidgets.QDockWidget.__init__(self, "PMT Control")
        self.setObjectName("pmt_control")
        self.setFeatures(QtWidgets.QDockWidget.DockWidgetMovable |
                         QtWidgets.QDockWidget.DockWidgetFloatable)

        self.cxn = labrad.connect()
        self.p = self.cxn.parametervault
        
        self.dset_ctl = Client("::1", 3251, "master_dataset_db")
        self.scheduler = Client("::1", 3251, "master_schedule")
        self.rid = None
        self.expid = {"arguments": {},
                      "class_name": "pmtcollect",
                      "file": "run_continuously/run_pmt.py",
                      "log_level": 30,
                      "repo_rev": "N/A"}

        layout = QtWidgets.QGridLayout()
        top_widget = QtWidgets.QWidget()
        vLayout = QtWidgets.QVBoxLayout(top_widget)
        vLayout.addLayout(layout)
        vLayout.addStretch(1)

        # top_widget.setLayout(layout)
        self.setWidget(top_widget)

        self.shortcut_widgets = dict()

        self.onButton = QtWidgets.QPushButton("On")
        self.onButton.setCheckable(True)
        self.onButton.clicked[bool].connect(self.set_state)

        self.countDisplay = QtWidgets.QLCDNumber()
        self.countDisplay.setSegmentStyle(2)
        self.countDisplay.display(0)
        # Using the timer for this seems like it's overly resource intensive
        # does it matter?
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.updateLCD)
        self.timer.start(250)
        self.countDisplay.setStyleSheet("background-color: lightGray;"
                                        "color: green;")
        self.unitsLabel = QtWidgets.QLabel("kcounts / s")

        self.durationLabel = QtWidgets.QLabel("Duration (ms): ")
        self.duration = QtWidgets.QLineEdit("100")
        self.p.set_parameter(["PmtReadout", "duration", U(100, "ms")])
        validator = QtGui.QDoubleValidator()
        self.duration.setValidator(validator)
        self.duration.returnPressed.connect(self.check_state)
        self.duration.setStyleSheet("QLineEdit { background-color:  #c4df9b}" )

        self.modeLabel = QtWidgets.QLabel("mode: ")
        self.setMode = QtWidgets.QComboBox()
        self.setMode.addItem("continuous")
        self.p.set_parameter(["PmtReadout", "pulsed", False])
        self.setMode.addItem("pulsed")
        self.setMode.currentIndexChanged.connect(self.set_mode)

        layout.addWidget(QtWidgets.QLabel(""), 0, 0)
        layout.addWidget(QtWidgets.QLabel(""), 1, 0)
        layout.addWidget(QtWidgets.QLabel(""), 2, 0)
        layout.addWidget(self.onButton, 3, 0)
        layout.addWidget(self.countDisplay, 3, 1)
        layout.addWidget(self.unitsLabel, 3, 2)
        layout.addWidget(self.durationLabel, 4, 0)
        layout.addWidget(self.duration, 4, 1, 1, 2)
        layout.addWidget(self.modeLabel, 5, 0)
        layout.addWidget(self.setMode, 5, 1, 1, 2)

    def set_state(self):
        if self.onButton.isChecked():
            if self.rid is None:
                self.rid = self.scheduler.submit("main", self.expid, 0)
            self.onButton.setText("Off")

        else:
            if self.rid is None:
                return  # Shouldn't happen
            else:
                self.scheduler.request_termination(self.rid)
                self.rid = None
            self.onButton.setText("On")

    def check_state(self, *args, **kwargs):
        # connect to parametervault here
        sender = self.sender()
        validator = sender.validator()
        state = validator.validate(sender.text(), 0)[0]
        if state == QtGui.QValidator.Acceptable:
            color = "#c4df9b" # green
        elif state == QtGui.QValidator.Intermediate:
            color = "#fff79a" # yellow
        else:
            color = "#f6989d" # red
        sender.setStyleSheet("QLineEdit { background-color: %s }" %color)
        try:
            min = 1e-3 # 1 us
            raw_duration = float(sender.text())
            duration = raw_duration if raw_duration >= min else min
            self.p.set_parameter(["PmtReadout", "duration", U(float(sender.text()), "ms")])
        except ValueError:
            # Shouldn't happen
            pass

    def set_mode(self):
        if str(self.setMode.currentText()) == "continuous":
            self.p.set_parameter(["PmtReadout", "pulsed", False])
        else:
            self.p.set_parameter(["PmtReadout", "pulsed", True])

    def updateLCD(self):
        if not self.onButton.isChecked():
            self.countDisplay.display(0)
            return
        try:
            raw_val = self.dset_ctl.get("pmt_counts")[-1]
            try:
                duration = float(self.duration.text())  # duration in mseconds
            except ValueError:
                # picked up a backspace or something
                return
            val = raw_val / duration  # kcounts / second
            self.countDisplay.display(val)
        except KeyError:
            # dataset doesn't exist 
            self.countDisplay.display(0)
        except IndexError:
            # timer too fast
            pass         