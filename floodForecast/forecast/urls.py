from django.urls import path
from . import views

urlpatterns = [
    # Pages
    path('', views.dashboard, name='dashboard'),
    path('history/', views.history, name='history'),
    path('about/', views.about, name='about'),

    # API endpoints
    path('api/data/', views.receive_sensor_data, name='receive_sensor_data'),  # ESP32 sends data here
    path('api/history/', views.get_history_data, name='get_history_data'),     # history page fetches data here
]