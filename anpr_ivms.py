import os

import time
import base64
import requests
import json
import glob
import shutil
from datetime import datetime

import cv2
from PIL import Image
import pika

from copy import deepcopy

from LPR_QAT.core.object_detector import ObjectDetector
from LPR_QAT.core.yaml_parser import YamlParser
from LPR_QAT.core.alpr_ktc import alpr_ktc

import traceback

class ANPR_IVMS(object):
    def __init__(self):
        self.url = 'http://192.168.10.111:4466/api/RecognizeImage/'
        self.lpr_dir_path = '/home/nvidia/ivms/.lpr'
        self.lpr_dir = os.path.join('/home/nvidia/ivms/lpr', datetime.now().strftime("%Y%m%d"))
        if not os.path.exists(self.lpr_dir):
            os.makedirs(self.lpr_dir)
        
        self.images_dirs = []
        
        # KTC OCR inits
        # Read YAML config file using YamlParser class 
        cfg = YamlParser(config_file="LPR_QAT/config/app_settings.yaml")
        
        ocr_detector = ObjectDetector(cfg, mode='ocr')
        self.lpr = alpr_ktc(ocr_detector)

        self.init_rabbitmq()
    
    def init_rabbitmq(self):
        # get this from config file
        rabbitmq_host = '127.0.0.1'
        connection_params = pika.ConnectionParameters(host=rabbitmq_host)
        # Establish connection
        connection = pika.BlockingConnection(connection_params)
        self.channel = connection.channel()

        # Declare a queue
        self.channel.queue_declare(queue='anpr', durable=False)
    
    def ktclpr_result_to_json(self,lpr_results):
       response_json = {"PlateText": "UnRec", "StateLong": "UnRec", "CountryLong": "UnRec"}
       if lpr_results is not None:
           response_json["PlateText"] = f'{lpr_results.decoded_label["prefix_label"]}' if lpr_results.decoded_label["prefix_label"] else 'NA'
           response_json["PlateText"] = f'{response_json["PlateText"]} {lpr_results.decoded_label["platenum_label"]}' if lpr_results.decoded_label["platenum_label"] else 'UnRec'
           response_json["StateLong"] = f'{self._city_code(lpr_results.decoded_label["state_label"])}' if lpr_results.decoded_label["state_label"] else 'UnRec'
           response_json["CountryLong"] = f'{self._country_code(lpr_results.decoded_label["state_label"])}' if lpr_results.decoded_label["state_label"] else 'UnRec'
       return response_json       
            
    def run(self):
        while(1):
            self.images_dir_path = os.path.join(self.lpr_dir_path, datetime.now().strftime("%Y%m%d"))
            self.images_dirs = [os.path.join(self.images_dir_path,i) for i in os.listdir(self.images_dir_path)]
            #print(self.images_dirs)
            
            for folder in self.images_dirs:
                    if 'unrec' in folder:
                        continue
                    #print(folder)
                    for img_path in glob.glob(os.path.join(folder, '*.png')):
                        try:
                            #print(img_path)
                            # Get the creation time
                            creation_time = datetime.fromtimestamp(os.path.getctime(img_path))#.strftime('%Y-%m-%d %H:%M:%S')
                            time_now = datetime.now()#.strftime('%Y-%m-%d %H:%M:%S')
                            
                            if (time_now-creation_time).seconds < 2:
                                continue
                            img = cv2.imread(img_path)
                        
                            # resize - recommended by Adeel(TechnoOCR)
                            #(h, w) = img.shape[:2]
                            #img = self.image_resize(img, height=(3*h))

                            if img is not None:
                                if 0: # TODO: make it configurable from app_settings.yaml to use technoocr
                                    response_json = deepcopy(self.simpleDetect(img))
                                else:
                                    response = deepcopy(self.lpr.process(img))
                                    response_json = self.ktclpr_result_to_json(response)
                                    
                                plate_details, dest_fname = self.postProcessDetails(response_json, img_path, img)
                                if (plate_details is not None) and (dest_fname is not None):
                                    # Publish a message
                                    self.channel.basic_publish(exchange='', routing_key='anpr', body=plate_details)
                                    #print("Message sent to UI via RabbitMQ!")
                            else:
                                os.remove(img_path)
                            
                        except Exception as e:
                             print("[ANPR_IVMS] Exception raised.", e, traceback.format_exc())
                             #os.remove(img_path)
                             #shutil.move(img_path, os.path.basename(os.path.dirname(img_path))+'_unrec')
                             self.moveToUnrecFolder(img_path)
            
            #print("Sleeping. Retry after 5 seconds...")        
            #time.sleep(5)
        
    def postProcessDetails(self, response_json:dict, img_path:str, img:None):
    
        plate_num = f'{response_json["PlateText"]}'.strip()
        plate_state = f'{response_json["StateLong"]}'.strip()
        plate_country = f'{response_json["CountryLong"]}'.strip()
        final_plate_details = f'{plate_country} {plate_state} {plate_num}'.strip()
        dest_fname = None
        #print("Response received from OCR system:", final_plate_details)
        #if (plate_num is not None) and (plate_num != "None") and (plate_num != "UnRec"):
        if ("UnRec" not in final_plate_details) and ("None" not in final_plate_details):
            dest_folder = os.path.join(self.lpr_dir, os.path.basename(os.path.dirname(img_path)))
            if not os.path.exists(dest_folder):
                os.makedirs(dest_folder)
            
            dest_fname = os.path.join(dest_folder, final_plate_details+".jpg")
            if not os.path.exists(dest_fname):
                color_coverted = cv2.cvtColor(img, cv2.COLOR_BGR2RGB) 
                pil_image = Image.fromarray(color_coverted) 
                exif = pil_image.getexif()
                exif[0x010e] = f'{os.path.splitext(os.path.basename(img_path))[0]}'
                pil_image.save(dest_fname, quality=95, exif=exif)
                os.remove(img_path)
                
                return final_plate_details, dest_fname

        # DEBUG
        self.moveToUnrecFolder(img_path,final_plate_details)

        return None, dest_fname
    
    def moveToUnrecFolder(self, img_path, final_plate_details=""):
    
        dest_folder = os.path.join(self.images_dir_path, os.path.basename(os.path.dirname(img_path))+'_unrec' )
        if not os.path.exists(dest_folder):
            os.makedirs(dest_folder)
        dest_fname_local = os.path.join(dest_folder, f'{final_plate_details}_{os.path.basename(img_path)}')
    
        #print(img_path, dest_fname_local)
        shutil.move(img_path, dest_fname_local)
        #cv2.imwrite(dest_fname_local, img)
        #os.remove(img_path)
        
    def image_resize(self, image, width = None, height = None, inter = cv2.INTER_AREA):
        # initialize the dimensions of the image to be resized and
        # grab the image size
        dim = None
        (h, w) = image.shape[:2]

        # if both the width and height are None, then return the
        # original image
        if width is None and height is None:
            return image

        # check to see if the width is None
        if width is None:
            # calculate the ratio of the height and construct the
            # dimensions
            r = height / float(h)
            dim = (int(w * r), height)

        # otherwise, the height is None
        else:
            # calculate the ratio of the width and construct the
            # dimensions
            r = width / float(w)
            dim = (width, int(h * r))

        # resize the image
        resized = cv2.resize(image, dim, interpolation = inter)

        # return the resized image
        return resized
    
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
   
    def _country_code(self, state_string):
        if state_string == 'STATE-QAT-ENGLISH' or state_string == 'STATE-QAT-ARABIC' or state_string == 'STATE-QAT-LOGO':
            return 'QAT'
        elif state_string == 'STATE-DXB-ENGLISH' or state_string == 'STATE-DXB-ARABIC' or state_string == 'STATE-DXB-LOGO' or \
             state_string == 'STATE-AUH-ENGLISH' or state_string == 'STATE-AUH-ARABIC' or state_string == 'STATE-AUH-LOGO' or \
             state_string == 'STATE-SHJ-ENGLISH' or state_string == 'STATE-SHJ-ARABIC' or state_string == 'STATE-SHJ-LOGO' or \
             state_string == 'STATE-FUJ-ENGLISH' or state_string == 'STATE-FUJ-ARABIC' or state_string == 'STATE-FUJ-LOGO' or \
             state_string == 'STATE-RAK-ENGLISH' or state_string == 'STATE-RAK-ARABIC' or state_string == 'STATE-RAK-LOGO' or \
             state_string == 'STATE-AJM-ENGLISH' or state_string == 'STATE-AJM-ARABIC' or state_string == 'STATE-AJM-LOGO' or \
             state_string == 'STATE-UAQ-ENGLISH' or state_string == 'STATE-UAQ-ARABIC' or state_string == 'STATE-UAQ-LOGO':
            return 'UAE'
        elif state_string == 'STATE-KSA-ENGLISH' or state_string == 'STATE-KSA-ARABIC' or state_string == 'STATE-KSA-LOGO':
            return 'KSA'
            
    def simpleDetect(self, img):
        response_json = None
        
        try:
                
                jpg_img = cv2.imencode('.jpg', img)
                b64_string = base64.b64encode(jpg_img[1]).decode('utf-8')
                
                myobj = {"Imagdata":b64_string,"CameraId":1,"SiteName":"DubaiPolice","processedFileId":1,"UID":"IVMS","UPASS":"KTC"}
                #print(myobj)

                x = requests.post(self.url, json = myobj, timeout=120)
                
                response_txt = x.text
                response_json = json.loads(response_txt)[0]

                #print(response_json["PlateText"], response_json["CountryLong"], response_json["StateLong"])
                
                # check if 200 status code, else send None
        except requests.ConnectionError:
               print("Failed querying to OCR PC")
               
        return response_json
        
# ================================================================

if __name__ == '__main__':
    obj = ANPR_IVMS()
    obj.run()
    #img = cv2.imread('/home/nvidia/4_ocr.jpg')
    #obj.simpleDetect(img)     
