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
from artiq.applets.rcg.parameter_view import parameterView
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
        self.is_closed = False
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
        self.task = self.loop.create_task(self.server.start(conf.host, conf.port))

    def closeEvent(self, event):
        self.is_closed = True
        self.task.cancel()
        self.loop.create_task(self.server.stop())
        super(rcgDock, self).closeEvent(event)


    class RemotePlotting:
        def __init__(self, rcg):
            self.rcg = rcg

        def echo(self, mssg):
            return mssg

        def get_tab_index_from_name(self, name):
            return self.rcg.tabs[name]

        def plot(self, x, y, tab_name="Current", plot_name=None,
                 plot_title="new_plot", append=False, file_=None, range_guess=None):
            if plot_name is None:
                # need to clean this up
                for tab, graph_configs in conf.tab_configs:
                    for gc in graph_configs:
                        if gc.name == tab_name:
                            plot_name = tab_name
                            tab_name = tab
                            break
            idx = self.rcg.tabs[tab_name]
            if type(x) is np.ndarray:
                x = x[~np.isnan(x)]
            if type(y) is np.ndarray:
                y = y[~np.isnan(y)]
            if (plot_title in self.rcg.widget(idx).gw_dict[plot_name].items.keys() and
                not append):
                i = 1
                while True:
                    try_plot_title = plot_title + str(i)
                    if try_plot_title not in self.rcg.widget(idx).gw_dict[plot_name].items.keys():
                        plot_title = try_plot_title
                        break
                    else:
                        i += 1
            try:
                self.rcg.widget(idx).gw_dict[plot_name].add_plot_item(plot_title,
                                x, y, append=append, file_=file_, range_guess=range_guess)
            except AttributeError:
                # curve not currently displayed on graph
                return

        def plot_from_file(self, file_, tab_name="Current", plot_name=None):
            if plot_name is None:
                plot_name = tab_name
            idx = self.rcg.tabs[tab_name]
            self.rcg.widget(idx).gw_dict[plot_name].upload_curve(file_=file_)


class RCG(PyQt5.QtWidgets.QTabWidget):
    def __init__(self):
        PyQt5.QtWidgets.QTabWidget.__init__(self)
        self.setFocusPolicy(0)
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
                for file_ in sorted(files):
                    if file_.endswith(".h5") or file_.endswith(".hdf5"):
                        h5file = os.path.join(root, file_)
                        try:
                            with h5py.File(h5file, "r") as f:
                                plot = f["scan_data"].attrs["plot_show"]
                            self.gw_dict[plot].upload_curve(file_=h5file, checked=autocheck, startup=True)
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

        self.event = lambda evt: True

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
        uncheck_action.setShortcut("U")
        uncheck_action.setShortcutContext(QtCore.Qt.WidgetShortcut)
        uncheck_action.triggered.connect(self.uncheck)
        self.tw.addAction(uncheck_action)

        select_all_action = QtWidgets.QAction("Select All", self.tw)
        select_all_action.setShortcut("A")
        select_all_action.setShortcutContext(QtCore.Qt.WidgetShortcut)
        select_all_action.triggered.connect(lambda: self.tw.selectAll())
        self.tw.addAction(select_all_action)

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
        upload_curve_action.setShortcut("Ctrl+O")
        upload_curve_action.setShortcutContext(QtCore.Qt.WidgetShortcut)
        upload_curve_action.triggered.connect(self.upload_curve)
        self.tw.addAction(upload_curve_action)

        # For some reason, pyqtgraph autoscale not working well, so adding this hack
        snap_to_view_action = QtWidgets.QAction("snap to view", self.tw)
        snap_to_view_action.setShortcut("Ctrl+I")
        snap_to_view_action.setShortcutContext(QtCore.Qt.WidgetShortcut)
        snap_to_view_action.triggered.connect(self.snap_to_view)
        self.tw.addAction(snap_to_view_action)

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
        cycle_colors_action.setShortcut("Ctrl+N")
        cycle_colors_action.setShortcutContext(QtCore.Qt.WidgetShortcut)
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
        toggle_autoscroll_action.setShortcut("Ctrl+A")
        toggle_autoscroll_action.setShortcutContext(QtCore.Qt.WidgetShortcut)
        toggle_autoscroll_action.triggered.connect(self.toggle_autoscroll)
        self.tw.addAction(toggle_autoscroll_action)

        load_params_action = QtWidgets.QAction("Load Parameters", self.tw)
        load_params_action.setShortcut("Ctrl+P")
        load_params_action.setShortcutContext(QtCore.Qt.WidgetShortcut)
        load_params_action.triggered.connect(self.load_params)
        self.tw.addAction(load_params_action)

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
        self.fitmenu = fitMenu(model, name, sI[0].plot_item, self)
        self.fitmenu.show()

    def upload_curve(self, *args, file_=None, checked=True, startup=False):
        if file_ is None:
            fname = QtWidgets.QFileDialog.getOpenFileName(self,
                            self.tr("Upload Data"), conf.data_dir,
                            self.tr("HDF5 Files (*.h5 *.hdf5)"))[0]
        else:
            fname = file_
        try:
            f = h5py.File(fname, "r")
        except ValueError:
            # User exited dialog without selecting file
            return
        except OSError:
            if not startup:
                self.warning_message("Can't open {}".format(fname))
            return
        try:
            data = f["scan_data"]
        except KeyError:
            if not startup:
                self.warning_message("HDF5 file does not contain a 'scan_data' group.")
            return
        try:
            plot_name = data.attrs["plot_show"]
            if plot_name != self.name:
                if not startup:
                    self.warning_message("Embeddding {} in {} window.".format(plot_name, self.name))
                # return
        except KeyError:
            if not startup:
                self.warning_message("Can't determine which plot to embed in.")
            return
        ylist = []
        for key in data.keys():
            try:
                data[key].attrs["x-axis"]
                x = key
            except KeyError:
                ylist.append(key)
        try:
            X = f["scan_data"][x].value
        except:
            if not startup:
                self.warning_message("Can't determine which is x-axis.")
            return

        Ylist = []
        txtlist = []
        for y in ylist:
            try:
                Y = f["scan_data"][y].value
                assert len(X) == len(Y)
                Ylist.append(Y)
                txt = fname.split(".")[0].split("/")[-1]  + " - " + y
                if txt in self.items.keys():
                    f.close()
                    return
                txtlist.append(txt)
            except AssertionError:
                continue
        if len(Ylist) == 0:
            return
        for i in range(len(Ylist)):
            item = self.add_plot_item(txtlist[i], X, Ylist[i], file_=fname)
            self.pg.setXRange(X[0], X[-1])
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

    def cycle_colors(self):
        for item in self.tw.selectedItems():
            item.color = next(self.color_chooser)
            item.plot()

    def change_color(self):
        if len(self.tw.selectedItems()) != 1:
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

    def load_params(self):
        if len(self.tw.selectedItems()) != 1:
            return
        item = self.tw.selectedItems()[0]
        try:
            f = h5py.File(item.file, "r")
        except:
            self.warning_message("Couldn't open data file.")
            return
        try:
            f["parameters"]
        except:
            self.warning_message("Couldn't find parameters.")
            f.close()
            return
        self.paramaterview = parameterView(f, item.file)
        self.paramaterview.show()
        f.close()

    def warning_message(self, txt):
        msg = QtWidgets.QMessageBox()
        msg.setIcon(QtWidgets.QMessageBox.Warning)
        msg.setWindowTitle("Warning")
        msg.setText(txt)
        msg.exec_()

    def snap_to_view(self):
        globalymin, globalymax, globalxmin, globalxmax = None, None, None, None
        for item in self.items.values():
            try:
                ymin, ymax = item.plot_item.dataBounds(1)
                xmin, xmax = item.plot_item.dataBounds(0)
            except AttributeError:
                continue
            if globalymin is None:
                globalymin = ymin
            elif globalymin > ymin:
                globalymin = ymin
            elif globalymax < ymax:
                globalymax = ymax
            if globalymax is None:
                globalymax = ymax
            if globalxmin is None:
                globalxmin = xmin
            if globalxmax is None:
                globalxmax = xmax
            elif globalxmin > xmin:
                globalxmin = xmin
            elif globalxmax < xmax:
                globalxmax = xmax
        self.pg.setXRange(globalxmin, globalxmax)
        self.pg.setYRange(globalymin, globalymax)

    def add_plot_item(self, name, x, y, over_ride_show_points=None,
                      append=False, file_=None, range_guess=None):
        if name in self.items.keys() and not append:
            return
        if over_ride_show_points is not None:
            show_points = over_ride_show_points
        else:
            show_points = self.show_points
        if append and name in self.items.keys():
            item = self.items[name]
            item.plot_item.setData(sorted(x), [i for _, i in sorted(zip(x, y))])
        else:
            color = next(self.color_chooser)
            try:
                item = treeItem(self, name, x, y, self.pg, color, show_points, file_=file_)
            except Exception as e:
                print("exception: ", e)
            self.items[name] = item
            self.tw.addTopLevelItem(item)
        (xmin_cur, xmax_cur), (ymin_cur, ymax_cur) = self.pg.viewRange()
        if range_guess is not None and self.autoscroll_enabled:
            if (xmin_cur > range_guess[0] or xmax_cur < range_guess[1] or
                    abs(xmax_cur - xmin_cur) > abs(range_guess[1] - range_guess[0]) * 3):
                self.pg.setXRange(*range_guess)

        try:
            max_x, min_y, max_y = None, None, None

            max_x = max(list(x))#self.items[name].plot_item.databounds(0)[-1]

            # Can optionally auto adjust range in response to all currently plotted items,
            # by uncommenting below
            for item in self.items.values():
            #     localxmax = item.plot_item.dataBounds(0)[-1]
                localymin, localymax = item.plot_item.dataBounds(1)
            #     if max_x is None:
            #         max_x = localxmax
            #     elif localxmax > max_x:
            #         max_x = localxmax
                if max_y is None:
                    max_y = localymax
                elif localymax > max_y:
                    max_y = localymax
                if min_y is None:
                    min_y = localymin
                elif localymin < min_y:
                    min_y = localymin

            window_width = abs(xmax_cur - xmin_cur)
            if not self.autoscroll_enabled:
                return item
            if max_x > xmin_cur + window_width:
                shift = window_width / 2
                xmax = max_x + shift
                limits = [xmin_cur, xmax]
                self.pg.setXRange(*limits)
            if max_y > ymax_cur:
                ymax = max_y
            if min_y < ymin_cur:
                ymin = min_y
                limits = [ymin, ymax]
                # self.pg.setYRange(*limits)
        except UnboundLocalError:
            # Autoscroll option is toggled simultaneously
            pass
        except AttributeError:
            # curve is not currently displayed on graph
            pass
        return item

    def mouse_moved(self, pos):
        pnt = self.img.mapFromScene(pos)
        xpnt = pnt.x()
        ypnt = pnt.y()
        if abs(xpnt) < 1e-3 or abs(xpnt) > 1e4:
            pnt_x = "{:.2E}".format(xpnt)
        else:
            pnt_x = "{:.4f}".format(xpnt)
        if abs(ypnt) < 1e-3 or abs(ypnt) > 1e4:
            pnt_y = "{:.2E}".format(ypnt)
        else:
            pnt_y = "{:.4f}".format(ypnt)
        str_ = "    ({} , {})".format(pnt_x, pnt_y)
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
    app = QtWidgets.QApplication(["Real Complicated Grapher"])
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
