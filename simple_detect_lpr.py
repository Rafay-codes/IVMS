import cv2
import numpy as np
import torch
from shapely import geometry

from LPR_QAT.core.object_detector import ObjectDetector
from LPR_QAT.core.yaml_parser import YamlParser

from LPR_QAT.core.alpr_ktc import alpr_ktc

from LPR_QAT.core.helpers import draw_box

custom_anpr = None
ocr_detector = None
cf=None
def detect():
    # Read YAML config file using YamlParser class 
    cfg = YamlParser(config_file="LPR_QAT/config/app_settings.yaml")
    
    # configure application logging
    # configure_logging(cfg, src='lpr')

    ocr_detector = None
    ocr_detector = ObjectDetector(cfg, mode='ocr')

    custom_anpr = alpr_ktc(ocr_detector)

    for i in range(0,3):
        img = cv2.imread(f'{i}.jpg')

        result = custom_anpr.process(img)

        if result is not None:        
            print(result.decoded_label.full_label)
        
        for idx, ocr_poly in enumerate(result.info_ocr.char_poly):
            #print(idx, result.info_ocr.char_id[idx])
            #print(idx, ocr_poly)
            draw_box(img, ocr_poly, color=(0,0,128), label=str(result.info_ocr.char_id[idx]), line_thickness=1, text_outside_box=True)
        cv2.imshow("", img)
        cv2.waitKey(2000)

def simpleDetect(img, displayDetections=False):
    global cfg, ocr_detector, custom_anpr

    if 1:
        result = custom_anpr.process(img)

        if result is not None:
            if displayDetections:
                #for idx, ocr_poly in enumerate(result.info_ocr.char_poly):
                #    draw_box(img, ocr_poly, color=(0,0,128), label=str(result.info_ocr.char_id[idx]), line_thickness=1, text_outside_box=True)
                draw_box(img, result.info_platenum.polygon, color=(0,0,128), line_thickness=1, text_outside_box=True)
                draw_box(img, result.info_prefix.polygon, color=(0,0,128), line_thickness=1, text_outside_box=True)
                for idx, ocr_poly in enumerate(result.info_ocr.char_poly):
                    #print(idx, result.info_ocr.char_id[idx])
                    #print(idx, ocr_poly)
                    draw_box(img, ocr_poly, color=(0,0,128), line_thickness=1, text_outside_box=True)
                
                print(result.decoded_label.full_label)
            else:
                print(result.decoded_label.full_label, result.decoded_label["platenum_label"], result.info_platenum)
        if displayDetections:
            #cv2.imshow("", img)
            #cv2.waitKey(1)
            cv2.imwrite("out.png", img)

def init():
    global cfg, ocr_detector, custom_anpr
    # Read YAML config file using YamlParser class 
    cfg = YamlParser(config_file="LPR_QAT/config/app_settings.yaml")
    
    # configure application logging
    # configure_logging(cfg, src='lpr')
    ocr_detector = ObjectDetector(cfg, mode='ocr')

    custom_anpr = alpr_ktc(ocr_detector)
    
def runFromCamera(displayDetections=False):
    cap = cv2.VideoCapture(0)
    while(cap.isOpened()):
        _, frame = cap.read()
        h, w, _ = frame.shape
        cap_h, cap_w = 180, 350
        x1, y1 = w/2 - cap_w/2, h/2-cap_h/2
        x2, y2 = x1 + cap_w, y1+cap_h
        poly = geometry.Polygon([(x1, y1), (x2,y1), (x2,y2), (x1, y2),(x1, y1)])
        #draw_box(frame, poly, color=(0,0,255))
        #cv2.imshow("", frame)
        #cv2.waitKey(1)
        simpleDetect(frame[int(y1):int(y2),int(x1):int(x2),:], displayDetections)
        
# ================================================================

if __name__ == '__main__':
    with torch.no_grad():
        init()
        #runFromCamera(displayDetections=True)
        img = cv2.imread('/srv/ivms/detect/UnRec UnRec UnRec_1397_10_17_35_565400_172.png')
        #print(type(img), np.unique(img)) 
        #cv2.imwrite("out.png", img)
        #cv2.waitKey(5)
        simpleDetect(img, displayDetections=True)     
