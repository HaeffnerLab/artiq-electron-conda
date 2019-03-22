import logging
from PyQt5 import QtCore, QtWidgets, QtGui
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
import matplotlib.gridspec as gridspec
import matplotlib.cm as cm
import matplotlib.pyplot as plt
from artiq.dashboard.drift_tracker_junk.helper_widgets import saved_frequencies_table
from artiq.dashboard.drift_tracker_junk.compound_widgets import table_dropdowns_with_entry
from artiq.dashboard.drift_tracker_junk.switch_button import TextChangingButton
import artiq.dashboard.drift_tracker_junk.drift_tracker_config as c
import artiq.dashboard.drift_tracker_junk.client_config as cl


logger = logging.getLogger(__name__)


class DriftTrackerControl(QtWidgets.QDockWidget):
    def __init__(self):
        QtWidgets.QDockWidget.__init__(self, "Drift Tracker Control")
        self.setObjectName("DriftTrackerControl")
        self.setFeatures(QtWidgets.QDockWidget.DockWidgetMovable |
                         QtWidgets.QDockWidget.DockWidgetFloatable)
        self.client_list = cl.client_list
        try:
            self.favorites = c.favorites
        except AttributeError:
            self.favorites = {}
        try:
            self.initial_selection = c.initial_selection
        except AttributeError:
            self.initial_selection = []
        try:
            self.initial_values = c.initial_values
        except AttributeError:
            self.initial_values = []
        self.tabs = QtWidgets.QTabWidget()
        self.widget1 = QtWidgets.QWidget()
        self.widget2 = QtWidgets.QWidget()
        self.tabs.addTab(self.widget1, "阴")
        self.tabs.addTab(self.widget2, "阳")
        self.setWidget(self.tabs)
        self.make_gui()

    def make_gui(self):
        layout1 = QtWidgets.QGridLayout()
        layout2 = QtWidgets.QGridLayout()
        self.frequency_table = saved_frequencies_table(suffix=" MHz", 
                                                       sig_figs=4)
        self.entry_table = table_dropdowns_with_entry(limits=c.frequency_limit, 
                                                      suffix=" MHz", sig_figs=4, 
                                                      favorites=self.favorites, 
                                                      initial_selection=self.initial_selection, 
                                                      initial_values=self.initial_values)
        self.entry_table.setMinimumHeight(85)
        self.entry_table.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.entry_table.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        
        self.last_B = 0
        self.Bfield_entry = QtWidgets.QDoubleSpinBox()
        self.Bfield_entry.setRange(0, 10000)
        self.Bfield_entry.setDecimals(6)
        self.Bfield_entry.setSuffix(" mGauss")
        self.Bfield_entry.setValue(self.last_B)

        self.last_center = 0
        self.linecenter_entry = QtWidgets.QDoubleSpinBox()
        self.linecenter_entry.setRange(-50000, 0)
        self.linecenter_entry.setDecimals(6)
        self.linecenter_entry.setSuffix(" kHz")
        self.linecenter_entry.setValue(self.last_center)
        
        self.entry_Bfield_and_center_button = QtWidgets.QPushButton("Submit All")
        self.entry_Bfield_button = QtWidgets.QPushButton("Submit B")
        self.entry_center_button = QtWidgets.QPushButton("Submit Center")
        self.entry_Bfield_and_center_button.setStyleSheet("QPushButton:pressed{background-color: green}")
        self.entry_Bfield_button.setStyleSheet("QPushButton:pressed{background-color: green}")
        self.entry_center_button.setStyleSheet("QPushButton:pressed{background-color: green}")
        entry_B_center = QtWidgets.QHBoxLayout()
        entry_B_center.addWidget(self.entry_Bfield_button)
        entry_B_center.addWidget(self.entry_center_button)
        entry_B_center.addWidget(self.entry_Bfield_and_center_button)

        self.entry_button = QtWidgets.QPushButton("Submit Lines")
        self.entry_line1_button = QtWidgets.QPushButton("Submit Line One")
        self.entry_line2_button = QtWidgets.QPushButton("Submit Line Two")
        self.entry_button.setStyleSheet("QPushButton:pressed{background-color: green}")
        self.entry_line1_button.setStyleSheet("QPushButton:pressed{background-color: green}")
        self.entry_line2_button.setStyleSheet("QPushButton:pressed{background-color: green}")
        entry_lines = QtWidgets.QHBoxLayout()
        entry_lines.addWidget(self.entry_line1_button)
        entry_lines.addWidget(self.entry_line2_button)
        entry_lines.addWidget(self.entry_button)        

        self.copy_clipboard_button = QtWidgets.QPushButton("Copy Info to Clipboard")
        self.copy_clipboard_button.setStyleSheet("QPushButton:pressed{background-color: green}")

        self.remove_all_B_and_lines_button = QtWidgets.QPushButton("Remove all B and Line Centers")
        self.remove_all_B_and_lines_button.setStyleSheet("QPushButton:pressed{background-color: green}")

        self.remove_B_button = QtWidgets.QPushButton("Remove B")
        self.remove_line_center_button = QtWidgets.QPushButton("Remove Line Center")
        self.remove_B_button.setStyleSheet("QPushButton:pressed{background-color: green}")
        self.remove_line_center_button.setStyleSheet("QPushButton:pressed{background-color: green}")

        self.remove_B_count = QtWidgets.QSpinBox()
        self.remove_B_count.setRange(-20,20)
        self.remove_line_center_count = QtWidgets.QSpinBox()
        self.remove_line_center_count.setRange(-20,20)

        self.bool_keep_last_button = TextChangingButton()
        self.bool_keep_last_button.setStyleSheet("QPushButton:checked{background-color: green}")
        
        self.track_B_duration = QtWidgets.QSpinBox()
        self.track_B_duration.setKeyboardTracking(False)
        self.track_B_duration.setSuffix("min")
        self.track_B_duration.setRange(1, 1000)
        
        self.track_line_center_duration = QtWidgets.QSpinBox()
        self.track_line_center_duration.setKeyboardTracking(False)
        self.track_line_center_duration.setSuffix("min")
        self.track_line_center_duration.setRange(1, 1000)

        self.track_global_line_center_duration = QtWidgets.QSpinBox()
        self.track_global_line_center_duration.setKeyboardTracking(False)
        self.track_global_line_center_duration.setSuffix("min")
        self.track_global_line_center_duration.setRange(1, 1000)

        self.global_checkbox = TextChangingButton()
        self.global_checkbox.setStyleSheet("QPushButton:checked{background-color: green}")

        self.client_checkbox = dict.fromkeys(self.client_list)
        for client in self.client_list:
            self.client_checkbox[client] = QtWidgets.QCheckBox(client)

        self.current_line_center = QtWidgets.QLineEdit(readOnly = True)
        self.current_line_center.setAlignment(QtCore.Qt.AlignHCenter)

        self.current_B = QtWidgets.QLineEdit(readOnly = True)
        self.current_B.setAlignment(QtCore.Qt.AlignHCenter)

        self.current_time = QtWidgets.QLineEdit(readOnly = True)
        self.current_time.setAlignment(QtCore.Qt.AlignHCenter)
        
        layout1.addWidget(self.frequency_table, 0, 0, 6, 1)
        layout2.addWidget(self.entry_table, 0, 1, 2, 1)
        layout2.addLayout(entry_lines, 2, 1, 1, 1)
        layout2.addWidget(self.Bfield_entry, 3, 1, 1, 1)
        layout2.addWidget(self.linecenter_entry, 4, 1, 1, 1)
        layout2.addLayout(entry_B_center, 5, 1, 1, 1)

        hlp_layout = QtWidgets.QHBoxLayout()
        hlp_layout.addWidget(self.copy_clipboard_button)
    
        hlp_layout.addWidget(self.remove_all_B_and_lines_button)
        
        remove_B_layout = QtWidgets.QHBoxLayout() 
        remove_B_layout.addWidget(self.remove_B_count)
        remove_B_layout.addWidget(self.remove_B_button)    

        remove_line_center_layout = QtWidgets.QHBoxLayout() 
        remove_line_center_layout.addWidget(self.remove_line_center_count)
        remove_line_center_layout.addWidget(self.remove_line_center_button)    

        keep_local_B_layout = QtWidgets.QHBoxLayout()
        keep_local_B_layout.addWidget(QtWidgets.QLabel("Tracking Duration (Local B)"))
        keep_local_B_layout.addWidget(self.track_B_duration)


        keep_local_line_center_layout = QtWidgets.QHBoxLayout()
        keep_local_line_center_layout.addWidget(QtWidgets.QLabel("Tracking Duration (Local Line Center)"))
        keep_local_line_center_layout.addWidget(self.track_line_center_duration)

        keep_global_line_center_layout = QtWidgets.QHBoxLayout()
        keep_global_line_center_layout.addWidget(QtWidgets.QLabel("Tracking Duration (Global Line Center)"))
        keep_global_line_center_layout.addWidget(self.track_global_line_center_duration)

        global_line_center = QtWidgets.QHBoxLayout()
        global_line_center.addWidget(QtWidgets.QLabel("Global Line Center"))
        global_line_center.addWidget(self.global_checkbox)

        client_checkbox_layout = QtWidgets.QHBoxLayout()
        for client in self.client_list:
            client_checkbox_layout.addWidget(self.client_checkbox[client])

        keep_last_point = QtWidgets.QHBoxLayout()
        keep_last_point.addWidget(QtWidgets.QLabel("Keep Last Point"))
        keep_last_point.addWidget(self.bool_keep_last_button)

        line_center_show = QtWidgets.QHBoxLayout()
        line_center_show.addWidget(QtWidgets.QLabel("Current Line Center: "))
        line_center_show.addWidget(self.current_line_center)

        B_field_show = QtWidgets.QHBoxLayout()
        B_field_show.addWidget(QtWidgets.QLabel("Current B Field: "))
        B_field_show.addWidget(self.current_B)

        time_show = QtWidgets.QHBoxLayout()
        time_show.addWidget(QtWidgets.QLabel("Current Time: "))
        time_show.addWidget(self.current_time)
      
        layout1.addLayout(hlp_layout, 6, 0, 1, 1)
        layout2.addLayout(keep_last_point, 6, 1, 1, 1)
        layout1.addLayout(remove_B_layout, 7, 0, 1, 1)
        layout2.addLayout(global_line_center, 7, 1, 1, 1)
        layout2.addLayout(client_checkbox_layout, 8, 1, 1, 1)
        layout1.addLayout(remove_line_center_layout, 8, 0, 1, 1)
        layout2.addLayout(keep_global_line_center_layout, 9, 1, 1, 1)
        layout1.addLayout(line_center_show, 9, 0, 1, 1)
        layout2.addLayout(keep_local_line_center_layout, 10, 1, 1, 1)
        layout1.addLayout(B_field_show, 10, 0, 1, 1)
        layout2.addLayout(keep_local_B_layout, 11, 1, 1, 1)
        layout1.addLayout(time_show, 11, 0, 1, 1)

        self.widget1.setLayout(layout1)
        self.widget2.setLayout(layout2)
    