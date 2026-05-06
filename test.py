import requests

TOKEN = '8784024411:AAGt_49V_x5cD5zacnTKBGSkKQIuBpeIIcI'
CHAT_ID = '604412691'

def send_telegram_alert(message):
    url = f'https://api.telegram.org/bot{TOKEN}/sendMessage'
    requests.post(url, data={
        'chat_id': CHAT_ID,
        'text': message,
        'parse_mode': 'HTML'
    })

# Test
send_telegram_alert('🌊 Flood Forecast Mark 1 is online!')