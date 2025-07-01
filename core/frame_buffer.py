from core.frame import Frame

# Used to buffer frames from video source (either video or rtsp camera)
class FrameBuffer(object):
        
    def __init__(self, buffer_size, stream_count):

        self.buffer_size = buffer_size

        # we create a separate buffer for each stream
        self.frame_buffer = []
        for i in range(stream_count):
            self.frame_buffer.append( list() ) #different object reference each time            

    def append(self, img, stream_no, index):
         # append new frame to frame buffer and remove first one if buffer is already full
        if len(self.frame_buffer[stream_no]) == self.buffer_size:
            self.frame_buffer[stream_no].pop(0)

        self.frame_buffer[stream_no].append(Frame(img, index))            

    # we need to return 'length' frames in total, starting from frame no = violation_fi - length / 2 
    def get_frames(self, stream_no, violation_fi, current_fi, length):

        start_fi = violation_fi - length / 2        
        first_frame = self.frame_buffer[stream_no][0]

        #DEBUG ONLY!!!
        print(f'[get_frames] Buffer size = {self.buffer_size}, Violation fi = {violation_fi}, current fi = {current_fi}, start fi = {start_fi}, first_frame fi = {first_frame.index}')

        if first_frame.index <= start_fi:
            frames = [frame for frame in self.frame_buffer[stream_no] if frame.index >= violation_fi - length / 2 and frame.index <= violation_fi + length / 2]
        else:
            print (f'[get_frames] Not enough frames for violation fi to be in the middle vfi={violation_fi}, sfi={start_fi}, ffi={first_frame.index}')
            frames = self.frame_buffer[stream_no][:length]

        return frames

    def length(self, stream_no):
        return len(self.frame_buffer[stream_no])