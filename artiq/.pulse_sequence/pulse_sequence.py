import labrad
import numpy as np
import h5py as h5
import os
import csv
import time
import sys
import inspect
import logging
from artiq.language import scan
from artiq.language.core import TerminationRequested
from artiq.experiment import *
from artiq.protocols.pc_rpc import Client
from artiq.dashboard.drift_tracker import client_config as dt_config
from artiq.readout_analysis import readouts
from easydict import EasyDict as edict
from datetime import datetime
from bisect import bisect
from collections import OrderedDict as odict
from itertools import product
from operator import mul
from functools import partial
from HardwareConfiguration import dds_config


absolute_frequency_plots = ["CalibLine1", "CalibLine2", "Spectrum"]
logger = logging.getLogger(__name__)


class PulseSequence(EnvExperiment):
    is_ndim = False
    kernel_invariants = set()
    scan_params = odict()  # Not working as expected
    range_guess = dict()
    data = edict()
    run_after = dict()
    set_subsequence = dict()
    fixed_params = list()
    
    def build(self):
        self.setattr_device("core")
        self.setattr_device("scheduler")
        self.setattr_device("pmt")
        self.setattr_device("linetrigger_ttl")
        self.setattr_device("camera_ttl")
        self.multi_scannables = dict()
        self.rcg_tabs = dict()
        self.selected_scan = dict()
        self.update_scan_params(self.scan_params)
        self.run_in_build()

        # Load all AD9910 and AD9912 DDS channels specified in device_db
        self.dds_names = list()
        self.dds_offsets = list()
        self.dds_dp_flags = list()
        self.dds_device_list = list()
        for key, val in self.get_device_db().items():
            if isinstance(val, dict) and "class" in val:
                if val["class"] == "AD9910" or val["class"] == "AD9912":
                    setattr(self, "dds_" + key, self.get_device(key))
                    self.dds_device_list.append(getattr(self, "dds_" + key))
                    try:
                        self.dds_offsets.append(float(dds_config[key].offset))
                        self.dds_dp_flags.append(float(dds_config[key].double_pass))
                        self.dds_names.append(key)
                    except KeyError:
                        continue
        self.dds_729 = self.get_device("729G")
        self.dds_729_SP = self.get_device("SP_729G")
        self.cpld_list = [self.get_device("urukul{}_cpld".format(i)) for i in range(3)]
        self.setattr_device("core_dma")

    def prepare(self):
        # Grab parametervault params:
        G = globals().copy()
        self.G = G
        cxn = labrad.connect()
        self.global_cxn = labrad.connect(dt_config.global_address,
                                         password=dt_config.global_password,
                                         tls_mode="off")
        self.sd_tracker = self.global_cxn.sd_tracker_global
        p = cxn.parametervault
        collections = p.get_collections()
        # Takes over 1 second to do this. We should move away from using labrad units
        # in registry. Would be nice if parametervault was not a labrad server.
        D = dict()
        for collection in collections:
            d = dict()
            names = p.get_parameter_names(collection)
            for name in names:
                try:
                    param = p.get_parameter([collection, name])
                    try:
                        units = param.units
                        if units == "":
                            param = param[units]
                        else:
                            param = param[units] * G[units]
                    except AttributeError:
                        pass
                    except KeyError:
                        if (units == "dBm" or
                            units == "deg" or
                            units == ""):
                            param = param[units]
                    d[name] = param
                except:
                    # broken parameter
                    continue
            D[collection] = d
        for item in self.fixed_params:
            collection, param = item[0].split(".")
            D[collection].update({param: item[1]})
        self.p = edict(D)
        self.cxn = cxn

        # Grab cw parameters:
        # NOTE: Because parameters are grabbed in prepare stage,
        # loaded dds cw parameters may not be the most current.
        self.dds_list = list()
        self.freq_list = list()
        self.amp_list = list()
        self.att_list = list()
        self.state_list = list()

        for key, settings in self.p.dds_cw_parameters.items():
            self.dds_list.append(getattr(self, "dds_" + key))
            self.freq_list.append(float(settings[1][0]) * 1e6)
            self.amp_list.append(float(settings[1][1]))
            self.att_list.append(float(settings[1][3]))
            self.state_list.append(bool(float(settings[1][2])))

        # Try to make rcg/hist connections
        try:
            self.rcg = Client("::1", 3286, "rcg")
        except:
            self.rcg = None
        try:
            self.pmt_hist = Client("::1", 3287, "pmt_histogram")
        except:
            self.pmt_hist = None

        # Make scan object for repeating the experiment
        N = int(self.p.StateReadout.repeat_each_measurement)
        self.N = N

        # Create datasets and setup readout
        self.x_label = dict()
        self.timestamp = dict()
        scan_specs = dict()
        self.set_dataset("time", [])
        for seq_name, scan_dict in self.multi_scannables.items():
            self.data[seq_name] = dict(x=[], y=[])
            if isinstance(scan_dict[self.selected_scan[seq_name]], scan.NoScan):
                self.rcg_tabs[seq_name] = "Current"
            if self.is_ndim:
                scan_specs[seq_name] = [len(scan) for scan in scan_dict.values()]
            else:
                scan_specs[seq_name] = [len(scan_dict[self.selected_scan[seq_name]])]
        self.rm = self.p.StateReadout.readout_mode
        self.set_dataset("raw_run_data", np.full(N, np.nan))

        self.camera_string_states = []
        if self.rm in ["pmt", "pmt_parity"]:
            self.use_camera = False
            self.n_ions = len(self.p.StateReadout.threshold_list)
            for seq_name, dims in scan_specs.items():
                if not self.is_ndim:
                # Currently not supporting any default plotting for (n>1)-dim scans
                    for i in range(self.n_ions):
                        setattr(self, "{}-dark_ions:{}".format(seq_name, i), np.full(dims, np.nan))
                    if self.rm == "pmt_parity":
                        setattr(self, seq_name + "-parity", np.full(dims, np.nan))
                    x_array = np.array(list(self.multi_scannables[seq_name][self.selected_scan[seq_name]]))
                    self.x_label[seq_name] = [self.selected_scan[seq_name]]
                    f = seq_name + "-" if len(self.scan_params) > 1 else ""
                    f += self.x_label[seq_name][0]
                    setattr(self, f, x_array)
                    if (self.rcg_tabs[seq_name] in absolute_frequency_plots 
                        and not self.p.Display.relative_frequencies):
                        self.set_dataset(seq_name + "-raw_x_data", [], broadcast=True)
                else:
                    raise NotImplementedError("Ndim scans with PMT not implemented yet")
                    # self.x_label[seq_name] = [element[0] for element in self.scan_params[seq_name][0]]
                    # dims = [mul(*dims), len(dims)]
                dims.append(N)
                self.set_dataset("{}-raw_data".format(seq_name), np.full(dims, np.nan), broadcast=True)
                self.timestamp[seq_name] = None

        elif self.rm in ["camera", "camera_states", "camera_parity"]:
            self.use_camera = True
            self.n_ions = int(self.p.IonsOnCamera.ion_number)
            for seq_name, dims in scan_specs.items():
                if not self.is_ndim:
                # Currently not supporting any default plotting for (n>1)-dim scans
                    self.average_confidences = np.full(dims, np.nan)
                    if self.rm == "camera":
                        for i in range(self.n_ions):
                            setattr(self, "{}-ion number:{}".format(seq_name, i), np.full(dims, np.nan))
                    else:
                        self.camera_string_states = self.camera_states_repr(self.n_ions)
                        for state in self.camera_string_states:
                            setattr(self, "{}-{}".format(seq_name, state), np.full(dims, np.nan))
                        if self.rm == "camera_parity":
                            setattr(self, "{}-parity".format(seq_name), np.full(dims, np.nan))
                    x_array = np.array(list(list(self.multi_scannables[seq_name].values())[0]))
                    self.x_label[seq_name] = [self.selected_scan[seq_name]]
                    f = seq_name + "-" if len(self.scan_params) > 1 else ""
                    f += self.x_label[seq_name][0]
                    setattr(self, f, x_array)
                    if (self.rcg_tabs[seq_name] in absolute_frequency_plots
                        and not self.p.Display.relative_frequencies):
                        self.set_dataset(seq_name + "-raw_x_data", [], broadcast=True)
                else:
                    raise NotImplementedError("Ndim scans with camera not implemented yet")
                    # self.x_label[seq_name] = [element[0] for element in self.scan_params[seq_name][0]]
                    # dims = [mul(*dims), len(dims)]
                self.timestamp[seq_name] = None

        # Setup for saving data
        self.filename = dict()
        self.dir = os.path.join(os.path.expanduser("~"), "data",
                                datetime.now().strftime("%Y-%m-%d"), type(self).__name__)
        os.makedirs(self.dir, exist_ok=True)
        os.chdir(self.dir)

        # Lists to keep track of current line calibrations
        self.carrier_names = ["S+1/2D-3/2",
                              "S-1/2D-5/2",
                              "S+1/2D-1/2",
                              "S-1/2D-3/2",
                              "S+1/2D+1/2",
                              "S-1/2D-1/2",
                              "S+1/2D+3/2",
                              "S-1/2D+1/2",
                              "S+1/2D+5/2",
                              "S-1/2D+3/2"]
        # Convenience dictionary for user sequences
        self.carrier_dict = {"S+1/2D-3/2": 0,
                             "S-1/2D-5/2": 1,
                             "S+1/2D-1/2": 2,
                             "S-1/2D-3/2": 3,
                             "S+1/2D+1/2": 4,
                             "S-1/2D-1/2": 5,
                             "S+1/2D+3/2": 6,
                             "S-1/2D+1/2": 7,
                             "S+1/2D+5/2": 8,
                             "S-1/2D+3/2": 9}
        self.carrier_values = self.update_carriers()
        self.trap_frequency_names = list()
        self.trap_frequency_values = list()
        for name, value in self.p.TrapFrequencies.items():
            self.trap_frequency_names.append(name)
            self.trap_frequency_values.append(value)
        self.run_initially()
        
    @classmethod
    def set_global_params(cls):
        cls.accessed_params.update({
            "Display.relative_frequencies",
            "StateReadout.amplitude_397",
            "StateReadout.amplitude_866",
            "StateReadout.att_397",
            "StateReadout.att_866",
            "StateReadout.frequency_397",
            "StateReadout.frequency_866",
            "StateReadout.readout_mode",
            "StateReadout.doppler_cooling_repump_additional",
            "StateReadout.frequency_397"
            }
        )

    def run(self):
        if self.rm in ["camera", "camera_states", "camera_parity"]:
            self.initialize_camera()
        linetrigger = self.p.line_trigger_settings.enabled
        linetrigger_offset = float(self.p.line_trigger_settings.offset_duration)
        linetrigger_offset = self.core.seconds_to_mu(linetrigger_offset*us)
        is_multi = True if len(self.multi_scannables) > 1 else False
        for seq_name, scan_dict in self.multi_scannables.items():
            self.variable_parameter_names = list()
            self.variable_parameter_values = list()
            self.parameter_names = list()
            self.parameter_values = list()
            scanned_params = set(scan_dict.keys())
            self.set_global_params()
            all_accessed_params = self.accessed_params | scanned_params
            self.kernel_invariants = set()
            for mode_name, frequency in self.p.TrapFrequencies.items():
                self.kernel_invariants.update({mode_name})
                setattr(self, mode_name, frequency)
            abs_freqs = True if self.rcg_tabs[seq_name] in absolute_frequency_plots else False
            self.abs_freqs = abs_freqs
            self.seq_name = seq_name
            self.current_x_value = 9898989898.9898989898
            self.kernel_invariants.update({"dds_names", "dds_offsets", 
                                           "dds_dp_flags", "seq_name", "abs_freqs"})
            for param_name in all_accessed_params:
                collection, key = param_name.split(".")
                param = self.p[collection][key]
                new_param_name = param_name.replace(".", "_")
                if (type(param) is (float or int)) and (param_name in scanned_params):
                    self.variable_parameter_names.append(new_param_name)
                    if self.selected_scan[seq_name] == param_name:
                        self.variable_parameter_values.append(list(scan_dict[param_name])[0])
                    else:
                        collection, parameter = param_name.split(".")
                        self.variable_parameter_values.append(self.p[collection][parameter])
                else:
                    self.parameter_names.append(param_name)
                    self.parameter_values.append(param)
                    self.kernel_invariants.update({new_param_name})
                    setattr(self, new_param_name, param)
            current_sequence = getattr(self, seq_name)
            selected_scan = self.selected_scan[seq_name]
            self.selected_scan_name = selected_scan.replace(".", "_")
            if not self.is_ndim:
                scan_iterable = sorted(list(scan_dict[selected_scan]))
                ndim_iterable = [[0]]
            else:
                ms_list = [list(x) for x in scan_dict.values()]
                ndim_iterable = list(map(list, list(product(*ms_list))))
                scan_iterable = [0]
                self.set_dataset("x_data", ndim_iterable)
            scan_names = list(map(lambda x: x.replace(".", "_"), self.x_label[seq_name]))
            self.start_point1, self.start_point2 = 0, 0
            self.run_looper = True
            try:
                set_subsequence = self.set_subsequence[seq_name]
            except KeyError:
                @kernel
                def maybe_needed_delay(): 
                    delay(.1*us)
                set_subsequence = maybe_needed_delay
            if self.use_camera:
                readout_duration = self.p.StateReadout.camera_readout_duration
            else:
                readout_duration = self.p.StateReadout.pmt_readout_duration
            while self.run_looper:
                self.looper(current_sequence, self.N, linetrigger, linetrigger_offset, scan_iterable,
                        self.rm, readout_duration, seq_name, is_multi, self.n_ions, self.is_ndim, scan_names, 
                        ndim_iterable, self.start_point1, self.start_point2, self.use_camera, set_subsequence)
                if self.scheduler.check_pause():
                    try:
                        self.core.comm.close()
                        self.scheduler.pause()
                    except TerminationRequested:
                        try:
                            self.run_after[seq_name]()
                            continue
                        except:
                            self.set_dataset("raw_run_data", None, archive=False)
                            self.reset_cw_settings(self.dds_list, self.freq_list, self.amp_list,
                                                self.state_list, self.att_list)
                            return
            try:
                self.run_after[seq_name]()
            except FitError:
                logger.error("Fit failed.", exc_info=True)
                break
            except KeyError:
                continue
            except:
                logger.error("run_after failed for seq_name: {}.".format(seq_name), exc_info=True)
                continue
        self.set_dataset("raw_run_data", None, archive=False)
        self.reset_cw_settings(self.dds_list, self.freq_list, self.amp_list, self.state_list, self.att_list)

    @kernel
    def turn_off_all(self):
        self.core.reset()
        for cpld in self.cpld_list:
            cpld.init()
        for device in self.dds_device_list:
            device.init()
            device.sw.off()
    
    @kernel
    def pmt_readout(self, duration) -> TInt32:
        self.core.break_realtime()
        while True:
            try:
                self.dds_397.set_att(self.StateReadout_att_397)
                break
            except RTIOUnderflow:
                delay(1*us)
        self.dds_397.set(self.StateReadout_frequency_397, amplitude=self.StateReadout_amplitude_397)
        self.dds_866.set(self.StateReadout_frequency_866, amplitude=self.StateReadout_amplitude_866)
        self.dds_866.set_att(self.StateReadout_att_866)
        self.dds_397.sw.on()
        self.dds_866.sw.on()
        t_count = self.pmt.gate_rising(duration)
        delay(duration)
        self.dds_397.sw.off()
        delay(self.StateReadout_doppler_cooling_repump_additional)
        self.dds_866.sw.off()
        self.core.wait_until_mu(now_mu())
        return self.pmt.count(t_count)
            
    @kernel
    def line_trigger(self, offset):
        # Phase lock to mains
        self.core.reset()
        self.camera_ttl.off()
        trigger_time = -1
        while True:
            with parallel:
                t_gate = self.linetrigger_ttl.gate_rising(1000*us)
                trigger_time = self.linetrigger_ttl.timestamp_mu(t_gate)
            if trigger_time == -1:
                delay(10*us)
                continue
            break
        at_mu(trigger_time + offset)

    @kernel
    def looper(self, sequence, reps, linetrigger, linetrigger_offset, scan_iterable,
               readout_mode, readout_duration, seq_name, is_multi, number_of_ions,
               is_ndim, scan_names, ndim_iterable, start1, start2, use_camera, 
               set_subsequence):
        self.turn_off_all()
        if is_ndim:
            for i in list(range(len(ndim_iterable)))[start1:]:
                if self.scheduler.check_pause():
                    break
                if i == start1:
                    Start2 = start2
                else:
                    Start2 = 0
                for j in list(range(len(ndim_iterable[i])))[Start2:]:
                    if self.scheduler.check_pause():
                        self.set_start_point(1, i)
                        self.set_start_point(2, j)
                        break
                    for k in range(reps):
                        if linetrigger:
                            self.line_trigger(linetrigger_offset)
                        sequence()
                        if not use_camera:
                            pmt_count = self.pmt_readout(readout_duration)
                            self.record_result(seq_name + "-raw_data",
                                ((i, i + 1), (j, j + 1), (k, k + 1)), pmt_count)
                        else:
                            pass
                if (i + 1) % 5 == 0:
                    self.update_carriers()
                    pass
            else:
                self.set_run_looper_off()
            return

        i = 0  # For compiler, always needs a defined value (even when iterable empty)
        for i in list(range(len(scan_iterable)))[start1:]:
            if self.scheduler.check_pause():
                self.set_start_point(1, i)
                return
            if use_camera:
                self.prepare_camera()
            for l in list(range(len(self.variable_parameter_names))):
                self.set_variable_parameter(
                    self.variable_parameter_names[l], scan_iterable[i])
            set_subsequence()
            for j in range(reps):
                if linetrigger:
                    self.line_trigger(linetrigger_offset)
                else:
                    self.core.break_realtime()
                sequence()
                if not use_camera:
                    pmt_count = self.pmt_readout(readout_duration)
                    self.record_result("raw_run_data", j, pmt_count)
                else:
                    delay(10*us)
                    self.dds_397.set(self.StateReadout_frequency_397, 
                                     amplitude=self.StateReadout_amplitude_397)
                    self.dds_397.set_att(self.StateReadout_att_397)
                    self.dds_866.set(self.StateReadout_frequency_866, 
                                     amplitude=self.StateReadout_amplitude_866)
                    self.dds_866.set_att(self.StateReadout_att_866)
                    with parallel:
                        self.camera_ttl.pulse(100*us)
                        self.dds_397.sw.on()
                        self.dds_866.sw.on()
                    self.core.wait_until_mu(now_mu())
                    delay(readout_duration)
                    self.dds_397.sw.off()
                    delay(100*us)
                    self.dds_866.sw.off()
            if not use_camera:
                self.update_raw_data(seq_name, i)
                if readout_mode == "pmt":
                    self.update_pmt(seq_name, i, is_multi)
                elif readout_mode == "pmt_parity":
                    self.update_pmt(seq_name, i, is_multi, with_parity=True)
            elif (readout_mode == "camera" or
                  readout_mode == "camera_states" or
                  readout_mode == "camera_parity"):
                self.update_camera(seq_name, i, is_multi, readout_mode)

            rem = (i + 1) % 5
            if rem == 0:
                if (i + 1) == len(scan_iterable):
                    edge = True
                    i = 4
                else:
                    edge = False
                self.update_carriers_on_kernel(self.update_carriers())
                if not use_camera:
                    self.save_result(seq_name, is_multi, xdata=True, i=i, edge=edge)
                    self.send_to_hist(seq_name, i, edge=edge)
                    for k in range(number_of_ions):
                        self.save_result(seq_name + "-dark_ions:", is_multi, i=i, index=k, 
                                         edge=edge)
                    if readout_mode == "pmt_parity":
                        self.save_result(seq_name + "-parity", is_multi, i=i, edge=edge)
                else:
                    if readout_mode == "camera":
                        for k in range(number_of_ions):
                            self.save_result(seq_name + "-ion number:", is_multi, i=i, 
                                            index=k, edge=edge)
                    else:
                        for state in self.camera_string_states:
                            self.save_result(seq_name + "-" + state, is_multi, i=i, edge=edge)
                        if readout_mode == "camera_parity":
                            self.save_result(seq_name + "-parity", is_multi, i=i, edge=edge)
        
        else:
            self.set_run_looper_off()
            rem = (i + 1) % 5
            if rem == 0:
                return
            if not use_camera:
                self.send_to_hist(seq_name, rem, edge=True)
                self.save_result(seq_name, is_multi, xdata=True, i=rem, edge=True)
                for k in range(number_of_ions):
                    self.save_result(seq_name + "-dark_ions:", is_multi, i=i, index=k, 
                                     edge=True)
                if readout_mode == "pmt_parity":
                    self.save_result(seq_name + "-parity", is_multi, i=i, edge=True)
            else:
                if readout_mode == "camera":
                    for k in range(number_of_ions):
                        self.save_result(seq_name + "-ion number:", is_multi, i=i, 
                                        index=k, edge=True)
                else:
                    for state in self.camera_string_states:
                        self.save_result(seq_name + "-" + state, is_multi, i=i, edge=True)
                    if readout_mode == "camera_parity":
                        self.save_result(seq_name + "-parity", is_multi, i=i, edge=True)

    def set_start_point(self, point, i):
        if point == 1:
            self.start_point1 = i
        if point == 2:
            self.start_point2 = i

    def set_run_looper_off(self):
        self.run_looper = False

    @rpc(flags={"async"})
    def update_pmt(self, seq_name, i, is_multi, with_parity=False):
        data = sorted(self.get_dataset(seq_name + "-raw_data")[i])
        thresholds = self.p.StateReadout.threshold_list
        name = seq_name + "-dark_ions:{}"
        idxs = [0]
        scan_name = self.selected_scan_name.replace("_", ".", 1)
        scanned_x = sorted(list(self.multi_scannables[seq_name][scan_name]))
        if isinstance(self.multi_scannables[seq_name][scan_name], scan.NoScan):
            scanned_x = np.linspace(0, len(scanned_x), len(scanned_x))
        if self.abs_freqs and not self.p.Display.relative_frequencies:
            x = [i * 1e-6 for i in self.get_dataset(seq_name + "-raw_x_data")]
            if seq_name not in self.range_guess.keys():
                try:
                    self.range_guess[seq_name] = x[0], x[0] + (scanned_x[-1] - scanned_x[0]) * 1e-6
                except IndexError:
                    self.range_guess[seq_name] = None
        else:
            x = scanned_x
            if seq_name not in self.range_guess.keys():
                self.range_guess[seq_name] = x[0], x[-1]
            x = x[:i + 1]
        for threshold in thresholds:
            idxs.append(bisect(data, threshold))
        idxs.append(self.N)
        parity = 0
        for k in range(self.n_ions):
            dataset = getattr(self, name.format(k))
            if idxs[k + 1] == idxs[k]:
                dataset[i] = 0
            else:
                dataset[i] = (idxs[k + 1] - idxs[k]) / self.N
            if k % 2 == 0:
                parity += dataset[i]
            else:
                parity -= dataset[i]
            self.save_and_send_to_rcg(x, dataset[:i + 1],
                                      name.split("-")[-1].format(k), seq_name, is_multi, self.range_guess[seq_name])
        if with_parity:
            dataset = getattr(self, seq_name + "-parity")
            dataset[i] = parity
            self.save_and_send_to_rcg(x, dataset[:i + 1], "parity", seq_name, is_multi, self.range_guess[seq_name])

    # Need this to be a blocking call
    def update_camera(self, seq_name, i, is_multi, readout_mode):
        done = self.camera.wait_for_kinetic()
        if not done:
            self.analyze()
            raise Exception("Failed to get all Kinetic images from the camera.")
        images = self.camera.get_acquired_data(self.N)
        self.camera.abort_acquisition()
        ion_state, camera_readout, confidences = readouts.camera_ion_probabilities(images,
                                                        self.N, self.p.IonsOnCamera, readout_mode)
        self.average_confidences[i] = np.mean(confidences)
        scan_name = self.selected_scan_name.replace("_", ".", 1)
        scanned_x = sorted(list(self.multi_scannables[seq_name][scan_name]))
        if isinstance(self.multi_scannables[seq_name][scan_name], scan.NoScan):
            scanned_x = np.linspace(0, len(scanned_x), len(scanned_x))
        if self.abs_freqs and not self.p.Display.relative_frequencies:
            x = [i * 1e-6 for i in self.get_dataset(seq_name + "-raw_x_data")]
            if seq_name not in self.range_guess.keys():
                self.range_guess[seq_name] = x[0], x[0] + (scanned_x[-1] - scanned_x[0]) * 1e-6
        else:
            x = scanned_x
            if seq_name not in self.range_guess.keys():
                self.range_guess[seq_name] = x[0], x[-1]
            x = x[:i + 1]
        if readout_mode == "camera":
            name = seq_name + "-ion number:{}"
            for k in range(self.n_ions):
                dataset = getattr(self, name.format(k))
                dataset[i] = ion_state[k]
                self.save_and_send_to_rcg(x, dataset[:i + 1],
                    name.split("-")[-1].format(k), seq_name, is_multi, self.range_guess[seq_name])
        elif readout_mode == "camera_states" or readout_mode == "camera_parity":
            name = seq_name + "-{}"
            for k, state in enumerate(self.camera_states_repr(self.n_ions)):
                dataset = getattr(self, name.format(state))
                dataset[i] = ion_state[k]
                self.save_and_send_to_rcg(x, dataset[:i + 1],
                    name.split("-")[-1].format(state), seq_name, is_multi, self.range_guess[seq_name])
            if readout_mode == "camera_parity":
                dataset = getattr(self, seq_name + "-parity")
                dataset[i] = ion_state[-1]
                self.save_and_send_to_rcg(x, dataset[:i + 1], "parity", 
                                          seq_name, is_multi, self.range_guess[seq_name])

    @rpc(flags={"async"})
    def save_and_send_to_rcg(self, x, y, name, seq_name, is_multi, range_guess=None):
        if self.timestamp[seq_name] is None:
            self.start_time = datetime.now()
            self.timestamp[seq_name] = self.start_time.strftime("%H%M_%S")
            self.filename[seq_name] = self.timestamp[seq_name] + ".h5"
            with h5.File(self.filename[seq_name], "w") as f:
                datagrp = f.create_group("scan_data")
                datagrp.attrs["plot_show"] = self.rcg_tabs[seq_name]
                params = f.create_group("parameters")
                for collection in self.p.keys():
                    collectiongrp = params.create_group(collection)
                    for key, val in self.p[collection].items():
                        collectiongrp.create_dataset(key, data=str(val))
            with open("../scan_list", "a+") as csvfile:
                csvwriter = csv.writer(csvfile, delimiter=",")
                cls_name = type(self).__name__
                if is_multi:
                    cls_name += "_" + seq_name
                csvwriter.writerow([self.timestamp[seq_name], cls_name,
                                    os.path.join(self.dir, self.filename[seq_name])])
            self.save_result(seq_name, is_multi, xdata=True)
        delta = datetime.now() - self.start_time
        self.append_to_dataset("time", delta.total_seconds())
        if self.rcg is None:
            try:
                self.rcg = Client("::1", 3286, "rcg")
            except:
                return
        try:
            self.rcg.plot(x, y, tab_name=self.rcg_tabs[seq_name],
                          plot_title=self.timestamp[seq_name] + " - " + name, append=True,
                          file_=os.path.join(os.getcwd(), self.filename[seq_name]), range_guess=range_guess)
        except:
            return

    @kernel
    def get_variable_parameter(self, name) -> TFloat:
        value = 0.
        for i in list(range(len(self.variable_parameter_names))):
            if name == self.variable_parameter_names[i]:
                # if name == self.selected_scan_name:
                value = self.variable_parameter_values[i]
                break
                # else:
                #     value = self.variable_parameter_values[0]
                #     break
        else:
            exc = name + " is not a scannable parameter."
            self.host_exception(exc)  
        return value
    
    @kernel
    def set_variable_parameter(self, name, value):
        for i in list(range(len(self.variable_parameter_names))):
            if name != self.selected_scan_name:
                break
            if name == self.variable_parameter_names[i]:
                self.variable_parameter_values[i] = value
                break

    def host_exception(self, exc) -> TNone:
        raise Exception(exc)
    
    @kernel
    def reset_cw_settings(self, dds_list, freq_list, amp_list, state_list, att_list):
        # Return the CW settings to what they were when prepare stage was run
        self.core.reset()
        self.camera_ttl.off()
        for cpld in self.cpld_list:
            cpld.init()
        self.core.break_realtime()
        for i in range(len(dds_list)):
            try:
                dds_list[i].init()
            except RTIOUnderflow:
                self.core.break_realtime()
                dds_list[i].init()
            dds_list[i].set(freq_list[i], amplitude=amp_list[i])
            dds_list[i].set_att(att_list[i]*dB)
            if state_list[i]:
                dds_list[i].sw.on()
            else:
                dds_list[i].sw.off()
        self.camera_ttl.off()

    @rpc(flags={"async"})
    def record_result(self, dataset, idx, val):
        self.mutate_dataset(dataset, idx, val)

    @rpc(flags={"async"})
    def append_result(self, dataset, val):
        self.append_to_dataset(dataset, val)

    @rpc(flags={"async"})
    def update_raw_data(self, seq_name, i):
        raw_run_data = self.get_dataset("raw_run_data")
        self.record_result(seq_name + "-raw_data", i, raw_run_data)

    @rpc(flags={"async"})
    def save_result(self, name, is_multi, xdata=False, i="", index=None, edge=False):
        seq_name = name.split("-")[0]
        if index is not None:
            name += str(index)
        if xdata:
            try:
                x_label = self.x_label[name][0]
            except:
                x_label = "x"
            if self.abs_freqs and not self.p.Display.relative_frequencies:
                data = np.array([i * 1e-6 for i in self.get_dataset(seq_name + "-raw_x_data")])
            else:
                data = getattr(self, seq_name + "-" + x_label if is_multi else x_label)
            dataset = self.x_label[name][0]
            self.data[seq_name]["x"] = data  # This will fail for ndim scans
        else:
            data = getattr(self, name)
            dataset = name
            self.data[seq_name]["y"] = data  # This will fail for ndim scans
        with h5.File(self.filename[seq_name], "a") as f:
            datagrp = f["scan_data"]
            try:
                del datagrp[dataset]
            except:
                pass
            data = datagrp.create_dataset(dataset, data=data, maxshape=(None,))
            if xdata:
                data.attrs["x-axis"] = True

    @rpc(flags={"async"})
    def send_to_hist(self, seq_name, i, edge=False):
        data = self.get_dataset(seq_name + "-raw_data")
        if edge:
            data = data[-i:]
        else:
            try:
                data = data[i - 4:i + 1]
            except IndexError:
                data = data[i - 4:]
        self.pmt_hist.plot(data.flatten())

    @kernel
    def calc_frequency(self, line, detuning=0., 
                    sideband="", order=0., dds="", bound_param="") -> TFloat:
        relative_display = self.Display_relative_frequencies
        freq = detuning
        abs_freq = 0.
        line_set = False
        sideband_set = True if sideband == "" else False
        for i in range(10):
            if line == self.carrier_names[i]:
                freq += self.carrier_values[i]
                line_set = True
            if sideband != "" and i <= len(self.trap_frequency_names) - 1:
                if sideband == self.trap_frequency_names[i]:
                    freq += self.trap_frequency_values[i] * order
                    sideband_set = True
            if line_set and sideband_set:
                abs_freq = freq
                break
        if dds != "":
            for i in range(len(self.dds_names)):
                if dds == self.dds_names[i]:
                    freq += self.dds_offsets[i] * 1e6
                    if self.dds_dp_flags[i]:
                        freq /= 2
        if self.abs_freqs and bound_param != "" and not relative_display:
            if self.current_x_value == abs_freq:
                return 220*MHz - freq
            else:
                self.current_x_value = abs_freq
            for i in list(range(len(self.variable_parameter_names))):
                if bound_param == self.variable_parameter_names[i]:
                    self.append_result(self.seq_name + "-raw_x_data", abs_freq)
                    break
        return 220*MHz - freq
    
    # @rpc(flags={"async"})  Can't use async call if function returns non-None value
    def update_carriers(self) -> TList(TFloat):
        current_lines = self.sd_tracker.get_current_lines(dt_config.client_name)
        _list = [0.] * 10
        for carrier, frequency in current_lines:
            units = frequency.units
            abs_freq = frequency[units] * self.G[units]
            for i in range(10):
                if carrier == self.carrier_names[i]:
                    _list[i] = abs_freq
                    break
        return _list

    @kernel
    def update_carriers_on_kernel(self, new_carrier_values):
        for i in list(range(10)):
            self.carrier_values[i] = new_carrier_values[i]

    @kernel
    def get_729_dds(self, name):
        if name == "729L1":
            self.dds_729 = self.dds_729L1
            self.dds_729_SP = self.dds_SP_729L1
        elif name == "729L2":
            self.dds_729 = self.dds_729L2
            self.dds_729_SP = self.dds_SP_729L2
        elif name == "729G":
            self.dds_729 = self.dds_729G
            self.dds_729_SP = self.dds_SP_729G
        else:
            self.dds_729 = self.dds_729G
            self.dds_729_SP = self.dds_SP_729G

    def prepare_camera(self):
        self.camera.abort_acquisition()
        self.camera.set_number_kinetics(self.N)
        self.camera.start_acquisition()

    def initialize_camera(self):
        camera = self.cxn.andor_server
        camera.abort_acquisition()
        self.initial_exposure = camera.get_exposure_time()
        exposure = self.p.StateReadout.camera_readout_duration
        p = self.p.IonsOnCamera
        camera.set_exposure_time(exposure)
        self.image_region = [int(p.horizontal_bin),
                             int(p.vertical_bin),
                             int(p.horizontal_min),
                             int(p.horizontal_max),
                             int(p.vertical_min),
                             int(p.vertical_max)]
        camera.set_image_region(*self.image_region)
        camera.set_acquisition_mode("Kinetics")
        self.initial_trigger_mode = camera.get_trigger_mode()
        camera.set_trigger_mode("External")
        self.camera = camera

    def camera_states_repr(self, N):
        str_repr = []
        for name in range(2**N):
            bin_rep = np.binary_repr(name, N)
            state = ""
            for j in bin_rep[::-1]:
                state += "S" if j=="0" else "D"
            str_repr.append(state)
        return str_repr

    def analyze(self):
        try:
            self.run_finally()
        except FitError:
            logger.error("Final fit failed.", exc_info=True)
        except:
            pass
        if self.rm in ["camera", "camera_states", "camera_parity"]:
            self.camera.abort_acquisition()
            self.camera.set_trigger_mode(self.initial_trigger_mode)
            self.camera.set_exposure_time(self.initial_exposure)
            self.camera.set_image_region(1, 1, 1, 658, 1, 496)
            self.camera.start_live_display()
        self.cxn.disconnect()
        self.global_cxn.disconnect()
        try:
            self.rcg.close_rpc()
            self.pmt_hist.close_rpc()
        except:
            pass

    @classmethod
    def initialize_parameters(cls):
        for class_ in EnvExperiment.__subclasses__():
            cls.accessed_params.update(class_.accessed_params)

    def _set_subsequence_defaults(self, subsequence):
        d = subsequence.__dict__
        kwargs = dict()
        for key, value in d.items():
            if type(value) == str:
                try:
                    c, v = value.split(".")
                except AttributeError:
                    continue
                try:
                    pv_value = self.p[c][v]
                except KeyError:
                    continue
                try:
                    pv_value = float(pv_value)
                except:
                    pass
                kwargs[key] = pv_value
        for key, value in kwargs.items():
            setattr(subsequence, key, value)

    def add_subsequence(self, subsequence):
        self._set_subsequence_defaults(subsequence)
        subsequence.run = kernel(subsequence.subsequence)
        return subsequence

    def update_scan_params(self, scan_params, iteration=None):
        for seq_name, (rcg_tab, scan_list) in scan_params.items():
            if iteration is not None:
                seq_name += str(iteration)
            self.rcg_tabs[seq_name] = rcg_tab
            self.multi_scannables[seq_name] = odict()
            scan_names = list()
            for scan_param in scan_list:
                scan_names.append(scan_param[0])
                scan_name = seq_name + ":" + scan_param[0]
                if len(scan_param) == 4:
                    scannable = scan.Scannable(default=scan.RangeScan(*scan_param[1:]))
                elif len(scan_param) == 5:
                    scannable = scan.Scannable(default=scan.RangeScan(*scan_param[1:-1]), 
                                            unit=scan_param[-1])
                self.multi_scannables[seq_name].update(
                    {scan_param[0]: self.get_argument(scan_name, scannable, group=seq_name)})
            self.selected_scan[seq_name] = self.get_argument(seq_name + "-Scan_Selection", 
                                                EnumerationValue(scan_names), group=seq_name)
    
    def dynamically_generate_scans(self, main_scan, scan_params):
        scan_length = len(list(main_scan))
        for i in range(scan_length):
            self.update_scan_params(scan_params, iteration=i)
            for seq_name in scan_params.keys():
                self.set_subsequence[seq_name + str(i)] = self.set_subsequence[seq_name]
                setattr(self, seq_name + str(i), getattr(self, seq_name))
                            
    
    def run_in_build(self):
        pass
    
    def run_initially(self):
        pass

    def sequence(self):
        raise NotImplementedError

    def run_finally(self):
        pass


class FitError(Exception):
    pass
