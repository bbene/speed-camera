# Speed-Camera Docker Quick Start Guide

## Setup (5 minutes)

### 1. Clone and Configure
```bash
cd speed-camera
cp config.yaml.example config.yaml
# Edit config.yaml with your settings
```

### 2. Configure Your Camera

#### Option A: RTSP Network Camera (Recommended)
```yaml
camera:
  type: rtsp
  rtsp_url: "rtsp://192.168.1.100:554/Streaming/Channels/101"
  username: admin
  password: mypassword
```

**Common RTSP URLs:**
- **Hikvision/Dahua**: `rtsp://ip:554/Streaming/Channels/101`
- **Reolink**: `rtsp://ip:554/h264Preview_01_main`
- **Generic**: Check your camera's manual for the stream URL

#### Option B: Raspberry Pi PiCamera (Legacy)
```yaml
camera:
  type: picamera
  # fps, resolution configured in other sections
```

### 3. Configure Monitoring Zone
Edit these in `config.yaml`:
```yaml
# Adjust to your monitoring area
upper_left_x: 0
upper_left_y: 0
lower_right_x: 1024
lower_right_y: 576

# Distance from camera to road in feet
l2r_distance: 75
r2l_distance: 85
```

Run `make docker-run` first, then check `preview.jpg` to adjust these values.

### 4. Configure Telegram Alerts (Optional)
```yaml
telegram_token: "YOUR_BOT_TOKEN"
telegram_chat_id: "YOUR_CHAT_ID"
telegram_frequency: 6  # hours between updates
```

## Running

### Start the Container
```bash
make docker-run
```

Or manually:
```bash
docker compose up -d
```

### View Logs
```bash
make docker-logs
# or
docker compose logs -f
```

### Stop the Container
```bash
make docker-stop
# or
docker compose down
```

### Access Shell (debugging)
```bash
make docker-shell
# or
docker compose exec speed-camera bash
```

## Files & Output

- **config.yaml**: Your configuration file (mounted read-only)
- **data/**: CSV logs and alert GIFs are saved here
- **logs/**: Application logs

## Troubleshooting

### "Cannot connect to RTSP stream"
1. Verify the RTSP URL: `ping camera-ip`
2. Check credentials are correct
3. Ensure firewall allows port 554 or your camera's port
4. Some cameras require full URL path - check manufacturer docs

### "Container exits immediately"
```bash
docker compose logs
```
Check the error messages - usually config or RTSP connection issues.

### "Permission denied" on data directory
```bash
mkdir -p data logs
chmod 777 data logs
```

### Adjust Detection Sensitivity
In `config.yaml`:
```yaml
min_speed: 10              # MPH threshold to record
min_speed_alert: 30        # MPH threshold to alert
min_confidence: 70         # Confidence threshold (0-100)
min_area: 2000             # Minimum object size in pixels
```

## Performance Tips

- **Lower resolution** if CPU usage is high: `image_width: 640, image_height: 360`
- **Reduce FPS** if needed: `fps: 15` instead of 30
- **Increase timeout** for slow networks: `camera: { timeout: 20 }`

## Next Steps

1. Test with preview: `docker compose up`, wait 2-3 seconds, check `preview.jpg`
2. Adjust monitoring zone coordinates based on preview
3. Set speed thresholds appropriate for your road
4. Configure Telegram for alerts (optional)
5. Run continuously with `make docker-run`

## Support

See main README.md for additional configuration options and troubleshooting.
