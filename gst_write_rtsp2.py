import gi
import time
import os
import argparse
import logging

from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from datetime import datetime, timedelta

gi.require_version('Gst', '1.0')
from gi.repository import Gst, GObject, GLib

class RTSPVideoWriter(object):
    def __init__(self, opt):

        self.configure_logging()              

        pipeline = None
        bus = None
        msg = None

        # get shutdown timestamp
        shutdown_time = datetime.strptime(f'{datetime.now().strftime("%Y%m%d")} 23:20', "%Y%m%d %H:%M") 

        # DEBUG 
        print(f"Hardcoded shutdown time = {shutdown_time}")
        
        try:

            # initialize GStreamer
            Gst.init(None)

            # we loop once for each file part
            for i in range(1, int(opt.parts) + 1):
                print("loop =",i," ")
                
                # get current time
                now = datetime.now()

                # check if current time + duration is past shutdown time
                finish_time = now + timedelta(minutes=int(opt.duration))

                # if finish time is past shutdown time then decrease the duration and raise flag to exit for loop
                isLastPart = False
                duration = int(opt.duration)
                if finish_time >= shutdown_time:
                    duration = int((shutdown_time - now).total_seconds() / 60.0)
                    isLastPart = True

                    print(f"Recording last part about to start, duration = {duration}")

                # calculate full path name of current file            
                full_path = f'{self.get_base_fname(opt)}_part{i}_{now.strftime("%Y%m%d_%H%M")}'

                # calculate pipeline string
                # h264 -> pipeline_str = f"rtspsrc location=rtsp://{opt.ip}/Streaming/channels/1/ user-id={opt.user} user-pw={opt.password} ! application/x-rtp, media=video, encoding-name=H264 ! queue ! rtph264depay ! h264parse ! nvv4l2decoder ! nvvidconv ! video/x-raw(memory:NVMM),width=960,height=540 ! nvv4l2h264enc ! h264parse ! matroskamux "
                
                # following uri is NOT suitable for Hikvision
                #pipeline_str = f"rtspsrc location=rtsp://{opt.ip}/stream0/ user-id={opt.user} user-pw={opt.password} " 
                
                pipeline_str = f"rtspsrc location=rtsp://{opt.ip}/0 user-id={opt.user} user-pw={opt.password} " 
                pipeline_str += f"! application/x-rtp, media=video, encoding-name=H264 ! queue ! rtph264depay ! h264parse ! nvv4l2decoder ! nvvidconv ! video/x-raw(memory:NVMM),width=1920,height=1080 ! nvv4l2h265enc bitrate=2500000 ! h265parse ! matroskamux "
                pipeline_str += f"! filesink location={full_path}.mkv"

                # DEBUG ONLY
                #print ('pipeline str =', pipeline_str)

                # build the pipeline
                pipeline = Gst.parse_launch(pipeline_str)                            

                # start playing
                print("Switch to PLAYING state")
                pipeline.set_state(Gst.State.PLAYING)

                time.sleep(60 * duration)
                print("Send EoS")
                Gst.Element.send_event(pipeline, Gst.Event.new_eos())
                # wait until EOS or error
                bus = pipeline.get_bus()
                msg = bus.timed_pop_filtered(
                    Gst.CLOCK_TIME_NONE, Gst.MessageType.EOS)

                # print message
                print(f"Message: {msg}")

                # free resources
                print("Switch to NULL state")
                pipeline.set_state(Gst.State.NULL)
                #time.sleep(2)

                # stop for loop if last part flag is raised (due to exceeding shutdown time)
                if isLastPart:
                    print("Last part flag has been raised: exiting recording loop")
                    break
        
        except:
            logging.exception("[RTSPVideoWriter] record function failed") 


    # ----- methods ---------

    # get the full path name of the recorded video file up to the time part 
    def get_base_fname(self, opt):     
        # calculate and create datetime folder if it doesn't exist
        dest_folder = f'{opt.folder}/{datetime.now().strftime("%Y%m%d")}'
        if not os.path.exists(dest_folder):
            os.mkdir(dest_folder)

        return f'{dest_folder}/{opt.filename}'

    # configure logging for the script; we don't use the helpers method in this case but include
    # the same code as a class method here instead
    def configure_logging(self):

        # remove any existing handlers
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)

        # see https://stackoverflow.com/questions/9856683/using-pythons-os-path-how-do-i-go-up-one-directory
        log_base_dir = '/srv/ivms_v2/detect'     
        log_fname = 'write_rtsp2.log'
        log_fullpath_name = f'{log_base_dir}/logs/{log_fname}'            

        logger = logging.getLogger()
        rotating_file_handler = TimedRotatingFileHandler(filename=log_fullpath_name, when='H', interval=6, backupCount=4)    
            
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        rotating_file_handler.setFormatter(formatter)

        logger.addHandler(rotating_file_handler)
        logger.setLevel(logging.DEBUG)

        # reduce pika log level
        # see https://github.com/pika/pika/issues/692
        logging.getLogger("pika").setLevel(logging.ERROR)    

    
if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument('--ip', type=str, default='192.168.100.103:8554', help='camera ip address')    
    parser.add_argument('--user', type=str, default='admin', help='camera username')    
    parser.add_argument('--password', type=str, default='Support01', help='camera password')    
    parser.add_argument('--width', type=str, default='1280', help='Width of output video')      
    parser.add_argument('--height', type=str, default='960', help='Height of output video') 
    parser.add_argument('--parts', type=str, default='12', help='Number of video files produced') 
    parser.add_argument('--duration', type=str, default='60', help='Duration in mins of each video file') 
    parser.add_argument('--folder', type=str, default='/srv/ivms_v2/recordings/2', help='output folder')      
    parser.add_argument('--filename', type=str, default='video', help='output filename, date/time will be appended')      

    opt = parser.parse_args()

    video_stream_widget = RTSPVideoWriter(opt)
