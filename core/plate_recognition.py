#import ALPR as alpr
import os
import cv2
import torch
import numpy as np

from datetime import datetime
from shapely.geometry import box
from typing import List
from easydict import EasyDict as edict

from utils.draw import draw_box

from LPR_QAT.core.object_detector import ObjectDetector
from LPR_QAT.core.yaml_parser import YamlParser

from LPR_QAT.core.alpr_ktc import alpr_ktc

from simple_detect_lpr_streamai import PlateRecognitionTechnoStreamAI
from collections import deque
import threading

#from PIL import Image
#from PIL.PngImagePlugin import PngInfo
                
class PlateRecognition(object):

    # custom model classes
    BELT = 0
    NO_BELT = 1
    MOBILE = 2
    CAR = 3
    STEERING_WHEEL = 4
    PHONE_HOLDER = 5
    PLATE = 6
    
    PLATE_TYPE_PRIVATE = 0

    REMOVE_SLOT_AFTER_FRAMES = 30

    def __init__(self
        , configs_dir: str
        , lpr_dir: str
        , stream_count: int
        , width: int
        , height: int
        , api_interface
        , anpr=False):
        
        self.lpr_dir = lpr_dir
        self.width = width
        self.height = height
        self.anpr = anpr

        # init Carrida
        #self.lpr = alpr.carrida.LPR(os.path.join(configs_dir,"lpr.ini"), None)
        #self.lpr = alpr_ktc()

        # we create a list of lists to hold the plates separately for each stream
        self.plates = deque(maxlen=100) #list()
        #for i in range(0, stream_count):
        #    self.plates.append( list() ) #different object reference each time

        # list of list of dicts with info of vehicles inside vehicle area
        # -> one list per stream
        self.v_slots = list()
        for i in range(0, stream_count):
            self.v_slots.append( list() ) #different object reference each time
        
        # KTC OCR inits
        # Read YAML config file using YamlParser class 
        cfg = YamlParser(config_file="LPR_QAT/config/app_settings.yaml")
        
        # configure application logging
        # configure_logging(cfg, src='lpr')

        #ocr_detector = ObjectDetector(cfg, mode='ocr')

        #self.lpr = alpr_ktc(ocr_detector)
        self.lpr = PlateRecognitionTechnoStreamAI()
        
        self.api_interface = api_interface


    # maintain one list with tracked vehicles per stream; use tracking in order to avoid
    # doing lpr for the same vehicle many times
    def update(self, detections: List, stream_no: int, fi: int, frame):
        #for plate in detections:
        #    if plate.class_id > 4 :
        #        print(plate.class_id, plate.score)
        #print(stream_no, "stream idx")
        # return list of car objects where alpr Carrida function was applied
        ret = []             

        # we only care about plates with score >= 85%
        #plates = [plate for plate in detections if plate.class_id == self.PLATE and plate.score >= 0.5]
        plates = [plate for plate in detections if plate.class_id == self.PLATE]
        # we filter out cars with score < 50%
        #cars = [car for car in detections if car.class_id == self.CAR and car.score >= 0.5]
        cars = [car for car in detections if car.class_id == self.CAR]
        self._link_plates_to_vehicles(cars, plates)
        
        #print(len(plates), len(cars))

        # get a ref to the vehicle slots of the current stream; easier to work with!       
        v_slots = self.v_slots[stream_no]

        # --- CLEAR slots that have not been updated since configured number of frames
        # see https://stackoverflow.com/questions/1207406/how-to-remove-items-from-a-list-while-iterating
        v_slots[:] = [slt for slt in v_slots if slt.fi + self.REMOVE_SLOT_AFTER_FRAMES >= fi]

        # update v_slots using car data of current frame        
        # -> we want to do lpr on slots with plate updated AND plate not yet recognised
        for slot in cars:
            # check if vehicle is already contained in a slot
            v_slot = next((v_slot for v_slot in v_slots if v_slot.id == slot.id), None)
            
            # id has not yet been added to a slot
            # -> add it now
            if v_slot is None:  
                slot.fi = fi
                v_slots.append(slot)
            # id is already contained in slot list:             
            else:
                # -> update its bbox, fi
                v_slot.fi = fi
                v_slot.bbox = slot.bbox

                # -> update maxy property
                min, miny, maxx, maxy = slot.bbox.bounds
                v_slot.maxy = maxy

                # -> update plate_bbox only if plate has not been yet recognized                
                if v_slot.plate_no is None:                     
                    v_slot.plate_bbox = slot.plate_bbox
                # -> otherwise set plate_bbox to None so that no lpr is performed anymore
                else:
                    v_slot.plate_bbox = None

        # perform lpr for all slots updated with new plate data
        # -> fields plate_no, plate_img are possibly updated
        cars = [v for v in v_slots if v.fi == fi and v.plate_bbox is not None]
        if self.anpr:
           workThread = threading.Thread(target=self._detect, args=(cars, stream_no, frame), daemon=True)
           workThread.start()
           #self._detect(cars, stream_no, frame)

        return v_slots

    # implement simple algorith to match plates to cars
    def _link_plates_to_vehicles(self, cars, plates):
        for plate in plates:
            # check if current plate is completely inside a vehicle bbox
            for car in [car for car in cars if not car.matched]: 
                # we check if plate_box is located on the lower part of the vehicle box
                if car.bbox.contains(plate.bbox):
                    car.matched = True
                    car.plate_bbox = plate.bbox
                    break

    # do lpr for vehicles 
    def _detect(self, vehicles, stream_no: int, frame):
        # calculate dir, create it if it doesn't yet exist
        folder = os.path.join(self.lpr_dir, datetime.now().strftime("%Y%m%d"), str(stream_no))
        if not os.path.exists(folder):
            os.makedirs(folder)

        # get current timestamp -> use it in vehicle, cropped img filenames
        tstamp = datetime.now().strftime("%H_%M_%S_%f")

        for car in vehicles:
        
            #if car.lpr_img is not None:
            if car.lpr_img_save_count >= 12:
                continue
            '''
            # if not yet set, then save img used for lpr frame
            # -> this image will be overriden in case plate is read
            if car.lpr_img is None:
                pass
                # get vehicle image
                #cminx, cminy, cmaxx, cmaxy = car.bbox.bounds
                #car_img = frame[int(cminy):int(cmaxy), int(cminx):int(cmaxx)]
            
                #plate_minx, plate_miny, plate_maxx, plate_maxy = car.plate_bbox.bounds
                #plate_img = frame[int(plate_miny):int(plate_maxy), int(plate_minx):int(plate_maxx)]     
            
                #fname = os.path.join(folder, f'{tstamp}-1.png') 
                #cropped_fname = os.path.join(folder, f'{tstamp}-2.png')
                #frame_fname = os.path.join(folder, f'{tstamp}-3.png')
                #cv2.imwrite(fname, car_img)
                #cv2.imwrite(cropped_fname, plate_img)
                #cv2.imwrite(frame_fname, frame)
            
                #car.lpr_img = frame.copy()
                #continue
                #draw_box(car.lpr_img, car.bbox, color=(50, 50, 220), line_thickness=3)
                #draw_box(car.lpr_img, car.plate_bbox, color=(50, 50, 220), line_thickness=3)
            else:
                continue
            '''
            # extract plate image from frame using coords from our custom plate detection model (Yolo V5)
            # -> after increasing the plate bbox
            plate_minx, plate_miny, plate_maxx, plate_maxy = car.plate_bbox.bounds
            #print("width of plate", (plate_maxx-plate_minx))
            #plate_minx, plate_miny, plate_maxx, plate_maxy = car.bbox.bounds
            with_offset = True
            x_offset = 10
            y_offset = 5
            plate_width = plate_maxx-plate_minx
            if with_offset:
                plate_minx = plate_minx - x_offset if plate_minx - x_offset > 0 else 0
                plate_miny = plate_miny - y_offset if plate_miny - y_offset > 0 else 0
                plate_maxx = plate_maxx + x_offset if plate_maxx + x_offset < self.width else self.width
                plate_maxy = plate_maxy + y_offset if plate_maxy + y_offset < self.height else self.height
                #print("width of plate", (plate_maxx-plate_minx))
                if ((plate_maxx-plate_minx) < 50):
                    continue
            elif(plate_width < 30):
                #print("width of plate", (plate_maxx-plate_minx))
                continue
            
            plate_img = frame[int(plate_miny):int(plate_maxy), int(plate_minx):int(plate_maxx)]
            
            ##########################################
            # Save images to folder
            ##########################################  
            
            # get vehicle image
            cminx, cminy, cmaxx, cmaxy = car.bbox.bounds
            car_img = frame[int(cminy):int(cmaxy), int(cminx):int(cmaxx)]
            
            save_img = False
            
            if ((plate_width >= 30) and (plate_width <= 40) and (car.lpr_imgs_dict['30'] == 0 )):
                car.lpr_imgs_dict['30']+=1
                save_img = True
            elif ((plate_width > 40) and (plate_width <= 50) and (car.lpr_imgs_dict['40'] == 0 )):
                car.lpr_imgs_dict['40']+=1
                save_img = True
            elif ((plate_width > 50) and (plate_width <= 60) and (car.lpr_imgs_dict['50'] == 0 )):
                car.lpr_imgs_dict['50']+=1
                save_img = True
            elif ((plate_width > 60) and (plate_width <= 65) and (car.lpr_imgs_dict['60'] == 0 )):
                car.lpr_imgs_dict['60']+=1
                save_img = True
            elif ((plate_width > 65) and (plate_width <= 70) and (car.lpr_imgs_dict['65'] == 0 )):
                car.lpr_imgs_dict['65']+=1
                save_img = True
            elif ((plate_width > 70) and (plate_width <= 75) and (car.lpr_imgs_dict['70'] == 0 )):
                car.lpr_imgs_dict['70']+=1
                save_img = True
            elif ((plate_width > 75) and (plate_width <= 80) and (car.lpr_imgs_dict['75'] == 0 )):
                car.lpr_imgs_dict['75']+=1
                save_img = True
            elif ((plate_width > 80) and (plate_width <= 85) and (car.lpr_imgs_dict['80'] == 0 )):
                car.lpr_imgs_dict['80']+=1
                save_img = True
            elif ((plate_width > 85) and (plate_width <= 90) and (car.lpr_imgs_dict['85'] == 0 )):
                car.lpr_imgs_dict['85']+=1
                save_img = True
            elif ((plate_width > 90) and (car.lpr_imgs_dict['90'] < 3 )): # only in this case, high resolution, we capture 3 frames
                car.lpr_imgs_dict['90']+=1
                save_img = True
            
            if save_img:
                fname = os.path.join(folder, f'{car.id}_{tstamp}_{int(plate_width)}.png')
                cv2.imwrite(fname, plate_img)
                
                #img = cv2.cvtColor(plate_img, cv2.COLOR_BGR2RGB)
                #im_pil = Image.fromarray(img)
                #metadata = PngInfo()
                #metadata.add_text("OCR_Results", json.dumps())
                #image.save("1.png", pnginfo=metadata)

                car.lpr_img_save_count+=1
            '''
            if((plate_maxx-plate_minx) > 80):
                car.lpr_img_save_count += 3
            elif((plate_maxx-plate_minx) > 50):
                car.lpr_img_save_count += 2
            else:
                car.lpr_img_save_count += 1
            '''

            '''
            # ---------------------------------
            # HACK: Save cropped image for testing purposes only

            #if car.plate_img is None:
                # save vehicle, cropped plate images
                #fname = os.path.join(folder, f'{tstamp}-{car.id}.jpg') 
                #cropped_fname = os.path.join(folder, f'{tstamp}-{car.id}-pl.jpg')                             
                #cv2.imwrite(fname, car_img)
                #cv2.imwrite(cropped_fname, plate_img)
                
            #     car.plate_img = plate_img

            # HACK end -------------------------------

            ##########################################
            # TechnoStream / KTC Custom OCR / CARRIDA
            ##########################################
            # convert img to form suitable for Carrida detection
            #plate_img_grey = cv2.cvtColor(plate_img, cv2.COLOR_BGRA2GRAY)
            #plate_img_grey = np.stack((plate_img_grey,)*3, axis=-1)
            #lpr_img = alpr.svcapture.Image()
            #lpr_img.set(img)
            #lpr_img = img

            # do alpr                    
            #result, lpr_results = self.lpr.process(lpr_img)
            #lpr_results = self.lpr.process(plate_img)
            lpr_results = self.lpr.simpleDetect(car_img)
            
            #print(lpr_results.decoded_label.full_label)   
            
            #if plate_img is not None:
                # save vehicle, cropped plate images
                #fname = os.path.join(folder, f'{tstamp}-{car.id}.jpg') 
                #cropped_fname = os.path.join(folder, f'{tstamp}-{car.id}-pl-{lpr_results.decoded_label.full_label}.jpg')                             
                #cv2.imwrite(fname, car_img)
                #cv2.imwrite(cropped_fname, plate_img)
            
            if ((lpr_results is not None)):    
                plate = plate_img
                plate_num = f'{lpr_results["PlateText"]}'.strip()
                #plate_prefix = lpr_results.decoded_label["prefix_label"].strip()
                plate_type = self.PLATE_TYPE_PRIVATE
                plate_state = f'{lpr_results["StateLong"]}'.strip()
                plate_country = f'{lpr_results["CountryLong"]}'.strip()
                plate_no = f'{plate_state} {plate_country} {plate_num}'.strip()
                
                if ((plate_num is not None) and (plate_num != "None") and (plate_no not in self.plates)):
                    
                    
                    # save vehicle, cropped plate images
                    fname = os.path.join(folder, f'{tstamp}-{plate_no}.jpg') 
                    #cropped_fname = os.path.join(folder, f'{tstamp}-{plate_no}-pl.jpg')                             
                    cv2.imwrite(fname, car_img)
                    #cv2.imwrite(cropped_fname, plate_img)
                    
                    # update car slot with plate_no, plate_img data
                    car.plate_no = plate_no
                    car.plate_img = plate_img

                    # save img used for lpr frame
                    car.lpr_img = frame.copy()
                    #draw_box(car.lpr_img, car.bbox, color=(50, 50, 220), line_thickness=3)
                    #draw_box(car.lpr_img, car.plate_bbox, color=(50, 50, 220), line_thickness=3)                    

                    #print (f'[PlateRecognition] Wrote image for plate {plate_no} to {cropped_fname}')
                    # append new plate no to list of already recognized plates
                    self.plates.append(plate_no)
                    #self.api_interface.update_plate_event(cropped_fname, plate_num, plate_type, plate_state, plate_country)
                elif (plate_no not in self.plates):
                    fname = os.path.join(folder, f'{tstamp}-{plate_no}-failed.jpg') 
                    cv2.imwrite(fname, car_img)
            '''        
            '''
            if lpr_results  and lpr_results.decoded_label["platenum_label"] and lpr_results.decoded_label["state_label"]:
                plate = plate_img
                plate_num = f'{lpr_results.decoded_label["platenum_label"]}'.strip()
                plate_prefix = f'{lpr_results.decoded_label["prefix_label"]}'.strip()
                plate_type = self.PLATE_TYPE_PRIVATE
                plate_state = f'{self._city_code(lpr_results.decoded_label["state_label"])}'.strip()
                plate_country = f'{self._city_code(lpr_results.decoded_label["state_label"])}'.strip()
                
                plate_no = f'{self._city_code(lpr_results.decoded_label["state_label"])} {lpr_results.decoded_label["prefix_label"]} {lpr_results.decoded_label["platenum_label"]}'.strip()
                
                # if plate no is NEW then save img to disk
                if plate_no not in self.plates:
                
                    # save vehicle, cropped plate images
                    fname = os.path.join(folder, f'{tstamp}-{plate_no}.jpg') 
                    cropped_fname = os.path.join(folder, f'{tstamp}-{plate_no}-pl.jpg')                             
                    cv2.imwrite(fname, car_img)
                    cv2.imwrite(cropped_fname, plate_img)
                    if lpr_results.decoded_label["state_label"]:
                    
                        # append new plate no to list of already recognized plates
                        self.plates.append(plate_no)

                        # update car slot with plate_no, plate_img data
                        car.plate_no = plate_no
                        car.plate_img = plate_img

                        # save img used for lpr frame
                        car.lpr_img = frame.copy()
                        draw_box(car.lpr_img, car.bbox, color=(50, 50, 220), line_thickness=3)
                        draw_box(car.lpr_img, car.plate_bbox, color=(50, 50, 220), line_thickness=3)
                    
                    print (f'[PlateRecognition] Wrote image for plate {plate_no} to {cropped_fname}')
                    self.api_interface.update_plate_event(cropped_fname, plate_num, plate_type, plate_state, plate_country)
            '''        
            '''
            if len(lpr_results) > 0 and len(lpr_results[0].plates) > 0:
                # get plate no
                plate = lpr_results[0].plates[0]
                plate_no = f'{self._city_code(plate.state_string)} {plate.value_unicode}'.strip()

                # if plate no is NEW then save img to disk
                if plate_no not in self.plates[stream_no]:

                    # save vehicle, cropped plate images
                    fname = os.path.join(folder, f'{tstamp}-{plate_no}.jpg') 
                    cropped_fname = os.path.join(folder, f'{tstamp}-{plate_no}-pl.jpg')                             
                    cv2.imwrite(fname, car_img)
                    cv2.imwrite(cropped_fname, plate_img)
                    
                    # append new plate no to list of already recognized plates
                    self.plates[stream_no].append(plate_no)

                    # update car slot with plate_no, plate_img data
                    car.plate_no = plate_no
                    car.plate_img = plate_img

                    # save img used for lpr frame
                    car.lpr_img = frame.copy()
                    draw_box(car.lpr_img, car.bbox, color=(50, 50, 220), line_thickness=3)
                    draw_box(car.lpr_img, car.plate_bbox, color=(50, 50, 220), line_thickness=3)
                    
                    print (f'[PlateRecognition] Wrote image for plate {plate_no} to {cropped_fname}')

                # DEBUG ONLY
                if len(lpr_results) > 1 and len(lpr_results[1].plates) > 0:
                    print ('$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$')
                    plate = lpr_results[1].plates[0]
                    print (f'Plate No: {plate_no}, Plate No 2: {self._city_code(plate.state_string)} {plate.value_unicode}'.strip())
                elif len(lpr_results[0].plates) > 1:
                    print ('******************************************')
            '''
    # # ------------------------
    # # send plate image to Carrida alpr module
    # def update(self, plate_rect_params, stream_no: int, frame):

    #     # skip very small detections (probably rubbish or small plates)
    #     if plate_rect_params.width < 20 or plate_rect_params.height < 10:
    #         return

    #     # calculate dir, create it if it doesn't yet exist
    #     folder = os.path.join(self.lpr_dir, datetime.now().strftime("%Y%m%d"), str(stream_no))
    #     if not os.path.exists(folder):
    #         os.makedirs(folder)

    #     # get current timestamp -> use it in vehicle, cropped img filenames
    #     tstamp = datetime.now().strftime("%H%M%S")

    #     # extract plate image from frame using coords from LPD 
    #     # -> after increasing the plate bbox
    #     plate_minx, plate_maxx = int(plate_rect_params.left), int(plate_rect_params.left + plate_rect_params.width)
    #     plate_miny, plate_maxy = int(plate_rect_params.top), int(plate_rect_params.top + plate_rect_params.height)                
    #     plate_minx = plate_minx - 20 if plate_minx - 20 > 0 else 0
    #     plate_miny = plate_miny - 10 if plate_miny - 10 > 0 else 0
    #     plate_maxx = plate_maxx + 20 if plate_maxx + 20 < self.width else self.width
    #     plate_maxy = plate_maxy + 10 if plate_maxy + 10 < self.height else self.height
    #     plate_img = frame[plate_miny:plate_maxy, plate_minx:plate_maxx]
        
    #     # # DEBUG ONLY - write full frame + bbox
    #     # plate_bbox = box(plate_minx, plate_miny, plate_maxx, plate_maxy)
    #     # draw_box(frame, plate_bbox, color=(50, 50, 220), line_thickness=3, label="")
    #     # fname = os.path.join(folder, f'{tstamp}.jpg') 
    #     # cv2.imwrite(fname, frame)                    

    #     # convert img to form suitable for Carrida detection
    #     img = cv2.cvtColor(plate_img, cv2.COLOR_BGRA2GRAY)
    #     lpr_img = alpr.svcapture.Image()
    #     lpr_img.set(img)

    #     # do alpr                    
    #     result, lpr_results = self.lpr.process(lpr_img)  
        
    #     if len(lpr_results) > 0 and len(lpr_results[0].plates) > 0:
    #         # get plate no
    #         plate = lpr_results[0].plates[0]
    #         plate_no = f'{self._city_code(plate.state_string)} {plate.value_unicode}'.strip()

    #         print (f'[PlateRecognition] Plate read {plate_no}')
    #         print(self.plates[stream_no])

    #         # if plate no is NEW then save img to disk
    #         if plate_no not in self.plates[stream_no]:
                
    #             print (f'[PlateRecognition] Plate read II {plate_no}')

    #             # save vehicle, cropped plate images
    #             fname = os.path.join(folder, f'{tstamp}-{plate_no}.jpg') 
    #             cropped_fname = os.path.join(folder, f'{tstamp}-{plate_no}-pl.jpg')                             
    #             cv2.imwrite(fname, frame)
    #             cv2.imwrite(cropped_fname, plate_img)
                
    #             print (f'[PlateRecognition] Wrote plate image to {cropped_fname}')

    #             # append new plate no to list of already recognized plates
    #             self.plates[stream_no].append(plate_no)

    #         # DEBUG ONLY
    #         if len(lpr_results) > 1 and len(lpr_results[1].plates) > 0:
    #             print ('$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$')
    #             plate = lpr_results[1].plates[0]
    #             print (f'Plate No: {plate_no}, Plate No 2: {self._city_code(plate.state_string)} {plate.value_unicode}'.strip())
    #         elif len(lpr_results[0].plates) > 1:
    #             print ('******************************************')


    # Convert Carrida supplied city code to default code
    def _city_code(self, state_string):
        if state_string == 'STATE-QAT-ENGLISH' or state_string == 'STATE-QAT-ARABIC' or state_string == 'STATE-QAT-LOGO':
            return 'QAT'
        elif state_string == 'STATE-DXB-ENGLISH' or state_string == 'STATE-DXB-ARABIC' or state_string == 'STATE-DXB-LOGO':
            return 'DXB'
        elif state_string == 'STATE-AUH-ENGLISH' or state_string == 'STATE-AUH-ARABIC' or state_string == 'STATE-AUH-LOGO':
            return 'AUH'
        elif state_string == 'STATE-SHJ-ENGLISH' or state_string == 'STATE-SHJ-ARABIC' or state_string == 'STATE-SHJ-LOGO':
            return 'SHJ'
        elif state_string == 'STATE-FUJ-ENGLISH' or state_string == 'STATE-FUJ-ARABIC' or state_string == 'STATE-FUJ-LOGO':
            return 'FUJ'
        elif state_string == 'STATE-RAK-ENGLISH' or state_string == 'STATE-RAK-ARABIC' or state_string == 'STATE-RAK-LOGO':
            return 'RAK'
        elif state_string == 'STATE-AJM-ENGLISH' or state_string == 'STATE-AJM-ARABIC' or state_string == 'STATE-AJM-LOGO':
            return 'AJM'
        elif state_string == 'STATE-UAQ-ENGLISH' or state_string == 'STATE-UAQ-ARABIC' or state_string == 'STATE-UAQ-LOGO':
            return 'UAQ'
        elif state_string == 'STATE-KSA-ENGLISH' or state_string == 'STATE-KSA-ARABIC' or state_string == 'STATE-KSA-LOGO':
            return 'KSA'
        '''
        if state_string == 'AE/DU':
            return 'DXB'
        elif state_string == 'AE/AZ':
            return 'AZ'
        elif state_string == 'AE/AJ':
            return 'AJM'
        elif state_string == 'AE/UQ':        
            return 'UAQ'
        elif state_string == 'AE/SH':        
            return 'SHJ'
        elif state_string == 'AE/RK':        
            return 'RAK'
        elif state_string == 'BH':
            return 'BHR'
        elif state_string == 'KW':
            return 'KWT'
        elif state_string == 'SA':
            return 'KSA'
        elif state_string == 'OM':
            return 'OMN'
        else:
            print (f'state_string: {state_string}')
            return state_string.replace('/', '_')
         '''
