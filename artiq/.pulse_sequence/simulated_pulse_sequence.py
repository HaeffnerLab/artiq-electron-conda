from datetime import datetime
from easydict import EasyDict as edict
import json
import labrad
import logging
import numpy as np
import os

logger = logging.getLogger(__name__)

class SimulatedDDSSwitch:
    def __init__(self):
        self.is_on = False
    def on(self):
        self.is_on = True
    def off(self):
        self.is_on = False
    def toggle(self):
        self.is_on = not self.is_on

class SimulatedDDS:

    def __init__(self, name):
        self.name = name
        self.sw = SimulatedDDSSwitch()
        self.freq = None
        self.amplitude = None
        self.phase = None
        self.ref_time_mu = None

    def set(self, freq, amplitude=None, phase=None, ref_time_mu=None):
        self.freq = freq
        if amplitude:
            self.amplitude = amplitude
        if phase:
            self.phase = phase
        if ref_time_mu:
            self.ref_time_mu = ref_time_mu

    def set_att(self, att):
        self.att = att

class PulseSequence:

    def __init__(self):
        self.p = None
        self.set_subsequence = dict()

        self.sequence_name = type(self).__name__
        self.timestamp = datetime.now().strftime("%H%M_%S")
        self.dir = os.path.join(os.path.expanduser("~"), "data", "simulation",
                                datetime.now().strftime("%Y-%m-%d"), self.sequence_name)
        os.makedirs(self.dir, exist_ok=True)
        os.chdir(self.dir)
    
    def output_parameters(self):
        if not self.p:
            self.p = self.load_parameter_vault()

        parameter_dict = {}
        for param_name in self.accessed_params:
            collection, key = param_name.split(".")
            param_value = self.p[collection][key]
            parameter_dict[param_name] = param_value

        with open(self.timestamp + "_params.txt", "w") as param_file:
            for k,v in parameter_dict.items():
                line = k + "=" + str(v)
                param_file.write(line + "\n")
                #logger.info(line)

    def simulate(self):
        if not self.p:
            self.p = self.load_parameter_vault()
        self.setup_carriers()
        self.setup_dds()
        self.setup_time_manager()

        # TODO: print out the 729 timings and settings to a file
        logger.info("*** calling simulate ***")
        self.run_initially()
        self.set_subsequence[self.sequence_name]()

        current_sequence = getattr(self, self.sequence_name)
        current_sequence()
        
        logger.info("*** simulate finished successfully ***")

    def setup_carriers(self):
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
        # in simulation mode, all carriers are 0 for now.
        self.carrier_values = [0.] * 10
        self.trap_frequency_names = list()
        self.trap_frequency_values = list()
        for name, value in self.p.TrapFrequencies.items():
            self.trap_frequency_names.append(name)
            self.trap_frequency_values.append(value)

    def setup_dds(self):
        self.dds_729G = SimulatedDDS("729G")
        self.dds_729L1 = SimulatedDDS("729L1")
        self.dds_729L2 = SimulatedDDS("729L2")
        self.dds_SP_729G = SimulatedDDS("SP_729G")
        self.dds_SP_729L1 = SimulatedDDS("SP_729L1")
        self.dds_SP_729L2 = SimulatedDDS("SP_729L2")
        self.dds_SP_729G_bichro = SimulatedDDS("SP_729G_bichro")
        self.dds_SP_729L1_bichro = SimulatedDDS("SP_729L1_bichro")
        self.dds_SP_729L2_bichro = SimulatedDDS("SP_729L2_bichro")
        self.dds_397 = SimulatedDDS("397")
        self.dds_854 = SimulatedDDS("854")
        self.dds_866 = SimulatedDDS("866")

    def setup_time_manager(self):
        class _FakeTimeManager:
            def _noop(self, *args, **kwargs):
                pass

            enter_sequential = _noop
            enter_parallel = _noop
            exit = _noop
            take_time_mu = _noop
            get_time_mu = _noop
            set_time_mu = _noop
            take_time = _noop

        from artiq.language import core as core_language
        core_language.set_time_manager(_FakeTimeManager())
                
    def get_729_dds(self, name="729G", id=0):
        if id == 0:
            self.dds_729 =           self.dds_729G if name == "729G" else self.dds_729L1 if name == "729L1" else self.dds_729L2
            self.dds_729_SP =        self.dds_SP_729G if name == "729G" else self.dds_SP_729L1 if name == "729L1" else self.dds_SP_729L2
            self.dds_729_SP_bichro = self.dds_SP_729G_bichro if name == "729G" else self.dds_SP_729L1_bichro if name == "729L1" else self.dds_SP_729L2_bichro
        elif id == 1:
            self.dds_7291 =           self.dds_729G if name == "729G" else self.dds_729L1 if name == "729L1" else self.dds_729L2
            self.dds_729_SP1 =        self.dds_SP_729G if name == "729G" else self.dds_SP_729L1 if name == "729L1" else self.dds_SP_729L2
            self.dds_729_SP_bichro1 = self.dds_SP_729G_bichro if name == "729G" else self.dds_SP_729L1_bichro if name == "729L1" else self.dds_SP_729L2_bichro
        elif id == 2:
            self.dds_729 =           self.dds_729G
            self.dds_729_SP_line1 =        self.dds_SP_729G 
            self.dds_729_SP_line1_bichro = self.dds_SP_729G_bichro 
            self.dds_729_SP_line2 =        self.dds_SP_729L2 
            self.dds_729_SP_line2_bichro = self.dds_SP_729L2_bichro 

    def prepare_pulse_with_amplitude_ramp(self, pulse_duration, ramp_duration, dds1_amp=0., use_dds2=False, dds2_amp=0.):
        self.pulse_duration = pulse_duration
        self.ramp_duration = ramp_duration
        self.dds1_amp = dds1_amp
        self.dds2_amp = dds2_amp
        self.use_dds2 = use_dds2
        
    def execute_pulse_with_amplitude_ramp(self, dds1_att=0., dds1_freq=0.,
                                          use_dds2=False, dds2_att=0., dds2_freq=0.):
        # TODO: need to implement this
        pass

    def add_subsequence(self, subsequence):
        self._set_subsequence_defaults(subsequence)
        subsequence.run = subsequence.subsequence
        try:
            subsequence.add_child_subsequences(self)
        except AttributeError:
            pass
        return subsequence

    def _set_subsequence_defaults(self, subsequence):
        d = subsequence.__dict__
        kwargs = dict()
        for key, value in d.items():
            if type(value) == str:
                try:
                    c, v = value.split(".")
                except AttributeError:
                    continue
                except ValueError:
                    continue
                try:
                    pv_value = self.p[c][v]
                except KeyError:
                    #TODO Ryan fix this - throw if a parameter isn't found
                    #raise Exception("Failed to find parameter: " + value)
                    continue
                try:
                    pv_value = float(pv_value)
                except:
                    pass
                kwargs[key] = pv_value
        for key, value in kwargs.items():
            setattr(subsequence, key, value)
            
    def get_offset_frequency(self, name):
        return 0.

    def calc_frequency(self, line, detuning=0.,
                    sideband="", order=0., dds="", bound_param=""):
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
        return freq

    def get_variable_parameter(self, name):
        # All params are fixed in simulation mode for now
        return getattr(self, name)

    def load_parameter_vault(self):
        # Grab parametervault params:
        G = globals().copy()
        cxn = labrad.connect()
        p = cxn.parametervault
        collections = p.get_collections()
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
                    setattr(self, collection + "_" + name, param)
                except:
                    # broken parameter
                    continue
            D[collection] = d
        return edict(D)