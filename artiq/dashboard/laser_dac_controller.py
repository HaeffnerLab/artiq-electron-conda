import labrad
from PyQt5 import QtCore, QtGui, QtWidgets
from labrad.wrappers import connectAsync
from labrad.types import Error
from artiq.dashboard.laser_room_DAC_configuration import hardwareConfiguration as hc
from artiq.dashboard.QCustomSpinBox import QCustomSpinBox
from twisted.internet import defer


laser_room_ip = "192.168.169.49"
SIGNALID = 270835


class LaserDACDock(QtWidgets.QDockWidget):
    def __init__(self, main_window):
        QtWidgets.QDockWidget.__init__(self, "LASERDAC")
        self.setObjectName("LASERDAC")
        self.setFeatures(QtWidgets.QDockWidget.DockWidgetMovable |
                         QtWidgets.QDockWidget.DockWidgetFloatable)

        self.topLevelWidget = QtWidgets.QWidget(self)
        self.setWidget(self.topLevelWidget)
        self.makeGUI()
        self.connect()

    def makeGUI(self):
        self.dacDict = dict(**hc.elec_dict, **hc.sma_dict)
        
        self.controls = {k: QCustomSpinBox(hc.channel_name_dict[k], 
                         self.dacDict[k].allowedVoltageRange) 
                         for k in self.dacDict.keys()}

        layout = QtWidgets.QHBoxLayout()
        layout.addStretch(1)
        elecBox = QtWidgets.QGroupBox("")
        elecLayout = QtWidgets.QVBoxLayout()
        elecBox.setLayout(elecLayout)
        layout.addWidget(elecBox)

        elecList = sorted(hc.elec_dict.keys())
        if bool(hc.centerElectrode):
            elecList.pop(hc.centerElectrode - 1)
        for e in elecList:
            self.controls[e].onNewValues.connect(self.sendToServer)
            if int(e) <= len(elecList) // 2:
                elecLayout.addWidget(self.controls[e])
            elif int(e) > len(elecList) // 2:
                elecLayout.addWidget(self.controls[e])
      
        self.inputUpdated = False                
        # self.timer = QtCore.QTimer(self)        
        # self.timer.timeout.connect(self.sendToServer)
        # self.timer.start(UpdateTime)

        
        for k in self.dacDict.keys():
            self.controls[k].onNewValues.connect(self.inputHasUpdated(k))

        layout.setAlignment(QtCore.Qt.AlignCenter)
        elecLayout.setAlignment(QtCore.Qt.AlignCenter)               
        self.topLevelWidget.setLayout(layout)

    @defer.inlineCallbacks
    def connect(self):
        global laser_room_ip
        self.cxn = yield connectAsync(laser_room_ip, password="lab", tls_mode="off")
        yield self.setupListeners()
        if self.initialized:
            yield self.followSignal(0, 0)

    @defer.inlineCallbacks    
    def setupListeners(self):
        try:
            self.dacserver = yield self.cxn['LASERDAC Server']
            yield self.dacserver.signal__ports_updated(SIGNALID)
            yield self.dacserver.addListener(listener = self.followSignal, 
                                             source = None, ID = SIGNALID)
            self.initialized = True
            self.setEnabled(True)
        except:
            self.initialized = False
            self.setEnabled(False)

        # signal when server connects or disconnects
        yield self.cxn.manager.subscribe_to_named_message("Server Connect", 9898989, True)
        yield self.cxn.manager.subscribe_to_named_message("Server Disconnect", 9898989+1, True)
        yield self.cxn.manager.addListener(listener = self.followServerConnect, 
                                            source = None, ID = 9898989)
        yield self.cxn.manager.addListener(listener = self.followServerDisconnect, 
                                            source = None, ID = 9898989+1)

    def inputHasUpdated(self, name):
        def iu():
            self.inputUpdated = True
            self.changedChannel = name
        return iu

    def sendToServer(self):
        if self.inputUpdated:
            value = float(round(self.controls[self.changedChannel].spinLevel.value(), 3))
            self.dacserver.set_individual_analog_voltages([(self.changedChannel, value)])
            self.inputUpdated = False

    @defer.inlineCallbacks
    def followSignal(self, x, s):
        av = yield self.dacserver.get_analog_voltages()
        for (c, v) in av:
            self.controls[c].setValueNoSignal(v)

    @defer.inlineCallbacks
    def followServerConnect(self, cntx, server_name):
        server_name = server_name[1]
        if server_name == 'LASERDAC Server':
            self.dacserver = yield self.cxn['LASERDAC Server']
            yield self.dacserver.signal__ports_updated(SIGNALID2)
            yield self.dacserver.addListener(listener = self.followSignal, source = None, ID = SIGNALID2)
            self.initialized = True
            yield self.followSignal(0, 0)
            self.setEnabled(True)
        else:
            yield None

    @defer.inlineCallbacks
    def followServerDisconnect(self, cntx, server_name):
        server_name = server_name[1]
        if server_name == 'LASERDAC Server':
            self.initialized = False
            self.setEnabled(False)
            yield None
        else:
            yield None

    def setEnabled(self, value):
        for key in self.controls.keys():
            self.controls[key].spinLevel.setEnabled(value)
    

if __name__ == "__main__":
    a = QtWidgets.QApplication( [] )
    from twisted.internet import reactor
    DAC_Control = LaserDACDock(reactor)
    DAC_Control.show()
    reactor.run()
        
