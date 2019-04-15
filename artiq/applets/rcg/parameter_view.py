from PyQt5 import QtWidgets, QtGui, QtCore
import h5py


class parameterView(QtWidgets.QWidget):
    def __init__(self, hfile, file_location):
        QtWidgets.QWidget.__init__(self)
        self.setWindowTitle("Parameter View -- {}".format(file_location))
        self.resize(700, 900)
        layout = QtWidgets.QVBoxLayout()

        tw = QtWidgets.QTreeWidget()
        tw.setHeaderLabels(["Collection", "Value"])
        tw.setAlternatingRowColors(True)
        tw.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        tw.setSortingEnabled(True)
        tw.setColumnWidth(0, 400)
        tw.setColumnWidth(1, 300)

        collections = hfile["parameters"]
        for collection in collections.keys():
            params = collections[collection]
            item = QtWidgets.QTreeWidgetItem()
            item.setText(0, collection)
            font = QtGui.QFont()
            font.setBold(True)
            item.setFont(0, font)
            item.setFlags(item.flags() ^ QtCore.Qt.ItemIsSelectable)
            for param in params.keys():
                child = QtWidgets.QTreeWidgetItem()
                child.setText(0, param)
                child.setText(1, params[param].value)
                item.addChild(child)
            tw.addTopLevelItem(item)
        
        tw.sortByColumn(0, 0)
        layout.addWidget(tw)
        self.setLayout(layout)