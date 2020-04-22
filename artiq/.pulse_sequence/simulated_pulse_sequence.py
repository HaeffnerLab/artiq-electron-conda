from easydict import EasyDict as edict
import json
import labrad
import logging
import numpy as np

logger = logging.getLogger(__name__)

class PulseSequence():
    
    def print_parameters(self):
        parameter_dict = {}
        parameter_vault = self.load_parameter_vault()
        for param_name in self.accessed_params:
            collection, key = param_name.split(".")
            param_value = parameter_vault[collection][key]
            parameter_dict[param_name] = param_value

        for k,v in parameter_dict.items():
            logger.info(k + "=" + str(v))

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
                except:
                    # broken parameter
                    continue
            D[collection] = d
        return edict(D)