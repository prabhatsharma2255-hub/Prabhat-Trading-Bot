# -*- coding: utf-8 -*-
import sys
print("Starting...")
sys.stdout.flush()

print("Importing delta_client...")
sys.stdout.flush()
from delta_client import DeltaClient
print("Imported!")
sys.stdout.flush()

print("Creating...")
sys.stdout.flush()
client = DeltaClient("test", "test")
print("Created!")
sys.stdout.flush()