from artiq.language import scan
from artiq.experiment import *
from easydict import EasyDict as edict
from datetime import datetime
import labrad
import numpy as np
import h5py as h5
import os
import csv
from artiq.protocols.pc_rpc import Client
from bisect import bisect
from collections import OrderedDict as odict
from itertools import product
from operator import mul


class PulseSequence(EnvExperiment):
    fixed_params = list()
    accessed_params = set()
    kernel_invariants = set()
    scan_params = odict()

    def build(self):
        self.setattr_device("core")
        self.setattr_device("scheduler")
        self.setattr_device("pmt")
        self.setattr_device("LTriggerIN")
        self.multi_scannables = dict()
        self.rcg_tabs = dict()
        for seq_name, (scan_list, rcg_tab) in self.scan_params.items():
            self.multi_scannables[seq_name] = [self.get_argument(seq_name + ":" + scan_param[0],
                scan.Scannable(default=scan.RangeScan(*scan_param[1:])), group=seq_name) for scan_param in scan_list]
            self.rcg_tabs[seq_name] = rcg_tab
        self.setup()

        # Load all AD9910 and AD9912 DDS channels specified in device_db:
        for key, val in self.get_device_db().items():
            if isinstance(val, dict) and "class" in val:
                if val["class"] == "AD9910" or val["class"] == "AD9912":
                    setattr(self, "dds_" + key, self.get_device(key))
        self.cpld_list = [self.get_device("urukul{}_cpld".format(i)) for i in range(3)]

    def prepare(self):
        # Grab parametervault params:
        G = globals().copy()
        cxn = labrad.connect()
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
        cxn.disconnect()

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
       
        # Try to make rcg/hist connection
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
        for seq_name, scan_list in self.multi_scannables.items():
            scan_specs[seq_name] = [len(scan) for scan in scan_list]
        self.rm = self.p.StateReadout.readout_mode
        self.set_dataset("raw_run_data", np.full(N, np.nan))
        if self.rm in ["pmt", "pmt_parity"]:
            self.n_ions = len(self.p.StateReadout.threshold_list)
            for seq_name, dims in scan_specs.items():
                if len(dims) == 1:
                # Currently not supporting any default plotting for (n>1)-dim scans
                    for i in range(self.n_ions):
                        setattr(self, "{}-dark_ions:{}".format(seq_name, i), np.full(dims, np.nan))
                    if self.rm == "pmt_parity":
                        setattr(self, seq_name + "-parity", np.full(dims, np.nan))
                    x_array = np.array(list(self.multi_scannables[seq_name][0]))
                    self.x_label[seq_name] = self.scan_params[seq_name][0][0][0]
                    f = seq_name + "-" if len(self.scan_params) > 1 else ""
                    f += self.x_label[seq_name]
                    setattr(self, f, x_array)
                else:
                    self.x_label[seq_name] = [element[0] for element in self.scan_params[seq_name][0]]
                    dims = [mul(*dims), len(dims)]
                dims.append(N)
                self.set_dataset("{}-raw_data".format(seq_name), np.full(dims, np.nan), broadcast=True)
                self.timestamp[seq_name] = None
        elif self.rm in ["camera", "camera_states", "camera_parity"]:
            self.n_ions = int(self.p.IonsOnCamera.ion_number)
        
        # Setup for saving data
        self.filename = dict()
        self.dir = os.path.join(os.path.expanduser("~"), "data",
                                datetime.now().strftime("%Y-%m-%d"), type(self).__name__)
        os.makedirs(self.dir, exist_ok=True)
        os.chdir(self.dir)
        self.run_initially()

    def run(self):
        self.core.reset()
        linetrigger = self.p.line_trigger_settings.enabled
        linetrigger_offset = float(self.p.line_trigger_settings.offset_duration)
        linetrigger_offset = self.core.seconds_to_mu((16 + linetrigger_offset)*ms)
        for param in self.accessed_params:
            key = param.split(".")
            param = param.replace(".", "_")
            value = self.p[key[0]][key[1]]
            self.kernel_invariants.update({param})
            setattr(self, param, value)
        is_multi = True if len(self.multi_scannables) > 1 else False
        for seq_name, scan_list in self.multi_scannables.items():
            current_sequence = getattr(self, seq_name)
            if len(scan_list) == 1:
                is_ndim = False
                scan_iterable = list(scan_list[0])
                setter = lambda val: setattr(self, self.scan_params[seq_name][0][0][0].replace(".", "_"), val)
                setter(0.)
                ndim_iterable = [[0]]
            else:
                is_ndim = True
                ms_list = [list(x) for x in self.multi_scannables[seq_name]]
                ndim_iterable = list(map(list, list(product(*ms_list))))  # list city
                scan_iterable = [0] 
                self.set_dataset("x_data", ndim_iterable)
                setter = lambda x, val: setattr(self, x.replace(".", "_"), val)
            scan_names = list(map(lambda x: x.replace(".", "_"), list(self.x_label[seq_name])))
            self.looper(current_sequence, self.N, linetrigger, linetrigger_offset, scan_iterable, setter,
                        self.rm, self.p.StateReadout.pmt_readout_duration, seq_name, is_multi, self.n_ions, 
                        is_ndim, scan_names, ndim_iterable)
        self.set_dataset("raw_run_data", None, archive=False)
        self.reset_cw_settings(self.dds_list, self.freq_list, self.amp_list, self.state_list, self.att_list)

    @kernel
    def pmt_readout(self, duration) -> TInt32:
        self.core.break_realtime()
        t_count = self.pmt.gate_rising(duration)
        return self.pmt.count(t_count)
    
    @kernel
    def line_trigger(self, offset):
        # Phase lock to mains
        self.core.break_realtime()
        t_gate = self.LTriggerIN.gate_rising(16*ms)
        trigger_time = self.LTriggerIN.timestamp_mu(t_gate)
        at_mu(trigger_time + offset)
    
    @kernel
    def looper(self, sequence, reps, linetrigger, linetrigger_offset, scan_iterable, 
               setter, readout_mode, readout_duration, seq_name, is_multi, number_of_ions, 
               is_ndim, scan_names, ndim_iterable):
        if is_ndim:
            for i in range(len(ndim_iterable)):
                for j in range(len(ndim_iterable[i])):
                    setter(scan_names[j], ndim_iterable[i][j])
                    for k in range(reps):
                        sequence()
                        if readout_mode == "pmt" or readout_mode == "pmt_parity":
                            pmt_count = self.pmt_readout(readout_duration)
                            self.record_result(seq_name + "-raw_data", 
                                ((i, i + 1), (j, j + 1), (k, k + 1)), pmt_count)
                        elif (readout_mode == "camera" or
                              readout_mode == "camera_states" or
                              readout_mode == "camera_parity"):
                            pass
            return

        i = 0  # For compiler, always needs a defined value (even when iterable empty)
        for i in range(len(scan_iterable)):
            if self.scheduler.check_pause():
                break
            setter(scan_iterable[i])
            for j in range(reps):
                if not self.scheduler.check_pause():
                    if linetrigger:
                        self.line_trigger(linetrigger_offset)
                    sequence()
                    if readout_mode == "pmt" or readout_mode == "pmt_parity":
                        pmt_count = self.pmt_readout(readout_duration)
                        self.record_result("raw_run_data", j, pmt_count)
                    elif (readout_mode == "camera" or
                          readout_mode == "camera_states" or 
                          readout_mode == "camera_parity"):
                        pass
                else:
                    break
            self.update_raw_data(seq_name, i)
            if readout_mode == "pmt":
                self.update_pmt(seq_name, i, is_multi)
            elif readout_mode == "pmt_parity":
                self.update_pmt(seq_name, i, is_multi, with_parity=True)
            elif readout_mode == "camera":
                pass
            elif readout_mode == "camera_states":
                pass
            elif readout_mode == "camera_parity":
                pass
            rem = (i + 1) % 5
            if rem == 0:
                self.save_result(seq_name, is_multi, xdata=True, i=i)
                self.send_to_hist(seq_name, i)
                if readout_mode == "pmt" or readout_mode == "pmt_parity":
                    for k in range(number_of_ions):
                        self.save_result(seq_name + "-dark_ions:", is_multi, i=i, index=k)
                if readout_mode == "pmt_parity":
                    self.save_result(seq_name + "-parity", is_multi, i=i)
                elif readout_mode == "camera":
                    pass
                elif readout_mode == "camera_states":
                    pass
                elif readout_mode == "camera_parity":
                    pass
        else:
            rem = (i + 1) % 5
            self.send_to_hist(seq_name, rem, edge=True)
            self.save_result(seq_name, is_multi, xdata=True, i=rem, edge=True)
            if readout_mode == "pmt" or readout_mode == "pmt_parity":
                for k in range(number_of_ions):
                    self.save_result(seq_name + "-dark_ions:", is_multi, i=i, index=k, edge=True)
            if readout_mode == "pmt_parity":
                self.save_result(seq_name + "-parity", is_multi, i=i, edge=True)
            elif readout_mode == "camera":
                pass
            elif readout_mode == "camera_states":
                pass
            elif readout_mode == "camera_parity":
                pass

    @rpc(flags={"async"})
    def update_pmt(self, seq_name, i, is_multi, with_parity=False):
        data = sorted(self.get_dataset(seq_name + "-raw_data")[i])
        thresholds = self.p.StateReadout.threshold_list
        name = seq_name + "-dark_ions:{}"
        idxs = [0]
        x = getattr(self, 
                seq_name + "-" + self.x_label[seq_name] if is_multi else self.x_label[seq_name])[:i + 1]
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
                                      name.split("-")[-1].format(k), seq_name, is_multi)
        if with_parity:
            dataset = getattr(self, seq_name + "-parity")
            dataset[i] = parity
            self.save_and_send_to_rcg(x, dataset[:i + 1], "parity", seq_name, is_multi)

    @rpc(flags={"async"})
    def save_and_send_to_rcg(self, x, y, name, seq_name, is_multi):
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
                          file_=os.path.join(os.getcwd(), self.filename[seq_name]))
        except:
            return

    @kernel
    def reset_cw_settings(self, dds_list, freq_list, amp_list, state_list, att_list):
        # Return the CW settings to what they were when prepare
        # stage was run
        self.core.reset()
        for cpld in self.cpld_list:
            cpld.init()
        with parallel:
            for i in range(len(dds_list)):
                dds_list[i].init()
                dds_list[i].set(freq_list[i], amplitude=amp_list[i])
                dds_list[i].set_att(att_list[i]*dB)
                if state_list[i]:
                    dds_list[i].sw.on()
                else:
                    dds_list[i].sw.off()

    @rpc(flags={"async"})
    def record_result(self, dataset, idx, val):
        self.mutate_dataset(dataset, idx, val)

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
                x_label = self.x_label[name]
            except:
                x_label = "x"
            data = getattr(self, seq_name + "-" + x_label if is_multi else x_label)
            if not edge:
                data = data[i - 4:i + 1] if i else data
            else:
                data = data[-i:] 
            dataset = self.x_label[name]
        else:
            data = getattr(self, name)
            if not edge:
                data = data[i - 4:i + 1] if i else data
            else:
                data = data[-i:]
            dataset = name
        with h5.File(self.filename[seq_name], "a") as f:
            datagrp = f["scan_data"]
            try:
                datagrp[dataset]
            except KeyError:
                data = datagrp.create_dataset(dataset, data=data, maxshape=(None,))
                if xdata:
                    data.attrs["x-axis"] = True
                return
            datagrp[dataset].resize(datagrp[dataset].shape[0] + data.shape[0], axis=0)
            datagrp[dataset][-data.shape[0]:] = data

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

    @rpc(flags={"async"})
    def update_parameters(self):
        pass

    def add_sequence(self, subsequence, replacement_parameters={}):
        new_parameters = self.p.copy()
        for key, val in replacement_parameters.items():
            collection, parameter = key.split(".")
            new_parameters[collection].update({parameter: val})
        subsequence.p = edict(new_parameters)
        subsequence(self).run()

    def analyze(self):
        try:
            self.rcg.close_rpc()
            self.pmt_hist.close_rpc()
        except:
            pass
        self.run_finally()
    
    def setup(self):
        pass
    
    def run_initially(self):
        pass

    def sequence(self):
        raise NotImplementedError

    def run_finally(self):
        pass
