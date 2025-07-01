from rest_framework import generics

from .models import Event, Plate, Stream, ViolationType, EventStatus
from .serializers import EventSerializer, PlateSerializer, StreamSerializer, ViolationTypeSerializer, EventStatusSerializer
from .permissions import IsAuthorOrReadOnly
from rest_framework.permissions import IsAuthenticated

class EventList(generics.ListCreateAPIView):
    permission_classes = (IsAuthenticated,)
    queryset = Event.objects.all()
    serializer_class = EventSerializer

    # Step 2 for automatically saving the current user as the created_by
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

class EventDetail(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = (IsAuthenticated,)
    queryset = Event.objects.all()
    serializer_class = EventSerializer


class PlateList(generics.ListCreateAPIView):
    permission_classes = (IsAuthenticated,)
    queryset = Plate.objects.all()
    serializer_class = PlateSerializer

class PlateDetail(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = (IsAuthenticated,)
    queryset = Plate.objects.all()
    serializer_class = PlateSerializer

class StreamList(generics.ListAPIView):
    permission_classes = (IsAuthenticated,)
    queryset = Stream.objects.all()
    serializer_class = StreamSerializer

class StreamDetail(generics.RetrieveAPIView):
    permission_classes = (IsAuthenticated,)
    queryset = Stream.objects.all()
    serializer_class = StreamSerializer

class ViolationTypeList(generics.ListAPIView):
    permission_classes = (IsAuthenticated,)
    queryset = ViolationType.objects.all()
    serializer_class = ViolationTypeSerializer

class ViolationTypeDetail(generics.RetrieveAPIView):
    permission_classes = (IsAuthenticated,)
    queryset = ViolationType.objects.all()
    serializer_class = ViolationTypeSerializer

class EventStatusList(generics.ListAPIView):
    permission_classes = (IsAuthenticated,)
    queryset = EventStatus.objects.all()
    serializer_class = EventStatusSerializer

class EventStatusDetail(generics.RetrieveAPIView):
    permission_classes = (IsAuthenticated,)
    queryset = ViolationType.objects.all()
    serializer_class = ViolationTypeSerializer