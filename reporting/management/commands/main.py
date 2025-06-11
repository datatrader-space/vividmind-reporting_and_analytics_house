from datetime import datetime
from pathlib import Path

import pandas as pd

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from .import main

import time
import psutil
import platform
import datetime
import requests
from django.core.management.base import BaseCommand
import json
from django.conf import settings  # Import Django settings

class Command(BaseCommand):
    help = 'Sends heartbeat and resource usage data to the central server as events'

    def handle(self, *args, **options):
        central_server_url = settings.CENTRAL_URL +'api/event/'
          # Updated URL

        try:
            server_id = settings.SERVER_ID
        except AttributeError:
            self.stderr.write(self.style.ERROR('CENTRAL_SERVER_ID not configured in Django settings.'))
            return

        while True:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            system_info = platform.uname()
            heartbeat_data = {
                'hostname': system_info.node,
                'os': f"{system_info.system} {system_info.release}",
            }
            event_payload_heartbeat = {
                'event_type': 'heartbeat',
                'server': server_id,  # Send the Server ID
                'timestamp': timestamp,
                'payload': heartbeat_data,
            }

            cpu_percent = psutil.cpu_percent()
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')  # Monitor root partition, add others as needed
            resource_data = {
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent,
                'disk_percent': disk.percent,
            }
            event_payload_resource = {
                'event_type': 'resource',
                'server': server_id,  # Send the Server ID
                'timestamp': timestamp,
                'payload': resource_data,
            }
        
            try:
                # Send Heartbeat Event
               
                response = requests.post(central_server_url, json=event_payload_heartbeat)
                response.raise_for_status()
                self.stdout.write(self.style.SUCCESS(f'[{timestamp}] Heartbeat event sent from server ID {server_id}'))

                # Send Resource Usage Event
                print(event_payload_resource)
                response = requests.post(central_server_url, json=event_payload_resource)
                response.raise_for_status()
                self.stdout.write(self.style.SUCCESS(f'[{timestamp}] Resource event sent from server ID {server_id}'))

            except requests.exceptions.RequestException as e:
                self.stderr.write(self.style.ERROR(f'[{timestamp}] Error sending event from server ID {server_id}: {e}'))

            time.sleep(60)  # Send updates every minute
        