import os
import sys
import logging 
import configparser
import math
import cv2
import pika
import json

import numpy as np
from datetime import datetime
from typing import List
from functools import partial
from inspect import signature
from threading import Thread

# Deepstream related imports
from charset_normalizer import detect
import pyds
from core.is_aarch_64 import is_aarch64

# GStreamer imports
import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import GObject, GstRtspServer, Gst, GLib

import core.detection_object as do
from utils.FPS import PERF_DATA
from utils.bbox import rect_params_to_coords
from core.bus_call import bus_call
from core.uri_bin_callbacks import cb_newpad, decodebin_child_added
from core.plate_recognition import PlateRecognition
from core.violation_recorder import ViolationRecorder
#from core.lane_detector import LaneDetector
from core.ms_violation_detector import MSViolationDetector
from core.api_interface import APIInterface
from core.queue_reader import QueueReader



class Pipeline(object):

    OSD_PROCESS_MODE = 1
    OSD_DISPLAY_TEXT = 1 
    CAMERA_POSITION_DEVICE_MAP = [2,4,5,6,1,3] # 0:2, 1:4, 2:5, 3:6       
    
    def __init__(self,
                 cfg,
                 options: str,     # Contains all arguments passed to the program 
                 configs_dir: str, # path to configs directory -> all pgie, tracker config files are there
                 output_dir: str   # path to output directory -> if output = 'screen' output file we be saved in this directory
                ): 


        self.cfg = cfg       
        self.output = options.output
        if options.record == 'True':
            self.record = True
        else:
            self.record = False

        if options.rtsp == 'True':
            self.to_stream = True
        else:
            self.to_stream = False

        self.configs_dir = configs_dir
        self.num_sources = len(cfg.VIDEO_SOURCES)
        self.source_uris = cfg.VIDEO_SOURCES
        self.is_live = True
        # self.is_live = any("rtsp" in s for s in self.source_uris)  # set to true if a least one of the sources is a live stream
        self.perf_data = PERF_DATA(self.num_sources)
        
        self.lpr = None

        api_interface = APIInterface(cfg, configs_dir)
        if options.anpr == 'CAR':
            self.lpr = PlateRecognition(configs_dir, cfg.VIDEO_OUTPUT.LPR_FOLDER,
                                        len(cfg.VIDEO_SOURCES), int(cfg.VIDEO_OUTPUT.MUXER.WIDTH),
                                        int(cfg.VIDEO_OUTPUT.MUXER.HEIGHT), api_interface, anpr = cfg.ANPR_ENABLE)

        self.ms_viol_detector = MSViolationDetector()

        self.lane_detector = None
        if options.lane == 'True':
            #self.lane_detector = LaneDetector(os.path.join(configs_dir, "..", cfg.LANE_ENGINE))
            pass
        else:
            self.lane_detector = None
        
        self.passtoprobe = {
            'lane_detector': self.lane_detector,
            'lanes': []
            }
        
        # Initialize API Interface
        
        self.recorder = ViolationRecorder(cfg, len(cfg.VIDEO_SOURCES), api_interface)
        self.output_video_path_list = []
        self.record_path = []
        output_folder = os.path.join(output_dir, datetime.now().strftime("%Y%m%d"))
        if not os.path.exists(output_folder):
            os.mkdir(output_folder)

        for i in range(self.num_sources):
            recordingpath = os.path.join(output_folder, str(i))
            if not os.path.exists(recordingpath):
                os.makedirs(recordingpath, exist_ok=True)
            recordingfile = os.path.join(recordingpath, f'{datetime.now().strftime("%H%M%S")}_Part%02d.mkv')
            self.output_video_path_list.append(recordingfile)
        print (f'Number of input sources: {self.num_sources}, is live stream: {self.is_live}')

        # if output is set to 'file' then compute filename
        if self.output == 'file':
            # compute output directory name and create it if it doesn't yet existself._detect(cars, stream_no, frame)
            output_folder = os.path.join(output_dir, datetime.now().strftime("%Y%m%d"))
            if not os.path.exists(output_folder):
                os.mkdir(output_folder)
            self.output_video_path = os.path.join(output_folder, f'{datetime.now().strftime("%H%M%S")}.mp4')                    

        # Standard GStreamer initialization
        GObject.threads_init() # -> NOT in new test1 python app
        Gst.init(None)

        logging.info("Creating Pipeline")
        self.pipeline = Gst.Pipeline()
        if not self.pipeline:
            logging.error("Failed to create Pipeline")

        # the elements of the pipeline
        self.elements = []

        self.source_bin = []
        self.sink_bin_list = []
        self.streammux = None
        self.pgie = None
        self.tracker = None        
        self.tiler = None
        self.nvvidconv1 = None
        self.filter = None
        self.nvosd = None
        self.sink_bin = None

        self.queue1 = None
        self.queue2 = None        
        self.queue3 = None
        self.queue4 = None 
        self.queue5 = None 
        self.queue6 = None 
        self.queue7 = None 

        self._create_elements()
        self._link_elements()
        self._add_probes()

        # RABBIT MQ consumer to create recordings for events
        events_consumer = QueueReader(cfg)
        # Look for messages in a separate thread and allow main loop to continue
        events_consumer.recorder = self.recorder
        self.events_consumer_thread = Thread(target=events_consumer.start, daemon=True).start()

    def _create_elements(self):
        # create all source bins
        for i in range(self.num_sources):
            print("Creating source_bin ",i," \n ")
            uri_name = self.source_uris[i]        
            self.source_bin.append(self._create_source_bin(i, uri_name))

        # gst-launch-1.0 uridecodebin uri=rtsp://127.0.0.1:8554/test ! nvvideoconvert ! videoflip method=horizontal-flip ! nv3dsink
        #self.nvvidconvsrc = self._create_element("nvvideoconvert", "convertor_src2", f"video nvconvert {index}")
        #self.videoflip = self._create_element("videoflip", "videoflip", f"videoflip {index}")
        #self.videoflip.set_property('method', 'horizontal-flip')
        
        # create streammux element
        self.streammux = self._create_streammux()   
        self.queue1 = self._create_element("queue", "queue1", "Queue 1")

        self.pgie = self._create_pgie()
        self.queue2 = self._create_element("queue", "queue2", "Queue 2")

        self.tracker = self._create_tracker()

        # Add tee element to connect to demuxer for recording raw videos
        self.tee1 = self._create_element("tee", "tee1", "Tee after tracker")
        self.queue3 = self._create_element("queue", "queue3", "Queue 3")

        # Use convertor to convert from NV12 to RGBA as required by nvosd 
        self.nvvidconv1 = self._create_element("nvvideoconvert", "convertor0", "Video converter 1")
        self.queue4 = self._create_element("queue", "queue4", "Queue 4")
        # add filter to convert the frames to RGBA which is easier to work with in Python. 
        # -> pyds.get_nvds_buf_surface doesn't work without these!
        caps = Gst.Caps.from_string("video/x-raw(memory:NVMM), format=RGBA")
        self.filter = self._create_element("capsfilter", "filter", "Filter")
        self.filter.set_property("caps", caps)

        self.tiler = self._create_tiler()
        self.queue5 = self._create_element("queue", "queue5", "Queue 5")

        # Create OSD to draw on the converted RGBA buffer 
        self.nvosd = self._create_osd()
        self.queue6 = self._create_element("queue", "queue6", "Queue 6")

        # final element: sink bin!
        if self.output.lower() == "file":
            self.sink_bin = self._create_h264_sink_bin()
        elif self.output.lower() == "screen":
            self.transform = self._create_element("nvegltransform", "nvegl-transform", "EGL Transform")
            self.sink_bin = self._create_element("nveglglessink", "nvvideo-renderer", "EGL video renderer")
        else:
            self.sink_bin = self._create_element("fakesink", "fakesink", "Sink")

        # Create necessary elements for recording and RTSP streaming
        if self.record or self.to_stream :
            self.queue7 = self._create_element("queue", "queue7", "Queue 7", add=False)
            self.demuxer = self._create_element("nvstreamdemux", "demuxer", "Demuxer", add=False)

            self.pipeline.add(self.queue7)
            self.pipeline.add(self.demuxer)

            self.tee1.link(self.queue7)
            self.queue7.link(self.demuxer)

            self._create_raw_recording_and_streaming_pipeline()


    def _create_raw_recording_and_streaming_pipeline(self):

        if self.to_stream:
            rtsp_port_num = 8554
            self.server = GstRtspServer.RTSPServer.new()
            self.server.props.service = "%d" % rtsp_port_num
            self.server.attach(None)

        for i in range(self.num_sources):
            nbin = self._create_h264_raw_sink_bin(i)
            #nbin = self._create_h265_raw_sink_bin(i)
            self.pipeline.add(nbin)
            self.sink_bin_list.append(nbin)

    def _create_h265_raw_sink_bin(self, index):
        bin_name = "h265-sink-bin%02d" % index
        h265_sink_bin = Gst.Bin.new(bin_name) 
        if not h265_sink_bin:
            logging.error(f"Unable to create source bin {bin_name}")

        queue_record = self._create_element("queue", "Queue", "Queue in h265bin", add=False)
        nvvidconv3 = self._create_element("nvvideoconvert", "convertor5", "Converter 5", add=False)

        capsfilter2 = self._create_element("capsfilter", "capsfilter4", "Caps filter 2", add=False)
        capsfilter2.set_property("caps", Gst.Caps.from_string("video/x-raw(memory:NVMM), format=NV12")) 

        encoder = self._create_element("nvv4l2h265enc", "h265encoder", "h265 encoder", add=False)
        bitrate = 2000000
        encoder.set_property('bitrate', bitrate)
        encoder.set_property('iframeinterval', 100)
        if is_aarch64():
            encoder.set_property('preset-level', 1)
            encoder.set_property('insert-sps-pps', 1)
            encoder.set_property('profile', 'Main')
            
        parser = self._create_element("h265parse", "h265-parse", "Parser de la h265", add=False)
        container = self._create_element("matroskamux", "matroskamux", "Container", add=False)
        
        filesink = self._create_element("filesink", "filesink", "Sink", add=False)
        filesink.set_property("location", self.output_video_path_list[index])
        filesink.set_property("sync", 0)
        filesink.set_property("async", 0)

        # add all elements to h265 sink bin
        h265_sink_bin.add(queue_record)        
        h265_sink_bin.add(nvvidconv3)
        h265_sink_bin.add(capsfilter2)
        h265_sink_bin.add(encoder)     
        h265_sink_bin.add(parser)   
        h265_sink_bin.add(container)
        h265_sink_bin.add(filesink)

        # We create a ghost pad on the h265 sink 
        sink_pad = queue_record.get_static_pad("sink")
        ghostpad = Gst.GhostPad.new("sink", sink_pad)
        h265_sink_bin.add_pad(ghostpad)
        # self._link_sequential([nvvidconv3, capsfilter2, videoconvert, capsfilter3, encoder, container, filesink])
        self._link_sequential([queue_record, nvvidconv3, capsfilter2, encoder, parser, container, filesink])

        return h265_sink_bin
    
    def _create_h264_raw_sink_bin(self, index):
        bin_name = "h264-sink-bin%02d" % index
        tee = None
        h264_sink_bin = Gst.Bin.new(bin_name) 
        if not h264_sink_bin:
            logging.error(f"Unable to create source bin {bin_name}")

        queue_record = self._create_element("queue", "Queue", "Queue in h264bin", add=False)
        nvvidconv3 = self._create_element("nvvideoconvert", "convertor5", "Converter 5", add=False)

        capsfilter2 = self._create_element("capsfilter", "capsfilter4", "Caps filter 2", add=False)
        capsfilter2.set_property("caps", Gst.Caps.from_string("video/x-raw(memory:NVMM), format=NV12")) 

        encoder = self._create_element("nvv4l2h265enc", "h264encoder", "h264 encoder", add=False)
        bitrate = 4000000
        encoder.set_property('bitrate', bitrate)
        if is_aarch64():
            encoder.set_property('preset-level', 1)
            encoder.set_property('insert-sps-pps', 1)
        parser = self._create_element("h265parse", "h264-parse", "Parser de la h264", add=False)

        h264_sink_bin.add(queue_record)        
        h264_sink_bin.add(nvvidconv3)
        h264_sink_bin.add(capsfilter2)
        h264_sink_bin.add(encoder)  
        h264_sink_bin.add(parser)  
        self._link_sequential([queue_record, nvvidconv3, capsfilter2, encoder, parser])
        
        if self.record and self.to_stream:
            tee = self._create_element("tee", "recordstreamtee",
                                    "Tee to crate stream and record pipes", add=False)
            h264_sink_bin.add(tee)
            
            parser.link(tee)
            
        # We create a ghost pad on the h264 sink 
        sink_pad = queue_record.get_static_pad("sink")
        ghostpad = Gst.GhostPad.new("sink", sink_pad)
        h264_sink_bin.add_pad(ghostpad)

        if self.record:
            
            #container = self._create_element("matroskamux", "matroskamux", "Container", add=False)
            
            #filesink = self._create_element("filesink", "filesink", "Sink", add=False)
            #filesink.set_property("location", self.output_video_path_list[index])
            #filesink.set_property("sync", 0)
            #filesink.set_property("async", 0)
            
            #filesink = self._create_element("multifilesink", "multifilesink", "Sink", add=False)
            #filesink.set_property("location", self.output_video_path_list[index])
            #filesink.set_property("next-file", "max-duration")
            #filesink.set_property("max-file-duration", 60000000000) # 1 min
            #filesink.set_property("max-file-duration", 600000000000) # 10 min
            #filesink.set_property("max-file-duration", 3600000000000) # 1 hour
            #filesink.set_property("sync", 0)
            #filesink.set_property("async", 0)
            
            filesink = self._create_element("splitmuxsink", "splitmuxsink", "Sink", add=False)
            filesink.set_property("location", self.output_video_path_list[index])
            filesink.set_property("max-size-time", 600000000000)
            filesink.set_property("muxer-factory", "matroskamux")
            #filesink.set_property("muxer-properties", "\"properties,streamable=true\"")        

            # add all elements to h264 sink bin   
            #h264_sink_bin.add(parser)   
            #h264_sink_bin.add(container)
            h264_sink_bin.add(filesink)

            # self._link_sequential([nvvidconv3, capsfilter2, videoconvert, capsfilter3, encoder, container, filesink])
            if tee:
                self._link_sequential([tee, filesink])
            else:
                self._link_sequential([parser, filesink])


        if self.to_stream:
            rtppay = Gst.ElementFactory.make("rtph265pay", "rtppay")
            rtppay.set_property('config-interval',1)
            updsink_port_num = 5400 + index
            sink = Gst.ElementFactory.make("udpsink", "udpsink")
            sink.set_property("host", "224.224.255.255")
            sink.set_property("port", updsink_port_num)
            sink.set_property("async", False)
            sink.set_property("sync", 1)
            #sink.set_property("sync", False)
            #h264_sink_bin.add(parser)
            h264_sink_bin.add(rtppay)
            h264_sink_bin.add(sink)

            if tee:
                self._link_sequential([tee, rtppay, sink])
            else:
                self._link_sequential([parser, rtppay, sink])

            factory = GstRtspServer.RTSPMediaFactory.new()
            factory.set_launch(
                '( udpsrc port=%d buffer-size=524288 caps=\"application/x-rtp, media=video, clock-rate=90000, encoding-name=(string)%s, payload=96 \" ! queue ! rtph265depay ! queue ! rtph265pay config-interval=1 name=pay0 pt=96 )'
                % (updsink_port_num, "H265")
                 )
            factory.set_shared(True)
            #rtsp_mount_point_str = "/ivms-ktc-" + str(index+1)
            rtsp_mount_point_str = "/ivms-ktc-" + str(self.CAMERA_POSITION_DEVICE_MAP[index])
            self.server.get_mount_points().add_factory(rtsp_mount_point_str, factory)
            print('************')
            print("RTSP: ", rtsp_mount_point_str)
            
        return h264_sink_bin
        
    @staticmethod
    def _link_sequential(elements: list):
        for i in range(0, len(elements) - 1):
            elements[i].link(elements[i + 1])
    

    def _link_elements(self):
        logging.info(f"Linking elements in the Pipeline: {self}")

        # link each src pad of source bin elements to streammux sink pad
        for i in range(self.num_sources):

            # get sink pad of streammux element
            padname = "sink_%u" %i
            sinkpad = self.streammux.get_request_pad(padname)
            if not sinkpad:
                logging.error(f"Unable to get the sink pad {padname} of streammux")

            srcpad = self.source_bin[i].get_static_pad("src")
            if not srcpad:
                logging.error(f"Unable to get source pad of decoder {i}")
            
            srcpad.link(sinkpad)
        # link the rest of the elements
        self._link_sequential(self.elements[self.num_sources:])
                
        if self.record == True or self.to_stream == True:
            for i in range(self.num_sources):
                # get src pad of demuxer element
                padname = "src_%u" %i
                srcpad = self.demuxer.get_request_pad(padname)
                if not srcpad:
                    logging.error(f"Unable to get the src pad {padname} of demux")

                sinkpad = self.sink_bin_list[i].get_static_pad("sink")
                if not sinkpad:
                    logging.error(f"Unable to get sink pad of sink bin {i}")
                
                srcpad.link(sinkpad)

    def _add_probes(self):
        # add probe to nvtracker sink; we use it to filter out bboxes from the upper 1/3 part of the viewport
        # tracker_sinkpad = self.tracker.get_static_pad("sink")
        # tracker_sinkpad.add_probe(Gst.PadProbeType.BUFFER, self._wrap_probe(self.tracker_sink_pad_buffer_probe))

        # we add probe to the sink pad of the tiler element, since by that time, the buffer would have
        # had got all the metadata. 
        tiler_sink_pad = self.tiler.get_static_pad("sink")
        if not tiler_sink_pad:
            logging.error(" Unable to get sink pad of nvtiler plugin")
        else:        
            # tiler_sink_pad.add_probe(Gst.PadProbeType.BUFFER, self.tiler_sink_pad_buffer_probe, self.passtoprobe)
            tiler_sink_pad.add_probe(Gst.PadProbeType.BUFFER, self._wrap_probe(self.tiler_sink_pad_buffer_probe))
            # perf callback function to print fps every 5 sec
            GLib.timeout_add(5000, self.perf_data.perf_print_callback)

    def __str__(self):
        return " -> ".join([elm.name for elm in self.elements])

    def _add_element(self, element, idx=None):
        if idx:
            self.elements.insert(idx, element)
        else:
            self.elements.append(element)
        self.pipeline.add(element)

    def _create_element(self, factory_name, name, print_name, add=True):
        """Creates an element with Gst Element Factory make.

        Return the element if successfully created, otherwise print to stderr and return None.
        """
        logging.info(f"Creating {print_name}")
        elm = Gst.ElementFactory.make(factory_name, name)
        if not elm:
            logging.error(f"Unable to create {print_name}")           
        if add:
            self._add_element(elm)
        return elm

    def _create_source_bin(self, index, uri):
        print(f"Creating source bin for stream {index}")

        # Create a source GstBin to abstract this bin's content from the rest of the pipeline    
        bin_name = "source-bin-%02d" % index
        nbin = Gst.Bin.new(bin_name)
        if not nbin:
            logging.error(f"Unable to create source bin {bin_name}")

        print(uri)
        if uri.find("/dev/video")== 0:
            # set is_live flag to True if uri is from rtsp stream
            self.is_live = True

            source = self._create_element("v4l2src", "onboard-cam-source", f"V4l2 src {index}", add=False)
            caps_v4l2src = self._create_element("capsfilter", "v4l2src_caps", f"V4l2 caps filter {index}", add=False)
            vidconvsrc = self._create_element("videoconvert", "convertor_src1", f"V4l2 video convert RAW {index}", add=False)
            nvvidconvsrc = self._create_element("nvvideoconvert", "convertor_src2", f"V4l2 video nvconvert {index}", add=False)
            caps_vidconvsrc = self._create_element("capsfilter", "nvmm_caps", f"V4l2 capsfilter after nvconvert {index}", add=False)
            
            caps_v4l2src.set_property('caps', Gst.Caps.from_string("video/x-raw, width=1920,height=1080, framerate=30/1"))
            caps_vidconvsrc.set_property('caps', Gst.Caps.from_string("video/x-raw(memory:NVMM)"))
            source.set_property('device', uri)

            Gst.Bin.add(nbin, source)
            Gst.Bin.add(nbin, caps_v4l2src)
            Gst.Bin.add(nbin, vidconvsrc)
            Gst.Bin.add(nbin, nvvidconvsrc)
            Gst.Bin.add(nbin, caps_vidconvsrc)

            source.link(caps_v4l2src)
            caps_v4l2src.link(vidconvsrc)
            vidconvsrc.link(nvvidconvsrc)
            nvvidconvsrc.link(caps_vidconvsrc)
            srcpad = caps_vidconvsrc.get_static_pad("src")
            if not srcpad:
                sys.stderr.write(" Unable to get source pad of caps_vidconvsrc \n")

            # We need to create a ghost pad for the source bin which will act as a proxy
            # for the video decoder src pad. The ghost pad will not have a target right
            # now. Once the decode bin creates the video decoder and generates the
            # cb_newpad callback, we will set the ghost pad target to the video decoder
            # src pad.
            bin_pad=nbin.add_pad(Gst.GhostPad.new("src",srcpad))
            if not bin_pad:
                logging.error(f"Failed to add ghost pad in source bin {bin_name}")
                return None

            self._add_element(nbin)
        elif uri.find("file://")== 0 or uri.find("rtsp://") == 0:
            
            # Source element for reading from the uri.
            # We will use decodebin and let it figure out the container format of the
            # stream and the codec and plug the appropriate demux and decode plugins.        
            uri_decode_bin = self._create_element("uridecodebin", "uri-decode-bin", f"URI decode bin {index}", add=False)
            #caps_v4l2src = self._create_element("capsfilter", "v4l2src_caps", f"V4l2 caps filter {index}", add=False)
            #caps_v4l2src.set_property('caps', Gst.Caps.from_string("video/x-raw, framerate=60/1"))
            #nvvidconvsrc = self._create_element("nvvideoconvert", "convertor_src2", f"V4l2 video nvconvert {index}", add=False)
                        
            # We set the input uri to the source element
            uri_decode_bin.set_property("uri", uri)
            # uri_decode_bin.set_property("buffer-duration",1)
            # uri_decode_bin.set_property("buffer-size",1)


            #if uri.find("rtsp://")== 0:
                # set is_live flag to True if uri is from rtsp stream
                #self.is_live = True

            # Connect to the "pad-added" signal of the decodebin which generates a
            # callback once a new pad for raw data has beed created by the decodebin
            uri_decode_bin.connect("pad-added", cb_newpad, nbin)
            uri_decode_bin.connect("child-added", decodebin_child_added, nbin)

            # We need to create a ghost pad for the source bin which will act as a proxy
            # for the video decoder src pad. The ghost pad will not have a target right
            # now. Once the decode bin creates the video decoder and generates the
            # cb_newpad callback, we will set the ghost pad target to the video decoder
            # src pad.
            Gst.Bin.add(nbin, uri_decode_bin)
            #Gst.Bin.add(nbin, caps_v4l2src)
            #Gst.Bin.add(nbin, nvvidconvsrc)
            #Gst.Bin.add(nbin, videoflip)
            
            #uri_decode_bin.link(caps_v4l2src)
            #uri_decode_bin.link(nvvidconvsrc)
            #nvvidconvsrc.link(videoflip)
            
            bin_pad=nbin.add_pad(Gst.GhostPad.new_no_target("src",Gst.PadDirection.SRC))
            #bin_pad=nbin.add_pad(Gst.GhostPad.new("src",nvvidconvsrc.get_static_pad("src")))
            if not bin_pad:
                logging.error(f"Failed to add ghost pad in source bin {bin_name}")
                return None

            self._add_element(nbin)
        else:
            print("Source", uri, "is not a valid source",
            "please enter source like rtsp://abcd or file://abcd or /dev/video0")
            exit()
        return nbin

    def _create_streammux(self):        
    
        #caps_v4l2src = self._create_element("capsfilter", "v4l2src_caps", f"V4l2 caps filter {index}")
        #caps_v4l2src.set_property('caps', Gst.Caps.from_string("video/x-raw, framerate=60/1"))
        #Gst.Bin.add(nbin, source)
        #Gst.Bin.add(nbin, caps_v4l2src)
        streammux = self._create_element("nvstreammux", "stream-muxer", "Stream mux")

        streammux.set_property('width', self.cfg.VIDEO_OUTPUT.MUXER.WIDTH)
        streammux.set_property('height', self.cfg.VIDEO_OUTPUT.MUXER.HEIGHT)
        streammux.set_property('batch-size', self.num_sources)
        streammux.set_property('batched-push-timeout', 4000000)
        #streammux.set_property('async-process', 4000000)

        # https://forums.developer.nvidia.com/t/fps-drops-to-0-2-after-some-time-in-deepstream-5-0-python-app/127811
        if self.is_live:
            streammux.set_property('live-source', 1)            
        
        return streammux

    def _create_pgie(self):
        pgie = self._create_element("nvinfer", "primary-inference", "Primary object detector")

        pgie.set_property('config-file-path', os.path.join(self.configs_dir, self.cfg.PGIE_CONFIG))
        pgie_batch_size = pgie.get_property("batch-size")
        if (pgie_batch_size != self.num_sources):
            print("WARNING: Overriding infer-config batch-size", pgie_batch_size, " with number of sources ", self.num_sources," \n")
        pgie.set_property("batch-size", self.num_sources)
        #pgie.set_property("unique-id", self.PRIMARY_DETECTOR_UID)

        return pgie

    def _create_tracker(self):
        tracker = self._create_element("nvtracker", "tracker", "Tracker")

        #Set properties of tracker
        config = configparser.ConfigParser()
        config.read(os.path.join(self.configs_dir, 'tracker_config.txt'))
        config.sections()

        for key in config['tracker']:
            if key == 'tracker-width' :
                tracker_width = config.getint('tracker', key)
                tracker.set_property('tracker-width', tracker_width)
            if key == 'tracker-height' :
                tracker_height = config.getint('tracker', key)
                tracker.set_property('tracker-height', tracker_height)
            if key == 'gpu-id' :
                tracker_gpu_id = config.getint('tracker', key)
                tracker.set_property('gpu_id', tracker_gpu_id)
            if key == 'll-lib-file' :
                tracker_ll_lib_file = config.get('tracker', key)
                tracker.set_property('ll-lib-file', tracker_ll_lib_file)
            if key == 'll-config-file' :
                tracker_ll_config_file = config.get('tracker', key)
                tracker.set_property('ll-config-file', os.path.join(self.configs_dir, tracker_ll_config_file))
            if key == 'enable-batch-process' :
                tracker_enable_batch_process = config.getint('tracker', key)
                tracker.set_property('enable_batch_process', tracker_enable_batch_process)
            if key == 'enable-past-frame' :
                tracker_enable_past_frame = config.getint('tracker', key)
                tracker.set_property('enable_past_frame', tracker_enable_past_frame)

        return tracker

    def _create_tiler(self):
        
        tiler = self._create_element("nvmultistreamtiler", "nvtiler", "Multi-stream Tiler")        

        tiler_rows=int(math.sqrt(self.num_sources))
        tiler_columns=int(math.ceil((1.0*self.num_sources)/tiler_rows))
        tiler.set_property("rows",tiler_rows)
        tiler.set_property("columns",tiler_columns)
        tiler.set_property("width", self.cfg.VIDEO_OUTPUT.TILER.WIDTH)
        tiler.set_property("height", self.cfg.VIDEO_OUTPUT.TILER.HEIGHT)
        
        return tiler

    def _create_osd(self):        
        nvosd = self._create_element("nvdsosd", "onscreendisplay", "On-screen Display")
        nvosd.set_property('process-mode',self.OSD_PROCESS_MODE)
        nvosd.set_property('display-text',self.OSD_DISPLAY_TEXT)
        return nvosd

    def _create_h265_sink_bin(self):
        h264_sink_bin = Gst.Bin.new("h265-sink-bin") 

        nvvidconv3 = self._create_element("nvvideoconvert", "convertor3", "Converter 3", add=False)

        capsfilter2 = self._create_element("capsfilter", "capsfilter2", "Caps filter 2", add=False)
        capsfilter2.set_property("caps", Gst.Caps.from_string("video/x-raw(memory:NVMM), format=NV12")) 

        encoder = self._create_element("nvv4l2h265enc", "h264encoder2", "h264 encoder 2", add=False)
        parser = self._create_element("h265parse", "h264-parse2", "Parser de la h264 2", add=False)
        container = self._create_element("matroskamux", "matroskamux", "Container", add=False)
        
        filesink = self._create_element("filesink", "filesink", "Sink", add=False)
        filesink.set_property("location", self.output_video_path)
        filesink.set_property("sync", 0)
        filesink.set_property("async", 0)

        # add all elements to h264 sink bin        
        h264_sink_bin.add(nvvidconv3)
        h264_sink_bin.add(capsfilter2)
        h264_sink_bin.add(encoder)    
        h264_sink_bin.add(parser)    
        h264_sink_bin.add(container)
        h264_sink_bin.add(filesink)

        # We create a ghost pad on the h264 sink 
        sink_pad = nvvidconv3.get_static_pad("sink")
        ghostpad = Gst.GhostPad.new("sink", sink_pad)
        h264_sink_bin.add_pad(ghostpad)
        self._link_sequential([nvvidconv3, capsfilter2, encoder, parser, container, filesink])
        self._add_element(h264_sink_bin)
        
    def _create_h264_sink_bin(self):
        h264_sink_bin = Gst.Bin.new("h264-sink-bin") 

        nvvidconv3 = self._create_element("nvvideoconvert", "convertor3", "Converter 3", add=False)

        capsfilter2 = self._create_element("capsfilter", "capsfilter2", "Caps filter 2", add=False)
        capsfilter2.set_property("caps", Gst.Caps.from_string("video/x-raw(memory:NVMM), format=NV12")) 

        encoder = self._create_element("nvv4l2h265enc", "h264encoder2", "h264 encoder 2", add=False)
        parser = self._create_element("h265parse", "h264-parse2", "Parser de la h264 2", add=False)
        container = self._create_element("matroskamux", "matroskamux", "Container", add=False)
        
        filesink = self._create_element("filesink", "filesink", "Sink", add=False)
        filesink.set_property("location", self.output_video_path)
        filesink.set_property("sync", 0)
        filesink.set_property("async", 0)

        # add all elements to h264 sink bin        
        h264_sink_bin.add(nvvidconv3)
        h264_sink_bin.add(capsfilter2)
        h264_sink_bin.add(encoder)    
        h264_sink_bin.add(parser)    
        h264_sink_bin.add(container)
        h264_sink_bin.add(filesink)

        # We create a ghost pad on the h264 sink 
        sink_pad = nvvidconv3.get_static_pad("sink")
        ghostpad = Gst.GhostPad.new("sink", sink_pad)
        h264_sink_bin.add_pad(ghostpad)
        self._link_sequential([nvvidconv3, capsfilter2, encoder, parser, container, filesink])
        self._add_element(h264_sink_bin)

        return h264_sink_bin
      
    def _probe_fn_wrapper(self, _, info, probe_fn, get_frames=False):
        gst_buffer = info.get_buffer()
        if not gst_buffer:
            logging.error("Unable to get GstBuffer")
            return

        frames = []
        l_frame_meta = []
        ll_obj_meta = []
        batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
        l_frame = batch_meta.frame_meta_list
        while l_frame is not None:
            try:
                frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
            except StopIteration:
                break

            if get_frames:
                frame = pyds.get_nvds_buf_surface(hash(gst_buffer), frame_meta.batch_id)
                frames.append(frame)

            l_frame_meta.append(frame_meta)
            l_obj_meta = []

            l_obj = frame_meta.obj_meta_list
            while l_obj is not None:
                try:
                    obj_meta = pyds.NvDsObjectMeta.cast(l_obj.data)
                except StopIteration:
                    break

                l_obj_meta.append(obj_meta)

                try:
                    l_obj = l_obj.next
                except StopIteration:
                    break

            ll_obj_meta.append(l_obj_meta)

            try:
                l_frame = l_frame.next
            except StopIteration:
                break

        if get_frames:
            probe_fn(frames, batch_meta, l_frame_meta, ll_obj_meta)
        else:
            probe_fn(batch_meta, l_frame_meta, ll_obj_meta)

        return Gst.PadProbeReturn.OK

    def _wrap_probe(self, probe_fn):
        get_frames = "frames" in signature(probe_fn).parameters # True if frames is included in the signature of the probe function
        return partial(self._probe_fn_wrapper, probe_fn=probe_fn, get_frames=get_frames)

    # we use this probe to filter out bboxes placed on the top 1/3 of the viewport
    def tracker_sink_pad_buffer_probe(self, batch_meta, l_frame_meta: List, ll_obj_meta: List[List]):
        for frame_meta, l_obj_meta in zip(l_frame_meta, ll_obj_meta):
            for obj_meta in l_obj_meta:        
                # get coords
                minx, miny, maxx, maxy = rect_params_to_coords(obj_meta.rect_params)
                
                # if object is placed on the top 1/3 of the viewport then it is considered to
                # be far away and is filtered out
                if maxy < self.cfg.VIDEO_OUTPUT.MUXER.HEIGHT / 3:                                    
                    # https://forums.developer.nvidia.com/t/function-nvds-remove-obj-meta-from-frame-in-python/111512
                    pyds.nvds_remove_obj_meta_from_frame(frame_meta, obj_meta)

    
    def tiler_sink_pad_buffer_probe(self, frames, batch_meta, l_frame_meta: List, ll_obj_meta: List[List]):
        #return
        for frame_meta, frame, l_obj_meta in zip(l_frame_meta, frames, ll_obj_meta):
            # peformance data for FPS
            stream_no = frame_meta.pad_index
            stream_index = "stream{0}".format(stream_no)
            self.perf_data.update_fps(stream_index)

            frame_number = frame_meta.frame_num

            ## TODO Add lane detection around here
            # Old commit with message "Gonna change probes for better performance" has
            # the reference code and loop for it from line 733 to 740, one with
            # probedict dictionary beind iterated
            #TODO ======================================================================


            #TODO find a better way to do this, i.e. record previous frames
            frame_copy = np.array(frame, copy=True, order='C')
            frame_copy = cv2.cvtColor(frame_copy, cv2.COLOR_RGBA2BGR)
            # if frame_number % 30 == 0:
            #     timestamp = datetime.now().strftime("%Y%m%d.%H%M%S.%f")
            #     img_filename = os.path.join('save_img', timestamp + '.png')
            #     cv2.imwrite(img_filename, frame_copy)
            self.recorder.update_buffer(frame_copy, stream_no, frame_number)
            #TODO ==========================================================

            detections = []
            for obj_meta in l_obj_meta:
                minx, miny, maxx, maxy = rect_params_to_coords(obj_meta.rect_params)
                #if obj_meta.class_id != do.PLATE:
                #   pyds.nvds_remove_obj_meta_from_frame(frame_meta, obj_meta)
                #else:
                detections.append(do.get_detection_from_meta(obj_meta))
                
                #if maxy < self.cfg.VIDEO_OUTPUT.MUXER.HEIGHT / 3: # TODO:instead of this hardcoded, draw zones and use it                              
                #    # https://forums.developer.nvidia.com/t/function-nvds-remove-obj-meta-from-frame-in-python/111512
                #    pyds.nvds_remove_obj_meta_from_frame(frame_meta, obj_meta) 
                #    pass
                #else:
                #    detections.append(do.get_detection_from_meta(obj_meta))
               
            ## TODO Man these loopies are killing me, Take sometime out and fix it
            # list comprehension is trendy but its a loop, get rid of em
            if self.lpr:   
                 # TODO too many loops fix this for performance this is n^2 at least #
                v_slots = self.lpr.update(detections, stream_no, frame_number, frame_copy)
            
            if stream_no == 1: # rear center camera
                # perform violation detection using object of current frame
                viol_objs = [v for v in detections if v.class_id in [do.BELT, do.NO_BELT, do.MOBILE]]
                st_wheels = [stw for stw in detections if stw.class_id == do.STEERING_WHEEL]
                violations = self.ms_viol_detector.detect(v_slots, viol_objs, st_wheels, stream_no, frame_number, frame_copy)
            
                # record violations (if any)
                self.recorder.record_mobile(violations, stream_no, frame_number)
                '''
            
                # TODO: make this executed only if based on udp message received from UI
                if len(violations) > 0:
                    for v in violations:
                        if v.mobile_detected:
                            v.violation_type = 'mobile'
                        else:
                            v.violation_type = 'seatbelt'
                        connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost'))
                        channel = connection.channel()
                        #channel.queue_declare(queue=queue_name)
                        channel.basic_publish(exchange='', routing_key='events_queue', body=json.dumps({'event_id': v.violation_id, 'event_violation_type': v.violation_type}))
                        connection.close()
                '''
            # Event Recording functions are called here #
            # make it more elegant?
            self.recorder.update_recording_events(frame_number)
            # TODO ==========================================================================================================

            '''
            ## TODO Pack it inside a function, looks ugly like this :/
            # Overlay Text on image
            # Step 1: Acquire the display_meta:
            display_meta=pyds.nvds_acquire_display_meta_from_pool(batch_meta)
            display_meta.num_labels = 1
            py_nvosd_text_params = display_meta.text_params[0]
            py_nvosd_text_params.display_text = "Frame Number={}".format(frame_number)
            # print(pyds.get_string(py_nvosd_text_params.display_text))
            # Now set the offsets where the string should appear
            py_nvosd_text_params.x_offset = 10
            py_nvosd_text_params.y_offset = 12

            # Font , font-color and font-size
            py_nvosd_text_params.font_params.font_name = "Serif"
            py_nvosd_text_params.font_params.font_size = 12
            # set(red, green, blue, alpha); set to White
            py_nvosd_text_params.font_params.font_color.set(1.0, 1.0, 1.0, 1.0)

            # Text background color
            py_nvosd_text_params.set_bg_clr = 1
            # set(red, green, blue, alpha); set to Black
            py_nvosd_text_params.text_bg_clr.set(0.0, 0.0, 0.0, 1.0)
            pyds.nvds_add_display_meta_to_frame(frame_meta, display_meta)
            '''
            # TODO ======================================================
            
            #for obj_meta in l_obj_meta:
                #if obj_meta.class_id != do.PLATE:
                #   pyds.nvds_remove_obj_meta_from_frame(frame_meta, obj_meta)

            if self.to_stream:
                pool = self.server.get_session_pool()
            
            #if pool.get_n_sessions() > 2:
            #    print(pool.get_n_sessions(), "active session")
            #    print(pool.cleanup(), "removed")

        return Gst.PadProbeReturn.OK 

    def run(self):
        # Create an event loop and feed gstreamer bus messages to it
        loop = GObject.MainLoop()
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", bus_call, loop)
        # Start play back and listen to events
        logging.info("Starting pipeline")
        Gst.debug_bin_to_dot_file(self.pipeline, Gst.DebugGraphDetails.ALL, "pipeline")
        self.pipeline.set_state(Gst.State.PLAYING)
        try:
            loop.run()
        except:
            pass      
        logging.info("Exiting pipeline")
        self.pipeline.send_event(Gst.Event.new_eos())
        bus = self.pipeline.get_bus()
        msg = bus.timed_pop_filtered(
            Gst.CLOCK_TIME_NONE, Gst.MessageType.EOS)
        print(f"Message: {msg}")

        self.pipeline.set_state(Gst.State.NULL)
