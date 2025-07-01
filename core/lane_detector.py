import numpy as np
import tensorrt as trt
import torch
import cv2
import pycuda.driver as cuda

# Use autoprimaryctx if available (pycuda >= 2021.1) to
# prevent issues with other modules that rely on the primary
# device context.
try:
    import pycuda.autoprimaryctx
except ModuleNotFoundError:
    import pycuda.autoinit


class LaneDetector:
    """
    Implements inference for the EfficientDet TensorRT engine.
    """

    def __init__(self, engine_path):
        """
        :param engine_path: The path to the serialized engine to load from disk.
        """
        # Load TRT engine
        self.logger = trt.Logger(trt.Logger.ERROR)
        trt.init_libnvinfer_plugins(self.logger, namespace="")
        with open(engine_path, "rb") as f, trt.Runtime(self.logger) as runtime:
            assert runtime
            self.engine = runtime.deserialize_cuda_engine(f.read())
        assert self.engine
        self.context = self.engine.create_execution_context()
        assert self.context

        # Setup I/O bindings
        self.inputs = []
        self.outputs = []
        self.allocations = []
        self.row_anchor = np.linspace(0.42,1, 72)
        self.col_anchor = np.linspace(0,1, 81)
        self.t_width = 1600
        self.t_height = 320
        for i in range(self.engine.num_bindings):
            is_input = False
            if self.engine.binding_is_input(i):
                is_input = True
            name = self.engine.get_binding_name(i)
            dtype = np.dtype(trt.nptype(self.engine.get_binding_dtype(i)))
            shape = self.context.get_binding_shape(i)
            if is_input and shape[0] < 0:
                assert self.engine.num_optimization_profiles > 0
                profile_shape = self.engine.get_profile_shape(0, name)
                assert len(profile_shape) == 3  # min,opt,max
                # Set the *max* profile as binding shape
                self.context.set_binding_shape(i, profile_shape[2])
                shape = self.context.get_binding_shape(i)
            if is_input:
                self.batch_size = shape[0]
            size = dtype.itemsize
            for s in shape:
                size *= s
            allocation = cuda.mem_alloc(size)
            host_allocation = None if is_input else np.zeros(shape, dtype)
            binding = {
                "index": i,
                "name": name,
                "dtype": dtype,
                "shape": list(shape),
                "allocation": allocation,
                "host_allocation": host_allocation,
            }
            self.allocations.append(allocation)
            if self.engine.binding_is_input(i):
                self.inputs.append(binding)
            else:
                self.outputs.append(binding)
            print("{} '{}' with shape {} and dtype {}".format(
                "Input" if is_input else "Output",
                binding['name'], binding['shape'], binding['dtype']))

        assert self.batch_size > 0
        assert len(self.inputs) > 0
        assert len(self.outputs) > 0
        assert len(self.allocations) > 0
        print("LANE Detector init done!")

    def input_spec(self):
        """
        Get the specs for the input tensor of the network. Useful to prepare memory allocations.
        :return: Two items, the shape of the input tensor and its (numpy) datatype.
        """
        return self.inputs[0]['shape'], self.inputs[0]['dtype']

    def output_spec(self):
        """
        Get the specs for the output tensors of the network. Useful to prepare memory allocations.
        :return: A list with two items per element, the shape and (numpy) datatype of each output tensor.
        """
        specs = []
        for o in self.outputs:
            specs.append((o['shape'], o['dtype']))
        return specs

    def infer(self, batch):
        """
        Execute inference on a batch of images.
        :param batch: A numpy array holding the image batch.
        :return A list of outputs as numpy arrays.
        """
        # Copy I/O and Execute
        cuda.memcpy_htod(self.inputs[0]['allocation'], batch)
        self.context.execute_v2(self.allocations)
        for o in range(len(self.outputs)):
            cuda.memcpy_dtoh(self.outputs[o]['host_allocation'], self.outputs[o]['allocation'])
        return [o['host_allocation'] for o in self.outputs]

    def process(self, batch):
        """
        Execute inference on a batch of images. The images should already be batched and preprocessed, as prepared by
        the ImageBatcher class. Memory copying to and from the GPU device will be performed here.
        :param batch: A numpy array holding the image batch.
        :param scales: The image resize scales for each image in this batch. Default: No scale postprocessing applied.
        :return: A nested list for each image in the batch and each detection in the list.
        """
        # frame_copy = np.array(batch, copy=True, order='C')
        # frame_copy = cv2.cvtColor(frame_copy, cv2.COLOR_RGBA2BGR)
        frame_copy = batch.copy()
        frame_copy = cv2.resize(frame_copy[int(frame_copy.shape[0]*0.4):,:,:], (self.t_width, self.t_height)).transpose((2,0,1))
        net_input = np.array(np.expand_dims(frame_copy, axis=0), copy=True, order='C').astype(np.float32)/255

        # Run inference
        outputs = self.infer(net_input)
        outdict = {'loc_row': outputs[0],
                    'loc_col': outputs[1],
                    'exist_row': outputs[2],
                    'exist_col': outputs[3]
                    } 
        lanes = self.pred2coordstrt(outdict, self.row_anchor, self.col_anchor,
                    original_image_width=batch.shape[1], original_image_height=batch.shape[0])
        return lanes
    

    
    def pred2coordstrt(self, pred, row_anchor, col_anchor, local_width = 1, original_image_width = 1640, original_image_height = 590):
        pred['loc_row'] = torch.Tensor(pred['loc_row'])
        pred['loc_col'] = torch.Tensor(pred['loc_col'])

        batch_size, num_grid_row, num_cls_row, num_lane_row = pred['loc_row'].shape
        batch_size, num_grid_col, num_cls_col, num_lane_col = pred['loc_col'].shape
        
        # n, num_cls, num_lanes
        max_indices_row = pred['loc_row'].argmax(1)
        # n , num_cls, num_lanes
        valid_row = pred['exist_row'].argmax(1)
        
        # n, num_cls, num_lanes
        max_indices_col = pred['loc_col'].argmax(1)
        # n ,num_cls, num_lanes
        valid_col = pred['exist_col'].argmax(1)
        
        coords_list = []
        for ins in range(batch_size):

            coords = []
            row_lane_idx = [1,2]
            col_lane_idx = [0,3]

            for i in row_lane_idx:
                tmp = []
                if valid_row[ins,:,i].sum() > num_cls_row / 2:
                    for k in range(valid_row.shape[1]):
                        
                        if valid_row[ins,k,i]:
                            all_ind = torch.tensor(list(range(max(0,max_indices_row[ins,k,i] - local_width), min(num_grid_row-1, max_indices_row[ins,k,i] + local_width) + 1)))
                            out_tmp = (pred['loc_row'][ins,all_ind,k,i].softmax(0) * all_ind.float()).sum() + 0.5 
                            out_tmp = out_tmp / (num_grid_row-1) * original_image_width
                            tmp.append((int(out_tmp), int(row_anchor[k] * original_image_height)))
                    coords.append(tmp)

            for i in col_lane_idx:
                tmp = []
                if valid_col[ins,:,i].sum() > num_cls_col / 4:
                    for k in range(valid_col.shape[1]):
                        if valid_col[ins,k,i]:
                            all_ind = torch.tensor(list(range(max(0,max_indices_col[ins,k,i] - local_width), min(num_grid_col-1, max_indices_col[ins,k,i] + local_width) + 1)))                        
                            out_tmp = (pred['loc_col'][ins,all_ind,k,i].softmax(0) * all_ind.float()).sum() + 0.5
                            out_tmp = out_tmp / (num_grid_col-1) * original_image_height
                            tmp.append((int(col_anchor[k] * original_image_width), int(out_tmp)))
                    coords.append(tmp)
            coords_list.append(coords)
        return coords_list


