from classes.frame import Frame

# Used to buffer frames from video source (either video or rtsp camera)
class FrameBuffer(object):
    FRAME_BUFFER_SIZE = 600     # The number of frames kepts in the buffer (simple python list)

    def __init__(self):
        # just initialize the frame buffer
        self.frame_buffer = []

    def append(self, img, index):
         # append new frame to frame buffer and remove first one if buffer is already full
        if len(self.frame_buffer) == self.FRAME_BUFFER_SIZE:
            self.frame_buffer.pop(0)

        self.frame_buffer.append(Frame(img, index))            

    def get_frames(self, end_fi, length, violation_fi = -1):
        # if a violation FI is provided and we can extract from frame buffer 'length' number of frames with violation FI in the middle 
        if violation_fi != -1 and self.frame_buffer[0].index < violation_fi - length / 2:
            frames = [frame for frame in self.frame_buffer if frame.index >= violation_fi - length / 2 and frame.index <= violation_fi + length / 2]
        elif violation_fi != -1:
            frames = self.frame_buffer[:length]
        else:
            frames = [frame for frame in self.frame_buffer if frame.index <= end_fi and frame.index >= end_fi - length].copy()
        return frames

    # return a frame with a specific frame index
    def get_frame(self, fi: int) -> Frame:
        frames = [frame for frame in self.frame_buffer if frame.index == fi]
        if len(frames):
            return frames[0]
        else:
            return None

    def length(self):
        return len(self.frame_buffer)