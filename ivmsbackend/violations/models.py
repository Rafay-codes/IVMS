from django.conf import settings
from django.db import models


class CameraPosition(models.Model):
    cam_position = models.CharField(max_length=20)
    def __str__(self):
        return self.cam_position
    
class Stream(models.Model):
    cam_position = models.ForeignKey(CameraPosition, on_delete=models.SET_NULL, null=True)
    rtsp_url = models.TextField(blank=True, null=True)
    def __str__(self):
        return "Cam " + str(self.id )+ " at " + str(self.cam_position)

class ViolationType(models.Model):
    violation_type = models.CharField(max_length=50)
    description = models.TextField(blank=True, null=True)
    def __str__(self):
        return self.violation_type


class Plate(models.Model):
    plate_num = models.CharField(max_length=10)
    plate_type = models.CharField(max_length=10)
    plate_state = models.CharField(max_length=100)
    plate_country = models.CharField(max_length=60, blank=True, null= True)
    image_path = models.CharField(null=True, blank=True, max_length=100)


class EventStatus(models.Model):
    status = models.CharField(max_length=20)
    description = models.TextField(blank=True, null=True)
    def __str__(self):
        return self.status


class Event(models.Model):
    stream = models.ForeignKey(Stream, on_delete=models.SET_NULL, null=True)
    violation_type = models.ForeignKey(ViolationType, on_delete=models.SET_NULL, null=True)
    plate_num = models.CharField(max_length=10)
    plate_type = models.CharField(max_length=10)
    plate_state = models.CharField(max_length=100)
    plate_country = models.CharField(max_length=60, blank=True, null= True)
    latitude = models.DecimalField(max_digits=11, decimal_places=7)
    longitude = models.DecimalField(max_digits=11, decimal_places=7)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    status = models.ForeignKey(EventStatus, on_delete=models.SET_NULL, null=True)
    recording_path = models.TextField(blank=True,null=True)

    