#!/bin/bash
# setup_simulator.sh

# Set the environment to use the simulator
export USE_WHATSAPP_SIMULATOR=True

# Apply migrations
python manage.py migrate

# Load initial data
python manage.py loaddata initial_data.json

# Initialize the simulator
python manage.py init_simulator

# Start the development server
python manage.py runserver