# Write video using DeepStream pipeline
# see https://forums.developer.nvidia.com/t/appsrc-with-numpy-input-in-python/120611/8

# GStreamer libs
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GObject

import os
import logging
import cv2
import time
import sys
import numpy as np

from core.bus_call import bus_call
#from app.utils.bus_call import bus_call

class DeepStreamVideoWriter(object):
    def __init__(self):

        self.output_video_path = '/srv/ivms_v2/detect/test.mp4'

        os.environ["GST_DEBUG"] = "2"  # view warnings, errors coming from GStreamer

        # Standard GStreamer initialization
        GObject.threads_init()
        Gst.init(None)

    def write_video(self):
        # --- Create Pipeline element that will form a connection of other elements
        print("Creating Pipeline \n ")
        pipeline = Gst.Pipeline()

        if not pipeline:
            print("[DeepStreamVideoWriter] Unable to create Pipeline")
            logging.error("[DeepStreamVideoWriter] Unable to create Pipeline")
            return

        # --- Source element for pushing np array into pipeline
        print("[DeepStreamVideoWriter] Creating App Source ... ")
        appsource = Gst.ElementFactory.make("appsrc", "numpy-source")
        if not appsource:
            print("[DeepStreamVideoWriter] Unable to create Source")
            logging.error("[DeepStreamVideoWriter] Unable to create Source")
            return

        caps_in = Gst.Caps.from_string("video/x-raw,format=RGBA,width=640,height=480,framerate=30/1")
        appsource.set_property('caps', caps_in)

        nvvideoconvert = Gst.ElementFactory.make("nvvideoconvert","nv-videoconv")
        if not nvvideoconvert:
            sys.stderr.write(" error nvvid1")

        caps_filter = Gst.ElementFactory.make("capsfilter","capsfilter1")
        if not caps_filter:
            sys.stderr.write(" error capsf1")
        caps = Gst.Caps.from_string("video/x-raw(memory:NVMM),format=NV12,width=640,height=480,framerate=30/1")        
        caps_filter.set_property('caps',caps)
        
        # ---

        # streammux = Gst.ElementFactory.make("nvstreammux", "stream-muxer")
        # streammux.set_property('width', 640)
        # streammux.set_property('height', 480)
        # streammux.set_property('batch-size', 1)
        # streammux.set_property('batched-push-timeout', 4000000)
        
        # ---

        # Make the encoder
        codec = "H264"
        bitrate = 4000000
        if codec == "H264":
            encoder = Gst.ElementFactory.make("nvv4l2h264enc", "encoder")
            print("Creating H264 Encoder")
        elif codec == "H265":
            encoder = Gst.ElementFactory.make("nvv4l2h265enc", "encoder")
            print("Creating H265 Encoder")
        if not encoder:
            sys.stderr.write(" Unable to create encoder")
        encoder.set_property('bitrate', bitrate)
        if True: #  is_aarch64():
            encoder.set_property('preset-level', 1)
            encoder.set_property('insert-sps-pps', 1)
            #encoder.set_property('bufapi-version', 1)

        parser = Gst.ElementFactory.make("h264parse", "parser")
        qtmux = Gst.ElementFactory.make("qtmux", "muxer")

        filesink = Gst.ElementFactory.make("filesink", "filesink")
        filesink.set_property("location", self.output_video_path)
        filesink.set_property("sync", 0)
        filesink.set_property("async", 0)

        # --- Output to screen
        egltransform = Gst.ElementFactory.make("nvegltransform", "nvegl-transform")
        sink = Gst.ElementFactory.make("nveglglessink", "nvvideo-renderer")
        if not sink:
            sys.stderr.write(" Unable to create egl sink \n")
        
        # --- Add elements to Pipeline
        print("[DeepStreamVideoWriter] Adding elements to Pipeline ...")
        pipeline.add(appsource)
        pipeline.add(nvvideoconvert)
        #pipeline.add(streammux)      
        pipeline.add(caps_filter)

        pipeline.add(encoder)
        pipeline.add(parser)
        pipeline.add(qtmux)
        pipeline.add(filesink)
        #pipeline.add(egltransform)
        #pipeline.add(sink)

        # --- Link elements 
        print("[DeepStreamVideoWriter] Linking elements in the Pipeline ...")

        appsource.link(nvvideoconvert)
        nvvideoconvert.link(caps_filter)
        caps_filter.link(encoder)
        #caps_filter.link(egltransform)
        #egltransform.link(sink)

       
        encoder.link(parser)
        parser.link(qtmux)
        qtmux.link(filesink)

        # --- Create an event loop and feed gstreamer bus mesages to it
        loop = GObject.MainLoop()
        bus = pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect ("message", bus_call, loop)

        # --- Start play back and listen to events
        print("[DeepStreamVideoWriter] Starting pipeline ...")
        pipeline.set_state(Gst.State.PLAYING)

        # --- Push buffer and check
        for _ in range(100):
            arr = np.random.randint(low=0,high=255,size=(480,640,3),dtype=np.uint8)
            arr = cv2.cvtColor(arr, cv2.COLOR_BGR2RGBA)
            appsource.emit("push-buffer", self._ndarray_to_gst_buffer(arr))
            time.sleep(0.3)
            appsource.emit("end-of-stream")

        try:
            loop.run()
        except:
            pass

        print("Send EoS")
        Gst.Element.send_event(pipeline, Gst.Event.new_eos())
        # wait until EOS or error
        bus = pipeline.get_bus()
        #msg = bus.timed_pop_filtered(Gst.CLOCK_TIME_NONE, Gst.MessageType.EOS)

        # print message
        #print(f"Message: {msg}")            
        #logging.info(f"[RTSPVideoWriter] Message: {msg}")
        # --- Cleanup
        pipeline.set_state(Gst.State.NULL)

    def _create_h264_sink_bin(self):
        h264_sink_bin = Gst.Bin.new("h264-sink-bin") 

        nvvidconv3 = self._create_element("nvvideoconvert", "convertor3", "Converter 3")

        capsfilter2 = self._create_element("capsfilter", "capsfilter2", "Caps filter 2")
        capsfilter2.set_property("caps", Gst.Caps.from_string("video/x-raw, format=RGBA")) 

        videoconvert = self._create_element("videoconvert", "convertor4", "Converter 4")

        capsfilter3 = self._create_element("capsfilter", "capsfilter3", "Caps filter 3")
        capsfilter3.set_property("caps", Gst.Caps.from_string("video/x-raw, format=NV12"))

        encoder = self._create_element("x264enc", "h264 encoder", "h264 encoder");
        container = self._create_element("qtmux", "qtmux", "Container")
        
        filesink = self._create_element("filesink", "filesink", "Sink")
        filesink.set_property("location", self.output_video_path)
        filesink.set_property("sync", 0)
        filesink.set_property("async", 0)

        # add all elements to h264 sink bin        
        h264_sink_bin.add(nvvidconv3)
        h264_sink_bin.add(capsfilter2)
        h264_sink_bin.add(videoconvert)
        h264_sink_bin.add(capsfilter3)
        h264_sink_bin.add(encoder)        
        h264_sink_bin.add(container)
        h264_sink_bin.add(filesink)

        # We create a ghost pad on the h264 sink 
        sink_pad = nvvidconv3.get_static_pad("sink")
        ghostpad = Gst.GhostPad.new("sink", sink_pad)
        h264_sink_bin.add_pad(ghostpad)
        self._link_sequential([nvvidconv3, capsfilter2, videoconvert, capsfilter3, encoder, container, filesink])        

        return h264_sink_bin

    def _create_element(self, factory_name, name, print_name, detail=""):
        """Creates an element with Gst Element Factory make.

        Return the element if successfully created, otherwise print to stderr and return None.
        """
        logging.info(f"[DeepStreamVideoWriter] Creating {print_name}")
        elm = Gst.ElementFactory.make(factory_name, name)

        if not elm:
            logging.error(f"[DeepStreamVideoWriter] Unable to create {print_name}")
            if detail:
                logging.error(detail)

        return elm

    def _ndarray_to_gst_buffer(self, array: np.ndarray) -> Gst.Buffer:
        """Converts numpy array to Gst.Buffer"""
        return Gst.Buffer.new_wrapped(array.tobytes())       

    @staticmethod
    def _link_sequential(elements: list):
        for i in range(0, len(elements) - 1):
            elements[i].link(elements[i + 1]) 