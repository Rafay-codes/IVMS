import numpy as np
import torch
import cv2

from LPR_QAT.utils.general import check_img_size, non_max_suppression, apply_classifier, scale_boxes
from LPR_QAT.models.experimental import attempt_load
from LPR_QAT.utils.torch_utils import select_device, time_sync
# from utils.plots import plot_one_box
from LPR_QAT.utils.datasets import letterbox

class ObjectDetector(object):
    """
        Implements object detection using YOLO v5 model
        source: https://github.com/ultralytics/yolov5    

        Remarks: Added mode argument. 'default' is for pedestrian zone violations.
    """

    def __init__(self, cfg, mode = 'default'):

        self.augment = False        # augmented inference flag (hardcoded here)     
        self.classes = None         # filter by class: --class 0, or --class 0 2 3 (flag from original yolov5 repo, not actually used)
        self.agnostic_nms = False   # class-agnostic NMS (flag from original yolov5 repo, not actually used)        

        # Load params from settings file
        dev = '' if cfg.DETECTIONS.DEVICE is None else cfg.DETECTIONS.DEVICE                        
        self.conf_thres = cfg.DETECTIONS.CONF_THRES
        self.iou_thres = cfg.DETECTIONS.IOU_THRES
        
        #weights
        if mode == 'default':
            self.img_size = cfg.DETECTIONS.PED.IMG_SIZE
            weights = cfg.DETECTIONS.PED.WEIGHTS
        elif mode == 'mobile':
            self.img_size = cfg.DETECTIONS.MOBI.IMG_SIZE
            weights = cfg.DETECTIONS.MOBI.WEIGHTS
        elif mode == 'lpr':
            self.img_size = cfg.DETECTIONS.LPR.IMG_SIZE
            weights = cfg.DETECTIONS.LPR.WEIGHTS
        elif mode == 'ocr':
            self.img_size = cfg.DETECTIONS.OCR.IMG_SIZE
            weights = cfg.DETECTIONS.OCR.WEIGHTS
        elif mode == 'ldms':
            self.img_size = cfg.DETECTIONS.LDMS.IMG_SIZE
            weights = cfg.DETECTIONS.LDMS.WEIGHTS
        elif mode in ['noentry', 'wrongentry']:
            self.img_size = cfg.DETECTIONS.NOENTRY.IMG_SIZE
            weights = cfg.DETECTIONS.NOENTRY.WEIGHTS

        # Initialize
        self.device = select_device(dev)
        self.half = self.device.type != 'cpu'  # half precision only supported on CUDA

        # Load model
        self.model = attempt_load(weights, device=self.device)  # load FP32 model        
        self.stride = int(self.model.stride.max())  # model stride
        self.img_size = check_img_size(self.img_size, s=self.stride)  # check img_size
        if self.half:
            self.model.half()  # to FP16

        # Second-stage classifier
        self.classify = False
        #if self.classify:
        #    self.modelc = load_classifier(name='resnet101', n=2)  # initialize
        #   self.modelc.load_state_dict(torch.load('weights/resnet101.pt', map_location=self.device)['model']).to(self.device).eval()

        # Get class names 
        self.class_names = self.model.module.names if hasattr(self.model, 'module') else self.model.names                      

        # object colors (only for debugging)
        self.colors = [[np.random.randint(0, 255) for _ in range(3)] for _ in self.class_names]

        # Run inference
        if self.device.type != 'cpu':
            self.model(torch.zeros(1, 3, self.img_size, self.img_size).to(self.device).type_as(next(self.model.parameters())))  # run once

        # Print message from object detector
        print (f'[ObjectDetector:init] Loaded model for weights: {weights}. Classes: {self.class_names}')
    def detect_objects(self, frame, mode):

        if mode == 'stream':
            # Letterbox
            img = [letterbox(frame, self.img_size, auto=True, stride=self.stride)[0]]
            
            # Stack
            img = np.stack(img, 0)

            # Convert
            img = img[:, :, :, ::-1].transpose(0, 3, 1, 2)  # BGR to RGB, to bsx3x416x416
            img = np.ascontiguousarray(img)

        elif mode == 'video':
            # Padded resize
            img = letterbox(frame, self.img_size, stride=self.stride)[0]

            # Convert
            img = img[:, :, ::-1].transpose(2, 0, 1)  # BGR to RGB, to 3x416x416
            img = np.ascontiguousarray(img)


        img = torch.from_numpy(img).to(self.device)
        img = img.half() if self.half else img.float()  # uint8 to fp16/32
        img /= 255.0  # 0 - 255 to 0.0 - 1.0
        if img.ndimension() == 3:
            img = img.unsqueeze(0)

        # Inference
        #t1 = time_sync()
        pred = self.model(img, augment=self.augment)[0]

        # Apply NMS
        pred = non_max_suppression(pred, self.conf_thres, self.iou_thres, classes=self.classes, agnostic=self.agnostic_nms)
        #t2 = time_sync()

        # Apply Classifier
        if self.classify:
            pred = apply_classifier(pred, self.modelc, img, frame)

        # ---- Process detections       
        
        # we only have one stream (original yolov5 repo handles multiple input video streams, hence pred is a list)
        det = pred[0]  
        
        if det is not None and len(det):

            # Rescale boxes from img_size to im0 size
            det[:, :4] = scale_boxes(img.shape[2:], det[:, :4], frame.shape).round()

            return det

            # commented below in order to return det
            #boxes = det[:, :4].cpu().numpy()
            #scores = det[:,4:5].cpu().numpy().flatten()
            #classes = det[:,5:].cpu().numpy().flatten()
            #valid_detections = len(det)

            ## transpose to get yolov4 compatible result
            #classes = np.transpose(classes)
            #scores = np.transpose(scores)         
            
            ## Draw bboxes with labels
            #for *xyxy, conf, cls in reversed(det):            
            #    label = f'{self.class_names[int(cls)]} {conf:.2f}'
            #    plot_one_box(xyxy, frame, label=label, color=self.colors[int(cls)], line_thickness=3)
        
            # commented below in order to return det
            #return boxes, scores, classes, valid_detections

        else:
            return None #, None, None, 0

        # Print time (inference + NMS)
        #print(f'Done. ({t2 - t1:.3f}s) FPS: {1.0 / (t2 - t1)} ')

     


