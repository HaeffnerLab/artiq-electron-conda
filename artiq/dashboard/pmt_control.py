import labrad
from labrad.units import WithUnit as U
import logging
from PyQt5 import QtCore, QtWidgets, QtGui
from artiq.protocols.pc_rpc import Client


logger = logging.getLogger(__name__)


class PMTControlDock(QtWidgets.QDockWidget):
    def __init__(self, main_window):
        QtWidgets.QDockWidget.__init__(self, "PMT / Linetrigger / Piezo Control")
        self.setObjectName("pmt_control")
        self.setFeatures(QtWidgets.QDockWidget.DockWidgetMovable |
                         QtWidgets.QDockWidget.DockWidgetFloatable)

        self.cxn = labrad.connect()
        self.p = self.cxn.parametervault

        self.dset_ctl = Client("::1", 3251, "master_dataset_db")
        self.scheduler = Client("::1", 3251, "master_schedule")
        self.rid = None
        self.pulsed = False
        self.expid_continuous = {"arguments": {},
                                "class_name": "pmt_collect_continuously",
                                "file": "run_continuously/run_pmt_continuously.py",
                                "log_level": 30,
                                "repo_rev": None}

        self.expid_pulsed = {"arguments": {},
                             "class_name": "pmt_collect_pulsed",
                             "file": "run_continuously/run_pmt_pulsed.py",
                             "log_level": 30,
                             "repo_rev": None}

        frame = QtWidgets.QFrame()
        frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
        frame.setFrameShadow(QtWidgets.QFrame.Raised)
        layout = QtWidgets.QGridLayout()
        vLayout = QtWidgets.QVBoxLayout(frame)
        vLayout.addLayout(layout)
        vLayout.addStretch(1)
        self.setWidget(frame)

        self.onButton = QtWidgets.QPushButton("On")
        self.onButton.setCheckable(True)
        self.onButton.clicked[bool].connect(self.set_state)
        self.autoLoadButton = QtWidgets.QPushButton("On")
        self.autoLoadButton.setCheckable(True)
        self.autoLoadButton.clicked[bool].connect(self.toggle_autoload)
        self.autoLoadSpin = QtWidgets.QSpinBox()

        self.countDisplay = QtWidgets.QLCDNumber()
        self.countDisplay.setSegmentStyle(2)
        self.countDisplay.display(0)
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
        self.duration.returnPressed.connect(self.duration_changed)
        self.duration.setStyleSheet("QLineEdit { background-color:  #c4df9b}" )

        self.modeLabel = QtWidgets.QLabel("Mode: ")
        self.setMode = QtWidgets.QComboBox()
        self.setMode.addItem("continuous")
        self.setMode.addItem("pulsed")
        self.setMode.currentIndexChanged.connect(self.set_mode)

        self.linetriggerButton = QtWidgets.QPushButton("Off")
        self.linetriggerButton.setCheckable(True)
        self.linetriggerButton.setChecked(True)
        self.linetriggerButton.clicked[bool].connect(self.toggle_linetrigger)
        self.linetriggerLineEdit = QtWidgets.QLineEdit("0")
        self.linetriggerLineEdit.returnPressed.connect(self.linetrigger_duration_changed)

        boldFont = QtGui.QFont()
        boldFont.setBold(True)
        self.pmtLabel = QtWidgets.QLabel("PMT")
        self.pmtLabel.setFont(boldFont)
        self.pmtLabel.setAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignVCenter)
        self.linetriggerLabel = QtWidgets.QLabel("LINETRIGGER")
        self.linetriggerLabel.setFont(boldFont)
        self.linetriggerLabel.setAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignVCenter)
        self.piezoLabel = QtWidgets.QLabel("PICOMOTOR")
        self.piezoLabel.setFont(boldFont)
        self.piezoLabel.setAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignVCenter)

        layout.addWidget(QtWidgets.QLabel(""), 0, 0)
        layout.addWidget(self.pmtLabel, 1, 0, 1, 3)
        layout.addWidget(self.onButton, 2, 0)
        layout.addWidget(self.countDisplay, 2, 1)
        layout.addWidget(self.unitsLabel, 2, 2)
        layout.addWidget(self.durationLabel, 3, 0)
        layout.addWidget(self.duration, 3, 1, 1, 2)
        layout.addWidget(self.modeLabel, 4, 0)
        layout.addWidget(self.setMode, 4, 1, 1, 2)
        layout.addWidget(QtWidgets.QLabel("Autoload: "), 5, 0)
        layout.addWidget(self.autoLoadButton, 5, 1)
        layout.addWidget(self.autoLoadSpin, 5, 2)

        layout.addWidget(QtWidgets.QLabel(""), 6, 0)
        layout.addWidget(QtWidgets.QLabel(""), 7, 0)
        layout.addWidget(QtWidgets.QLabel(""), 8, 0)
        layout.addWidget(QtWidgets.QLabel(""), 9, 0)
        layout.addWidget(self.linetriggerLabel, 10, 0, 1, 3)
        layout.addWidget(self.linetriggerButton, 11, 0, 1, 3)
        layout.addWidget(QtWidgets.QLabel("Offset duration (us): "), 12, 0)
        layout.addWidget(self.linetriggerLineEdit, 12, 1, 1, 2)

        layout.addWidget(QtWidgets.QLabel(""), 13, 0)
        layout.addWidget(QtWidgets.QLabel(""), 14, 0)
        layout.addWidget(QtWidgets.QLabel(""), 15, 0)
        layout.addWidget(QtWidgets.QLabel(""), 16, 0)
        layout.addWidget(self.piezoLabel, 17, 0, 1, 3)

        ctls = ["Local X", "Local Y", "Global X", "Global Y"]
        starting_row = 18
        self.piezoStepSize = dict()
        self.piezoCurrentPos = dict()
        self.piezoLastPos = dict()
        for i, ctl in enumerate(ctls):
            layout.addWidget(QtWidgets.QLabel(ctl + ": "),
                             starting_row + i, 0)
            self.piezoStepSize[ctl] = QtWidgets.QSpinBox()
            self.piezoStepSize[ctl].setToolTip("Set step size.")
            self.piezoStepSize[ctl].setObjectName(ctl)
            self.piezoStepSize[ctl].setKeyboardTracking(False)
            self.piezoStepSize[ctl].valueChanged.connect(self.piezo_step_size_changed)
            self.piezoStepSize[ctl].setRange(0, 300)
            layout.addWidget(self.piezoStepSize[ctl],
                             starting_row + i, 1)
            self.piezoCurrentPos[ctl] = QtWidgets.QSpinBox()
            self.piezoCurrentPos[ctl].setSingleStep(0)
            self.piezoCurrentPos[ctl].setToolTip("Current position.")
            self.piezoCurrentPos[ctl].setRange(-100000, 100000)
            self.piezoCurrentPos[ctl].setObjectName(str(i + 1))
            self.piezoLastPos[i + 1] = 0
            self.piezoCurrentPos[ctl].setKeyboardTracking(False)
            self.piezoCurrentPos[ctl].valueChanged.connect(self.piezo_changed)
            layout.addWidget(self.piezoCurrentPos[ctl],
                             starting_row + i, 2)

        if "picomotorserver" in self.cxn.servers:
            self.piezo = self.cxn.PicomotorServer
        else:
            self.piezo = None


    def set_state(self, override=False):
        if override:
            flag = True
        else:
            flag = self.onButton.isChecked()

        if flag:
            if self.rid is None:
                if self.setMode.currentText() == "continuous":
                    self.rid = self.scheduler.submit("main", self.expid_continuous, 0)
                else:
                    self.rid = self.scheduler.submit("main", self.expid_pulsed, 0)
            self.onButton.setText("Off")

        else:
            if self.rid is None:
                return  # Shouldn't happen
            else:
                self.scheduler.delete(self.rid)
                self.rid = None
            self.onButton.setText("On")

    def duration_changed(self, *args, **kwargs):
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
            self.p.set_parameter(["PmtReadout", "duration", U(duration, "ms")])
            if self.rid is None:
                return
            else:
                self.scheduler.delete(self.rid)
                self.rid = None
                self.set_state(True)
        except ValueError:
            # Shouldn't happen
            pass

    def set_mode(self):
        txt = str(self.setMode.currentText())
        if self.rid is None:
            self.pulsed = txt == "pulsed"
        elif  txt == "continuous":
            if not self.pulsed:
                return
            else:
                self.pulsed = False
                self.scheduler.delete(self.rid)
                self.rid = self.scheduler.submit("main", self.expid_continuous, 0)
        else:
            if self.pulsed:
                return
            else:
                self.pulsed = True
                self.scheduler.delete(self.rid)
                self.rid = self.scheduler.submit("main", self.expid_pulsed, 0)

    def updateLCD(self):
        if not self.onButton.isChecked():
            self.countDisplay.display(0)
            return
        try:
            raw_val = self.dset_ctl.get("pmt_counts")[-1]
            try:
                # duration in mseconds
                duration = float(self.duration.text())  
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

    def toggle_linetrigger(self):
        sender = self.sender()
        flag = sender.isChecked()
        if flag:
            sender.setText("Off")
        else:
            sender.setText("On")

    def linetrigger_duration_changed(self):
        pass

    def piezo_step_size_changed(self):
        sender = self.sender()
        step = int(sender.value())
        ctl = sender.objectName()
        self.piezoCurrentPos[ctl].setSingleStep(step)

    def piezo_changed(self):
        if "picomotorserver" in self.cxn.servers:
            sender = self.sender()
            piezo = int(sender.objectName())
            current_pos = int(sender.value())
            last_pos = self.piezoLastPos[piezo]
            self.piezoLastPos[piezo] = current_pos
            if self.piezo is None:
                self.piezo = self.cxn.PicomotorServer
            move = current_pos - last_pos
            self.piezo.relative_move(piezo, move)
        else:
            QtWidgets.QMessageBox.warning(None, "Warning", 
                                "Picomotor is not connected.")

    def toggle_autoload(self):
        sender = self.sender()
        flag = sender.isChecked()
        if flag:
            sender.setText("Off")
        else:
            sender.setText("On")

    def save_state(self):
        return {"ctl": {ctl: self.piezoStepSize[ctl].value()
                        for ctl in self.piezoStepSize.keys()},
                "offset":  self.linetriggerLineEdit.text(),
                "autoload": self.autoLoadSpin.value(),
                "mode": self.setMode.currentText(),
                "ltrigger": self.linetriggerButton.isChecked()
               }   

    def restore_state(self, state):
        for ctl, value in state["ctl"].items():
            self.piezoStepSize[ctl].setValue(value)
            self.piezoCurrentPos[ctl].setSingleStep(int(value))
        self.linetriggerLineEdit.setText(state["offset"])
        self.autoLoadSpin.setValue(int(state["autoload"]))
        self.setMode.setCurrentText(state["mode"])
        self.linetriggerButton.setChecked(state["ltrigger"])
        d = {False: "On", True: "Off"}
        self.linetriggerButton.setText(d[state["ltrigger"]])
