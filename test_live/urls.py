# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/test_live/urls.py
from django.urls import path
from .views import WalkieTalkieView, ProcessAudioView

app_name = 'test_live'

urlpatterns = [
    path('walkie-talkie/', WalkieTalkieView.as_view(), name='walkie_talkie'),
    path('process-audio/', ProcessAudioView.as_view(), name='process_audio'),
]
