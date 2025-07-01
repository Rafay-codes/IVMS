import cv2
import io
import logging
import numpy as np

from pathlib import Path
from shapely import geometry

from core.helpers import denormalize_coords

# Used ONLY in mobile no-entry apps for the time being
class Zones:
    input_width: int
    input_height: int
    vehicleArea: np.ndarray
    entryLine: np.ndarray
    laneLine: np.ndarray
    checkLine: np.ndarray
    bottomEdge: np.ndarray
    leftEdge: np.ndarray

    def __init__(self 
                 , cfg
                 , opt                               
                 , input_width: int
                 , input_height: int
                 , app_type = 'mobile'):

        self.input_width = input_width
        self.input_height = input_height
        self.app_type = app_type

        # --- get the zones file path name
        # if a name is given in command line argument then use this one        
        zones_file_name = opt.zones if opt.zones is not None else None
        # otherwise use the one from settings file
        if zones_file_name is None:
            if app_type == 'noentry':
                zones_file_name = cfg.DETECTIONS.NOENTRY.ZONES_FILE 
            elif app_type == 'noparking':
                zones_file_name = cfg.DETECTIONS.NOPARKING.ZONES_FILE 
            elif app_type == 'mobile': 
                zones_file_name = cfg.DETECTIONS.MOBI.ZONES_FILE
            elif app_type == 'lpr': 
                zones_file_name = cfg.DETECTIONS.LPR.ZONES_FILE
        
        # --- load the zone coordinates from the zones file
        if app_type == 'noentry':
            self.vehicleArea, self.middleLine, self.trajectoryLine = self._load_zones_noentry(zones_file_name)    
            self.vehicle_area = geometry.Polygon(self.vehicleArea)            
            self.trajectory_line = geometry.LineString(self.trajectoryLine)             
            self.lpr_line = geometry.LineString(self.middleLine) 

        elif app_type == 'noparking':
            self.vehicleArea, self.noParkingArea, self.entryLine, self.exitLine, self.lprLine = self._load_zones_noparking(zones_file_name)    
            self.vehicle_area = geometry.Polygon(self.vehicleArea)
            self.noparking_area = geometry.Polygon(self.noParkingArea)            
            self.entry_line = geometry.LineString(self.entryLine) 
            self.exit_line = geometry.LineString(self.exitLine) 
            self.lpr_line = geometry.LineString(self.lprLine) 

        elif app_type == 'mobile':
            self.vehicleArea, self.entryLine, self.laneLine, self.checkLine = self._load_zones_mobile(zones_file_name)

        elif app_type == 'lpr':
            self.vehicleArea = self._load_zones_lpr(zones_file_name)
            self.vehicle_area = geometry.Polygon(self.vehicleArea)

        # we take the coords of the bottom edge of the video frame
        self.bottomEdge =  np.array([[0, input_height - 20], [input_width, input_height - 20]]) 
        self.bottom_edge = geometry.LineString(self.bottomEdge)

        # we take the coords of the left edge of the video frame 
        # (only used when corresponding flag is set in yaml config file)
        use_left_edge = cfg.DETECTIONS.NOENTRY.USE_LEFT_EDGE if app_type == 'noentry' else (cfg.DETECTIONS.MOBI.USE_LEFT_EDGE if app_type == 'mobile' else False)
        if use_left_edge:
            self.leftEdge =  np.array([[10, 100], [10, input_height - 100]]) 
            self.left_edge = geometry.LineString(self.leftEdge)
        else:
            self.leftEdge = None
            self.left_edge = None


    # ---- Draw vehicle zone, lpr line on frame
    def draw_zones(self, frame):
            
        color = (0, 255, 0)
        vertices = self.vehicleArea.reshape(-1,1,2)
        frame = cv2.polylines(frame, [vertices], True, color, 2)

        if self.app_type == 'mobile':
            color = (0, 240, 240) # BGR
            vertices = self.entryLine.reshape(-1,1,2)
            frame = cv2.polylines(frame, [vertices], False, color, 2)

            if self.laneLine is not None:
                color = (240, 0, 0) # BGR
                vertices = self.laneLine.reshape(-1,1,2)
                frame = cv2.polylines(frame, [vertices], False, color, 5)

            if self.checkLine is not None:
                color = (240, 0, 0) # BGR
                vertices = self.checkLine.reshape(-1,1,2)
                frame = cv2.polylines(frame, [vertices], False, color, 5)
        
        elif self.app_type == 'noentry':
            color = (0, 240, 240) # BGR
            vertices = self.trajectoryLine.reshape(-1,1,2)
            frame = cv2.polylines(frame, [vertices], False, color, 2)

            color = (0, 240, 240) # BGR
            vertices = self.middleLine.reshape(-1,1,2)
            frame = cv2.polylines(frame, [vertices], False, color, 2)

        elif self.app_type == 'noparking':
            color = (0, 255, 0)
            vertices = self.noParkingArea.reshape(-1,1,2)
            frame = cv2.polylines(frame, [vertices], True, (0, 0, 250), 2)

            color = (240, 40, 40) # BGR
            vertices = self.entryLine.reshape(-1,1,2)
            frame = cv2.polylines(frame, [vertices], False, color, 2)

            color = (40, 40, 240) # BGR
            vertices = self.exitLine.reshape(-1,1,2)
            frame = cv2.polylines(frame, [vertices], False, color, 2)

            color = (40, 240, 40) # BGR
            vertices = self.lprLine.reshape(-1,1,2)
            frame = cv2.polylines(frame, [vertices], False, color, 2)

        # color = (240, 0, 0) # BGR
        # vertices = self.bottomEdge.reshape(-1,1,2)
        # frame = cv2.polylines(frame, [vertices], False, color, 5)

        if self.leftEdge is not None:
            color = (240, 0, 0) # BGR
            vertices = self.leftEdge.reshape(-1,1,2)
            frame = cv2.polylines(frame, [vertices], False, color, 5)

        return frame

    # ---- load zones file and return the coordinates of:
    #  1) vehicle tracking zone, 
    #  2) middle line -> lpr line (for noentry app type)
    #  3) trajectory line
    def _load_zones_noentry(self, zones_file):

        # use relative path for zones file
        zonesFilename = f'{Path(__file__).parent}/../{zones_file}'

        print(f'[Zones:load_zones] Reading zones file from path: {zonesFilename}')

        if Path(zonesFilename).is_file():
            # Read the array from disk
            zoneCoords = np.loadtxt(zonesFilename, dtype=np.float16)
            
            vehicleArea = denormalize_coords(zoneCoords[0:-4, 0:2], self.input_width, self.input_height)         
            lprLine = denormalize_coords(zoneCoords[-4:-2, 0:2], self.input_width, self.input_height)       # two rows before last two rows are lpr line
            trajectoryLine = denormalize_coords(zoneCoords[-2:, 0:2], self.input_width, self.input_height)    # last two rows are trajectory line

            return vehicleArea, lprLine, trajectoryLine
        else:
            print (f"[Zones:load_zones] Couldn't find zones configuration file: {zonesFilename}")
            logging.critical(f"Couldn't find zones configuration file: {zonesFilename}")        
                        
            return None, None, None
            
   # ---- load zones file and return the coordinates of:
    #  1) vehicle tracking zone, 
    #  2) entry line     
    def _load_zones_noparking(self, zones_file):

        # use relative path for zones file
        zonesFilename = f'{Path(__file__).parent}/../{zones_file}'

        print(f'[Zones:load_zones] Reading zones file from path: {zonesFilename}')

        if Path(zonesFilename).is_file():
            # Read the array from disk
            zoneCoords = np.loadtxt(zonesFilename, dtype=np.float16)
            
            # we use this are for tracking
            vehicleArea = denormalize_coords(zoneCoords[0:-10, 0:2], self.input_width, self.input_height)  
            # we start counting parking time as soon as vehicle touches this zone
            noParkingArea = denormalize_coords(zoneCoords[-10:-6, 0:2], self.input_width, self.input_height)  
            # these rows are entry line          
            entryLine = denormalize_coords(zoneCoords[-6:-4, 0:2], self.input_width, self.input_height) 
            # two rows before last two rows are entry line  
            exitLine = denormalize_coords(zoneCoords[-4:-2, 0:2], self.input_width, self.input_height)    
            # last two rows are LPR line   
            lprLine = denormalize_coords(zoneCoords[-2:, 0:2], self.input_width, self.input_height) 

            return vehicleArea, noParkingArea, entryLine, exitLine, lprLine
        else:
            print (f"[Zones:load_zones] Couldn't find zones configuration file: {zonesFilename}")
            logging.critical(f"Couldn't find zones configuration file: {zonesFilename}")        
                        
            return None, None, None, None, None
            
    # -- load zones file and return the coordinates of 1) vehicle tracking zone, 2) lpr line
    def _load_zones_mobile(self, zones_file_name):

        # use relative path for zones file
        zonesFilename = f'{Path(__file__).parent}/../{zones_file_name}'

        if Path(zonesFilename).is_file():

            vehicle_area_lines = ''
            entry_line = ''
            lane_line = ''
            check_line = ''

            with open(zonesFilename) as f:
                for line in f:
                    if line.startswith('# Vehicle'):
                        lines_type = 'vehicle_area'
                    elif line.startswith('# Detection'):
                        lines_type = 'entry_line'
                    elif line.startswith('# Lane'):
                        lines_type = 'lane_line'
                    elif line.startswith('# Check lane'):
                        lines_type = 'check_line'

                    elif lines_type == 'vehicle_area':
                        vehicle_area_lines += line
                    elif lines_type == 'entry_line':
                        entry_line += line
                    elif lines_type == 'lane_line':
                        lane_line += line
                    elif lines_type == 'check_line':
                        check_line += line

            coords = np.loadtxt(io.StringIO(vehicle_area_lines), dtype=np.float16)
            vehicleArea = denormalize_coords(coords[:, :], self.input_width, self.input_height)

            coords = np.loadtxt(io.StringIO(entry_line), dtype=np.float16)
            entryLine = denormalize_coords(coords[:, :], self.input_width, self.input_height)

            if lane_line != '':
                coords = np.loadtxt(io.StringIO(lane_line), dtype=np.float16)
                laneLine = denormalize_coords(coords[:, :], self.input_width, self.input_height)
            else:
                laneLine = None

            if check_line != '':
                coords = np.loadtxt(io.StringIO(check_line), dtype=np.float16)
                checkLine = denormalize_coords(coords[:, :], self.input_width, self.input_height)
            else:
                checkLine = None

            return vehicleArea, entryLine, laneLine, checkLine        

        else:
            print (f"[Zones:_load_zones] Couldn't find zones configuration file: {zonesFilename}")
            logging.critical(f"Couldn't find zones configuration file: {zonesFilename}")        
            return None, None, None, None

    def _load_zones_lpr(self, zones_file_name):

        # use relative path for zones file
        zonesFilename = f'{Path(__file__).parent}/../{zones_file_name}'

        if Path(zonesFilename).is_file():

            vehicle_area_lines = ''

            with open(zonesFilename) as f:
                for line in f:
                    if line.startswith('# Vehicle'):
                        lines_type = 'vehicle_area'

                    elif lines_type == 'vehicle_area':
                        vehicle_area_lines += line

            coords = np.loadtxt(io.StringIO(vehicle_area_lines), dtype=np.float16)
            vehicleArea = denormalize_coords(coords[:, :], self.input_width, self.input_height)

            return vehicleArea

        else:
            print (f"[Zones:_load_zones] Couldn't find zones configuration file: {zonesFilename}")
            logging.critical(f"Couldn't find zones configuration file: {zonesFilename}")        
            return None
