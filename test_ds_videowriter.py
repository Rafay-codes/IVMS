import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GObject, GLib


import os
import numpy as np
import cv2
import time
import sys

class DeepStreamVideoWriter(object):
    def __init__(self):

        self.output_video_path = '/srv/ivms_v2/detect/test0.mp4'

        os.environ["GST_DEBUG"] = "2"  # view warnings, errors coming from GStreamer

        # Standard GStreamer initialization
        GObject.threads_init()
        Gst.init(None)

    def write_video(self):
        # --- Create Pipeline element that will form a connection of other elements
        print("Creating Pipeline \n ")
        pipeline = Gst.Pipeline()
     
        # --- Source element for pushing np array into pipeline
        print("[DeepStreamVideoWriter] Creating App Source ... ")
        appsource = Gst.ElementFactory.make("appsrc", "numpy-source")
     
        caps_in = Gst.Caps.from_string("video/x-raw,format=RGBA,width=640,height=480,framerate=30/1")
        appsource.set_property('caps', caps_in)

        # instructs appsrc that we will be dealing with timed buffer
        appsource.set_property("format", Gst.Format.TIME)
        
        nvvideoconvert = Gst.ElementFactory.make("nvvideoconvert","nv-videoconv")

        caps_filter = Gst.ElementFactory.make("capsfilter","capsfilter1")
        caps = Gst.Caps.from_string("video/x-raw(memory:NVMM),format=NV12,width=640,height=480,framerate=30/1")        
        caps_filter.set_property('caps',caps)
             
        # Make the encoder           
        encoder = Gst.ElementFactory.make("nvv4l2h264enc", "encoder")    
        encoder.set_property('bitrate', 4000000)
        encoder.set_property('preset-level', 1)
        encoder.set_property('insert-sps-pps', 1)        

        parser = Gst.ElementFactory.make("h264parse", "parser")
        qtmux = Gst.ElementFactory.make("qtmux", "muxer")

        filesink = Gst.ElementFactory.make("filesink", "filesink")
        filesink.set_property("location", self.output_video_path)
        filesink.set_property("sync", 0)
        filesink.set_property("async", 0)
        
        # --- Add elements to Pipeline
        print("[DeepStreamVideoWriter] Adding elements to Pipeline ...")
        pipeline.add(appsource)
        pipeline.add(nvvideoconvert)
        pipeline.add(caps_filter)
        pipeline.add(encoder)
        pipeline.add(parser)
        pipeline.add(qtmux)
        pipeline.add(filesink)

        # --- Link elements 
        print("[DeepStreamVideoWriter] Linking elements in the Pipeline ...")
        appsource.link(nvvideoconvert)
        nvvideoconvert.link(caps_filter)
        caps_filter.link(encoder)       
        encoder.link(parser)
        parser.link(qtmux)
        qtmux.link(filesink)

        # --- Create an event loop and feed gstreamer bus mesages to it
        loop = GLib.MainLoop()  # GObject.MainLoop()
        bus = pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect ("message", self._bus_call, loop)

        # --- Start play back and listen to events
        print("[DeepStreamVideoWriter] Starting pipeline ...")
        pipeline.set_state(Gst.State.PLAYING)

        pts = 0  # buffers presentation timestamp
        duration = 10**9 / (30.0 / 1.0)  # frame duration
        
        print ('duration = ', duration)
        
        # --- Push buffer and check
        for _ in range(100):
            arr = np.random.randint(low=0,high=255,size=(480,640,3),dtype=np.uint8)
            arr = cv2.cvtColor(arr, cv2.COLOR_BGR2RGBA)
            
             # convert np.ndarray to Gst.Buffer
            gst_buffer = self._ndarray_to_gst_buffer(arr) # utils.ndarray_to_gst_buffer(arr)
            
              # set pts and duration to be able to record video, calculate fps
            pts += duration  # Increase pts by duration
            gst_buffer.pts = pts
            gst_buffer.duration = duration

            # emit <push-buffer> event with Gst.Buffer
            appsource.emit("push-buffer", gst_buffer)
            
            #appsource.emit("push-buffer", self._ndarray_to_gst_buffer(arr))
            #time.sleep(0.3)
            
        appsource.emit("end-of-stream")

        try:
            loop.run()
        except:
            pass

        print("Send EoS")
        Gst.Element.send_event(pipeline, Gst.Event.new_eos())
        # wait until EOS or error
        bus = pipeline.get_bus()

        # --- Cleanup
        pipeline.set_state(Gst.State.NULL)


    def _ndarray_to_gst_buffer(self, array: np.ndarray) -> Gst.Buffer:
        """Converts numpy array to Gst.Buffer"""
        return Gst.Buffer.new_wrapped(array.tobytes())       

    @staticmethod
    def _bus_call(_, message, loop):
        t = message.type
        if t == Gst.MessageType.EOS:
            sys.stdout.write("End-of-stream\n")            
            loop.quit()
        elif t == Gst.MessageType.WARNING:
            err, debug = message.parse_warning()
            sys.stderr.write("Warning: %s: %s\n" % (err, debug))            
        elif t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            sys.stderr.write("Error: %s: %s\n" % (err, debug))            
            loop.quit()
        return True

    @staticmethod
    def _link_sequential(elements: list):
        for i in range(0, len(elements) - 1):
            elements[i].link(elements[i + 1]) 

if __name__ == '__main__':
        
    video_writer = DeepStreamVideoWriter()
    video_writer.write_video()