import os
import sys
from math import sqrt

import cv2
import numpy as np
from matplotlib import pyplot as plt

class PreprocessVehicleLicensePlate:
    def __init__(self):
        self.kernel = np.ones((3,3))

    def run(self, image):
        # 1: increase contrast to higlight borders
        lab= cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        l_channel, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=5.0, tileGridSize=(4,4))
        cl = clahe.apply(l_channel)
        limg = cv2.merge((cl,a,b))
        imgHighContrast = cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)

        # 2: bgr2gray
        imgGray = cv2.cvtColor(imgHighContrast, cv2.COLOR_BGR2GRAY)

        # 3: blur
        imgBlur = cv2.GaussianBlur(imgGray,(5,5),1)

        # 4: close connections 
        imgClose = cv2.morphologyEx(imgBlur, cv2.MORPH_CLOSE, self.kernel)

        # 5, binary thresholding
        imgBinary = cv2.threshold(imgClose, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]

        # 6: edge detection
        imgCanny = cv2.Canny(imgBinary,100,300)

        # 7: dilation
        imgDial = cv2.dilate(imgCanny, self.kernel,iterations=2)

        # 8: erode or opening connections
        # Gives poor result with my set of selected images, but important operation, check according to your dateset and enable this optional step
        # imgThres = cv2.erode(imgDial,self.kernel,iterations=2)
        # (or)
        # imgThres =  cv2.morphologyEx(imgDial, cv2.MORPH_OPEN, self.kernel)
        
        #9: get contours and do perspective transform
        imgContour, warped = self.getWarpedImage(imgDial, imgHighContrast)

        return imgHighContrast, imgBlur, imgBinary, imgCanny, imgDial, imgContour, warped

    def distanceOfPoints(self, x1, y1, x2, y2):
        result = int(sqrt(pow(x1 - x2, 2.0) + pow(y1 - y2, 2.0)))
        return result

    def hw(self, p1, p2, p3, p4):
        a = [0,0]

        if(self.distanceOfPoints(p1[0],p1[1],p2[0],p2[1])<self.distanceOfPoints(p3[0],p3[1],p4[0],p4[1])):
            a[0]=self.distanceOfPoints(p3[0],p3[1],p4[0],p4[1])
        else:
            a[0]=self.distanceOfPoints(p1[0],p1[1],p2[0],p2[1])

        if(self.distanceOfPoints(p2[0],p2[1],p3[0],p3[1])<self.distanceOfPoints(p4[0],p4[1],p1[0],p1[1])):
            a[1]=self.distanceOfPoints(p4[0],p4[1],p1[0],p1[1])
        else:
            a[1]=self.distanceOfPoints(p2[0],p2[1],p3[0],p3[1])

        return a

    def order_points(self,pts):
        # Step 1: Find centre of object
        center = np.mean(pts)

        # Step 2: Move coordinate system to centre of object
        shifted = pts - center

        # Step #3: Find angles subtended from centroid to each corner point
        theta = np.arctan2(shifted[:, 0], shifted[:, 1])

        # Step #4: Return vertices ordered by theta
        ind = np.argsort(theta)

        return pts[ind]

    def getWarpedImage(self, img, orig):  # Change - pass the original image too
        biggest = np.array([])
        maxArea = 0
        imgContour = orig.copy()  # Make a copy of the original image to return
        contours, _ = cv2.findContours(img, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        index = None
        for i, cnt in enumerate(contours):  # Change - also provide index
            area = cv2.contourArea(cnt)
            if area > 500:
                peri = cv2.arcLength(cnt, True)
                approx = cv2.approxPolyDP(cnt,0.02*peri, True)
                if area > maxArea and len(approx) == 4:
                    biggest = approx
                    maxArea = area
                    index = i  # Also save index to contour

        warped = None  # Stores the warped license plate image
        if index is not None: # Draw the biggest contour on the image
            cv2.drawContours(imgContour, contours, index, (0, 0, 255), 10,cv2.LINE_AA)

            src = np.squeeze(biggest).astype(np.float32) # Source points
            biggest = self.order_points(src)

            height, width = self.hw(biggest[0],biggest[1],biggest[2],biggest[3])

            # Destination points
            dst = np.float32([[0, 0], [0, height - 1], [width - 1, 0], [width - 1, height - 1]])
            dst = self.order_points(dst)

            # Get the perspective transform
            M = cv2.getPerspectiveTransform(biggest, dst)

            # Warp the image
            img_shape = (width, height)
            warped = cv2.warpPerspective(orig, M, img_shape, flags=cv2.INTER_LINEAR)
            
        return imgContour, warped  # Change - also return drawn image


def main(image_filepath, display_out):
    print("Checking image filepath")
    if os.path.exists(image_filepath):
        print("Image Found")
        image = cv2.imread(image_filepath)
        preprocess_obj = PreprocessVehicleLicensePlate()
        imgHighContrast, imgBlur, imgBinary, imgCanny, imgDial, imgContour, warped = preprocess_obj.run(image)
        print("Done processing")

        if display_out:
            titles = ['Original', 'Contrast', 'Blur', 'Binary', 'Canny', 'Dilate', 'Contours', 'Warped']  # Change - also show warped image
            images = [image[...,::-1],  imgHighContrast[...,::-1], imgBlur, imgBinary, imgCanny, imgDial, cv2.cvtColor(imgContour, cv2.COLOR_BGR2RGB), cv2.cvtColor(warped, cv2.COLOR_BGR2RGB)]  # Change

            # Change - Also show contour drawn image + warped image
            for i in range(6):
                plt.subplot(3, 3, i+1)
                plt.imshow(images[i], cmap='gray')
                plt.title(titles[i])

            if images[-2] is not None:
                plt.subplot(3, 3, 7)
                plt.imshow(images[-2])
                plt.title(titles[-2])

            if images[-1] is not None:
                plt.subplot(3, 3, 9)
                plt.imshow(images[-1])
                plt.title(titles[-1])

            plt.show()
    else:
        print("Image does not exist. Please check file path provided. Try again with absolute path.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage:\n python {sys.argv[0]} /path/to/image.jpg --display\n  or  \n python {sys.argv[0]} /path/to/image.jpg")
        exit(0)

    if len(sys.argv) >= 3 and sys.argv[2] == "--display":
        main(sys.argv[1], True)
    else:
        main(sys.argv[1], False)