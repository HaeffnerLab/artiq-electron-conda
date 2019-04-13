import labrad
import os
from labrad.units import WithUnit as U
import logging
from PyQt5 import QtCore, QtWidgets, QtGui
from artiq.protocols.pc_rpc import Client
from twisted.internet.defer import inlineCallbacks
from runpy import run_path


logger = logging.getLogger(__name__)


class PMTControlDock(QtWidgets.QDockWidget):
    def __init__(self, acxn):
        QtWidgets.QDockWidget.__init__(self, "Manual Controls")
        self.setObjectName("pmt_control")
        self.setFeatures(QtWidgets.QDockWidget.DockWidgetMovable |
                         QtWidgets.QDockWidget.DockWidgetFloatable)
        self.acxn = acxn
        self.setup_listeners()
        self.pv = None
        self.pm = None

        self.dset_ctl = Client("::1", 3251, "master_dataset_db")
        self.scheduler = Client("::1", 3251, "master_schedule")
        self.rid = None
        self.pulsed = False
        self.expid_continuous = {"arguments": {},
                                 "class_name": "pmt_collect_continuously",
                                 "file": "run_continuously/run_pmt_continuously.py",
                                 "log_level": 30,
                                 "repo_rev": None,
                                 "priority": 0}

        self.expid_pulsed = {"arguments": {},
                             "class_name": "pmt_collect_pulsed",
                             "file": "run_continuously/run_pmt_pulsed.py",
                             "log_level": 30,
                             "repo_rev": None,
                             "priority": 0}

        self.expid_dds_control = {"arguments": {},
                                  "class_name": "pmt_collect_pulsed",
                                  "file": "misc/manual_dds_control.py",
                                  "log_level": 30,
                                  "repo_rev": None,
                                  "priority": 1}

        frame = QtWidgets.QFrame()
        frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
        layout = QtWidgets.QVBoxLayout()
        pmt_frame = self.create_pmt_frame()
        linetrigger_frame = self.create_linetrigger_frame()
        dds_frame = self.create_dds_frame()
        picomotor_frame = self.create_picomotor_frame()
        layout.addWidget(pmt_frame)
        layout.addWidget(dds_frame)
        layout.addWidget(linetrigger_frame)
        layout.addWidget(picomotor_frame)
        layout.setSpacing(25)
        frame.setLayout(layout)

        scroll = QtWidgets.QScrollArea()
        scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        scroll.setWidgetResizable(False)
        scroll.setWidget(frame)
        scroll.setAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignVCenter)
        scroll.setSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding,
                             QtWidgets.QSizePolicy.MinimumExpanding)
        self.setWidget(scroll)

        self.connect_servers()

    def create_pmt_frame(self):
        pmtLabel = boldLabel("PMT")
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
        try:
            with labrad.connection() as cxn:
                p = cxn.parametervault
                p.set_parameter(["PmtReadout", "duration", U(100, "ms")])
        except:
            logger.error("Failed to initially connect to labrad.")
            self.duration.setDisabled(True)
        validator = QtGui.QDoubleValidator()
        self.duration.setValidator(validator)
        self.duration.returnPressed.connect(self.duration_changed)
        self.duration.setStyleSheet("QLineEdit { background-color:  #c4df9b}" )
        self.modeLabel = QtWidgets.QLabel("Mode: ")
        self.setMode = QtWidgets.QComboBox()
        self.setMode.addItem("continuous")
        self.setMode.addItem("pulsed")
        self.setMode.currentIndexChanged.connect(self.set_mode)
        layout = QtWidgets.QGridLayout()
        frame = QtWidgets.QFrame()
        frame.setFrameStyle(QtWidgets.QFrame.Panel | QtWidgets.QFrame.Sunken)
        frame.setLineWidth(2)
        frame.setMidLineWidth(3)
        layout.addWidget(pmtLabel, 0, 0, 1, 3)
        layout.addWidget(self.onButton, 1, 0)
        layout.addWidget(self.countDisplay, 1, 1)
        layout.addWidget(self.unitsLabel, 1, 2)
        layout.addWidget(self.durationLabel, 2, 0)
        layout.addWidget(self.duration, 2, 1, 1, 2)
        layout.addWidget(self.modeLabel, 3, 0)
        layout.addWidget(self.setMode, 3, 1, 1, 2)
        layout.addWidget(QtWidgets.QLabel("Autoload: "), 4, 0)
        layout.addWidget(self.autoLoadButton, 4, 1)
        layout.addWidget(self.autoLoadSpin, 4, 2)
        frame.setLayout(layout)
        return frame

    def create_linetrigger_frame(self):
        linetriggerLabel = boldLabel("LINETRIGGER")
        self.linetriggerButton = QtWidgets.QPushButton("Off")
        self.linetriggerButton.setCheckable(True)
        self.linetriggerButton.setChecked(True)
        self.linetriggerButton.clicked[bool].connect(self.toggle_linetrigger)
        self.linetriggerLineEdit = QtWidgets.QLineEdit("0")
        self.linetriggerLineEdit.returnPressed.connect(self.linetrigger_duration_changed)
        layout = QtWidgets.QGridLayout()
        frame = QtWidgets.QFrame()
        frame.setFrameStyle(QtWidgets.QFrame.Panel | QtWidgets.QFrame.Sunken)
        frame.setLineWidth(2)
        frame.setMidLineWidth(3)
        layout.addWidget(linetriggerLabel, 0, 0, 1, 3)
        layout.addWidget(self.linetriggerButton, 1, 0, 1, 3)
        layout.addWidget(QtWidgets.QLabel("Offset duration (us): "), 2, 0)
        layout.addWidget(self.linetriggerLineEdit, 2, 1, 1, 2)
        frame.setLayout(layout)
        return frame

    def create_picomotor_frame(self):
        layout = QtWidgets.QGridLayout()
        frame = QtWidgets.QFrame()
        frame.setFrameStyle(QtWidgets.QFrame.Panel | QtWidgets.QFrame.Sunken)
        frame.setLineWidth(2)
        frame.setMidLineWidth(3)
        piezoLabel = boldLabel("PICOMOTOR")
        ctls = ["Local X", "Local Y", "Global X", "Global Y"]
        self.piezoStepSize = dict()
        self.piezoCurrentPos = dict()
        self.piezoLastPos = dict()
        layout.addWidget(piezoLabel, 0, 0, 1, 3)
        for i, ctl in enumerate(ctls):
            layout.addWidget(QtWidgets.QLabel(ctl + ": "), i + 1, 0)
            self.piezoStepSize[ctl] = QtWidgets.QSpinBox()
            self.piezoStepSize[ctl].setToolTip("Set step size.")
            self.piezoStepSize[ctl].setObjectName(ctl)
            self.piezoStepSize[ctl].setKeyboardTracking(False)
            self.piezoStepSize[ctl].valueChanged.connect(self.piezo_step_size_changed)
            self.piezoStepSize[ctl].setRange(0, 300)
            layout.addWidget(self.piezoStepSize[ctl], i + 1, 1)
            self.piezoCurrentPos[ctl] = QtWidgets.QSpinBox()
            self.piezoCurrentPos[ctl].setSingleStep(0)
            self.piezoCurrentPos[ctl].setToolTip("Current position.")
            self.piezoCurrentPos[ctl].setRange(-100000, 100000)
            self.piezoCurrentPos[ctl].setObjectName(str(i + 1))
            self.piezoLastPos[i + 1] = 0
            self.piezoCurrentPos[ctl].setKeyboardTracking(False)
            self.piezoCurrentPos[ctl].valueChanged.connect(self.piezo_changed)
            layout.addWidget(self.piezoCurrentPos[ctl], i + 1, 2)
        frame.setLayout(layout)
        return frame

    def create_dds_frame(self):
        layout = QtWidgets.QGridLayout()
        frame = QtWidgets.QFrame()
        frame.setFrameStyle(QtWidgets.QFrame.Panel | QtWidgets.QFrame.Sunken)
        frame.setLineWidth(2)
        frame.setMidLineWidth(3)
        ddsLabel = boldLabel("DDS Control")
        layout.addWidget(ddsLabel, 0, 0, 1, 2)
        home_dir = os.path.expanduser("~")
        dir_ = os.path.join(home_dir, "artiq-master/HardwareConfiguration.py")
        settings = run_path(dir_)
        dds_dict = settings["dds_config"]
        self.dds_widgets = dict()
        for i, (name, specs) in enumerate(dds_dict.items()):
            self.dds_widgets[name] = ddsControlWidget(name, *specs, False)
            layout.addWidget(self.dds_widgets[name], i // 2 + 1 , i % 2)
        frame.setLayout(layout)
        return frame
    
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

    @inlineCallbacks
    def duration_changed(self, *args, **kwargs):
        # connect to parametervault here
        if self.pv is None:
            self.pv = yield self.acxn.get_server("ParameterVault")
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
            yield self.pv.set_parameter(["PmtReadout", "duration", U(duration, "ms")])
            a = yield self.pv.get_parameter(["PmtReadout", "duration"])
            if self.rid is None:
                return
            else:
                self.scheduler.delete(self.rid)
                self.rid = None
                self.set_state(True)
        except ValueError:
            # Shouldn't happen
            yield print("")
            logger.warning("Problem trying to update duration", exc_info=True)

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
                logger.warning("Failed to update LCD", exc_info=True)
                return
            val = raw_val / duration  # kcounts / second
            self.countDisplay.display(val)
        except KeyError:
            # dataset doesn't exist
            logger.info("dataset doesn't exist yet")
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

    @inlineCallbacks
    def piezo_changed(self):
        if self.pm is None:
            yield print("not connected to picomotor")
        sender = self.sender()
        piezo = int(sender.objectName())
        current_pos = int(sender.value())
        last_pos = self.piezoLastPos[piezo]
        self.piezoLastPos[piezo] = current_pos
        move = current_pos - last_pos
        yield self.pm.relative_move(piezo, move)

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
                "ltrigger": self.linetriggerButton.isChecked()}   

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


    def setup_listeners(self):
        self.acxn.add_on_connect("ParameterVault", self.parameter_vault_connect)
        self.acxn.add_on_disconnect("ParameterVault", self.parameter_vault_disconnect)
        self.acxn.add_on_connect("picomotorserver", self.picomotor_connect)
        self.acxn.add_on_disconnect("picomotorserver", self.picomotor_disconnect)

    def parameter_vault_connect(self):
        self.duration.setDisabled(False)

    def parameter_vault_disconnect(self):
        self.duration.setDisabled(True)
    
    def picomotor_connect(self):
        for spinbox in self.piezoStepSize.values():
            spinbox.setDisabled(False)
        for spinbox in self.piezoCurrentPos.values():
            spinbox.setDisabled(False)

    def picomotor_disconnect(self):
        for spinbox in self.piezoStepSize.values():
            spinbox.setDisabled(True)
        for spinbox in self.piezoCurrentPos.values():
            spinbox.setDisabled(True)

    @inlineCallbacks
    def connect_servers(self):
        if self.pv is None:
            try:
                self.pv = yield self.acxn.get_server("ParameterVault")
            except:
                self.parameter_vault_disconnect()
        if self.pm is None:
            try:
                self.pm = yield self.acxn.get_server("picomotorserver")
            except:
                self.picomotor_disconnect()


class ddsControlWidget(QtWidgets.QFrame):
    def __init__(self, name, freq, amp, state):
        QtWidgets.QFrame.__init__(self)
        self.setFrameStyle(QtWidgets.QFrame.Panel | QtWidgets.QFrame.Sunken)
        self.setLineWidth(2)
        self.setMidLineWidth(3)

        layout = QtWidgets.QGridLayout()
        layout.addWidget(boldLabel(name), 0, 0, 1, 3)
        layout.addWidget(QtWidgets.QLabel("Frequency"), 1, 0)
        layout.addWidget(QtWidgets.QLabel("Attenuation"), 1, 1)

        self.freq_spin = QtWidgets.QDoubleSpinBox()
        self.freq_spin.setSuffix(" MHz")
        self.att_spin = QtWidgets.QDoubleSpinBox()
        self.att_spin.setSuffix(" dB")
        self.state_button = QtWidgets.QPushButton()

        layout.addWidget(self.freq_spin, 2, 0)
        layout.addWidget(self.att_spin, 2, 1)
        layout.addWidget(self.state_button, 2, 2)
        self.setLayout(layout)


class boldLabel(QtWidgets.QLabel):
    def __init__(self, txt):
        QtWidgets.QLabel.__init__(self, txt)
        boldFont = QtGui.QFont()
        boldFont.setBold(True)
        self.setFont(boldFont)
        self.setAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignVCenter)

