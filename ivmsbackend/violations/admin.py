# violations/admin.py
from django.contrib import admin
from .models import Event, ViolationType, CameraPosition, Plate, Stream, EventStatus

models = [Event]

class StreamAdmin(admin.ModelAdmin):
    list_display = ('id', 'cam_position', 'rtsp_url')

class PlateAdmin(admin.ModelAdmin):
    list_display = ('id', 'plate_type', 'plate_num', 'plate_state', 'plate_country')

class ViolationTypeAdmin(admin.ModelAdmin):
    list_display = ('id', 'violation_type', 'description')

class CameraPositionAdmin(admin.ModelAdmin):
    list_display = ('id', 'cam_position')

class EventAdmin(admin.ModelAdmin):
    list_display = ('id', 'stream', 'violation_type', 'plate_num',
                    'plate_type', 'plate_state', 'plate_country',
                    'created_at', 'created_by', 'recording_path')

class EventStatusAdmin(admin.ModelAdmin):
    list_display = ['id', 'status', 'description']

admin.site.register(Stream, StreamAdmin)
admin.site.register(Plate, PlateAdmin)
admin.site.register(ViolationType, ViolationTypeAdmin)
admin.site.register(CameraPosition, CameraPositionAdmin)
admin.site.register(Event, EventAdmin)
admin.site.register(EventStatus, EventStatusAdmin)
