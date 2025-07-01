import os
import logging
import cv2

from datetime import datetime
from easydict import EasyDict as edict
from shapely import geometry

import core.detection_object as do
from utils.draw import draw_box

class MSViolationDetector(object):
    """Implements mobile / seatbelt violation detections"""
    
    # above this score the mobile object detection is considered valid
    MOBILE_CONF_THRES = 0.10

    # above this score the no-belt object detection is considered valid
    NOBELT_CONF_THRES = 0.10

    # above this score the belt object detection is considered valid
    BELT_CONF_THRES = 0.10

    def __init__(self):               
        self.violations_counter = 0 # used to assign ids to violations

    # # update the data structures that hold detected data
    # def update(self, detections, alpr_cars, stream_no, fi):

    #     objects = []    # belt, no belt, mobile
    #     st_wheels = []

    #     # get a ref to the vehicle slots of the current stream; easier to work with!
    #     v_slots = self.v_slots[stream_no]

    #     # --- CLEAR slots that have not been updated since configured number of frames
    #     # see https://stackoverflow.com/questions/1207406/how-to-remove-items-from-a-list-while-iterating
    #     v_slots[:] = [slt for slt in v_slots if slt.frame_index[-1] + self.REMOVE_SLOT_AFTER_FRAMES >= fi]

    #     try:

    #         for det in detections:
    #             if det.name in ['belt', 'no belt', 'mobile']:
    #                 obj = edict({
    #                     'bbox': det.bbox,
    #                     'name': det.name,
    #                     'score': det.score,
    #                     'processed': False
    #                 })
    #                 objects.append(obj)
                    
    #             elif det.name == 'steering wheel':
    #                 obj = edict({
    #                     'bbox': det.bbox,
    #                     'name': det.name,
    #                     'score': det.score,
    #                     'assigned': False
    #                 })
    #                 st_wheels.append(obj)
                    
    #             else: # -> it's a vehicle!

    #                 # cross check id with ids of vehicles where alpr was applied  
    #                 # -> alpr_cars contains those tracked vehicles that were detected for 3rd/4th time in a row
    #                 alpr_car = next((c for c in alpr_cars if c.id == det.id), None)
                
    #                 # check if vehicle is already contained in a slot
    #                 v_slot = next((v_slot for v_slot in v_slots if v_slot.id == det.id), None)
                    
    #                 if v_slot is None:  # id has not yet been added to a slot

    #                     if not alpr_car:
    #                         # we wait until the vehicle is tracked at least 3 times and alpr has been applied once on it
    #                         continue

    #                     #print (f"[MSViolationDetector:update] New vehicle in slot, stream: {stream_no}, id:{det.id}, plate: {alpr_car.plate_no}")

    #                     # create a NEW slot
    #                     v_slot = edict({
    #                         'id': det.id,
    #                         'plate_no': alpr_car.plate_no,
    #                         'plate_img': alpr_car.cropped_img,
    #                         'violation_id': None,
    #                         'violation_img': None,
    #                         'violation_fi': None,
    #                         'violation_timestamp': None,
    #                         'violation_sent': False,

    #                         'st_wheel': None,           # ref to st. wheel object during current frame

    #                         'crossed_entry_line': False,   
    #                         'entry_fi': None,                 
    #                         'entry_timestamp': None,
    #                         'crossed_bottom_edge': False,
    #                         'bottom_edge_fi': None,
    #                         'bottom_edge_timestamp': None,

    #                         'mobile_detected': False,
    #                         'mobile_det_fi': None,
    #                         'mobile_det_timestamp': None,
    #                         'mobile_violations': 0,
                                                            
    #                         'nobelt_driver_fi': None,
    #                         'nobelt_driver_timestamp': None,
    #                         'nobelt_driver_image': None,
    #                         'nobelt_driver': 0,

    #                         'maxy': 0,         # used to sort the slots, from closest to furthest
    #                         'frame_index': [],  
    #                         'bbox': [],
    #                         'score': [] 
    #                     })

    #                     v_slots.append(v_slot)
    #                 elif v_slot.plate_no is None and alpr_car is not None and alpr_car.plate_no is not None:
    #                         # we have a case where plate no was detected after 3rd frame
    #                         v_slot.plate_no = alpr_car.plate_no
    #                         v_slot.plate_img = alpr_car.cropped_img

    #                         # DEBUG ONLY
    #                         #print (f'### Found plate no for vehicle with id = {v_slot.id}, plate no = {alpr_car.plate_no}')
    #                         #cropped_fname = f'{datetime.now().strftime("%H%M%S")}-{alpr_car.plate_no}.jpg' 
    #                         #cv2.imwrite(cropped_fname, alpr_car.cropped_img)

    #                 # st. wheel is initialized for current frame
    #                 v_slot.st_wheel = None                

    #                 # update maxy property
    #                 min, miny, maxx, maxy = det.bbox.bounds
    #                 v_slot.maxy = maxy
                    
    #                 v_slot.bbox.append(det.bbox)
    #                 v_slot.frame_index.append(fi)
    #                 v_slot.score.append(det.score)
        
    #     except Exception:
    #         logging.exception("[MSViolationDetector] Error during update()") 
                 
    #     return objects, st_wheels

    # perform mobile / seatbelt violation detection using the detections object of current frame
    def detect(self, v_slots, viol_objects, st_wheels, stream_no, fi, frame):
        # get current timestamp formatted as string 
        timestamp = datetime.now().strftime("%Y%m%d.%H%M%S.%f")[:-3]
      
        # ---- we process all vehicles looking for detections
        # - We consider only vehicles having slots updated during current frame AND not yet returned as violations
        # - Closest vehicles are processed first 
        # -> this way a person poly that is inside two vehicles will be placed inside the closest vehicle 
        #    (i.e. the vehicle that is in the front)
        newlist = [sl for sl in v_slots if sl.fi == fi and not sl.violation_sent]
        newlist = sorted(newlist, key=lambda k: k.maxy, reverse=True) 

        #print("[KTC][DEBUG] Detect called")
        # ------------
        
        # # DEBUG ONLY
        # path = os.path.dirname(os.path.abspath(__file__))
        # folder = os.path.join(path, str(fi))

        # if fi % 6 == 0:
        #     fname = os.path.join(folder, f'{datetime.now().strftime("%Y%m%d_%H%M%S.%f")}.{fi}.jpg')

        #     if not os.path.exists(folder):
        #         os.makedirs(folder)
            
        #     img = frame.copy()
        #     i = 1
        #     for v_slot in newlist:
        #         draw_box(img, v_slot.bbox, label=f"ID: {v_slot.id}, {i}")
        #         i += 1
        #     # for sw in st_wheels:
        #     #     draw_box(img, sw.bbox, label=f"sw {int(sw.score*100)}%", color=(50, 50, 220), line_thickness=3)
        #     for obj in viol_objects:
        #         draw_box(img, obj.bbox, label=f"{obj.class_id} {int(obj.score*100)}%", color=(50, 50, 220), line_thickness=3)
        #     print(f'Writing file {fname}')
        #     cv2.imwrite(fname, img)

        # -------------

        for v_slot in newlist: # <-- closest vehicle is processed first
            
            # we reset st. wheel possibly set during previous frame
            v_slot.st_wheel = None

            # get vehicle's bbox
            v_poly = v_slot.bbox

            # --- check for mobile / seatbelt violations INSIDE the CURRENT vehicle
            try:

                # STEERING WHEEL DETECTION
                # --- we find the steering wheel of the vehicle (if anyone is detected); 
                # already assigned steering wheels are skipped
                for sw in [sw for sw in st_wheels if not sw.assigned]:
                    # steering wheel must be completely inside the vehicle
                    if v_poly.contains(sw.bbox):                        
                        if not v_slot.st_wheel:
                            # vehicle slot st. wheel is none so far -> add this one
                            v_slot.st_wheel = sw
                            sw.assigned = True
                        else:
                            # vehicle slot already contains st. wheel -> find best between matches
                            vminx, vminy, vmaxx, vmaxy = v_slot.st_wheel.bbox.bounds
                            dminx, dminy, dmaxx, dmaxy = sw.bbox.bounds

                            # take the st. wheel that is on the right side
                            if dminx > vmaxx + 50:
                                v_slot.st_wheel.assigned = False # un-assign previous st. wheel object
                                v_slot.st_wheel = sw 
                                sw.assigned = True
                            elif vminx > dmaxx + 50:
                                continue
                            # we have two st. wheels inside same vehicle; none of them is completely on the right
                            # so we prefer the one with the biggest area (in case his score is bigger than 50%)
                            elif sw.score > 0.5 and sw.bbox.area > v_slot.st_wheel.bbox.area:
                                v_slot.st_wheel.assigned = False # un-assign previous st. wheel object
                                v_slot.st_wheel = sw 
                                sw.assigned = True

                # steering wheel has been detected
                #  -> get coordinates of vehicle's steering wheel bbox    
                if v_slot.st_wheel:                    
                    sw_minx, sw_miny, sw_maxx, sw_maxy = v_slot.st_wheel.bbox.bounds    

                    # # DEBUG ONLY: draw st. wheel bbox with the related vehicle ID               
                    # if fi % 6 == 0:                                   
                    #     img = frame.copy()
                    #     draw_box(img, v_slot.st_wheel.bbox, label=f"Stw {int(v_slot.st_wheel.score*100)}%, cid:{v_slot.id}", color=(50, 50, 220), line_thickness=3)
                    #     draw_box(img, v_poly, label=f"ID: {v_slot.id}")
                    #     fname =  os.path.join(folder, f'SW{datetime.now().strftime("%Y%m%d_%H%M%S.%f")}.{v_slot.id}.jpg')

                    #     print (f'Writing st. wheel detection to {fname}')
                    #     cv2.imwrite(fname, img)
                    #print("[KTC][DEBUG] steering wheel detected")
                else:
                    # if NO st. wheel has been identified then 
                    #  -> we cannot process mobile / no seatbelt detections for this vehicle
                    continue

                # --- we cross check [no belt, belt, mobile] detections against the current vehicle slot
                for obj in viol_objects:
                    #print("stage 1 done")
                    # skip viol object if it was processed for some other vehicle
                    if obj.processed:
                        continue
                    # check if poly is inside the current vehicle
                    #elif obj.bbox.intersection(v_poly).area / obj.bbox.area < 0.9:
                    #    continue

                    #print("stage 2", obj.class_id, obj.score)
                    # set flag so that the same object will not be examined again
                    obj.processed = True
                    
                    # get object's bbox coordinates
                    pminx, pminy, pmaxx, pmaxy = obj.bbox.bounds  
                    

                    if obj.class_id == do.MOBILE and not v_slot.mobile_detected:    
                        print("mobile phone detected")         
                        # if mobile phone detection is high enough and it's bbox is on the driver's side 
                        #   -> we have detection!
                        # CAUTION: Factor 0.3 may need to be adjusted for different camera angle
                        if obj.score >= self.MOBILE_CONF_THRES and pmaxx > sw_minx - (sw_maxx - sw_minx) * 0.3:
                            v_slot.mobile_violations += 1 
                            print("mobile phone detected on driver side")

                            # if we have second mobile detection then we have violation
                            if v_slot.mobile_violations >= 2:
                                v_slot.mobile_detected = True
                                v_slot.mobile_det_timestamp = timestamp
                                v_slot.mobile_det_fi = fi  
                                v_slot.mobile_bbox = obj.bbox                                          
                                #v_slot.violation_img = frame.copy()
                                
                                print(f'[V] Mobile phone detected {timestamp}, VID: {v_slot.id}, Stream: {stream_no}, FI: {fi}')                                  
            
                    # we consider belt / no belt detection only if score is above corresponding threshold
                    elif (obj.class_id == do.NO_BELT and obj.score >= self.NOBELT_CONF_THRES) or (obj.class_id == do.BELT and obj.score >= self.BELT_CONF_THRES):
                        
                        # --> p.class_name in ['no belt', 'belt']
                        # check if object is the driver or not 
                        #   --> construct shapely polygon by extending the bbox to the bottom
                        obj_poly = geometry.Polygon([(pminx, pmaxy + 20), (pminx, pminy), (pmaxx, pminy), (pmaxx, pmaxy + 20)])
                                               
                        if 1: #obj_poly.intersects(v_slot.st_wheel.bbox):
                            if obj.class_id == do.NO_BELT:                             
                                v_slot.nobelt_driver += 1

                                print (f'vehile id = {v_slot.id}, v_slot.nobelt_driver = {v_slot.nobelt_driver}', fi)

                                if not v_slot.nobelt_driver_fi:
                                    v_slot.nobelt_driver_fi = fi
                                    v_slot.nobelt_driver_timestamp = timestamp  
                                    v_slot.nobelt_bbox = obj.bbox                                   
                                    #v_slot.nobelt_driver_image = frame.copy()
                            else:
                                v_slot.nobelt_driver -= 1             
                
            except Exception:
                logging.exception("[MSViolationDetector] Error during traversing v_slots in detect()") 
                print("[MSViolationDetector] Error during traversing v_slots in detect()") 

        # --- Get return values         
        # init detections to return 
        ret = []        

        try:

            # Go through ALL slots (except for slots with an already sent violation) and add to ret 
            # list any violation found that has been kept in the slot for too long (e.g. because of 
            # traffic jam)
            for slt in [slt for slt in v_slots if not slt.violation_sent]:

                violation_fi = None
                #violation_img = None
                violation_timestamp = None
                violation_bbox = None

                # get violation FI (if a violation exists)            
                if slt.nobelt_driver >= 1:
                    violation_fi = slt.nobelt_driver_fi      
                    #violation_img = slt.nobelt_driver_image                           
                    violation_timestamp = slt.nobelt_driver_timestamp
                    violation_bbox = slt.nobelt_bbox

                elif slt.mobile_detected:
                    violation_fi = slt.mobile_det_fi
                    #violation_img = slt.violation_img
                    violation_timestamp = slt.mobile_det_timestamp
                    violation_bbox = slt.mobile_bbox

                # if there is no violation continue with next slot
                if not violation_fi:
                    continue
                            
                # CAUTION: if it's a no-belt violation, then we don't send the violation immediately \
                #          after it has been detected because we want to evaluate
                #          no belt / belt detections (by add / subbtract) for as long as possible
                #          -> if slot is too old then we send the violation 
                if slt.mobile_detected or fi > violation_fi + 30:
                    slt.violation_sent = True  

                    print (f'Going to send violation!!! fi={fi} vfi={violation_fi}')

                    self.violations_counter += 1
                    slt.violation_id = self.violations_counter                              
                    slt.violation_fi = violation_fi
                    #slt.violation_img = violation_img
                    slt.violation_timestamp = violation_timestamp               
                    slt.violation_bbox = violation_bbox
                    
                    ret.append(slt)
        except Exception:
            logging.exception("[MSViolationDetector] Error during calculating ret values in detect()") 

        return ret
