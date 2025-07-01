# simple class that represents a frame saved in frame buffer
class Frame:
    def __init__(self, img, cnt): 
        self.img = img
        self.index = cnt