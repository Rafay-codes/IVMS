from easydict import EasyDict as edict
from utils.bbox import rect_params_to_box

# custom model classes
BELT = 0
NO_BELT = 1
MOBILE = 2
CAR = 3
STEERING_WHEEL = 4
PHONE_HOLDER = 5
PLATE = 6

# convert DeepStream metadata to dictionary object 
#  -> used for plate recognition and violation detection 
def get_detection_from_meta(obj_meta):

    # also check: obj_meta.detector_bbox_info.org_bbox_coords
    bbox = rect_params_to_box(obj_meta.rect_params) 
       
    if obj_meta.class_id == CAR:   
        det = edict({
            'id': obj_meta.object_id,
            'bbox': bbox,
            'class_id' : obj_meta.class_id,
            'score': obj_meta.confidence,
                        
            'fi': None,         # is updated if we have a new car detection with the same id, or if id is a new one
            'matched': False,   # used by plate matching procedure -> set to True if car is matched to a plate
            'plate_bbox': None, # used for car objects by plate matching procedure
            'plate_no': None,   # is updated once a plate has been read for an object maintained in car slots list
            'plate_img': None,  # cropped image of license plate
            'lpr_img': None,    # lpr frame; it is set by plate recognition module
            'lpr_img_save_count': 0,
            
            'lpr_imgs_dict': {'30':0,'40':0,'50':0,'60':0,'65':0,'70':0,'75':0,'80':0,'85':0,'90':0},

            # -- used by violation detection module --
            'violation_fi': None,
            #'violation_img': None,
            'violation_timestamp': None,
            'violation_sent': False,
            'violation_bbox': None,
           

            'maxy': obj_meta.rect_params.top + obj_meta.rect_params.height,  # used to sort the slots, from closest to furthest
            'st_wheel': None,                                                # ref to st. wheel object during current frame

            'mobile_detected': False,
            'mobile_violations': 0,
            'mobile_det_timestamp': None,
            'mobile_det_fi': None,
            'mobile_bbox': None,

            'nobelt_driver': 0,
            'nobelt_driver_fi': None,
            #'nobelt_driver_image': None,
            'nobelt_bbox': None,
            'nobelt_driver_timestamp': None
        })
    elif obj_meta.class_id == STEERING_WHEEL:
        det = edict({
            'id': obj_meta.object_id,
            'bbox': bbox,
            'class_id' : obj_meta.class_id,
            'score': obj_meta.confidence,
            'assigned': False
        })
    else:
        det = edict({
            'id': obj_meta.object_id,
            'bbox': bbox,
            'class_id' : obj_meta.class_id,
            'score': obj_meta.confidence,
            'processed': False
        })

    return det