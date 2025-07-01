# violations/urls.py
from django.urls import path
from .views import EventList, EventDetail, PlateDetail, PlateList,\
      EventStatusList, EventStatusDetail, ViolationTypeList,\
      ViolationTypeDetail, StreamList, StreamDetail
      


urlpatterns = [
    path("events/<int:pk>/", EventDetail.as_view(), name="event_detail"),
    path("events/", EventList.as_view(), name="event_list"),
    path("plates/<int:pk>/", PlateDetail.as_view(), name="plate_detail"),
    path("plates/", PlateList.as_view(), name="plate_list"),
    path("eventstatus/<int:pk>/", EventStatusDetail.as_view(), name="eventstatus_detail"),
    path("eventstatus/", EventStatusList.as_view(), name="eventstatus_list"),
    path("violationtypes/<int:pk>/", ViolationTypeDetail.as_view(), name="violationtype_detail"),
    path("violationtypes/", ViolationTypeList.as_view(), name="violationtype_list"),
    path("streams/<int:pk>/", StreamDetail.as_view(), name="stream_detail"),
    path("streams/", StreamList.as_view(), name="stream_list")
]