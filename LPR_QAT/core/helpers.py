# Helper functions

import cv2
import numpy as np
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from datetime import datetime
from shapely import geometry
import random

# --- draw shapely Polygon object (obj_poly)
def draw_box(img, obj_poly, color = (128, 128, 128), line_thickness = 2, label = None, label_font_scale=None, text_color=(255,255,255), text_bg_filled=True, text_outside_box=False, label_font_thickness=1, bbox=True):
    tl = line_thickness or round(0.002 * (img.shape[0] + img.shape[1]) / 2) + 1  # line/font thickness

    minx, miny, maxx, maxy = obj_poly.bounds
    c1, c2 = (int(minx), int(maxy)), (int(maxx), int(miny))
    if bbox:
        cv2.rectangle(img, c1, c2, color, thickness=tl, lineType=cv2.LINE_AA)        
    
    if label:
        if text_outside_box:
            c1 = (int(minx), int(miny)) # to draw outside the box (above)
        tf = max(tl - 1, 1)  # font thickness
        t_size = cv2.getTextSize(label, 0, fontScale=tl / 3, thickness=tf)[0]
        c2 = c1[0] + t_size[0], c1[1] - t_size[1] - 3
        if text_bg_filled:
            cv2.rectangle(img, c1, c2, color, -1, cv2.LINE_AA) # filled
        sf = label_font_scale if label_font_scale else tl/3
        st = label_font_thickness if label_font_thickness else tf
        cv2.putText(img, label, (c1[0], c1[1] - 2), 0, sf, text_color, thickness=st, lineType=cv2.LINE_AA)

def remove_elements_by_indices_from_list(my_list, popup_indices):
        for index in sorted(popup_indices, reverse=True): # Note that you need to delete them in reverse order so that you don't throw off the subsequent indexes.
            del my_list[index]
            
        # for i, e in reversed(list(enumerate(a))):

def random_color():
    b = random.randint(0,255)
    g = random.randint(0,255)
    r = random.randint(0,255)
    return (b,g,r)

def crop_image(img, poly, hpad=0, vpad=0):
    minx, miny, maxx, maxy = poly.bounds
    return img[int(miny)-vpad:int(maxy)+vpad, int(minx)-hpad:int(maxx)+hpad] # shallow copy

# --- draw line from two shapely Points
def draw_line(img, p1, p2, color = (128, 128, 128), line_thickness = 2):
    cv2.line(img, (int(p1.x), int(p1.y)), (int(p2.x), int(p2.y)), color, thickness=line_thickness)

# --- draw line from line segment
def draw_line2(img, line: geometry.LineString, color = (128, 128, 128), line_thickness = 2):
    line_coords = line.coords    
    cv2.line(img, (int(line_coords[0][0]), int(line_coords[0][1])), (int(line_coords[1][0]), int(line_coords[1][1])), color, thickness=line_thickness)

# helper method: write some text on the image
# see https://stackoverflow.com/questions/16615662/how-to-write-text-on-a-image-in-windows-using-python-opencv2
def write_text(image, text, pos = (50,20), color = (255,0,0), scale=0.7):
    font                   = cv2.FONT_HERSHEY_SIMPLEX
    fontScale              = scale
    fontColor              = color
    lineType               = 2

    cv2.putText(image,text, pos, font, fontScale, fontColor, lineType)   

# --- denormalize coordinates using specified width (w), height (h)
def denormalize_coords(coords, w, h):
    v = np.array([w, h])    
    ret = coords * v[None,:]                
    return ret.astype(int)

# --- return minx of a shapely rectangle object
def poly_min_x(poly):
    pl_minx, pl_miny, pl_maxx, pl_maxy = poly.bounds
    return int(pl_minx)

# --- return miny of a shapely rectangle object
def poly_min_y(poly):
    pl_minx, pl_miny, pl_maxx, pl_maxy = poly.bounds
    return int(pl_miny)

def convert_plate_coords_to_global_image_coords(lp_coords_poly, glabal_coords_lp_poly):
    l_minx, l_miny, l_maxx, l_maxy = lp_coords_poly.bounds
    g_minx, g_miny, g_maxx, g_maxy = glabal_coords_lp_poly.bounds
    x1, y1 = (int(g_minx)+ int(l_minx)), (int(g_miny)+ int(l_miny))
    x2, y2 = (int(g_minx)+ int(l_maxx)), (int(g_miny)+ int(l_maxy))
    return geometry.Polygon([(x1, y1), (x2,y1), (x2,y2), (x1, y2),(x1, y1)])

# ---- Configure logging based on yaml settings file
def configure_logging(cfg, src = 'ped'):
    # get log level from settings file
    if cfg.LOG_LEVEL == 'DEBUG':
        debug_level = logging.DEBUG
    elif cfg.LOG_LEVEL == 'INFO':
        debug_level = logging.INFO
    elif cfg.LOG_LEVEL == 'WARN':
        debug_level = logging.WARN
    elif cfg.LOG_LEVEL == 'ERROR':
        debug_level = logging.ERROR

    # remove any existing handlers
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    # see https://stackoverflow.com/questions/9856683/using-pythons-os-path-how-do-i-go-up-one-directory
    log_base_dir = Path(__file__).parents[1] 
    
    if src == 'ped':
        log_fname = 'detect.log'
    if src == 'lpr':
        log_fname = 'detect.lpr.log'
    elif src == 'mobile':
        log_fname = 'detect_mobile.log'
    elif src == 'noparking':
        log_fname = 'detect_noparking.log'
    elif src == 'anpr':
        log_fname = 'anpr.log'
    elif src == 'signal':
        log_fname = 'stop_signal.log'
    elif src == 'noentry':        
        log_fname = 'detect_noentry.log'    
    elif src == 'wrongentry':        
        log_fname = 'detect_wrongentry.log'    
    elif src == 'ldms':        
        log_fname = 'detect_ldms.log'
    elif src == 'auto_delete_upload':
        log_fname = 'auto_delete_upload.log'
    else:
        log_fname = 'record_video.log'

    log_fullpath_name = f'{log_base_dir}/logs/{log_fname}'            

    logger = logging.getLogger()
    rotating_file_handler = TimedRotatingFileHandler(filename=log_fullpath_name, when='H', interval=6, backupCount=4)    
            
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    rotating_file_handler.setFormatter(formatter)

    logger.addHandler(rotating_file_handler)
    logger.setLevel(debug_level)

    # reduce requests log level
    logging.getLogger("requests").setLevel(logging.ERROR)
    logging.getLogger("urllib3").setLevel(logging.ERROR)

    # reduce pika log level
    # see https://github.com/pika/pika/issues/692
    logging.getLogger("pika").setLevel(logging.ERROR)    