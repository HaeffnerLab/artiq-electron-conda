import asyncio
import logging
import labrad
import lmfit
import numpy as np
from PyQt5 import QtCore, QtWidgets, QtGui
from matplotlib.backends.backend_qt5agg import (NavigationToolbar2QT,
                                                FigureCanvasQTAgg)
from matplotlib.figure import Figure
from matplotlib.cm import get_cmap
from matplotlib import colors
from sipyco.pc_rpc import Server, Client
from artiq.readout_analysis.ion_state_detector import ion_state_detector
from artiq.dashboard.parameter_editor import ParameterEditorDock
from contextlib import suppress
from datetime import datetime as dt


logger = logging.getLogger(__name__)


class CameraReadoutDock(QtWidgets.QDockWidget):
    def __init__(self, acxn):
        QtWidgets.QDockWidget.__init__(self, "Camera Readout")
        self.acxn = acxn
        self.setObjectName("CameraReadoutHistogram")
        self.setFeatures(QtWidgets.QDockWidget.DockWidgetMovable |
                         QtWidgets.QDockWidget.DockWidgetFloatable)
        self.image = None
        self.image_region = None
        self.run_time = None
        self.main_widget = QtWidgets.QWidget()
        self.setWidget(self.main_widget)
        self.make_GUI()
        self.connect_GUI()
        self.connect_asyncio_server()

    def connect_asyncio_server(self):
        self.loop = asyncio.get_event_loop()
        self.asyncio_server = Server({"camera_reference_image": self.RemotePlotting(self)}, None, True)
        self.task = self.loop.create_task(self.asyncio_server.start("::1", 3288))


    class RemotePlotting:
        def __init__(self, plt):
            self.plt = plt

        def plot(self, image, image_region, run_time=None):
            self.plt.image = image
            self.plt.image_region = image_region
            if run_time is None:
                self.run_time = dt.now().strftime("%Y%m%d_%H%M.%S")
            try:
                cxn = labrad.connect()
                p = cxn.parametervault
            except:
                logger.error("Couldn't connect to parametervault", exc_info=True)
            N = int(p.get_parameter("IonsOnCamera", "ion_number"))
            x_axis = np.arange(image_region[2], image_region[3] + 1, image_region[0])
            y_axis = np.arange(image_region[4], image_region[5] + 1, image_region[1])
            xx, yy = np.meshgrid(x_axis, y_axis)

            fitter = ion_state_detector(N)
            result, params = fitter.guess_parameters_and_fit(xx, yy, image)
            p.set_parameter("IonsOnCamera","fit_background_level", params["background_level"].value)
            p.set_parameter("IonsOnCamera","fit_amplitude", params["amplitude"].value)
            p.set_parameter("IonsOnCamera","fit_rotation_angle", params["rotation_angle"].value)
            p.set_parameter("IonsOnCamera","fit_center_horizontal", params["center_x"].value)
            p.set_parameter("IonsOnCamera","fit_center_vertical", params["center_y"].value)
            p.set_parameter("IonsOnCamera","fit_spacing", params["spacing"].value)
            p.set_parameter("IonsOnCamera","fit_sigma", params["sigma"].value)

            self.plt.ax.clear()
            with suppress(Exception):
                self.plt.cb.remove()
            I = self.plt.ax.imshow(image, cmap="cividis", interpolation="spline16",
                               extent=[x_axis.min(), x_axis.max(), y_axis.max(), y_axis.min()])
            self.plt.cb = self.plt.fig.colorbar(I, fraction=0.046, pad=0.04)
            x_axis_fit = np.linspace(x_axis.min(), x_axis.max(), x_axis.size * 10)
            y_axis_fit = np.linspace(y_axis.min(), y_axis.max(), y_axis.size * 10)
            xx, yy = np.meshgrid(x_axis_fit, y_axis_fit)
            fit = fitter.ion_model(params, xx, yy)
            self.plt.ax.contour(x_axis_fit, y_axis_fit, fit, 3, colors=[(1., .49, 0., .75)])

            if result is not None:
                # print(lmfit.fit_report(result, show_correl=False))
                results_text = lmfit.fit_report(result, show_correl=False)
                param_results = results_text.split("\n")[-7:]
                for i, param_result in enumerate(param_results):
                    param_result = param_result.split("(")[0]
                    param_result = param_result.replace(" +/- ", "(")[:-1]
                    param_result = param_result.split(".")
                    param_result1 = param_result[1].split("(")
                    param_result[1] = param_result1[0][:3] + "("
                    try:
                        param_result[2] = param_result[2][:3]
                    except IndexError:
                        pass
                    param_result = ".".join(param_result)
                    param_result += ")"
                    param_results[i] = param_result
                results_text = "\n".join(param_results)
                results_text += "\n    chi_red = {:.2f}".format(result.redchi)
                results_text += "\n    runtime = " + str(self.run_time)
                self.plt.ax.annotate(results_text, (0.5, 0.75), xycoords="axes fraction",
                                     color=(1., .49, 0., 1.))

            self.plt.canvas.draw()
            self.plt.ax.relim()
            self.plt.ax.autoscale(enable=True, axis="both")

            cxn.disconnect()

        def enable_button(self):
            self.plt.reference_image_button.setDisabled(False)


    def closeEvent(self, event):
        self.task.cancel()
        self.loop.create_task(self.asyncio_server.stop())
        super(CameraReadoutDock, self).closeEvent(event)

    def make_GUI(self):
        layout = QtWidgets.QGridLayout()

        self.fig = Figure(figsize=(10,10), tight_layout=True)
        self.fig.patch.set_facecolor((.97, .96, .96))
        self.canvas = FigureCanvasQTAgg(self.fig)
        self.canvas.setParent(self)
        # self.canvas.setMinimumSize(800, 800)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor((.97,.96,.96))
        self.ax.tick_params(
                top=False, bottom=False, left=False, right=False,
                labeltop=True, labelbottom=True, labelleft=True, labelright=False
            )
        self.mpl_toolbar = NavigationToolbar2QT(self.canvas, self)
        self.canvas.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                                  QtWidgets.QSizePolicy.Expanding)
        self.ax.tick_params(axis="both", direction="in")
        self.reference_image_button = QtWidgets.QPushButton("reference image")

        try:
            cxn = labrad.connect()
            p = cxn.parametervault
        except:
            pass
        accessed_params = set()
        parameters = p.get_parameter_names("IonsOnCamera")
        for parameter in parameters:
            accessed_params.update({"IonsOnCamera." + parameter})

        d_accessed_parameter_editor = ParameterEditorDock(
                acxn=None,
                name="Camera Options",
                accessed_params=accessed_params
            )
        d_accessed_parameter_editor.setFeatures(QtGui.QDockWidget.NoDockWidgetFeatures)
        d_accessed_parameter_editor.setTitleBarWidget(QtGui.QWidget())
        d_accessed_parameter_editor.table.setMaximumWidth(390)

        layout.addWidget(self.mpl_toolbar, 0, 0, 1, 1)
        layout.addWidget(self.reference_image_button, 0, 2, 1, 1)
        layout.addWidget(d_accessed_parameter_editor, 1, 0, 1, 1)
        layout.addWidget(self.canvas, 1, 1, 1, 2)

        self.main_widget.setLayout(layout)

    def connect_GUI(self):
        self.scheduler = Client("::1", 3251, "master_schedule")
        self.reference_image_button.clicked.connect(self.get_reference_image)

    def get_reference_image(self):
        self.reference_image_button.setDisabled(True)
        expid = {"arguments": {},
                 "class_name": "ReferenceImage",
                 "file": "misc/reference_image.py",
                 "log_level": 30,
                 "repo_rev": None,
                 "priority": 2}
        self.scheduler.submit("main", expid, 2)

    def save_state(self):
        return {"image": self.image,
                "image_region": self.image_region,
                "run_time": self.run_time}

    def restore_state(self, state):
        if state["image"] is not None and state["image_region"] is not None:
            r = self.RemotePlotting(self)
            r.plot(state["image"], state["image_region"], run_time=state["run_time"])
