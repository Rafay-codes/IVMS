import cv2
import numpy as np
from shapely import geometry

from LPR_QAT.core.object_detector import ObjectDetector
from LPR_QAT.core.helpers import draw_box, crop_image, remove_elements_by_indices_from_list
from LPR_QAT.core.custom_anpr_result import CustomANPRResult
from LPR_QAT.core.preprocess import PreprocessVehicleLicensePlate

from easydict import EasyDict as edict

from copy import deepcopy

import math
from shapely import affinity
import traceback

# TODO: 
# 1, check if all are neatly spaced and in a specific pattern

class alpr_ktc(object):
    # Thresholds
    DETECTION_CONFIDENCE_SCORE_THRESHOLD = 0.2 # this should be above the thresold mentioned in app_settings.yaml file of KTC_LPR
    MIN_OVERLAPPING_CHARS_IOU_THRESH = 0.8 # if iou of platenum chars more than 0.1, then just remove it - same characters detected twice?
    MIN_PLATENUM_AND_CHAR_OVERLAP_THRESH = 0.9
    #MIN_PLATENUM_ASSUMPTION_CHAR_SCORE_GRACE_THRESH_IF_NUMERIC = 0.8 # if its numeric and dont intersect with any state/special poly and has a very good character score. then lets assume its platenum even though platenum position is not detected
    
    MIN_PREFIX_AND_CHAR_OVERLAP_THRESH = 0.9
    #MIN_PREFIX_AND_CHAR_GRACE_THRESH_IF_ALPHABET = 0.05 # potential prefix - dont need if prefix is detected good by our model
    #MIN_PREFIX_ASSUMPTION_CHAR_SCORE_GRACE_THRESH_IF_ALPHABET = 0.30 # if its alphabet and dont intersect with any state/special poly and has a very good character score. then lets assume its prefix even though prefix position is not provided - # this is very low score for making such assumption. Increase this after new training
    
    # in degrees
    ANGLE_ROTATION_THRESH_FOR_AREA_COMPARE = 13
    
    # full 
    MIN_THRESH_FOR_UNREC_PLATENUM_BASED_ON_AREA_COMPARE = 0.7
    
    def __init__(self, obj_detector:ObjectDetector):
        self.ocr_detector = obj_detector

        # get this as input from weights given
        #self.lpr_class_name = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "state-qat-english", "state-qat-arabic", "plate-number"]
        #self.state_class_names = ["state-qat-english", "state-qat-arabic"]
        
        self.lpr_class_name = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'a', 'b', 'c', 'd', 'e', 
               'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't',
               'u', 'v', 'w', 'x', 'y', 'z', 'prefix', 'plate_number',
               'state-dxb-english', 'state-dxb-arabic', 
               'state-auh-logo',
               'state-shj-english', 'state-shj-arabic',
               'state-fuj-arabic',
               'state-rak-english', 'state-rak-arabic',
               'state-ajm-english', 'state-ajm-arabic',
               'state-uaq-arabic',
               'state-qat-english', 'state-qat-arabic']
        self.state_class_names = ['state-dxb-english', 'state-dxb-arabic', 'state-dxb-logo',
               'state-auh-english', 'state-auh-arabic', 'state-auh-logo',
               'state-shj-english', 'state-shj-arabic', 'state-shj-logo',
               'state-fuj-english', 'state-fuj-arabic', 'state-fuj-logo',
               'state-rak-english', 'state-rak-arabic', 'state-rak-logo',
               'state-ajm-english', 'state-ajm-arabic', 'state-ajm-logo',
               'state-uaq-english', 'state-uaq-arabic', 'state-uaq-logo',
               'state-qat-english', 'state-qat-arabic', 'state-qat-logo',
               'state-ksa-english', 'state-ksa-arabic', 'state-ksa-logo']

        # result should be a queue with license plate image
        # should we maintain the queue or let application do that?        
        self.result = CustomANPRResult()
        
        self.license_plate_img = None # for debugging we need it across this class
        
        self.preprocess_lpr = PreprocessVehicleLicensePlate()
    
    def reset(self):
        self.result.reset()
        
    def process(self, plate_img):
        # self.result = {"state_info": {"poly":[], "state":[], "score":[]},
        #                 "prefix": {"poly":None, "score":0, "char": [], "char_score":[], "char_poly":[]},
        #                 "platenum": {"poly":None, "score":0, "char": [], "char_score":[], "char_poly":[]},
        #                 "single_char": {"char_id": [], "char_score":[], "char_poly":[]},
        #                 "aux": None,
        #                 "decoded_label": {"full_label":"", "state_label":"", "prefix_label":"", "platenum_label":""}}
        
        # reset previous result
        self.reset()
        
        # check if it has some valid img height before processing
        # do this here, or else we are getting cv2 divide by 0 issue during letterbox in dataset.py
        if plate_img.shape[1] < 5:
            return None
        
        license_plate_img = plate_img.copy()
        #imgHighContrast, imgBlur, imgBinary, imgCanny, imgDial, imgContour, warped = preprocess_obj.run(image)
        #_, _, _, _, _, _, warped_license_plate_img = self.preprocess_lpr.run(license_plate_img)
        #warped_license_plate_img = license_plate_img
        
        # detector
        #if np.all(warped_license_plate_img):
        #    print(warped_license_plate_img.shape)
        #    model_pred = self.ocr_detector.detect_objects(warped_license_plate_img, "video") # video flag will do letterpad padding - no aspect ratio change
        #else:
        #    model_pred = self.ocr_detector.detect_objects(license_plate_img, "video")
        model_pred = self.ocr_detector.detect_objects(license_plate_img, "video")
        
        # No ocr detections made for this plate? - may be wrong plate?
        if model_pred is None:
            return None
            
        # result will be populated - converts model_pred into a data format which will be easy to post process
        # Example: bbox as array in model_pred will be converted to shapely.geometry.Polygon 
        # this mainly populates prefix/state/single_char/platenum global position poly
        self.__populate_pred_data_into_results(model_pred)
        
        if self.result.info_platenum.polygon is None:
            #print("No platenum polygon")
            return None

        pop_indices = edict({"info_prefix": set(), "info_platenum": set(), "info_ocr": set()})
        self.__populate_prefix_and_platenum_characters(pop_indices)
        
        # TODO: shall we move this to the last part after all unwated elements removed
        self.__rearrange_chars_based_on_xaxis(self.result.info_platenum)
        
        self.__rearrange_chars_based_on_xaxis(self.result.info_prefix)
        
        # find and remove if there are multiple ocr detections made for 1 char
        self.__find_overlapping_chars_indices(self.result.info_platenum, pop_indices.info_platenum)
        self.__find_overlapping_chars_indices(self.result.info_prefix, pop_indices.info_prefix)

        self.__remove_all_unwanted_elements(pop_indices) # remove from result

        self.result.populate_final_number_plate_decoded_data()
        
        # check this first, as this will work in most scenerio
        try:
            if len(self.result.info_platenum.char_poly) > 2 and (not (self.__is_equally_spaced(self.result.info_platenum))):
                print("Not __is_equally_spaced", self.result.decoded_label.full_label)
                return None
            
            if not (self.__is_complete_area_recognised(self.result.info_platenum)):
                print("Not __is_complete_platenum", self.result.decoded_label.full_label)
                return None
            
            if ((self.result.info_prefix.polygon is not None) and (len(self.result.info_prefix.char_poly) > 0) and (not (self.__is_complete_area_recognised(self.result.info_prefix)))):
                print("Not __is_complete_prefix", self.result.decoded_label.full_label)
                return None
        except Exception as e:
            print("[ALPR_KTC] Exception raised.", e, traceback.format_exc())
        
        return deepcopy(self.result)
    
    def __populate_prefix_and_platenum_characters(self, pop_indices):
    
        # populate ocr detections data in platenum dict
        for i, lpoly in enumerate(self.result.info_ocr.char_poly):
            non_platenum = True
            non_prefix = True
            
            #print(self.lpr_class_name[self.result.info_ocr.char_id[i]])
            
            # find if the char belongs to prefix - direct method
            if self.result.info_prefix.score > 0: # by default it is set to 0 - ('0.001 > 0' is 'True' in python) or check for "polygon" which is set to None by default
                #iou =  (lpoly.intersection(self.result.info_prefix.polygon).area / lpoly.union(self.result.info_prefix.polygon).area)
                intersection_percent =  (lpoly.intersection(self.result.info_prefix.polygon).area / lpoly.area) 
                if(intersection_percent > self.MIN_PREFIX_AND_CHAR_OVERLAP_THRESH):
                    #print(self.lpr_class_name[self.result.info_ocr.char_id[i]])
                    self.result.info_prefix.char.append(self.lpr_class_name[self.result.info_ocr.char_id[i]])
                    self.result.info_prefix.char_score.append(self.result.info_ocr.char_score[i])
                    self.result.info_prefix.char_poly.append(lpoly)
                    non_prefix = False
                    
            # find if the char belongs to platenum - direct method
            if ((non_prefix) and (self.result.info_platenum.score > 0)): # by default it is set to 0 - ('0.001 > 0' is 'True' in python) or check for "polygon" which is set to None by default
                #iou =  (lpoly.intersection(self.result.info_platenum.polygon).area / lpoly.union(self.result.info_platenum.polygon).area)
                intersection_percent =  (lpoly.intersection(self.result.info_platenum.polygon).area / lpoly.area) 
                #print(self.result.info_platenum.polygon.contains(lpoly), lpoly.intersection(self.result.info_platenum.polygon).area)
                
                if(intersection_percent > self.MIN_PLATENUM_AND_CHAR_OVERLAP_THRESH):
                    self.result.info_platenum.char.append(self.lpr_class_name[self.result.info_ocr.char_id[i]])
                    self.result.info_platenum.char_score.append(self.result.info_ocr.char_score[i])
                    self.result.info_platenum.char_poly.append(lpoly)
                    non_platenum = False
                
            if non_prefix and non_platenum:
                pop_indices.info_ocr.add(i)
                
                # Grace Threshold
                '''
                is_state_poly = self.__is_lpoly_belong_to_state_poly(lpoly, self.result.info_logo.state.polygon)

                #if this character belongs to state_poly, shall we remove from info_ocr.char*? - dont use popup indices for this

                if is_state_poly:
                    pop_indices.info_ocr.add(i)
                    
                # find if the char belongs to platenum - indirect method
                # what if all ocr detected but there is no platenum detected? - in this case, if its numeric with good score, consider it
                # but this may give more false data as we dont know position to look for platenum
                #elif ((self.result.info_ocr.char_id[i].isnumeric()) and (self.result.info_ocr.char_score[i] > MIN_PLATENUM_ASSUMPTION_CHAR_SCORE_GRACE_THRESH_IF_NUMERIC)):
                # self.result.info_ocr.char_id[i] is converted to int by default, so no need to do isnumeric()
                
                elif ((self.result.info_ocr.char_score[i] > self.MIN_PLATENUM_ASSUMPTION_CHAR_SCORE_GRACE_THRESH_IF_NUMERIC)):
                    #TODO: check if all are neatly spaced and in a specific pattern
                    print("Assuming platenum")
                    self.result.info_platenum.char.append(self.lpr_class_name[self.result.info_ocr.char_id[i]])
                    self.result.info_platenum.char_score.append(self.result.info_ocr.char_score[i])
                    self.result.info_platenum.char_poly.append(lpoly)
                
                #elif(not is_state_poly):
                    # sometimes iou (lpoly and prefix poly) is zero - so it can be nearer char of prefix
                    # print("dont know still")
                    #pop_indices.info_ocr.add(i) # remove this if we are not using this character anywhere
                '''
        
    def __find_overlapping_chars_indices(self, lpr_obj, pop_indices):
        for i in range(0,len(lpr_obj.char_poly)):
            if i in pop_indices:
                continue
            for j in range(i+1,len(lpr_obj.char_poly)):
                if j in pop_indices:
                    continue
                
                lpoly = lpr_obj.char_poly[i]
                #iou =  lpoly.intersection(lpr_obj.char_poly[j]).area / lpoly.union(lpr_obj.char_poly[j]).area
                intersection_percent =  (lpoly.intersection(lpr_obj.char_poly[j]).area / lpoly.area) 

                if intersection_percent > self.MIN_OVERLAPPING_CHARS_IOU_THRESH: # okay, now we have to remove either i or j
                    # check if same or diff character
                    if lpr_obj.char[i] == lpr_obj.char[j]:
                        pop_indices.add(i) # or j - no issues
                    # check what to remove based on score
                    else:
                        pop_indices.add(i if (lpr_obj.char_score[j] > lpr_obj.char_score[i]) else j)
    
    def __remove_all_unwanted_elements(self, pop_indices):
        for key in pop_indices.keys():
            if key == "info_platenum" and len(pop_indices[key]) > 0:
                remove_elements_by_indices_from_list(self.result.info_platenum.char, pop_indices[key])
                remove_elements_by_indices_from_list(self.result.info_platenum.char_poly, pop_indices[key])
                remove_elements_by_indices_from_list(self.result.info_platenum.char_score, pop_indices[key])
            
            elif key == "info_prefix" and len(pop_indices[key]) > 0:
                remove_elements_by_indices_from_list(self.result.info_prefix.char, pop_indices[key])
                remove_elements_by_indices_from_list(self.result.info_prefix.char_poly, pop_indices[key])
                remove_elements_by_indices_from_list(self.result.info_prefix.char_score, pop_indices[key])

            elif key == "info_ocr" and len(pop_indices[key]) > 0:
                remove_elements_by_indices_from_list(self.result.info_ocr.char_id, pop_indices[key])
                remove_elements_by_indices_from_list(self.result.info_ocr.char_poly, pop_indices[key])
                remove_elements_by_indices_from_list(self.result.info_ocr.char_score, pop_indices[key])

    def __is_lpoly_belong_to_state_poly(self, lpoly, state_poly):
        ret_val = False
        if len(state_poly) == 0:
            return ret_val
        else:
            for poly in state_poly:
                # if there is no overlaps, then 'lpoly.intersection(poly).area' will be '0', this will give a runtime warning, but no issues, ignore
                # RuntimeWarning: invalid value encountered in intersection
                #iou = lpoly.intersection(poly).area / lpoly.union(poly).area
                intersection_percent = lpoly.intersection(poly).area / lpoly.area
                
                if intersection_percent > 0.9:
                    ret_val = True
                    break
        return ret_val
    '''  
    def __remove_platenum_if_not_properly_spaced(self, lp_obj):
        offset_pixels = 5
        prev_space = -1
        # minx to maxx i.e., in an image it will be left to right repositioning of chars
        for i, _ in enumerate(lp_obj.char_poly):
            for j in range(i+1,len(lp_obj.char_poly)):
                i_minx = lp_obj.char_poly[i].bounds[0]
                j_minx = lp_obj.char_poly[j].bounds[0]
                space = i_minx - j_minx
                if ((prev_space != -1) and ()):
                    prev_space = space
                    
                space_lst.append
                if space > offset_pixels:
                    # remove all platenums
                    # swapping
                    lp_obj.char_poly[i], lp_obj.char_poly[j] = lp_obj.char_poly[j], lp_obj.char_poly[i]
                    lp_obj.char[i], lp_obj.char[j] = lp_obj.char[j], lp_obj.char[i]
                    lp_obj.char_score[i], lp_obj.char_score[j] = lp_obj.char_score[j], lp_obj.char_score[i]
    '''                
    
    def __is_equally_spaced(self, lp_obj):
        spaces = []
        #print("char_poly", lp_obj.char_poly)
        for idx in range(1, len(lp_obj.char_poly)):
            i_minx = lp_obj.char_poly[idx].bounds[0]
            j_minx = lp_obj.char_poly[idx-1].bounds[0]
            space = i_minx - j_minx
            #print(space, lp_obj.char[idx], lp_obj.char[idx-1])
            spaces.append(space)
        
        # find if there is any outlier
        l = np.array(spaces)
        #print("arr", l)
        l = l/np.median(l)
        #print("divide by median", l)
        if True in (l>1.5):
           #print(spaces, l, np.median(l))
           return False
        else:
           return True
    
    def __is_equally_spaced_1(self, lp_obj):
        spaces = []
        for idx in range(1, len(lp_obj.char_poly)):
            i_minx = lp_obj.char_poly[idx].bounds[0]
            j_minx = lp_obj.char_poly[idx-1].bounds[0]
            space = i_minx - j_minx
            #print(space, lp_obj.char[idx], lp_obj.char[idx-1])
            spaces.append(space)
        
        # find if there is any outlier
        l = np.array(spaces)
        if np.argmax(l>np.quantile(l,0.7)):
           #print(spaces, np.quantile(l,0.7))
           return False
        else:
           return True
    
    def calculate_angle(self, x1, y1, x2, y2):
        # Calculate the differences in coordinates
        delta_y = y2 - y1
        delta_x = x2 - x1
        
        # Calculate the angle in radians
        angle_radians = math.atan2(delta_y, delta_x)
        
        # Convert the angle to degrees
        angle_degrees = math.degrees(angle_radians)
        
        return angle_degrees
        
    def __is_complete_area_recognised(self, lp_obj):
        
        if len(lp_obj.char_poly) > 1:
            start_pt = lp_obj.char_poly[0].bounds
            end_pt = lp_obj.char_poly[-1].bounds        
            angle_rotated = self.calculate_angle(start_pt[0], start_pt[1], end_pt[0], end_pt[1])
            
            # correct bounding box if license plate is rotated more than the thresh
            if abs(angle_rotated) > self.ANGLE_ROTATION_THRESH_FOR_AREA_COMPARE: # this algo wont work for this much rotated plates
                # highly rotated plate
                print("highly rotated plate", angle_rotated)
                #lp_obj.polygon = affinity.rotate(lp_obj.polygon, angle_rotated)
                minx, miny, maxx, maxy = lp_obj.polygon.bounds
                c_minx, c_miny, c_maxx, c_maxy = lp_obj.char_poly[0].bounds
                height = c_maxy - c_miny
                
                # corrected polygon
                lp_obj.polygon = geometry.polygon.Polygon(((minx, miny),(maxx, miny),(maxx, miny+height),(minx, miny+height),(minx, miny)))
                #print(lp_obj.polygon.area)
        
        ocr_cumulative_area = 0            
        for poly in lp_obj.char_poly:
            #print(poly.area)
            ocr_cumulative_area += poly.area
        #print("Licence-Plate area",lp_obj.polygon.area, ocr_cumulative_area)
        #print(ocr_cumulative_area / lp_obj.polygon.area)
        area_percent = ocr_cumulative_area / lp_obj.polygon.area
        
        if area_percent > self.MIN_THRESH_FOR_UNREC_PLATENUM_BASED_ON_AREA_COMPARE:
            return True
        else:
            #print("Incomplete platenum:", area_percent)
            return False
            
    def __rearrange_chars_based_on_xaxis(self, lp_obj):
        # minx to maxx i.e., in an image it will be left to right repositioning of chars
        for i, _ in enumerate(lp_obj.char_poly):
            for j in range(i+1,len(lp_obj.char_poly)):
                i_minx = lp_obj.char_poly[i].bounds[0]
                j_minx = lp_obj.char_poly[j].bounds[0]
                if j_minx < i_minx:
                    # swapping
                    lp_obj.char_poly[i], lp_obj.char_poly[j] = lp_obj.char_poly[j], lp_obj.char_poly[i]
                    lp_obj.char[i], lp_obj.char[j] = lp_obj.char[j], lp_obj.char[i]
                    lp_obj.char_score[i], lp_obj.char_score[j] = lp_obj.char_score[j], lp_obj.char_score[i]
                    
    def __populate_pred_data_into_results(self, model_pred): # ASSUMPTION: model_pred wont be None
        for *xyxy, conf, cls in model_pred:
            x1 = int(xyxy[0].item())
            y1 = int(xyxy[1].item())        
            x2 = int(xyxy[2].item())
            y2 = int(xyxy[3].item())
            obj_poly = geometry.Polygon([(x1, y1), (x1, y2), (x2,y2), (x2,y1)])

            # parallel actions
            class_name = self.lpr_class_name[int(cls.item())]
            score = conf.item()
            #print(class_name, score, self.result.info_platenum.score, score > self.result.info_platenum.score)

            # TODO: uncomment this later
            # Now our model is not so good for recognition, 
            # so we are not able to eliminate any detections based on detection score currently
            if score < self.DETECTION_CONFIDENCE_SCORE_THRESHOLD: 
                continue

            # if class_name not in ["prefix", "platenum"]:
            #     draw_box(self.license_plate_img, obj_poly,color=(0,0,255))


            # 1, populate 'STATE' detections
            if class_name in self.state_class_names: # to remember both arabic and english logo of state sometimes. used append
                self.result.info_logo.state.polygon.append(obj_poly)
                self.result.info_logo.state.data_str.append(class_name)
                self.result.info_logo.state.score.append(score)
            # 2, populate 'PLATENUM' detections
            elif class_name=="plate_number" and score > self.result.info_platenum.score: # should be one good plate-number bbox or choose best conf one
                self.result.info_platenum.polygon = obj_poly
                self.result.info_platenum.score = score
            # 3, populate 'PREFIX' detections
            elif class_name=="prefix"  and score > self.result.info_prefix.score: # should be one good prefix or choose best conf one
                self.result.info_prefix.polygon = obj_poly # TODO: pad the poly to cover nearby prefix if any
                self.result.info_prefix.score = score
            # 4, populate 'SINGLE CHARS' detections - 0-9,a-z
            elif class_name.isalnum() and len(class_name) == 1:
                # draw_box(self.license_plate_img, obj_poly, color=(0,0,255))
                self.result.info_ocr.char_poly.append(obj_poly)
                self.result.info_ocr.char_score.append(conf.item())
                self.result.info_ocr.char_id.append(int(cls.item()))
            else: # misc - consulate, taxi, dubai police
                # draw_box(self.license_plate_img, obj_poly, color=(0,0,255))
                # print("other class detect :", class_name, score)
                # cv2.imshow("weird character", self.license_plate_img)
                # cv2.waitKey(2000)
                pass
    
    '''
    def __populate_prefix_and_platenum_characters(self, pop_indices):
        # populate ocr detections data in prefix or platenum dict
        for i, lpoly in enumerate(self.result.info_ocr.char_poly):
            non_prefix = True
            non_platenum = True

            # find if the char belongs to prefix
            if self.result.info_prefix.score > 0:
                iou =  (lpoly.intersection(self.result.info_prefix.polygon).area / lpoly.union(self.result.info_prefix.polygon).area)
                # TODO: remember this iou - compare if any other detection we have for this char with more IoU intersection and Confidence
                if((iou > self.MIN_PREFIX_AND_CHAR_OVERLAP_THRESH) or
                    ((iou > self.MIN_PREFIX_AND_CHAR_GRACE_THRESH_IF_ALPHABET) and 
                    (self.lpr_class_name[self.result.info_ocr.char_id[i]].isalpha()))):
                    # ((iou > 0.4) and 
                    # ((len(self.result.info_prefix.char_score) > 0) and 
                    #     (self.result.info_ocr.char_score[i] > self.result.info_prefix.char_score)))): # adjust this threshold 
                    self.result.info_prefix.char.append(self.lpr_class_name[self.result.info_ocr.char_id[i]])
                    self.result.info_prefix.char_score.append(self.result.info_ocr.char_score[i])
                    self.result.info_prefix.char_poly.append(lpoly)
                    non_prefix = False

            # find if the char belongs to platenum - do this after prefix as its easy to determine a
            # basic assumption - if its not prefix and not a alphabet, it belongs to platenum
            # we need to check iou with platenum, but current model is not predicting right platenum position
            if non_prefix and (not(self.lpr_class_name[self.result.info_ocr.char_id[i]].isalpha())): # and self.result.info_platenum.score > 0:
                self.result.info_platenum.char.append(self.lpr_class_name[self.result.info_ocr.char_id[i]])
                self.result.info_platenum.char_score.append(self.result.info_ocr.char_score[i])
                self.result.info_platenum.char_poly.append(lpoly)
                non_platenum = False

            if non_platenum and non_prefix:
                # cv2.imshow("weird character", self.license_plate_img)
                # cv2.waitKey(5000)
                is_state_poly = self.__is_lpoly_belong_to_state_poly(lpoly, self.result.info_logo.state.polygon)

                #if this character belongs to state_poly, shall we remove from info_ocr.char*? - dont use popup indices for this

                if is_state_poly:

                    pop_indices.info_ocr.add(i)
                elif((not is_state_poly) and (len(self.result.info_logo.state.polygon) > 0) and (self.result.info_prefix.polygon is None)):
                    # prefix bbox is not there, but alphabet is detected and thats not on state poly
                    # this may be prefix - no other way to confirm its a prefix
                    
                    if (self.lpr_class_name[self.result.info_ocr.char_id[i]].isalpha() and self.result.info_ocr.char_score[i] > self.MIN_PREFIX_ASSUMPTION_CHAR_SCORE_GRACE_THRESH_IF_ALPHABET):
                        self.result.info_prefix.char.append(self.lpr_class_name[self.result.info_ocr.char_id[i]])
                        self.result.info_prefix.char_score.append(self.result.info_ocr.char_score[i])
                        self.result.info_prefix.char_poly.append(lpoly)
                elif(not is_state_poly):
                    # sometimes iou (lpoly and prefix poly) is zero - so it can be nearer char of prefix
                    # print("dont know still")
                    pop_indices.info_ocr.add(i) # remove this if we are not using this character anywhere
                    # print(self.lpr_class_name[self.result.info_ocr.char_id[i]]) # d, j
                    # print(self.result.info_ocr.char_score[i]) # 0.54, 0.56
                    # draw_box(self.license_plate_img, lpoly, color=(0,0,255))
                    # cv2.imshow("weird character", self.license_plate_img)
                    # cv2.waitKey(5000)
                    
    '''
