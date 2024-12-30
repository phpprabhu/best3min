#!/bin/bash

# Convert UTC to IST (IST is UTC + 5:30)
current_time=$(date -u --date="+5 hours 30 minutes" +%H:%M)
current_day=$(date -u --date="+5 hours 30 minutes" +%u)  # 1 = Monday, 7 = Sunday

# Check if it's a weekday (Monday to Friday) and within 9:30 AM to 3:30 PM
if [[ "$current_day" -le 5 && "$current_time" > "09:24" && "$current_time" < "15:30" ]]; then
    cd /root/best3min/ && export FLASK_APP=app.py && flask check_entry >> /root/best3min/log/check_entry.log 2>&1
fi