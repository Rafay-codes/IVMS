import pyds
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst
import cv2
import numpy as np
import tensorrt as trt
import torch
import pycuda.driver as cuda

from lane_engine import TensorRTInfer

# Use autoprimaryctx if available (pycuda >= 2021.1) to
# prevent issues with other modules that rely on the primary
# device context.
try:
    import pycuda.autoprimaryctx
except ModuleNotFoundError:
    import pycuda.autoinit


LANE_ENGINE = TensorRTInfer('assets/LaneDetector/culaneres182.engine') ##TODO 
row_anchor = np.linspace(0.42,1, 72)
col_anchor = np.linspace(0,1, 81)
t_width = 1600
t_height = 320

def nvvidconv_src_pad_buffer_probe(pad, info, u_data):
    gst_buffer = info.get_buffer()
    if not gst_buffer:
        print("Unable to get GstBuffer ")
        return

    # Retrieve batch metadata from the gst_buffer
    # Note that pyds.gst_buffer_get_nvds_batch_meta() expects the
    # C address of gst_buffer as input, which is obtained with hash(gst_buffer)
    batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
    l_frame = batch_meta.frame_meta_list
    
    while l_frame is not None:
        try:
            # Note that l_frame.data needs a cast to pyds.NvDsFrameMeta
            # The casting is done by pyds.glist_get_nvds_frame_meta()
            # The casting also keeps ownership of the underlying memory
            # in the C code, so the Python garbage collector will leave
            # it alone.
            #frame_meta = pyds.glist_get_nvds_frame_meta(l_frame.data)
            frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
        except StopIteration:
            break
        frame = pyds.get_nvds_buf_surface(hash(gst_buffer), frame_meta.batch_id)
        frame_copy = np.array(frame, copy=True, order='C')
        frame_copy = cv2.cvtColor(frame_copy, cv2.COLOR_RGBA2BGR)
        frame_copy = cv2.resize(frame_copy[int(frame_copy.shape[0]*0.4):,:,:], (t_width, t_height)).transpose((2,0,1))
        net_input = np.array(np.expand_dims(frame_copy, axis=0), copy=True, order='C').astype(np.float32)/255
        print(net_input.shape, net_input.dtype)
        lanes_out = LANE_ENGINE.process(net_input)
        # print(lanes_out)
        # print(" I RUN")
        outdict = {'loc_row': lanes_out[0],
                    'loc_col': lanes_out[1],
                    'exist_row': lanes_out[2],
                    'exist_col': lanes_out[3]
                    }  

        coords = LANE_ENGINE.pred2coordstrt(outdict, row_anchor, col_anchor, original_image_width = frame.shape[1], original_image_height = frame.shape[0])
        for coord in coords:
            for lane in coord:
                for coord in lane:
                    cv2.circle(frame, coord,5,(0,255,0),-1)            
        try:
            l_frame=l_frame.next
        except StopIteration:
            break
			
    return Gst.PadProbeReturn.OK

