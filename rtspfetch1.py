import cv2 as cv
vcap = cv.VideoCapture("rtsp://localhost:8554/ds-test-1")
while(1):
    ret, frame = vcap.read()
    cv.imshow('VIDEO', frame)
    cv.waitKey(1)