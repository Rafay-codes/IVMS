def tiler_sink_pad_buffer_probe(self, frames, batch_meta, l_frame_meta: List, ll_obj_meta: List[List]):
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
                # The casting is done by pyds.NvDsFrameMeta.cast()
                # The casting also keeps ownership of the underlying memory
                # in the C code, so the Python garbage collector will leave
                # it alone.
                frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
            except StopIteration:
                break

            # Update frame rate through this probe
            stream_no = frame_meta.pad_index
            stream_index = "stream{0}".format(stream_no)            
            self.perf_data.update_fps(stream_index)

            frame_number = frame_meta.frame_num

            # Getting Image data using nvbufsurface
            # the input should be address of buffer and batch_id
            n_frame = pyds.get_nvds_buf_surface(hash(gst_buffer), frame_meta.batch_id)
            # convert python array into numpy array format in the copy mode.
            frame_copy = np.array(n_frame, copy=True, order='C')
            # convert the array into cv2 default color format
            #frame_copy = cv2.cvtColor(frame_copy, cv2.COLOR_RGBA2BGRA)  <-- NO!!!, if memory type is not correctly set         
            frame_copy = cv2.cvtColor(frame_copy, cv2.COLOR_RGBA2BGR)
            
            # print(frame_copy.shape)
            # Lane detection happens here
            # if probedict['lane_detector'] and frame_number %4 ==0:
            #     probedict['lanes'] = probedict['lane_detector'].process(frame_copy)
            #     ## Visualize Lanes ##
            #     for lanes in probedict['lanes']:
            #         for lane in lanes:
            #             for coord in lane:
            #                 cv2.circle(n_frame, coord,5,(0,255,0), -1)
            # we have to save the current frame in the buffer  
            self.recorder.update_buffer(frame_copy, stream_no, frame_number)

            # get detections of current frame
            detections = []
            not_detections = []
           
            l_obj = frame_meta.obj_meta_list
            num_rects = frame_meta.num_obj_meta

            while l_obj is not None:
                try:
                    # Casting l_obj.data to pyds.NvDsObjectMeta
                    obj_meta = pyds.NvDsObjectMeta.cast(l_obj.data)
                    minx, miny, maxx, maxy = rect_params_to_coords(obj_meta.rect_params)
                
                    # # if object is placed on the top 1/3 of the viewport then it is considered to
                    # # be far away and is filtered out
                    if maxy < self.cfg.VIDEO_OUTPUT.MUXER.HEIGHT / 3:  
                        # print("Removed box" , maxy)
                    # if maxy > 1:                                   
                        # https://forums.developer.nvidia.com/t/function-nvds-remove-obj-meta-from-frame-in-python/111512
                        # pyds.nvds_remove_obj_meta_from_frame(frame_meta, obj_meta)
                        not_detections.append(obj_meta)
                    # convert object metadata to dictionary object
                    else :
                        detections.append(do.get_detection_from_meta(obj_meta))   
                        # print("retained box", maxy)
                    # detection = do.get_detection_from_meta(obj_meta)
                    # if detection.class_id in [do.BELT, do.NO_BELT, do.MOBILE]:
                    #     viol_objs.append(detection)
                    
                except StopIteration:
                    break              

                try:
                    l_obj = l_obj.next
                except StopIteration:
                    break

                for objmeta in not_detections:
                    pyds.nvds_remove_obj_meta_from_frame(frame_meta, objmeta)

            # perform LPR with Carrida using detection objects
            # -> PlateRecognition object is responsible for keeping vehicle slot lists
            ## TODO shift this inside the l_obj loop, this will reduce redundancy ##
            if self.lpr:   
                v_slots = self.lpr.update(detections, stream_no, frame_number, frame_copy)

                # perform violation detection using object of current frame
                # TODO too many loops fix this for performance this is n^3 #
                viol_objs = [v for v in detections if v.class_id in [do.BELT, do.NO_BELT, do.MOBILE]]
                st_wheels = [stw for stw in detections if stw.class_id == do.STEERING_WHEEL]
                violations = self.ms_viol_detector.detect(v_slots, viol_objs, st_wheels, stream_no, frame_number, frame_copy)

            # record violations (if any)
            # self.recorder.record_mobile(violations, stream_no, frame_number)

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

            try:
                l_frame=l_frame.next
            except StopIteration:
                break

        return Gst.PadProbeReturn.OK 