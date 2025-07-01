import cv2
import os
import numpy as np
import logging
import threading
import time
from lxml import etree
from easydict import EasyDict as edict
from datetime import datetime

from core.frame_buffer import FrameBuffer
from utils.draw import write_text
from utils.draw import draw_box
from utils.create_directories import create_directories

import pika
import json

class ViolationRecorder(object):
    """Implements violation recordings"""    

    LABEL_COLOR = (0, 60, 60)                   # Background color of label printed on violation image
    TEXT_COLOR = (240,240,240)                  # Color of label text
    LABEL_FONT = cv2.FONT_HERSHEY_COMPLEX_SMALL # Font of text written on the label
    FONT_SCALE = 0.74

    def __init__(self, cfg, stream_count, api_interface):
        
        self.api_interface = api_interface
        self.fps = 30  # hardcoded! TODO: get it from DeepStream nvstreamux?
        self.stream_count = stream_count
        # As soon as the required number of frames have passed after the event is received
        # we write the accumulated frames to file, all of this is governed by fps and
        # length of the recording in the app_setings.yaml
        self.received_events = [] # events from rabbitmq are accumulated here

        self.codec = cv2.VideoWriter_fourcc(*cfg.VIDEO_OUTPUT.FORMAT)    
        self.ext = '.mp4' if 'MP4V' in cfg.VIDEO_OUTPUT.FORMAT else '.avi'
        # self.ext = '.mp4'
        self.output_folder = cfg.VIDEO_OUTPUT.VIOLATION_FOLDER 
        self.event_recordings_folder = cfg.VIDEO_OUTPUT.EVENT_RECORDING_FOLDER

        # recorded video will be in the same resolution with nvstreammux plugin        
        self.output_width = int(cfg.VIDEO_OUTPUT.MUXER.WIDTH)
        self.output_height = int(cfg.VIDEO_OUTPUT.MUXER.HEIGHT) 

        # calculate frame recording threshold: the buffer must contain at least this number of frames
        # before recording can start
        # we subtract 1sec because one frame (central) is going to be repeated fps times
        # so violation video consists of: 
        # --> TOTAL = FRAME_RECORDING_THRESH + fps + FRAME_RECORDING_THRESH number of frames
        self.FRAME_RECORDING_THRESH = int(self.fps * (cfg.VIDEO_OUTPUT.DURATION - 1) / 2) 
        
        # save all incoming frames to this buffer; we add 100 frames more because some times the 
        # lpr frame comes BEFORE that 1st frame of the video 
        self.frame_buffer = FrameBuffer(2 * self.FRAME_RECORDING_THRESH + 100, stream_count)       

        # --- image label parameters
        self.sitecode = cfg.LABEL.SITECODE
        self.radar_id = cfg.LABEL.RADAR_ID
        self.place = cfg.LABEL.PLACE
        self.device_id = cfg.LABEL.DEVICE_ID
        self.name = cfg.LABEL.NAME if cfg.LABEL.NAME else ''

        # label coords
        label_w = cfg.VIDEO_OUTPUT.MUXER.WIDTH # <-- We draw the label from one edge to the other. 
        self.label_points = np.array([[0, 0], [label_w, 0], [label_w, cfg.LABEL.HEIGHT], [0, cfg.LABEL.HEIGHT]], dtype=np.int32)

        # --- List of Lists with detections to write
        self.detections = list()
        for i in range(0, stream_count):
            self.detections.append( list() ) #different object reference each time
            
        self.init_rabbitmq()

    def init_rabbitmq(self):
        # get this from config file
        rabbitmq_host = '127.0.0.1'
        connection_params = pika.ConnectionParameters(host=rabbitmq_host)
        # Establish connection
        connection = pika.BlockingConnection(connection_params)
        self.channel = connection.channel()
        
        # Declare a queue
        self.channel.queue_declare(queue='event_video', durable=False)
        
    # update buffer with specified frame, frame number
    def update_buffer(self, img, stream_no, index):
        self.frame_buffer.append(img, stream_no, index)       
    
    # ---- mobile & seatbelt violation recording ----------
    def record_mobile(self, violations, stream_no, fi):
     
        try:
            # process all new violations received from the violation detector module
            for v in violations:              
                # --- create violation detection object
                detection = edict({
                    'id': v.violation_id,
                    'violation_type': None,
                    'violation_bbox': v.violation_bbox,
                    'violation_fi': v.violation_fi,
                    #'violation_img': v.violation_img,     
                    'lpr_img': v.lpr_img,               
                    'timestamp': v.violation_timestamp,
                    'frames_elapsed': fi - v.violation_fi - 1,
                    'sent': False
                })

                # we might have a double detecion 
                # TODO: handle both detections
                if v.mobile_detected:
                    detection.violation_type = 'mobile'
                    print (f'[!] New mobile phone violation, ID = {v.violation_id}, Time: {v.violation_timestamp}, Det. FI = {v.violation_fi}, Elapsed = {detection.frames_elapsed}')
                else:
                    detection.violation_type = 'seatbelt'
                    print (f'[!] New seatbelt violation, ID = {v.violation_id}, Time: {v.violation_timestamp}, Det. FI = {v.violation_fi}, Elapsed = {detection.frames_elapsed}')

                self.detections[stream_no].append(detection)

            # we increment the frames_elapsed property of all detections by 1
            # -> we initiate a new recording thread for all detections having reached the FRAME_RECORDING_THRESH
            for det in self.detections[stream_no]:

                det.frames_elapsed += 1

                if det.frames_elapsed >= self.FRAME_RECORDING_THRESH:
                    det.sent = True
                    frames_to_write = self.frame_buffer.get_frames(stream_no, det.violation_fi, fi, 2 * self.FRAME_RECORDING_THRESH)
                                       
                    workThread = threading.Thread(target=self.write_ms_detection, args=(frames_to_write, det), daemon=True)
                    workThread.start()                        
          
            # clear detections sent in the loop above
            self.detections[stream_no][:] = [det for det in self.detections[stream_no] if not det.sent]

        except Exception:
            logging.exception("[ViolationRecorder] record_mobile function failed") 


    # write images / video of a mobile phone usage detection to output folder, then send message to rabittMQ broker
    def write_ms_detection(self, frames, det):       

        try:
            # DEBUG ONLY !!!
            first = frames[0]
            last = frames[-1]
            print (f'Length = {2 * self.FRAME_RECORDING_THRESH}, first = {first.index}, last = {last.index}')


            case_index = det.id

            # datetime folder to store the detection files
            dest_folder = self.output_folder + '/' + det.timestamp[0:8]

            # create datetime folder if it doesn't exist
            if not os.path.exists(dest_folder):
                os.mkdir(dest_folder)

            # create incident subfolder
            dest_folder += '/' + det.timestamp
            if not os.path.exists(dest_folder):
                os.mkdir(dest_folder)

            # compute filename
            dest_filename = self.device_id + '-' + det.timestamp + f'{case_index:08}'  # see https://stackoverflow.com/questions/339007/how-to-pad-zeroes-to-a-string           

            # write lpr image
            lprframe_fname = ''
            if det.lpr_img is not None:
                lprframe_fname = dest_filename + '-2.png'
                cv2.imwrite(dest_folder + '/' + lprframe_fname, det.lpr_img)        

            # write video 
            print (f'[ViolationRecorder] Writing video .... No. of frames: {len(frames)}, Dimensions: {(self.output_width, self.output_height)}')

            video_fname = dest_filename + f'.{self.ext}'
            out = cv2.VideoWriter(dest_folder + '/' + video_fname, self.codec, self.fps, (self.output_width, self.output_height))                
            violation_img = None
            for frame in frames:
                frame_img = frame.img
                frame_img = cv2.resize(frame_img, (self.output_width, self.output_height), interpolation = cv2.INTER_LINEAR)  
                
                #DEBUG ONLY!!!
                # write FRAME INDEX on current frame                
                write_text(frame_img, f"FI: {frame.index}", (30, self.output_height - 50), (255,0,0))
                
                # --- write violation frame multiple times (1 sec)
                if frame.index == det.violation_fi:     

                    # DEBUG ONLY !!!
                    print (f'Found viol. index {frame.index}')

                    draw_box(frame_img, det.violation_bbox, label="", color=(50, 50, 220), line_thickness=3)

                    # we get a copy of the violation image originally saved in the detection slot
                    violation_img = frame_img.copy()
                    for i in range(int(self.fps)):                                        
                        out.write(frame_img)
                else:
                    out.write(frame_img)
            out.release()
                      
            # write overview image            
            print ('Writing overview frame ....')
            self.write_label(violation_img, det.timestamp, None, det.violation_type)
            overview_fname = dest_filename + '-1.png'
            cv2.imwrite(dest_folder + '/' + overview_fname, violation_img)
            
            #DEBUG ONLY
            print(f'Wrote overview frame {overview_fname}')
            
            # --- transcode file from XVID -> x264 using ffmpeg
            time.sleep(5) # Sleep for 5 seconds
            os.system(f'ffmpeg -i {dest_folder}/{video_fname} -c:v h264_nvmpi -c:a copy {dest_folder}/{dest_filename}.mp4')
            self._remove_file(f'{dest_folder}/{video_fname}')
            
            # get xml and write it to disk
            xml = self.create_xml(det.timestamp, case_index, video_fname, overview_fname, lprframe_fname, det.violation_type)
            xml.write(dest_folder + '/' + dest_filename + '.xml', pretty_print=True)

        except Exception:
            logging.exception("[ViolationRecorder] write_mobile_detection function failed") 

    # create violation xml file
    def create_xml(self, timestamp, case_index, video_fname, overview_fname, videoframe_fname, v_type):
        incident_name = str(self.device_id) + '-' + timestamp[0:8] + timestamp[9:15] + '-' + f'{case_index:03}'
        incident_time = timestamp[0:4] + '-' + timestamp[4:6] + '-' + timestamp[6:8] + ' ' + timestamp[9:11] + ':' + timestamp[11:13] + ':' + timestamp[13:19] 

        if v_type == 'ped':
            primary_type = "Pedestrian"
        elif v_type == 'mobile':
            primary_type = "MobilePhone"
        elif v_type == 'ldms':
            primary_type = "TransitProhibited"
        else:
            primary_type = "Seatbelt"

        root = etree.Element("Incident", Name=incident_name, PrimaryType=primary_type, Vendor="KTC", Version="1")
        
        capture = etree.SubElement(root, "Capture", IncidentDateTime=incident_time)
        vehicleclass = etree.SubElement(capture, "VehicleClass", Measured="Car")
        lane = etree.SubElement(capture, "Lane", Alias="RoadShoulder", Index="0")

        devices = etree.SubElement(root, "Devices")
        device = etree.SubElement(devices, "Device", Name=str(self.device_id)) 

        files = etree.SubElement(root, "Files")
        file = etree.SubElement(files, "File", Group="Overview", Name=overview_fname)
        file = etree.SubElement(files, "File", Group="VideoFrame", Name=videoframe_fname)
        file = etree.SubElement(files, "File", Group="Video", Name=video_fname)

        locations = etree.SubElement(root, "Locations")
        etree.SubElement(locations, "Location", Address=self.place, Code=str(self.sitecode), Direction="Departing" if v_type == 'ldms' else "Approaching", Name=self.name)

        measurements = etree.SubElement(root, "Measurements")
        if v_type == 'ldms':
            measurements = etree.SubElement(measurements, primary_type, Type="Restricted")      
        else:
            measurements = etree.SubElement(measurements, primary_type)

        # LPR details are to be updated by the script the match the plate no to the violation
        plate = etree.SubElement(root, "Plate", Category="Private", Country="", Region="", Symbol="", Text="")

        # Namespace
        NAMESPACE = "http://www.w3.org/2001/XMLSchema-instance"
        NS = "{%s}" % NAMESPACE
        root.set(NS + "noNamespaceSchemaLocation", "VitronicOpenFormatReader.V04.05.xsd")

        return etree.ElementTree(root)


    # --- label the violation image
    def write_label(self, img, timestamp, redlight_time, v_type):
        cv2.fillPoly(img, [self.label_points], self.LABEL_COLOR)
        
        # 1st column
        org = self.label_points[0] + np.array([10,15])
        cv2.putText(img,'Site Code', (org[0], org[1]), self.LABEL_FONT, self.FONT_SCALE, self.TEXT_COLOR, 1, lineType=cv2.LINE_AA)
        org += np.array([0,15])
        cv2.putText(img, str(self.sitecode), (org[0], org[1]), self.LABEL_FONT, self.FONT_SCALE, self.TEXT_COLOR, 1, lineType=cv2.LINE_AA)

        org += np.array([0,20])
        cv2.putText(img,'Radar ID', (org[0], org[1]), self.LABEL_FONT, self.FONT_SCALE, self.TEXT_COLOR, 1, lineType=cv2.LINE_AA)
        org += np.array([0,15])
        cv2.putText(img, self.radar_id, (org[0], org[1]), self.LABEL_FONT, self.FONT_SCALE, self.TEXT_COLOR, 1, lineType=cv2.LINE_AA)

        # 2nd column
        org = self.label_points[0] + np.array([150,15])
        cv2.putText(img,'Date', (org[0], org[1]), self.LABEL_FONT, self.FONT_SCALE, self.TEXT_COLOR, 1, lineType=cv2.LINE_AA)
        org += np.array([0,15])
        cv2.putText(img, f'{timestamp[:4]}-{timestamp[4:6]}-{timestamp[6:8]}', (org[0], org[1]), self.LABEL_FONT, self.FONT_SCALE, self.TEXT_COLOR, 1, lineType=cv2.LINE_AA)

        org += np.array([0,20])
        cv2.putText(img,'Speed', (org[0], org[1]), self.LABEL_FONT, self.FONT_SCALE, self.TEXT_COLOR, 1, lineType=cv2.LINE_AA)
        org += np.array([0,15])
        cv2.putText(img, 'N/A', (org[0], org[1]), self.LABEL_FONT, self.FONT_SCALE, self.TEXT_COLOR, 1, lineType=cv2.LINE_AA)

        # 3rd column
        org = self.label_points[0] + np.array([300,15])
        cv2.putText(img,'Time', (org[0], org[1]), self.LABEL_FONT, self.FONT_SCALE, self.TEXT_COLOR, 1, lineType=cv2.LINE_AA)
        org += np.array([0,15])
        cv2.putText(img, f'{timestamp[9:11]}:{timestamp[11:13]}:{timestamp[13:15]}', (org[0], org[1]), self.LABEL_FONT, self.FONT_SCALE, self.TEXT_COLOR, 1, lineType=cv2.LINE_AA)

        org += np.array([0,20])
        cv2.putText(img,'Place', (org[0], org[1]), self.LABEL_FONT, self.FONT_SCALE, self.TEXT_COLOR, 1, lineType=cv2.LINE_AA)
        org += np.array([0,15])
        cv2.putText(img, self.place, (org[0], org[1]), self.LABEL_FONT, self.FONT_SCALE, self.TEXT_COLOR, 1, lineType=cv2.LINE_AA)

        # 4th column
        if v_type == 'ped':
            violation_type = 'Pedestrian'
            direction = 'Arrival'
        elif v_type == 'mobile':
            violation_type = 'MobilePhone'
            direction = 'Arrival'
        elif v_type == 'ldms':
            violation_type = 'TransitProhibited'            
            direction = 'Departing'
        else:
            violation_type = 'SeatBelt'
            direction = 'Arrival'

        org = self.label_points[0] + np.array([450,15])
        cv2.putText(img,'ViolationType', (org[0], org[1]), self.LABEL_FONT, self.FONT_SCALE, self.TEXT_COLOR, 1, lineType=cv2.LINE_AA)
        org += np.array([0,15])
        cv2.putText(img, violation_type, (org[0], org[1]), self.LABEL_FONT, self.FONT_SCALE, self.TEXT_COLOR, 1, lineType=cv2.LINE_AA)

        # redlight time
        org += np.array([0,20])
        cv2.putText(img,'Redlight t.', (org[0], org[1]), self.LABEL_FONT, self.FONT_SCALE, self.TEXT_COLOR, 1, lineType=cv2.LINE_AA)
        org += np.array([0,15])
        if redlight_time:
            # CAUTION: We add the trigger alarm time (in seconds) to the redlight time!
            cv2.putText(img, f'{redlight_time.seconds + self.trigger_alarm_t}s {int(redlight_time.microseconds / 1000)}ms', (org[0], org[1]), self.LABEL_FONT, self.FONT_SCALE, self.TEXT_COLOR, 1, lineType=cv2.LINE_AA)

        # 5th column
        org = self.label_points[0] + np.array([600,15])
        cv2.putText(img,'Plate No.', (org[0], org[1]), self.LABEL_FONT, self.FONT_SCALE, self.TEXT_COLOR, 1, lineType=cv2.LINE_AA)
        org += np.array([0,15])
        cv2.putText(img, '', (org[0], org[1]), self.LABEL_FONT, self.FONT_SCALE, self.TEXT_COLOR, 1, lineType=cv2.LINE_AA)

        org += np.array([0,20])
        cv2.putText(img,'Dir', (org[0], org[1]), self.LABEL_FONT, self.FONT_SCALE, self.TEXT_COLOR, 1, lineType=cv2.LINE_AA)
        org += np.array([0,15])
        cv2.putText(img, direction, (org[0], org[1]), self.LABEL_FONT, self.FONT_SCALE, self.TEXT_COLOR, 1, lineType=cv2.LINE_AA)
    
    # --- helper method: removes file
    def _remove_file(self, path):
        # removing the file
        if not os.remove(path):
            # success message
            print(f"{path} is removed successfully")
            logging.info(f"{path} is removed successfully")
        else:
            # failure message
            print(f"Unable to delete the {path}")
            logging.info(f"Unable to delete the {path}")
            
    ## Functions for handling event recordings ##
    ## TODO Major overhaul where events and violations and treated as one ##
    # Currently events have a very different and leaner structure compared to violation
    # The reason being violations are much more complex, they have ALPR, violation detection,
    # and other data built-in. Also violations only record 1 stream, where they occure,
    # but for event we record all the streams.

    # This is called inside Queue Reader Thread
    def create_recording_event(self, payload):
        event = {
            "event_id": payload['event_id'],
            'event_violation_type': payload['event_violation_type'],
            "elapsed_frames": 0,
            "fi_set": False,
            "frame_index": 0,
            "recorded": False,
            "stream_id": int(payload['stream_id'])-1
        }
        print(event)
        self.received_events.append(event)
        video_file_path = f"event_recordings/{datetime.now().strftime('%Y%m%d.%H%M%S.%f')[:-3][0:8]}/{payload['event_id']}/{int(payload['stream_id'])-1}.avi"
        message = {'event_id': int(payload['event_id']), "event_videos_path": video_file_path, "gps_coordinates": "None"}
        
        try:
            self.channel.basic_publish(exchange='', routing_key='event_video', body=json.dumps(message))
        except:
            self.init_rabbitmq()
            # retry
            self.channel.basic_publish(exchange='', routing_key='event_video', body=json.dumps(message))
    
    # Called at every iteration inside tiler probe, 
    def update_recording_events(self, frame_index):
        for event in self.received_events:
            # Set frame index when event is received
            if not event['fi_set']:
                event['fi_set'] = True
                event['frame_index'] = frame_index
                
            event['elapsed_frames'] += 1
            if event['elapsed_frames'] > self.FRAME_RECORDING_THRESH:
                timestamp = datetime.now().strftime("%Y%m%d.%H%M%S.%f")[:-3]
                dest_folder = os.path.join(self.event_recordings_folder, timestamp[0:8], str(event['event_id']))
                create_directories(dest_folder)
                # These will be raw recordings
                print("Record it")
                for stream_no in range(self.stream_count):
                    frames_to_write = self.frame_buffer.get_frames(stream_no, event['frame_index'], 
                                                                   frame_index, 2 * self.FRAME_RECORDING_THRESH)
                    
                    workThread = threading.Thread(target=self.write_event_recordings, args=(frames_to_write, stream_no, dest_folder), daemon=True)
                    workThread.start()
                event['recorded'] = True        
                #self.api_interface.update_event(event['event_id'], dest_folder, event['event_violation_type'])

        self.received_events = [event for event in self.received_events if not event['recorded']]

        # for det in self.detections[stream_no]:

        # det.frames_elapsed += 1

        # if det.frames_elapsed >= self.FRAME_RECORDING_THRESH:
        #     det.sent = True
        #     frames_to_write = self.frame_buffer.get_frames(stream_no, det.violation_fi, fi, 2 * self.FRAME_RECORDING_THRESH)
                                
        #     workThread = threading.Thread(target=self.write_ms_detection, args=(frames_to_write, det), daemon=True)
        #     workThread.start()                        
    
        # # clear detections sent in the loop above
        # self.detections[stream_no][:] = [det for det in self.detections[stream_no] if not det.sent]
        
    def write_event_recordings(self, frames, stream_no, dest_folder):
        # TODO Write file path to API
        # timestamp = datetime.now().strftime("%Y%m%d.%H%M%S.%f")[:-3]
        # dest_folder = os.path.join(self.event_recordings_folder, timestamp[0:8], str(event['event_id']))
        # create_directories(dest_folder)
        video_fname = str(stream_no) + self.ext 
        print(os.path.join(dest_folder, video_fname))
        out = cv2.VideoWriter(os.path.join(dest_folder, video_fname), self.codec, self.fps,
                               (self.output_width, self.output_height))
        for frame in frames:
            frame_img = frame.img
            out.write(frame_img)
        out.release()


