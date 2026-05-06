from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.conf import settings

import json
import joblib
import numpy as np
import pandas as pd
import requests
import os
from datetime import datetime, timedelta

from .models import SensorReading

# ============================================================
#  CONFIGURATION
# ============================================================

TELEGRAM_TOKEN   = '8784024411:AAGt_49V_x5cD5zacnTKBGSkKQIuBpeIIcI'
TELEGRAM_CHAT_ID = '604412691'

FLOOD_THRESHOLD   = 150.0   # cm — red alert
WARNING_THRESHOLD = 100.0   # cm — orange warning

# Load XGBoost models once when server starts
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ML_DIR   = os.path.join(BASE_DIR, 'ml')

try:
    reg_model = joblib.load(os.path.join(ML_DIR, 'flood_regression.pkl'))
    clf_model = joblib.load(os.path.join(ML_DIR, 'flood_classifier.pkl'))
    print('✅ XGBoost models loaded successfully!')
except Exception as e:
    reg_model = None
    clf_model = None
    print(f'⚠️  Could not load models: {e}')


# ============================================================
#  HELPER FUNCTIONS
# ============================================================

def send_telegram_alert(message):
    """Send a flood alert message to Telegram."""
    try:
        url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
        requests.post(url, data={
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message,
            'parse_mode': 'HTML'
        }, timeout=5)
    except Exception as e:
        print(f'Telegram alert failed: {e}')


def get_flood_status(water_depth):
    """Return flood status based on water depth."""
    if water_depth >= FLOOD_THRESHOLD:
        return 'flood'
    elif water_depth >= WARNING_THRESHOLD:
        return 'warning'
    else:
        return 'safe'


def prepare_features(reading):
    """Build XGBoost feature row from latest database readings."""

    # Get last 7 readings for lag features
    recent = list(reversed(SensorReading.objects.order_by('-timestamp')[:7]))

    now         = reading.timestamp
    water_depth = reading.water_depth
    rain_volume = reading.rain_volume
    temp        = reading.temperature
    humidity    = reading.humidity

    # Helper to get lag value safely
    def get_lag(n, field):
        try:
            return getattr(recent[-(n + 1)], field)
        except IndexError:
            return getattr(reading, field)

    wd_lag1 = get_lag(1, 'water_depth')
    wd_lag2 = get_lag(2, 'water_depth')
    wd_lag3 = get_lag(3, 'water_depth')
    wd_lag6 = get_lag(6, 'water_depth')
    rv_lag1 = get_lag(1, 'rain_volume')
    rv_lag2 = get_lag(2, 'rain_volume')
    rv_lag3 = get_lag(3, 'rain_volume')
    tp_lag1 = get_lag(1, 'temperature')
    hm_lag1 = get_lag(1, 'humidity')

    # Rolling statistics
    depths = [r.water_depth for r in recent[-6:]]
    rains  = [r.rain_volume for r in recent[-6:]]

    wd_roll3 = np.mean(depths[-3:]) if len(depths) >= 3 else water_depth
    wd_roll6 = np.mean(depths)      if len(depths) >= 1 else water_depth
    rv_roll3 = np.sum(rains[-3:])   if len(rains)  >= 3 else rain_volume
    rv_roll6 = np.sum(rains)        if len(rains)  >= 1 else rain_volume

    features = {
        'Temperature':             temp,
        'Humidity':                humidity,
        'Water Depth':             water_depth,
        'Rain Volume':             rain_volume,
        'hour':                    now.hour,
        'day':                     now.day,
        'month':                   now.month,
        'dayofweek':               now.weekday(),
        'WaterDepth_lag1':         wd_lag1,
        'WaterDepth_lag2':         wd_lag2,
        'WaterDepth_lag3':         wd_lag3,
        'WaterDepth_lag6':         wd_lag6,
        'RainVolume_lag1':         rv_lag1,
        'RainVolume_lag2':         rv_lag2,
        'RainVolume_lag3':         rv_lag3,
        'Temperature_lag1':        tp_lag1,
        'Humidity_lag1':           hm_lag1,
        'WaterDepth_rolling3_mean': wd_roll3,
        'WaterDepth_rolling6_mean': wd_roll6,
        'RainVolume_rolling3_sum':  rv_roll3,
        'RainVolume_rolling6_sum':  rv_roll6,
        'WaterDepth_change':        water_depth - wd_lag1,
        'WaterDepth_change2':       water_depth - wd_lag2,
    }

    return pd.DataFrame([features])


def predict_next_5(current_reading):
    """Predict water depth and flood probability for next 5 readings (~38 min each)."""
    if reg_model is None or clf_model is None:
        return []

    predictions   = []
    feature_row   = prepare_features(current_reading)
    current_depth = current_reading.water_depth
    now           = current_reading.timestamp

    for step in range(1, 6):
        try:
            next_depth = float(reg_model.predict(feature_row)[0])
            flood_prob = float(clf_model.predict_proba(feature_row)[0][1]) * 100
            next_time  = now + timedelta(minutes=38 * step)

            predictions.append({
                'time':         next_time.strftime('%H:%M'),
                'water_depth':  round(next_depth, 1),
                'flood_prob':   round(flood_prob, 1),
                'flood_status': get_flood_status(next_depth),
            })

            # Update features for next prediction step
            feature_row['WaterDepth_lag2']         = feature_row['WaterDepth_lag1']
            feature_row['WaterDepth_lag3']         = feature_row['WaterDepth_lag2']
            feature_row['WaterDepth_lag6']         = feature_row['WaterDepth_lag3']
            feature_row['WaterDepth_lag1']         = current_depth
            feature_row['WaterDepth_change2']      = next_depth - current_depth
            feature_row['WaterDepth_change']       = next_depth - float(feature_row['WaterDepth_lag1'].iloc[0])
            feature_row['Water Depth']             = next_depth
            feature_row['hour']                    = next_time.hour
            current_depth = next_depth

        except Exception as e:
            print(f'Prediction step {step} failed: {e}')
            break

    return predictions


# ============================================================
#  PAGE 1: DASHBOARD
# ============================================================

def dashboard(request):
    """Main dashboard — live sensor data + 5 future predictions."""
    latest = SensorReading.objects.order_by('-timestamp').first()

    if latest:
        predictions  = predict_next_5(latest)
        flood_status = get_flood_status(latest.water_depth)
        context = {
            'latest':       latest,
            'flood_status': flood_status,
            'predictions':  predictions,
            'last_updated': latest.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'recent_readings': SensorReading.objects.order_by('-timestamp')[:10],  # ← add this
            'pred1': predictions[0] if len(predictions) > 0 else None,
            'pred2': predictions[1] if len(predictions) > 1 else None,
            'pred3': predictions[2] if len(predictions) > 2 else None,
            'pred4': predictions[3] if len(predictions) > 3 else None,
            'pred5': predictions[4] if len(predictions) > 4 else None,
        }
    else:
        context = {
            'latest':       None,
            'flood_status': 'safe',
            'predictions':  [],
            'last_updated': 'Waiting for ESP32 data...',
        }

    return render(request, 'dashboard.html', context)


# ============================================================
#  PAGE 2: HISTORY
# ============================================================

def history(request):
    """History page with calendar navigation."""
    # Get list of dates that have data (for calendar highlighting)
    dates_with_data = SensorReading.objects.dates('timestamp', 'day')
    date_list = [d.strftime('%Y-%m-%d') for d in dates_with_data]

    context = {
        'dates_with_data': json.dumps(date_list),
    }
    return render(request, 'history.html', context)


def get_history_data(request):
    """
    API endpoint — returns sensor readings for a selected date as JSON.
    Called by calendar.js when user picks a date.
    Usage: GET /api/history/?date=2026-05-07
    """
    date_str = request.GET.get('date', '')

    if not date_str:
        return JsonResponse({'error': 'No date provided'}, status=400)

    try:
        selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=400)

    readings = SensorReading.objects.filter(
        timestamp__date=selected_date
    ).order_by('timestamp')

    if not readings.exists():
        return JsonResponse({
            'date':     date_str,
            'count':    0,
            'readings': [],
            'message':  'No data found for this date',
        })

    data = [{
        'timestamp':         r.timestamp.strftime('%H:%M:%S'),
        'temperature':       round(r.temperature, 2),
        'humidity':          round(r.humidity, 2),
        'water_depth':       round(r.water_depth, 2),
        'rain_volume':       round(r.rain_volume, 2),
        'flood_status':      r.flood_risk,
        'flood_probability': round(r.flood_probability, 1),
    } for r in readings]

    depths = [r.water_depth for r in readings]
    summary = {
        'max_depth':    round(max(depths), 2),
        'min_depth':    round(min(depths), 2),
        'avg_depth':    round(np.mean(depths), 2),
        'flood_events': sum(1 for r in readings if r.flood_risk == 'flood'),
        'total_rain':   round(sum(r.rain_volume for r in readings), 2),
    }

    return JsonResponse({
        'date':     date_str,
        'count':    readings.count(),
        'summary':  summary,
        'readings': data,
    })


# ============================================================
#  PAGE 3: ABOUT
# ============================================================

def about(request):
    """About page — project overview, Telegram bot link, contact info."""
    context = {
        'telegram_bot_url': 'https://t.me/FloodForecastMark1Bot',
        'email':            'wmhzq02@gmail.com',
        'linkedin':         'https://www.linkedin.com/in/w-m-haziq-138155321',
        'project_name':     'River Flood Forecasting Device',
        'bot_name':         'Flood Forecast Mark 1',
    }
    return render(request, 'about.html', context)


# ============================================================
#  ESP32 API ENDPOINT
# ============================================================

@csrf_exempt
def receive_sensor_data(request):
    """
    ESP32 sends sensor data here via HTTP POST.

    Expected JSON from ESP32:
    {
        "temperature":  26.5,
        "humidity":     85.2,
        "water_depth":  67.4,
        "rain_volume":  2.1
    }
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=405)

    try:
        body        = json.loads(request.body)
        temperature = float(body.get('temperature', 0))
        humidity    = float(body.get('humidity', 0))
        water_depth = float(body.get('water_depth', 0))
        rain_volume = float(body.get('rain_volume', 0))
        wind_speed     = float(body.get('wind_speed', 0))      # new
        wind_direction = str(body.get('wind_direction', 'N'))  # new

        flood_status = get_flood_status(water_depth)

        # Save reading to database
        reading = SensorReading.objects.create(
            temperature    = temperature,
            humidity       = humidity,
            water_depth    = water_depth,
            rain_volume    = rain_volume,
            wind_speed     = wind_speed,        # new
            wind_direction = wind_direction,    # new
            flood_risk     = flood_status,
            flood_probability = 0.0,
        )

        # Run XGBoost flood probability prediction
        flood_probability = 0.0
        if clf_model is not None:
            try:
                features          = prepare_features(reading)
                flood_probability = float(clf_model.predict_proba(features)[0][1]) * 100
                reading.flood_probability = round(flood_probability, 1)
                reading.save()
            except Exception as e:
                print(f'Prediction error: {e}')

        # Send Telegram alert for flood or warning
        if flood_status == 'flood':
            send_telegram_alert(
                f'🚨 <b>FLOOD ALERT!</b>\n\n'
                f'📍 River Flood Forecasting Device\n'
                f'💧 Water Depth: <b>{water_depth}cm</b> ‼️ DANGER\n'
                f'🌡️ Temperature: {temperature}°C\n'
                f'💦 Humidity: {humidity}%\n'
                f'🌧️ Rain Volume: {rain_volume}mm\n'
                f'📊 Flood Probability: <b>{round(flood_probability, 1)}%</b>\n'
                f'🕐 {reading.timestamp.strftime("%Y-%m-%d %H:%M:%S")}'
            )
        elif flood_status == 'warning':
            send_telegram_alert(
                f'⚠️ <b>FLOOD WARNING!</b>\n\n'
                f'📍 River Flood Forecasting Device\n'
                f'💧 Water Depth: <b>{water_depth}cm</b> ⚠️ WARNING\n'
                f'🌡️ Temperature: {temperature}°C\n'
                f'💦 Humidity: {humidity}%\n'
                f'🌧️ Rain Volume: {rain_volume}mm\n'
                f'📊 Flood Probability: <b>{round(flood_probability, 1)}%</b>\n'
                f'🕐 {reading.timestamp.strftime("%Y-%m-%d %H:%M:%S")}'
            )

        return JsonResponse({
            'status':            'success',
            'message':           'Data received and saved',
            'flood_status':      flood_status,
            'flood_probability': round(flood_probability, 1),
            'reading_id':        reading.id,
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON format'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
