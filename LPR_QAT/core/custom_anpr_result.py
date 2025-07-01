# import easydict
from easydict import EasyDict as edict

class CustomANPRResult:
    def __init__(self):
        # self.result = {"state_info": {"poly":[], "state":[], "score":[]},
        #                 "prefix": {"poly":None, "score":0, "char": [], "char_score":[], "char_poly":[]},
        #                 "platenum": {"poly":None, "score":0, "char": [], "char_score":[], "char_poly":[]},
        #                 "single_char": {"char_id": [], "char_score":[], "char_poly":[]},
        #                 "aux": None,
        #                 "decoded_label": {"full_label":"", "state_label":"", "prefix_label":"", "platenum_label":""}}

        self.decoded_label = edict({"full_label":"", "state_label":"", "prefix_label":"", "platenum_label":""})

        # "type" can be state, taxi, classic, consulate 
        # "data_str" will populated today only if state
        self.info_logo = edict({"state": {"polygon":[], "data_str":[], "score":[]}})

        self.info_prefix = edict({"polygon":None, "score":0, "char": [], "char_score":[], "char_poly":[]})
        self.info_platenum = edict({"polygon":None, "score":0, "char": [], "char_score":[], "char_poly":[]})

        self.info_ocr = edict({"char_id": [], "char_score":[], "char_poly":[]})

    def reset(self):
        self.decoded_label = edict({"full_label":"", "state_label":"", "prefix_label":"", "platenum_label":""})

        # "type" can be state, taxi, classic, consulate 
        # "data_str" will populated today only if state
        self.info_logo = edict({"state": {"polygon":[], "data_str":[], "score":[]}})

        self.info_prefix = edict({"polygon":None, "score":0, "char": [], "char_score":[], "char_poly":[]})
        self.info_platenum = edict({"polygon":None, "score":0, "char": [], "char_score":[], "char_poly":[]})

        self.info_ocr = edict({"char_id": [], "char_score":[], "char_poly":[]})

    # mandatory last step things here
    def populate_final_number_plate_decoded_data(self):
        self.decoded_label = edict({"full_label":"", "state_label":"", "prefix_label":"", "platenum_label":""})

        if ("state" in self.info_logo.keys()) and (len(self.info_logo.state.data_str)>0):
            # swap best conf index to 0th index
            self.swap_best_conf_state_to_first()
            
            self.decoded_label.full_label += (self.info_logo.state.data_str[0]).upper()
            self.decoded_label.state_label = (self.info_logo.state.data_str[0]).upper()
            self.decoded_label.full_label += ","

        if ("char" in self.info_prefix.keys()) and (len(self.info_prefix.char) > 0):
            self.decoded_label.full_label += ("".join(self.info_prefix.char)).upper()
            self.decoded_label.prefix_label = ("".join(self.info_prefix.char)).upper()
            self.decoded_label.full_label += ","

        if ("char" in self.info_platenum.keys()) and (len(self.info_platenum.char) > 0):
            self.decoded_label.full_label += ("".join(self.info_platenum.char)).upper()
            self.decoded_label.platenum_label = ("".join(self.info_platenum.char)).upper()

    def swap_best_conf_state_to_first(self):
        best_conf_idx = 0
        if len(self.info_logo.state.data_str)>0:
            for idx in range(1, len(self.info_logo.state.data_str)):
                if self.info_logo.state.score[idx] > self.info_logo.state.score[best_conf_idx]:
                    best_conf_idx = idx

        # swap best conf state to 0th index if not already
        if best_conf_idx != 0:
            self.info_logo.state.data_str[best_conf_idx], self.info_logo.state.data_str[0] = self.info_logo.state.data_str[0], self.info_logo.state.data_str[best_conf_idx]
            self.info_logo.state.polygon[best_conf_idx], self.info_logo.state.polygon[0] = self.info_logo.state.polygon[0], self.info_logo.state.polygon[best_conf_idx]
            self.info_logo.state.score[best_conf_idx], self.info_logo.state.score[0] = self.info_logo.state.score[0], self.info_logo.state.score[best_conf_idx]
