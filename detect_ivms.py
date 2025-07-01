import os
import subprocess
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst
from argparse import ArgumentParser

from utils.yaml_parser import YamlParser
from utils.configure_logging import configure_logging
from core.pipeline import Pipeline
from core.plate_recognition import PlateRecognition
from core.ms_violation_detector import MSViolationDetector
from core.violation_recorder import ViolationRecorder
#from core.lane_detector import LaneDetector

def run_pipeline(opt):

    # Path to app settings file
    PATH = os.path.dirname(os.path.abspath(__file__))
    CONFIGS_DIR = os.path.join(PATH, "config")    
    OUTPUT_DIR = "/home/nvidia/ivms/recordings"
        
    # Read YAML config file using YamlParser class 
    settings_path = os.path.join(CONFIGS_DIR, opt.settings)
    print(settings_path)
    cfg = YamlParser(config_file=settings_path)
    
    configure_logging(cfg.LOG_LEVEL)

    # # create module used for recording violations
    # viol_recorder = ViolationRecorder(cfg, len(cfg.VIDEO_SOURCES))

    # # create module used for detecting violations
    # ms_viol_detector = MSViolationDetector()

    # # create module used for plate detection
    # plate_recognition = PlateRecognition(CONFIGS_DIR, cfg.VIDEO_OUTPUT.LPR_FOLDER, len(cfg.VIDEO_SOURCES), int(cfg.VIDEO_OUTPUT.MUXER.WIDTH), int(cfg.VIDEO_OUTPUT.MUXER.HEIGHT))

    # create context and engine for lane detection using
    # Lane Detector class and provide it to pipeline
    # lane_detector = LaneDetector(cfg.LANE_ENGINE)

    # Create & run pipeline
    # pipeline = Pipeline(cfg, opt.output, opt.record, CONFIGS_DIR, OUTPUT_DIR, plate_recognition, ms_viol_detector, viol_recorder, lane_detector)
    # pipeline = Pipeline(cfg, opt.output, opt.record, CONFIGS_DIR, OUTPUT_DIR, plate_recognition, ms_viol_detector, viol_recorder)
    # pipeline = Pipeline(cfg, opt.output, opt.record, CONFIGS_DIR, OUTPUT_DIR, ms_viol_detector, viol_recorder, lane_detector)

    
    camera_config_command = ["v4l2-ctl","-c","<will-update-params>","-d", "<will-update-device-id>"]
    camera_idx_to_remove = []
    for idx, d in enumerate(cfg.VIDEO_SOURCES):
        if d.startswith("/dev/video"):
           camera_config_command[2] = cfg.CAMERA_CONTROL[idx]
           camera_config_command[4] = d[-1]
           print(camera_config_command)
           ret = subprocess.run(camera_config_command)
           if (ret.returncode) != 0:
              print(idx, "Camera configuration issue: ", ret)
              camera_idx_to_remove.append(idx)
              
    camera_nums_removed = 0
    for camera_id in camera_idx_to_remove:
        del(cfg.VIDEO_SOURCES[camera_id-camera_nums_removed])
        camera_nums_removed+=1
    
    print(cfg.VIDEO_SOURCES)
    

    pipeline = Pipeline(cfg, opt, CONFIGS_DIR, OUTPUT_DIR)
    pipeline.run()

    
if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('--settings', type=str, default='app_settings.yaml', 
                        help='application settings file name (default = app_settings.yaml)')
    
    parser.add_argument('--output', type=str, default='file', 
                        help='type of output sink bin (default = screen): fake, screen, file')
    
    parser.add_argument('--record', type=str, default='True', 
                        help='To record RAW streams (default = True): True, False')
    
    parser.add_argument('--lane', type=str, default='False',
                        help='To detect lanes pass True. (default = False): True, False')
    
    parser.add_argument('--anpr', type=str, default='CAR',
                        help='Which ANPR to use, OFF for disabling ANPR (default = OFF): \
                            1) For Carrida -> "CAR" 2) For StreamAI -> "SAI"  3) Disable -> "OFF"')
    
    parser.add_argument('--rtsp', type=str, default='True',
                        help='To create RTSP server pass True, (default = False): True, False')
    
    
    args = parser.parse_args()
    run_pipeline(args)
