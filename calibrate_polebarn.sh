#!/bin/bash
# calibrate_polebarn.sh – One-click auto calibration pipeline
set -e

echo "🚀 Starting Polebarn Calibration Pipeline..."
cd ~/polebarn_control

# Step 1 – Run the speaker sweeps
echo "🎧 Running deep_venue.py..."
python3 calibration/deep_venue.py

# Step 2 – Analyze the recordings
echo "📊 Running analyze_calibration.py..."
python3 analysis/analyze_calibration.py

# Step 3 – Apply EQ + delay settings to XR18 + QLC+
echo "🎚️  Applying EQ & delay..."
python3 calibration/eq_apply.py

echo "✅ Calibration complete!"
