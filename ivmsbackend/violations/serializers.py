# violations/serializers.py
from rest_framework import serializers
from .models import Event, Stream, Plate, EventStatus, ViolationType

class EventSerializer(serializers.ModelSerializer):

    # The name here needs to be same as the one in the model field
    # Step 1 for automatically setting the username as creator
    #created_by = serializers.StringRelatedField(default=serializers.CurrentUserDefault(), read_only=True)
    class Meta:
        fields = "__all__"
        model = Event


class PlateSerializer(serializers.ModelSerializer):

    class Meta:
        fields = "__all__"
        model = Plate


class StreamSerializer(serializers.ModelSerializer):

    class Meta:
        fields = "__all__"
        model = Stream


class EventStatusSerializer(serializers.ModelSerializer):

    class Meta:
        fields = "__all__"
        model = EventStatus

class ViolationTypeSerializer(serializers.ModelSerializer):

    class Meta:
        fields = "__all__"
        model = ViolationType