from artiq.language import core as core_language
from datetime import datetime
from easydict import EasyDict as edict
import json
import labrad
from labrad.units import WithUnit
import logging
import numpy as np
import os

logger = logging.getLogger(__name__)

class SimulatedDDSSwitch:
    def __init__(self, dds):
        self.dds = dds
        self.is_on = False
    def on(self):
        if not self.is_on:
            self.is_on = True
            self.dds._switched_on()
    def off(self):
        if self.is_on:
            self.is_on = False
            self.dds._switched_off()
    def toggle(self):
        if self.is_on:
            self.off()
        else:
            self.on()

class SimulatedDDS:

    def __init__(self, name, pulse_sequence):
        self.name = name
        self.pulse_sequence = pulse_sequence
        self.sw = SimulatedDDSSwitch(self)
        self.freq = 0.0
        self.amplitude = 0.0
        self.phase = 0.0
        self.ref_time_mu = 0

    def _switched_on(self):
        self.time_switched_on = self.pulse_sequence.time_manager.get_time()

    def _switched_off(self):
        if self.time_switched_on is not None:
            time_switched_off = self.pulse_sequence.time_manager.get_time()
            self.pulse_sequence.report_pulse(self, self.time_switched_on, time_switched_off)
            self.time_switched_on = None

    def set(self, freq, amplitude=None, phase=None, ref_time_mu=None):
        if isinstance(freq, WithUnit):
            freq = freq['Hz']

        self.freq = freq
        if amplitude:
            self.amplitude = amplitude
        if phase:
            self.phase = phase
        if ref_time_mu:
            self.ref_time_mu = ref_time_mu

    def set_att(self, att):
        self.att = att

class _FakeCore:
    def seconds_to_mu(self, time):
        return time

class PulseSequence:

    scan_params = dict()

    def __init__(self):
        self.p = None
        self.set_subsequence = dict()
        self.selected_scan = dict()
        self.time_manager = None
        self.simulated_pulses = []
        self.core = _FakeCore()

        csv_headers = ["Name","On","Off","Frequency","Amplitude","Phase"]
        self.simulated_pulses.append(csv_headers)

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

        filename = self.timestamp + "_params.txt"
        with open(filename, "w") as param_file:
            for k,v in parameter_dict.items():
                line = k + "=" + str(v)
                param_file.write(line + "\n")
                logger.info(line)

        logger.info("*** parameters written to " + os.path.join(self.dir, filename))

    def report_pulse(self, dds, time_switched_on, time_switched_off):
        simulated_pulse = [
            dds.name,
            str(round(time_switched_on, 8)),
            str(round(time_switched_off, 8)),
            str(dds.freq),
            str(dds.amplitude),
            str(dds.phase)
        ]
        self.simulated_pulses.append(simulated_pulse)

    def simulate(self):
        if not self.p:
            self.p = self.load_parameter_vault()
        self.setup_carriers()
        self.setup_dds()
        self.setup_time_manager()
        
        self.N = int(self.p.StateReadout.repeat_each_measurement)
        
        for seq_name, scan_list in PulseSequence.scan_params.items():
            self.selected_scan[seq_name] = seq_name

        self.run_initially()
        main_sequence_name = list(self.set_subsequence.keys())[0]
        self.set_subsequence[main_sequence_name]()

        current_sequence = getattr(self, main_sequence_name)
        current_sequence()

        filename = self.timestamp + "_pulses.csv"
        with open(filename, "w") as pulses_file:
            for pulse in self.simulated_pulses:
                line = ",".join(pulse)
                pulses_file.write(line + "\n")
                logger.info(line)
        
        logger.info("*** pulse sequence written to " + os.path.join(self.dir, filename))

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

    def get_trap_frequency(self, name):
        freq = 0.
        for i in range(len(self.trap_frequency_names)):
            if self.trap_frequency_names[i] == name:
                freq = self.trap_frequency_values[i]
                if isinstance(freq, WithUnit):
                    freq = freq['Hz']
                return freq
        return 0.

    def make_dds(self, name):
        return SimulatedDDS(name, self)

    def setup_dds(self):
        self.dds_729G = self.make_dds("729G")
        self.dds_729L1 = self.make_dds("729L1")
        self.dds_729L2 = self.make_dds("729L2")
        self.dds_SP_729G = self.make_dds("SP_729G")
        self.dds_SP_729L1 = self.make_dds("SP_729L1")
        self.dds_SP_729L2 = self.make_dds("SP_729L2")
        self.dds_SP_729G_bichro = self.make_dds("SP_729G_bichro")
        self.dds_SP_729L1_bichro = self.make_dds("SP_729L1_bichro")
        self.dds_SP_729L2_bichro = self.make_dds("SP_729L2_bichro")
        self.dds_397 = self.make_dds("397")
        self.dds_854 = self.make_dds("854")
        self.dds_866 = self.make_dds("866")

    def setup_time_manager(self):
        class _FakeTimeManager:
            def __init__(self):
                self.time = 0.

            def _noop(self, *args, **kwargs):
                pass

            def _take_time(self, duration):
                if isinstance(duration, WithUnit):
                    duration = duration['s']
                self.time += duration

            def _get_time(self):
                return self.time

            enter_sequential = _noop
            enter_parallel = _noop
            exit = _noop
            set_time_mu = _noop
            get_time_mu = _get_time
            get_time = _get_time
            take_time_mu = _take_time
            take_time = _take_time

        self.time_manager = _FakeTimeManager()
        core_language.set_time_manager(self.time_manager)
                
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

    def make_random_list(self, n, mean, std, min=None, max=None):
        #
        # Returns a list of n values pulled from a Gaussian distribution
        # with the given mean and standard deviation, in the range [min, max].
        #
        values = (std * np.random.randn(n) + mean).tolist()
        for i in range(len(values)):
            # make sure the values are between min and max
            if min:
                values[i] = max(min, amps[i])
            if max:
                values[i] = min(max, amps[i])
        return values

    def make_random_amplitudes(self, n, mean, std):
        #
        # Returns a list of n amplitudes pulled from a Gaussian distribution
        # with the given mean and standard deviation, in the range [0,1].
        #
        return self.make_random_list(n, mean, std, min=0.0, max=1.0)

    def make_random_frequencies(self, n, mean, std):
        #
        # Returns a list of n frequencies pulled from a Gaussian distribution
        # with the given mean and standard deviation, in the range [0,].
        #
        return self.make_random_list(n, mean, std, min=0.0)

    def generate_single_pass_noise_waveform(self, mean, std, freq_noise=False):
        pass
    
    def prepare_noisy_single_pass(self, freq_noise=False, id=0):
        pass

    def start_noisy_single_pass(self, phase_ref_time, freq_noise=False,
        freq_sp=WithUnit(80, 'MHz'), amp_sp=1.0, att_sp=8.0, phase_sp=0.,
        use_bichro=False, freq_sp_bichro=WithUnit(80, 'MHz'), amp_sp_bichro=1.0, att_sp_bichro=8.0, phase_sp_bichro=0.,
        id=0):
        # TODO: this doesn't add any noise right now.
        dds = self.dds_729_SP
        dds_bichro = self.dds_729_SP_bichro
        if id == 1:
            dds = self.dds_729_SP1
            dds_bichro = self.dds_729_SP_bichro1

        dds.set(freq_sp, amplitude=amp_sp, phase=phase_sp, ref_time_mu=phase_ref_time)
        dds.set_att(att_sp)
        dds.sw.on()
        if use_bichro:
            dds_bichro.set(freq_sp_bichro, amplitude=amp_sp_bichro, phase=phase_sp_bichro, ref_time_mu=phase_ref_time)
            dds_bichro.set_att(att_sp_bichro)
            dds_bichro.sw.on()

    def stop_noisy_single_pass(self, use_bichro=False, id=0):
        dds = self.dds_729_SP
        dds_bichro = self.dds_729_SP_bichro
        if id == 1:
            dds = self.dds_729_SP1
            dds_bichro = self.dds_729_SP_bichro1

        # Turn off the DDS outputs.
        dds.sw.off()
        if use_bichro:
            dds_bichro.sw.off()

    def prepare_pulse_with_amplitude_ramp(self, pulse_duration, ramp_duration, dds1_amp=0., use_dds2=False, dds2_amp=0.):
        self.pulse_duration = pulse_duration
        self.ramp_duration = ramp_duration
        self.dds1_amp = dds1_amp
        if use_dds2:
            self.dds2_amp = dds2_amp
        
    def execute_pulse_with_amplitude_ramp(self, dds1_att=8.0, dds1_freq=0.,
                                          use_dds2=False, dds2_att=8.0, dds2_freq=0.):
        # TODO: currently this doesn't actually do any ramping
        self.dds_729.set(dds1_freq, self.dds1_amp)
        self.dds_729.sw.on()
        if use_dds2:
            self.dds_7291(dds2_freq, self.dds2_amp)
            self.dds_7291.sw.on()

        self.time_manager.take_time(self.pulse_duration)

        self.dds_729.sw.off()
        if use_dds2:
            self.dds_7291.sw.off()

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
                        if isinstance(param, WithUnit):
                            param = param.inBaseUnits()
                            param = param[param.units]
                        # units = param.units
                        # if units == "":
                        #     param = param[units]
                        # else:
                        #     param = param[units] * G[units]
                    #except AttributeError:
                        #pass
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