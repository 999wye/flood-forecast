from django.db import models

class SensorReading(models.Model):
    timestamp         = models.DateTimeField(auto_now_add=True)

    # All ESP32 sensors
    temperature       = models.FloatField()
    humidity          = models.FloatField()
    water_depth       = models.FloatField()
    rain_volume       = models.FloatField()
    wind_speed        = models.FloatField(default=0.0)   # new
    wind_direction    = models.CharField(max_length=10, default='N')  # new (e.g. "NE", "SW")

    # XGBoost output
    flood_risk        = models.CharField(
                            max_length=10,
                            choices=[
                                ('safe',    'Safe'),
                                ('warning', 'Warning'),
                                ('flood',   'Flood')
                            ],
                            default='safe'
                        )
    flood_probability = models.FloatField(default=0.0)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.timestamp} | Depth: {self.water_depth}cm | Wind: {self.wind_speed}m/s {self.wind_direction} | {self.flood_risk}"