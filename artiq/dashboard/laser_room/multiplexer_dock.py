import labrad
import logging
import os
import artiq.dashboard.laser_room.RGBconverter as RGB
from functools import partial
from PyQt5 import uic, QtWidgets, QtCore
from labrad.wrappers import connectAsync
from labrad.types import Error
from artiq.dashboard.laser_room.MULTIPLEXER_CONTROL_config import multiplexer_control_config as config
from twisted.internet.defer import inlineCallbacks


laser_room_ip = "192.168.169.49"
SIGNALID1 = 187567
SIGNALID2 = 187568
SIGNALID3 = 187569
SIGNALID4 = 187570
SIGNALID5 = 187571 # for the new locked state signals
logger = logging.getLogger(__name__)


class MultiplexerDock(QtWidgets.QDockWidget):
    finished = QtCore.pyqtSignal()
    def __init__(self, main_window):
        QtWidgets.QDockWidget.__init__(self, "MULTIPLEXER")
        self.setObjectName("MULTIPLEXER")
        self.setFeatures(QtWidgets.QDockWidget.DockWidgetFloatable)
        global laser_room_ip
        try:
            self.normal_cxn = labrad.connect(laser_room_ip,
                                         password="lab",
                                         tls_mode="off")
            self.finished.connect(self.finish_make_gui)
            self.topLevelWidget = QtWidgets.QWidget(self)
            self.setWidget(self.topLevelWidget)
            self.channelWidgets = dict()
            self.channels = list()
            self.start_make_gui()
            self.connect()
        except:
            self.normal_cxn = None

    def start_make_gui(self):
        self.verticalLayout = QtWidgets.QVBoxLayout()
        self.frame = QtWidgets.QFrame()
        self.frame.setFrameShape(QtWidgets.QFrame.Box)
        self.frame.setFrameShadow(QtWidgets.QFrame.Sunken)
        self.gridLayout = QtWidgets.QGridLayout()
        self.onButton = QtWidgets.QPushButton()
        self.onButton.setCheckable(True)
        self.onButton.setChecked(True)
        self.onButton.setText("OFF")
        self.onButton.clicked[bool].connect(self.set_on_off)
        self.gridLayout.addWidget(self.onButton, 0, 0, 1, 2)
        self.topLevelWidget.setLayout(self.gridLayout)

    def finish_make_gui(self):
        server = self.normal_cxn.multiplexer_server
        for channel in self.channels:
            wavelength = server.get_wavelength_from_channel(channel)
            widget_config = config.info.get(channel, None)
            if widget_config is not None: 
                user_hint, location = widget_config
            else:
                continue
            widget = MultiplexerChannel(channel, wavelength, user_hint)
            l1, l2 = location
            self.gridLayout.addWidget(widget, l1 + 1, l2)
            freq = server.get_frequency(channel)
            widget.set_frequency((float(freq)))
            exp = server.get_exposure(channel)
            widget.set_exposure(exp)
            state = server.get_state(channel)
            widget.set_state(state)
            widget.checkBox.stateChanged.connect(partial(self.set_state, channel))
            widget.exposureSpinBox.valueChanged.connect(partial(self.set_exposure, channel))
            self.channelWidgets[channel] = widget
            self.topLevelWidget.update()

    @inlineCallbacks
    def connect(self):
        global laser_room_ip
        self.cxn = yield connectAsync(laser_room_ip, password="lab", 
                                      tls_mode="off")
        try:
            self.server = yield self.cxn.multiplexer_server
            yield self.setupListeners()
            self.channels = yield self.server.get_available_channels()
            logger.info("Channels: " + str(self.channels))
            self.finished.emit()
        except:
            logger.warning("Couldn't connect to labrad", exc_info=True)
            self.setEnabled(False)
    
    @inlineCallbacks
    def setupListeners(self):
        yield self.server.signal__channel_toggled(SIGNALID1)
        yield self.server.addListener(listener=self.follow_new_state, 
                                      source=None, ID=SIGNALID1)
        yield self.server.signal__new_exposure_set(SIGNALID2)
        yield self.server.addListener(listener=self.follow_new_exposure, 
                                      source=None, ID=SIGNALID2)
        yield self.server.signal__new_frequency_measured(SIGNALID3)
        yield self.server.addListener(listener=self.follow_new_freq, 
                                      source=None, ID=SIGNALID3)
        yield self.server.signal__updated_whether_cycling(SIGNALID4)
        yield self.server.addListener(listener=self.follow_new_cycling, 
                                      source=None, ID=SIGNALID4)
        logger.info("Listeners are set.")

    def follow_new_state(self, _, channel_state):
        channel, state = channel_state
        if channel in self.channelWidgets.keys():
            self.channelWidgets[channel].set_state(state, True)
        
    def follow_new_exposure(self, _, channel_exp):
        channel, exp = channel_exp
        if channel in self.channelWidgets.keys():
            self.channelWidgets[channel].set_exposure(exp, True)
    
    def follow_new_freq(self, _, channel_freq):
        channel, freq = channel_freq
        if channel in self.channelWidgets.keys():
            self.channelWidgets[channel].set_frequency(freq)

    def follow_new_cycling(self, _, cycling):
        self.onButton.blockSignals(True)
        self.onButton.setChecked(cycling)
        self.onButton.blockSignals(False)
        self.set_button_text()
    
    def set_button_text(self):
        if self.onButton.isChecked():
            self.onButton.setText("OFF")
        else:
            self.onButton.setText("ON")

    @inlineCallbacks
    def set_on_off(self, *args):
        sender = self.sender()
        self.set_button_text()
        if sender.isChecked():
            self.set_button_text()
            yield self.server.start_cycling()
        else:
            self.set_button_text()
            yield self.server.stop_cycling()
    
    @inlineCallbacks
    def set_state(self, channel, state):
        yield self.server.set_state(channel, bool(state))
    
    @inlineCallbacks
    def set_exposure(self, channel, exp):
        yield self.server.set_exposure(channel, exp)


class MultiplexerChannel(QtWidgets.QFrame):
    def __init__(self, name, wavelength, hint):
        super(QtWidgets.QFrame, self).__init__()
        basepath = os.path.dirname(__file__)
        self.uipath = basepath + "/multiplexer_channel.ui"
        uic.loadUi(self.uipath, self)
        self.rgb_converter = RGB.RGBconverter()
        self.set_color(wavelength)
        self.set_hint(hint)
        self.set_name(name)
        self.channel = name
        self.wavelength = wavelength
        self.hint = hint
        self.code_dict = {-3: "Under Exposed",
                          -4: "Over Exposed",
                          -6: "Not Measured"}

    def set_color(self, wavelength):
        r, g, b = self.rgb_converter.wav2RGB(int(wavelength))
        self.name.setStyleSheet("color:rgb(%d,%d,%d)" %(r, g, b))

    def set_name(self, name):
        self.name.setText(name)

    def set_hint(self, hint):
        self.hintLineEdit.setText(hint)

    def set_frequency(self, freq):
        if freq in self.code_dict.keys():
            text = self.code_dict[freq]
        else:
            text = "%.5f" %freq
        self.freqLineEdit.setText(text)            
            
    def set_state(self, state, disableSignals=False):
        if disableSignals:
            self.checkBox.blockSignals(True)
        self.checkBox.setChecked(state)
        if disableSignals:
            self.checkBox.blockSignals(False)
        
    def set_exposure(self, exposure, disableSignals=False):
        if disableSignals:
            self.checkBox.blockSignals(True)
        self.exposureSpinBox.setValue(exposure)
        if disableSignals:
            self.checkBox.blockSignals(False)

