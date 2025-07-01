import cv2

# --- draw shapely Polygon object (obj_poly)
def draw_box(img, obj_poly, color = (128, 128, 128), line_thickness = 2, label = None):
    tl = line_thickness or round(0.002 * (img.shape[0] + img.shape[1]) / 2) + 1  # line/font thickness

    minx, miny, maxx, maxy = obj_poly.bounds
    c1, c2 = (int(minx), int(maxy)), (int(maxx), int(miny))
    cv2.rectangle(img, c1, c2, color, thickness=tl, lineType=cv2.LINE_AA)        
    
    if label:
        tf = max(tl - 1, 1)  # font thickness
        t_size = cv2.getTextSize(label, 0, fontScale=tl / 3, thickness=tf)[0]
        c2 = c1[0] + t_size[0], c1[1] - t_size[1] - 3
        cv2.rectangle(img, c1, c2, color, -1, cv2.LINE_AA)  # filled
        cv2.putText(img, label, (c1[0], c1[1] - 2), 0, tl / 3, [225, 255, 255], thickness=tf, lineType=cv2.LINE_AA)

# --- draw line from two shapely Points
def draw_line(img, p1, p2, color = (128, 128, 128), line_thickness = 2):
    cv2.line(img, (int(p1.x), int(p1.y)), (int(p2.x), int(p2.y)), color, thickness=line_thickness)

# helper method: write some text on the image
# see https://stackoverflow.com/questions/16615662/how-to-write-text-on-a-image-in-windows-using-python-opencv2
def write_text(image, text, pos = (50,20), color = (255,0,0), scale=0.7):
    font                   = cv2.FONT_HERSHEY_SIMPLEX
    fontScale              = scale
    fontColor              = color
    lineType               = 2

    cv2.putText(image,text, pos, font, fontScale, fontColor, lineType)  
