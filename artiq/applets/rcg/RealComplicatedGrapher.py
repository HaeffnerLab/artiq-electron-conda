import asyncio
import numpy as np
import PyQt5
from PyQt5 import QtWidgets, QtCore, QtGui
import pyqtgraph
import h5py
import pickle
import logging
import os
from datetime import datetime
from itertools import cycle
import pyperclip
from artiq.applets.rcg.fitting.fit_menu import fitMenu
import artiq.applets.rcg.RealComplicatedGrapherConfig as conf
from artiq.applets.rcg.tree_item import treeItem
from artiq.gui.tools import QDockWidgetCloseDetect
from artiq.protocols.pc_rpc import Server
from functools import partial


logger = logging.getLogger(__name__)
pyqtgraph.setConfigOptions(**conf.opts)


class rcgDock(QDockWidgetCloseDetect):
    def __init__(self, main_window):
        QDockWidgetCloseDetect.__init__(self, "Real Complicated Grapher")
        self.setObjectName("RCG")
        self.main_window = main_window
        self.main_window.addDockWidget(QtCore.Qt.TopDockWidgetArea, self)
        self.setFeatures(QtWidgets.QDockWidget.DockWidgetMovable)
        self.setFloating(True)
        self.rcg = RCG()
        self.setWidget(self.rcg)
        self.setTitleBarWidget(QtWidgets.QMainWindow())
        self.top_level_changed()
        self.connect_server()

    def top_level_changed(self):
        if self.isFloating():
            self.setWindowFlags(QtCore.Qt.CustomizeWindowHint | 
                                QtCore.Qt.Window |
                                QtCore.Qt.WindowMinimizeButtonHint |
                                QtCore.Qt.WindowMaximizeButtonHint |
                                QtCore.Qt.WindowCloseButtonHint)

    def connect_server(self):
        self.loop = asyncio.get_event_loop()
        self.server = Server({"rcg": self.RemotePlotting(self.rcg)}, None, True)
        self.loop.create_task(self.server.start(conf.host, conf.port))

    def closeEvent(self, event):
        for task in asyncio.Task.all_tasks():
            task.cancel() 
        self.loop.create_task(self.server.stop())
        super(rcgDock, self).closeEvent(event)


    class RemotePlotting:
        def __init__(self, rcg):
            self.rcg = rcg

        def echo(self, mssg):
            return mssg
        
        def get_tab_index_from_name(self, name):
            return self.rcg.tabs[name]
        
        def plot(self, x, y, tab_name="Current", plot_name=None, plot_title="new_plot"):
            if plot_name is None:
                plot_name = tab_name
            idx = self.rcg.tabs[tab_name]
            self.rcg.widget(idx).gw_dict[plot_name].add_plot_item(plot_title, x, y, append=True)
    
        def plot_from_file(self, file_, tab_name="Current", plot_name=None):
            if plot_name is None:
                plot_name = tab_name
            idx = self.rcg.tabs[tab_name]
            self.rcg.widget(idx).gw_dict[plot_name].upload_curve(file_=file_)

    
class RCG(PyQt5.QtWidgets.QTabWidget):
    def __init__(self):
        PyQt5.QtWidgets.QTabWidget.__init__(self)
        self.tabs = dict()
        for name, graphconfigs in conf.tab_configs:
            idx = self.addTab(graphTab(graphconfigs), name)
            self.tabs[name] = idx


class graphTab(QtWidgets.QWidget):
    def __init__(self, graphconfigs):
        QtWidgets.QWidget.__init__(self)
        layout = QtWidgets.QGridLayout()
        
        self.gw_dict = {}
        for gc in graphconfigs:
            gw = graphWindow(gc.name, gc.show_points, gc.ylims)
            layout.addWidget(gw, gc.row, gc.col, gc.rowspan, gc.colspan)
            self.gw_dict[gc.name] = gw
        layout.setHorizontalSpacing(3)
        layout.setVerticalSpacing(3)
        layout.setContentsMargins(0, 0, 0, 0)
        
        for gw in self.gw_dict.values():
            s1 = gw.tw.sizeHint().width()
            s2 = gw.pg.sizeHint().width()
            gw.main_widget.setSizes([s1 * .4, s2 * 1.25])

        self.setLayout(layout)

        autoload, autocheck = conf.auto_load
        if autoload:
            os.chdir(conf.data_dir)
            dir_ = datetime.now().strftime("/%Y-%m-%d")
            if not os.path.isdir(conf.data_dir + dir_):
                return
            for root, _, files in os.walk(conf.data_dir + dir_):
                for file_ in files:
                    if file_.endswith(".h5") or file_.endswith(".hdf5"):
                        h5file = os.path.join(root, file_)
                        try:
                            with h5py.File(h5file, "r") as f:
                                plot = f["data"].attrs["plot_show"]
                            self.gw_dict[plot].upload_curve(h5file, autocheck)
                        except:
                            continue


class graphWindow(QtWidgets.QWidget):
    def __init__(self, name, show_points, ylims):
        QtWidgets.QWidget.__init__(self)
        self.items = dict()
        self.show_points = show_points
        self.name = name
        self.autoscroll_enabled = True

        self.color_chooser = cycle(conf.default_colors)
        self.custom_colors = conf.custom_colors
        self.color_dialog = QtGui.QColorDialog()
        try:
            for i in range(self.color_dialog.customCount()):
                self.color_dialog.setCustomColor(i, self.custom_colors[i])
        except:
            # Not that important
            pass

        self.main_widget = QtWidgets.QSplitter()
        self.main_widget.setHandleWidth(1)

        self.tw = QtWidgets.QTreeWidget()
        self.tw.setHeaderHidden(True)
        palette = QtGui.QPalette()
        palette.setColor(9, QtGui.QColor(75, 75, 75))
        self.tw.setPalette(palette)
        self.tw.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.tw.setSelectionMode(QtWidgets.QAbstractItemView.ContiguousSelection)
        self.tw.setIndentation(0)

        self.tw.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)
        uncheck_action = QtWidgets.QAction("Uncheck", self.tw)
        uncheck_action.setShortcut("ENTER")
        uncheck_action.setShortcutContext(QtCore.Qt.WidgetShortcut)
        uncheck_action.triggered.connect(self.uncheck)
        self.tw.addAction(uncheck_action)
        
        uncheck_all_action = QtWidgets.QAction("Uncheck All", self.tw)
        uncheck_all_action.setShortcut("SHIFT+ENTER")
        uncheck_all_action.setShortcutContext(QtCore.Qt.WidgetShortcut)
        uncheck_all_action.triggered.connect(self.uncheck_all)
        self.tw.addAction(uncheck_all_action)
        
        fit_menu = QtWidgets.QMenu()
        fit_curve_action = QtWidgets.QAction("Fit", self.tw)
        fit_curve_action.setMenu(fit_menu)
        self.tw.addAction(fit_curve_action)
        for model in conf.fit_models:
            action = QtWidgets.QAction(model, self.tw)
            action.triggered.connect(partial(self.fit, model))
            fit_menu.addAction(action)
        self.fit_menu = fit_menu
        
        upload_curve_action = QtWidgets.QAction("Upload Curve", self.tw)
        upload_curve_action.setShortcut("TAB")
        upload_curve_action.setShortcutContext(QtCore.Qt.WidgetShortcut)
        upload_curve_action.triggered.connect(self.upload_curve)
        self.tw.addAction(upload_curve_action)
        
        remove_curve_action = QtWidgets.QAction("Remove", self.tw)
        remove_curve_action.setShortcut("DELETE")
        remove_curve_action.setShortcutContext(QtCore.Qt.WidgetShortcut)
        remove_curve_action.triggered.connect(self.remove_curve)
        self.tw.addAction(remove_curve_action)
        
        colors_menu = QtWidgets.QMenu()
        colors_action = QtWidgets.QAction("Color Options", self.tw)
        colors_action.setMenu(colors_menu)
        self.tw.addAction(colors_action)
        cycle_colors_action = QtWidgets.QAction("Cycle Colors", self.tw)
        cycle_colors_action.triggered.connect(self.cycle_colors)
        colors_menu.addAction(cycle_colors_action)
        change_color_action = QtWidgets.QAction("Change Color", self.tw)
        change_color_action.triggered.connect(self.change_color)
        colors_menu.addAction(change_color_action)
        use_default_colors_action = QtWidgets.QAction("Use Default Colors", self.tw)
        use_default_colors_action.triggered.connect(self.use_default_colors)
        colors_menu.addAction(use_default_colors_action)
        use_custom_colors_action = QtWidgets.QAction("Use Custom Colors", self.tw)
        use_custom_colors_action.triggered.connect(self.use_custom_colors)
        colors_menu.addAction(use_custom_colors_action)

        toggle_autoscroll_action = QtWidgets.QAction("Toggle AutoScroll", self.tw)
        toggle_autoscroll_action.setShortcut("SHIFT+TAB")
        toggle_autoscroll_action.setShortcutContext(QtCore.Qt.WidgetShortcut)
        toggle_autoscroll_action.triggered.connect(self.toggle_autoscroll)
        self.tw.addAction(toggle_autoscroll_action)

        self.pg = pyqtgraph.PlotWidget()
        self.pg.showGrid(x=True, y=True, alpha=0.7)
        self.pg.setYRange(*ylims)
        self.pg.setTitle(name)
        vb = self.pg.plotItem.vb
        self.img = pyqtgraph.ImageItem()
        vb.addItem(self.img)
        self.pg.scene().sigMouseMoved.connect(self.mouse_moved)
        self.pg.scene().sigMouseClicked.connect(self.mouse_clicked)
        
        self.main_widget.addWidget(self.tw)

        sublayout = QtWidgets.QVBoxLayout()
        sublayout.addWidget(self.pg)
        self.coords = QtWidgets.QLabel()
        self.coords.setStyleSheet("QLabel { background-color: rgb(75, 75, 75); "
                                            "color: white}")
        self.coords.setAutoFillBackground(True)
        sublayout.addWidget(self.coords)
        sublayout.setContentsMargins(0, 0, 0, 2)
        frame = QtWidgets.QFrame()
        frame.setLayout(sublayout)
        self.main_widget.addWidget(frame)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.main_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)
        
    def uncheck(self):
        for item in self.tw.selectedItems():
            item.setCheckState(0, 0)

    def fit(self, model):
        sI = self.tw.selectedItems()
        if len(sI) != 1:
            return
        name = sI[0].name
        if "::FIT::  " + name in self.items.keys():
            return
        if "::FIT::  " in name:
            return
        data = sI[0].x, sI[0].y
        self.fitmenu = fitMenu(model, name, data, self)
        self.fitmenu.show()
    
    def upload_curve(self, *args, file_=None, checked=True):
        if file_ is None:
            fname = QtWidgets.QFileDialog.getOpenFileName(self, 
                            self.tr("Upload Data"), conf.data_dir,
                            self.tr("HDF5 Files (*.h5 *.hdf5)"))[0]
            print("fname: ", fname)
        else:
            fname = file_
        try:
            f = h5py.File(fname, "r")
        except ValueError:
            # User exited dialog without selecting file
            return
        except OSError:
            self.warning_message("Can't open {}".format(fname))
            return
        try:
            data = f["data"]
        except KeyError:
            self.warning_message("HDF5 file does not contain a 'data' group.")
            return

        try: 
            plot_name = data.attrs["plot_show"]
            if plot_name != self.name:
                self.warning_message("Can't embed in this plot.")
                return
        except KeyError:
            self.warning_message("Can't determine which plot to embed in.")
            return

        ylist = []
        for key in data.keys():
            try:
                data[key].attrs["x-axis"]
                x = key
            except KeyError:
                ylist.append(key)
        X = f["data"][x].value
        Ylist = []
        txtlist = []
        for y in ylist:
            Ylist.append(f["data"][y].value)
            txt = y + " - " + fname.split(".")[0].split("/")[-1]
            if txt in self.items.keys():
                f.close()
                return
            txtlist.append(txt)
        for i in range(len(Ylist)):
            item = self.add_plot_item(txtlist[i], X, Ylist[i])
            if not checked:
                item.setCheckState(0, 0)
        f.close()

    def remove_curve(self, *args, curve=None):
        root = self.tw.invisibleRootItem()
        if curve is not None:
            items = [curve]
        else:
            items = self.tw.selectedItems()
        for item in items:
            item.remove_plot()
            (item.parent() or root).removeChild(item)
            removed_item = self.items.pop(item.text(0))
            del removed_item

    def uncheck_all(self):
        for widget in self.items.values():
            widget.setCheckState(0, 0)

    def cycle_colors(self):
        for item in self.tw.selectedItems():
            item.color = next(self.color_chooser)
            item.plot()

    def change_color(self):
        if (len(self.tw.selectedItems()) > 1 or
            len(self.tw.selectedItems()) == 0):
            return
        color = self.color_dialog.getColor(options=QtGui.QColorDialog.DontUseNativeDialog)
        for item in self.tw.selectedItems():
            item.color = color
            item.plot()
        N = self.color_dialog.customCount()
        for i in range(N):
            if self.color_dialog.customColor(i).getRgb() != (254, 254, 254):
                self.custom_colors = [self.color_dialog.customColor(i).getRgb() for i in range(N)]
                pickle.dump(self.custom_colors, 
                            open("/home/lattice/artiq/artiq/applets/rcg/custom_colors.pkl", "wb"))

    def use_default_colors(self):
        self.color_chooser = cycle(conf.default_colors)

    def use_custom_colors(self):
        self.color_chooser = cycle(self.custom_colors)

    def toggle_autoscroll(self):
        self.autoscroll_enabled = not self.autoscroll_enabled

    def warning_message(self, txt):
        msg = QtWidgets.QMessageBox()
        msg.setIcon(QtWidgets.QMessageBox.Warning)
        msg.setWindowTitle("Warning")
        msg.setText(txt)
        msg.exec_()

    def add_plot_item(self, name, x, y, over_ride_show_points=None, append=False):
        if name in self.items.keys() and not append:
            return
        if over_ride_show_points is not None:
            show_points = over_ride_show_points
        else:
            show_points = self.show_points
        if append and name in self.items.keys():
            item = self.items[name]
            item.plot_item.setData(x, y)
        else:
            color = next(self.color_chooser)
            item = treeItem(self, name, x, y, self.pg, color, show_points)
            self.items[name] = item
            self.tw.addTopLevelItem(item)

        if not self.autoscroll_enabled:
            return item
        try:
            (xmin_cur, xmax_cur), (ymin_cur, ymax_cur) = self.pg.viewRange()
            max_x, min_y, max_y = 0, 0, 0
            for item in self.items.values():
                localxmax = item.plot_item.dataBounds(0)[-1]
                localymin, localymax = item.plot_item.dataBounds(1)
                if localxmax > max_x:
                    max_x = localxmax
                if localymax > max_y:
                    max_y = localymax
                if localymin < min_y:
                    min_y = localymin
            window_width = xmax_cur - xmin_cur
            if max_x > xmin_cur + window_width:
                shift = (xmax_cur - xmin_cur) / 2
                xmin = xmin_cur + shift
                xmax = xmax_cur + shift
                limits = [xmin, xmax]
                self.pg.setXRange(*limits)
            if max_y > ymax_cur:
                ymax = max_y
            if min_y < ymin_cur:
                ymin = min_y
                limits = [ymin, ymax]
                self.pg.setYRange(*limits)
        except UnboundLocalError:
            # Autoscroll option is toggled simultaneously
            pass
        return item

    def mouse_moved(self, pos):
        pnt = self.img.mapFromScene(pos)
        str_ = "    ({:.5f} , {:.5f})".format(pnt.x(), pnt.y())
        self.coords.setText(str_)
        self.pos = pos

    def mouse_clicked(self, ev):
        if ev.button() == QtCore.Qt.RightButton:
            pnt = self.img.mapFromScene(ev.scenePos())
            pyperclip.copy(pnt.x())
            # Would like to copy to qt clipboard, for example
            # to copy peak point for driftracker. But the following
            # code doesn't work.
            # cb = QtWidgets.QApplication.clipboard()
            # cb.clear(mode=cb.Clipboard)
            # cb.setText(str(pnt.x()), mode=cb.Clipboard)


def main():
    from quamash import QEventLoop, QtWidgets, QtCore
    from artiq import __artiq_dir__ as artiq_dir
    from concurrent.futures._base import CancelledError
    app = QtWidgets.QApplication([])
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    class mainWindow(QtWidgets.QMainWindow):
        def __init__(self):
            QtWidgets.QMainWindow.__init__(self)
            icon = QtGui.QIcon(os.path.join(artiq_dir, "applets", 
                               "rcg", "rcg.svg"))
            self.setWindowIcon(icon)
            self.exit_request = asyncio.Event()
            self.setWindowTitle("Real Complicated Grapher")
        def closeEvent(self, event):
            event.ignore()
            self.exit_request.set()

    main_window = mainWindow()
    dock = rcgDock(main_window)
    dock.setFloating(False)
    main_window.addDockWidget(QtCore.Qt.TopDockWidgetArea, dock)
    main_window.show()
    try:
        loop.run_until_complete(main_window.exit_request.wait())
    except CancelledError:
        # Don't understand this
        pass
    finally:
        loop.close()
    

if __name__ == "__main__":
    main()
