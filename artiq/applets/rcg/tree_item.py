import PyQt5
from PyQt5 import QtWidgets, QtGui, QtCore
from datetime import datetime
import pyqtgraph
import pyperclip

class checkStateChanged(QtCore.QObject):
    checkStateChanged = QtCore.pyqtSignal(str, bool)

class treeItem(QtWidgets.QTreeWidgetItem):
    signal = checkStateChanged()
    def __init__(self, parent_, txt, x, y, axes, color, show_points, file_=None):
        QtWidgets.QTreeWidgetItem.__init__(self)
        self.axes = axes; self.x = x; self.y = y; self.name = txt
        self.color = color; self.show_points = show_points
        self.file = file_
        self.parent_ = parent_
        self.plot_item = None
        self.is_selected = False
        self.setText(0, txt)
        self.setForeground(0, QtGui.QBrush(QtGui.QColor("white")))
        font = QtGui.QFont()
        font.setBold(True)
        self.setFont(0, font)
        self.setCheckState(0, 2)
        self.plot()
        self.signal.checkStateChanged.connect(self.item_check_state_changed)

    def plot(self):
        if self.plot_item is not None:
            self.remove_plot()
        self.plot_item = self.axes.plot(x=self.x, y=self.y,
                                        pen=pyqtgraph.mkPen(self.color, width=2),
                                        symbolBrush=self.color if self.show_points else None,
                                        symbol="o" if self.show_points else None)
        self.plot_item.sigClicked.connect(self.curve_clicked)
        self.plot_item.sigPlotChanged.connect(self.plot_changed)

    def curve_clicked(self, curve, *args):
        for c in list(self.parent_.items.values()):
            if c.plot_item is curve:

                if not self.is_selected:
                    lighter_color = c.color[0]//3, c.color[1]//2, c.color[2]//2
                    c.plot_item.setShadowPen(color=lighter_color, width=12)
                    self.is_selected = True
                    self.parent_.tw.clearSelection()
                    self.setSelected(True)
                else:
                    menu = QtGui.QMenu()
                    deselect_action = QtWidgets.QAction("deselect", menu)
                    deselect_action.triggered.connect(self.deselect)
                    menu.addAction(deselect_action)
                    fit_curve_action = QtWidgets.QAction("Fit", menu)
                    fit_curve_action.setMenu(self.parent_.fit_menu)
                    menu.addAction(fit_curve_action)
                    copy_to_clipboard_action = QtWidgets.QAction("Copy to Clipboard", menu)
                    copy_to_clipboard_action.triggered.connect(self.copy_to_clipboard)
                    menu.addAction(copy_to_clipboard_action)
                    # probably the wrong way to do this
                    p = QtCore.QPoint()
                    p.setX(self.parent_.pos.x() + 100)  # Values determined empirically
                    p.setY(self.parent_.pos.y() - 10)   #
                    menu.exec_(self.parent_.mapToGlobal(p))
            else:
                if c.plot_item is not None:
                    c.plot_item.setShadowPen(color=c.color, width=2)
                c.is_selected = False

    def deselect(self):
        self.parent_.tw.clearSelection()
        self.plot_item.setShadowPen(color=self.color, width=2)
        self.is_selected = False

    def copy_to_clipboard(self):
        # Only works if data was generated that day
        day = datetime.now().strftime("%Y%m%d")
        data = self.name.split("-")[0].replace(" ", "").replace("_", ".")
        pyperclip.copy("#data {}/{}#".format(day, data))

    def remove_plot(self):
        if self.plot_item is None:
            return
        self.axes.removeItem(self.plot_item)
        del self.plot_item
        self.plot_item = None

    def setData(self, index, role, value):
        super(treeItem, self).setData(index, role, value)
        if role == 10:
            # 10 --> QtCore.Qt.CheckStateRole
            self.signal.checkStateChanged.emit(str(self), value)

    def item_check_state_changed(self, name, val):
        if name != str(self):
            return
        if val:
            self.plot()
        else:
            self.remove_plot()

    def plot_changed(self, curve):
        self.x, self.y = curve.getData()
