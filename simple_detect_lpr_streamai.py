import cv2
import base64
import requests
import json

class PlateRecognitionTechnoStreamAI(object):
    def __init__(self):
        self.url = 'http://192.168.10.111:4466/api/RecognizeImage/'
        
    def simpleDetect(self, img):
        response_json = None
        
        try:
                jpg_img = cv2.imencode('.jpg', img)
                b64_string = base64.b64encode(jpg_img[1]).decode('utf-8')
                
                myobj = {"Imagdata":b64_string,"CameraId":1,"SiteName":"DubaiPolice","processedFileId":1,"UID":"IVMS","UPASS":"KTC"}

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
    obj = PlateRecognitionTechnoStreamAI()
    img = cv2.imread('/home/nvidia/4_ocr.jpg')
    obj.simpleDetect(img)     
