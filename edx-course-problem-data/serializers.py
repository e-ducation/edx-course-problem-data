# -*- coding:utf-8 -*-
from __future__ import unicode_literals

from rest_framework import serializers
from django.contrib.auth import get_user_model


class UserSerializer(serializers.ModelSerializer):
    username = serializers.CharField(read_only=True)

    class Meta:
        model = get_user_model()
        fields = ('id','username','email')
