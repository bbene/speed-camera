# speed-camera v4.0
"""
Script to capture moving car speed

Usage:
    speed-camera.py [preview] [--config=<file>]

Options:
    -h --help     Show this screen.
"""

# import the necessary packages
from docopt import docopt
from pathlib import Path
from datetime import datetime, timezone, timedelta
import cv2
import numpy as np
import logging
import time
import math
import json
import yaml
import shutil
import subprocess
from PIL import Image
from threading import Thread
from camera import create_camera
from flask import Flask, render_template, jsonify, request, send_file, redirect
from io import BytesIO
from models import Detection
from database import init_database, get_database
import os

# Location for files/logs
FILENAME_SERVICE = "logs/service.log"

# Global database connection
db = None

# Important constants
MIN_SAVE_BUFFER = 2
THRESHOLD = 25
BLURSIZE = (15,15)

# the following enumerated values are used to make the program more readable
WAITING = 0
TRACKING = 1
SAVING = 2
UNKNOWN = 0
LEFT_TO_RIGHT = 1
RIGHT_TO_LEFT = 2

class Config:
    # monitoring area
    upper_left_x = 0
    upper_left_y = 0
    lower_right_x = 1024
    lower_right_y = 576
    # range
    l2r_distance = 65         # <---- distance-to-road in feet (left-to-right side)
    r2l_distance = 80         # <---- distance-to-road in feet (right-to-left side)
    # camera settings
    fov = 62.2                # <---- field of view
    fps = 30                  # <---- frames per second
    image_width = 1024        # <---- resolution width
    image_height = 576        # <---- resolution height
    image_min_area = 500      # <---- minimum area for detecting motion
    camera_vflip = False      # <---- flip camera vertically
    camera_hflip = False      # <---- flip camera horizontally
    # thresholds for recording
    min_distance = 0.4        # <---- minimum distance between cars
    min_speed = 10            # <---- minimum speed for recording events
    min_speed_alert = 30      # <---- minimum speed for sending an alert
    min_area = 2000           # <---- minimum area for recording events
    min_confidence = 70       # <---- minimum percentage confidence for recording events
    min_confidence_alert = 90 # <---- minimum percentage confidence for saving images
    # communication
    telegram_token = ""       # <---- bot token to authenticate with Telegram
    telegram_chat_id = ""     # <---- person/group `chat_id` to send the alert to
    telegram_frequency = 6    # <---- hours between periodic text updates
    # web interface preview
    preview_enabled = True    # <---- enable continuous preview updates
    preview_frame_skip = 5    # <---- save preview every N frames (prevents excessive I/O)
    # camera configuration
    camera = {}               # <---- camera type and settings

    @staticmethod
    def load(config_file):
        cfg = Config()
        with open(config_file, 'r') as stream:
            try:
                data = yaml.safe_load(stream)

                for key, value in data.items():
                    setattr(cfg, key, value)

            except yaml.YAMLError as exc:
                logging.error("Failed to load config: {}".format(exc))
                exit(1)

        # Swap positions
        if cfg.upper_left_x > cfg.lower_right_x:
            cfg.upper_left_x = cfg.lower_right_x
            cfg.lower_right_x = cfg.upper_left_x

        if cfg.upper_left_y > cfg.lower_right_y:
            cfg.upper_left_y = cfg.lower_right_y
            cfg.lower_right_y = cfg.upper_left_y

        cfg.upper_left = (cfg.upper_left_x, cfg.upper_left_y)
        cfg.lower_right = (cfg.lower_right_x, cfg.lower_right_y)

        cfg.monitored_width = cfg.lower_right_x - cfg.upper_left_x
        cfg.monitored_height = cfg.lower_right_y - cfg.upper_left_y

        cfg.resolution = [cfg.image_width, cfg.image_height]

        return cfg

class Recorder:
    min_speed = 10            # <---- minimum speed for recording events
    min_speed_alert = 30      # <---- minimum speed for sending an alert
    min_area = 2000           # <---- minimum area for recording events
    min_confidence = 70       # <---- minimum percentage confidence for recording events
    min_confidence_alert = 70 # <---- minimum percentage confidence for saving images

    def __init__(self, cfg):
        for key, value in cfg.__dict__.items():
            if hasattr(self, key):
                setattr(self, key, value)

    def send_animation(self, timestamp, events, confidence, mph):
        # Validate events list
        if not events:
            logging.warning("send_animation called with empty events list")
            return

        folder = "logs/{}-{:02.0f}mph-{:.0f}".format(timestamp.strftime('%Y-%m-%d_%H:%M:%S.%f'), mph, confidence)
        gif_file = "{}.gif".format(folder)
        json_file = "{}.json".format(folder)

        # Create the directory
        Path(folder).mkdir(parents=True, exist_ok=True)

        logging.info(f"Creating GIF for {len(events)} frames at {mph:.1f} mph ({confidence:.0f}% confidence)")

        data = []
        for i, e in enumerate(events):
            # annotate it
            image = annotate_image(e['image'], e['ts'], mph=e['mph'], confidence=confidence, x=e['x'], y=e['y'], w=e['w'], h=e['h'])

            # and save the image to disk with a safe filename
            cv2.imwrite("{}/{:04d}.jpg".format(folder, i), image)

            del(e['image'])
            e['ts'] = e['ts'].timestamp()
            data.append(e)

        with open(json_file, 'w') as outfile:
            json.dump(data, outfile)

        # Create a GIF from the saved images using PIL
        gif_data = None
        try:
            images = []
            for i in range(len(events)):
                frame_path = f"{folder}/{i:04d}.jpg"
                if Path(frame_path).exists():
                    try:
                        img = Image.open(frame_path)
                        images.append(img)
                    except Exception as e:
                        logging.error(f"Failed to open frame {i}: {frame_path} - {e}")
                else:
                    logging.warning(f"Frame {i} not found: {frame_path}")

            logging.info(f"Loaded {len(images)} frames out of {len(events)} expected")

            if images:
                # Save as GIF with 100ms per frame
                try:
                    images[0].save(
                        gif_file,
                        format='GIF',
                        save_all=True,
                        append_images=images[1:],
                        duration=100,
                        loop=0
                    )
                    logging.info(f"GIF created successfully: {gif_file} ({len(images)} frames)")

                    # Read GIF data into memory
                    with open(gif_file, 'rb') as f:
                        gif_data = f.read()
                    logging.info(f"GIF data read successfully: {len(gif_data)} bytes")
                except Exception as e:
                    logging.error(f"Failed to save GIF: {e}")
            else:
                logging.warning(f"No frames found to create GIF in {folder}")
        except Exception as e:
            logging.error(f"Failed to create GIF: {e}")

        # Remove the temporary files
        shutil.rmtree(folder, ignore_errors=True)
        if Path(gif_file).exists():
            os.remove(gif_file)

        # Store GIF in database
        try:
            detection = Detection(
                timestamp=timestamp,
                speed_mph=mph,
                confidence=confidence,
                gif_data=gif_data
            )
            db.add_detection(detection)
            gif_status = "with GIF" if gif_data else "without GIF"
            logging.info(f"Stored alert to database: {mph:.1f} mph @ {confidence:.0f}% {gif_status}")
        except Exception as e:
            logging.error(f"Failed to store alert to database: {e}")

        return gif_file

    def record(self, confidence, image, timestamp, mean_speed, avg_area, sd_speed, sd_area, speeds, secs, direction, events):
        if confidence < self.min_confidence or mean_speed < self.min_speed or avg_area < self.min_area:
            return False

        # Store detection to database
        try:
            detection = Detection(
                timestamp=timestamp,
                speed_mph=mean_speed,
                speed_deviation=sd_speed,
                area=int(avg_area),
                area_deviation=sd_area,
                frames=len(speeds),
                seconds=secs,
                direction=str_direction(direction),
                confidence=confidence
            )
            db.add_detection(detection)
        except Exception as e:
            logging.error(f"Failed to record detection: {e}")
            return False

        # If the threshold is high enough, alert and write to disk
        if confidence >= self.min_confidence_alert and mean_speed >= self.min_speed_alert:
            thread = Thread(target=self.send_animation, args=(timestamp, events, confidence, mean_speed,), daemon=True)
            thread.start()

        return True

# calculate speed from pixels and time
def get_speed(pixels, ftperpixel, secs):
    if secs > 0.0:
        return ((pixels * ftperpixel)/ secs) * 0.681818
    else:
        return 0.0

# calculate pixel width
def get_pixel_width(fov, distance, image_width):
    frame_width_ft = 2 * (math.tan(math.radians(fov * 0.5)) * distance)
    ft_per_pixel = frame_width_ft / float(image_width)

    return ft_per_pixel

def str_direction(direction):
    if direction == LEFT_TO_RIGHT:
        return "LTR"
    elif direction == RIGHT_TO_LEFT:
        return "RTL"
    else:
        return "???"

# calculate elapsed seconds
def secs_diff(endTime, begTime):
    diff = (endTime - begTime).total_seconds()
    return diff

def parse_command_line():
    preview = False
    config_file = None

    logging.info("Initializing")
    args = docopt(__doc__)

    if args['preview']:
        preview=True

    if args['--config']:
        config_file = Path(args['--config'])
        if not config_file.is_file():
            logging.error("config file does NOT exist")
            exit(1)

    return (preview, config_file)

def detect_motion(image, min_area):
    # dilate the thresholded image to fill in any holes, then find contours
    # on thresholded image
    image = cv2.dilate(image, None, iterations=2)
    cnts, _ = cv2.findContours(image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # look for motion
    motion_found = False
    biggest_area = 0
    x = 0
    y = 0
    w = 0
    h = 0

    # examine the contours, looking for the largest one
    for c in cnts:
        (x1, y1, w1, h1) = cv2.boundingRect(c)
        # get an approximate area of the contour
        found_area = w1 * h1
        # find the largest bounding rectangle
        if (found_area > min_area) and (found_area > biggest_area):
            biggest_area = found_area
            motion_found = True
            x = x1
            y = y1
            w = w1
            h = h1

    return (motion_found, x, y, w, h, biggest_area)

def annotate_image(image, timestamp, mph=0, confidence=0, h=0, w=0, x=0, y=0):
    global cfg

    # colors
    color_green = (0, 255, 0)
    color_red = (0, 0, 255)

    # make it gray
    image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)

    # timestamp the image
    cv2.putText(image, timestamp.strftime("%d %B %Y %H:%M:%S.%f"),
                (10, image.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 1, color_red, 2)

    # write the speed
    if mph > 0:
        msg = "{:.0f} mph".format(mph)
        (size, _) = cv2.getTextSize(msg, cv2.FONT_HERSHEY_SIMPLEX, 2, 3)

        # then center it horizontally on the image
        cntr_x = int((cfg.image_width - size[0]) / 2)
        cv2.putText(image, msg, (cntr_x, int(cfg.image_height * 0.2)), cv2.FONT_HERSHEY_SIMPLEX, 2.00, color_red, 3)

    # write the confidence
    if confidence > 0:
        msg = "{:.0f}%".format(confidence)
        (size, _) = cv2.getTextSize(msg, cv2.FONT_HERSHEY_SIMPLEX, 2, 3)

        # then right align it horizontally on the image
        cntr_x = int((cfg.image_width - size[0]) / 4) * 3
        cv2.putText(image, msg, (cntr_x, int(cfg.image_height * 0.2)), cv2.FONT_HERSHEY_SIMPLEX, 1.00, color_red, 3)

    # define the monitored area right and left boundary
    cv2.line(image, (cfg.upper_left_x, cfg.upper_left_y),
                (cfg.upper_left_x, cfg.lower_right_y), color_green, 4)
    cv2.line(image, (cfg.lower_right_x, cfg.upper_left_y),
                (cfg.lower_right_x, cfg.lower_right_y), color_green, 4)

    # Add the boundary
    if h > 0 and w > 0:
        cv2.rectangle(image,
            (cfg.upper_left_x + x, cfg.upper_left_y + y),
            (cfg.upper_left_x + x + w, cfg.upper_left_y + y + h), color_green, 2)

    return image

# Setup logging
Path("logs").mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(message)s',
    handlers=[
        logging.FileHandler(FILENAME_SERVICE),
        logging.StreamHandler()
    ]
)

# parse command-line
(PREVIEW, config_file) = parse_command_line()

# load config
cfg = Config.load(config_file)

# initialize camera (with automatic type detection)
camera = create_camera(cfg)
camera.start()

# determine the boundary
logging.info("Monitoring: ({},{}) to ({},{}) = {}x{} space".format(
    cfg.upper_left_x, cfg.upper_left_y, cfg.lower_right_x, cfg.lower_right_y, cfg.monitored_width, cfg.monitored_height))

# initialize messaging
recorder = Recorder(cfg)

# Initialize database
db = init_database()
logging.info("Database initialized")

# Initialize Flask app
app = Flask(__name__, template_folder='templates', static_folder='static')

# Flask Routes
@app.route('/')
def index():
    return redirect('/dashboard')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/preview')
def preview():
    return render_template('preview.html')

# Flask API Routes
@app.route('/api/stats')
def api_stats():
    """Get detection statistics for a date range"""
    from sqlalchemy import func

    # Get query parameters
    date_from = request.args.get('from')
    date_to = request.args.get('to')

    try:
        if date_from:
            date_from = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
        else:
            date_from = datetime.now(timezone.utc) - timedelta(days=7)

        if date_to:
            date_to = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
        else:
            date_to = datetime.now(timezone.utc)

        session = db.get_session()

        # Total count
        total = session.query(func.count(Detection.id)).filter(
            Detection.timestamp >= date_from,
            Detection.timestamp <= date_to
        ).scalar() or 0

        # Average speeds by direction
        l2r_avg = session.query(func.avg(Detection.speed_mph)).filter(
            Detection.direction == 'LTR',
            Detection.timestamp >= date_from,
            Detection.timestamp <= date_to
        ).scalar() or 0

        r2l_avg = session.query(func.avg(Detection.speed_mph)).filter(
            Detection.direction == 'RTL',
            Detection.timestamp >= date_from,
            Detection.timestamp <= date_to
        ).scalar() or 0

        # Speed distribution (histogram bins)
        detections = session.query(Detection.speed_mph).filter(
            Detection.timestamp >= date_from,
            Detection.timestamp <= date_to
        ).all()

        speeds = [d[0] for d in detections]
        bins = [0, 10, 20, 30, 40, 50, 60]
        distribution = {}
        for i in range(len(bins)-1):
            count = sum(1 for s in speeds if bins[i] <= s < bins[i+1])
            distribution[f'{bins[i]}-{bins[i+1]}'] = count
        distribution['60+'] = sum(1 for s in speeds if s >= 60)

        # Peak hours
        peak_hours = {}
        for i in range(24):
            count = session.query(func.count(Detection.id)).filter(
                func.extract('hour', Detection.timestamp) == i,
                Detection.timestamp >= date_from,
                Detection.timestamp <= date_to
            ).scalar() or 0
            peak_hours[str(i)] = count

        session.close()

        return jsonify({
            'total': total,
            'l2r_avg': round(l2r_avg, 1) if l2r_avg else 0,
            'r2l_avg': round(r2l_avg, 1) if r2l_avg else 0,
            'distribution': distribution,
            'peak_hours': peak_hours
        })
    except Exception as e:
        logging.error(f"Error in api_stats: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/detections')
def api_detections():
    """Get paginated list of detections"""
    from sqlalchemy import desc

    # Get query parameters
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 25, type=int)
    date_from = request.args.get('from')
    date_to = request.args.get('to')
    speed_min = request.args.get('speed_min', 0, type=float)
    speed_max = request.args.get('speed_max', 200, type=float)
    direction = request.args.get('direction')  # 'LTR', 'RTL', or None for all

    try:
        if date_from:
            date_from = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
        else:
            date_from = datetime.now(timezone.utc) - timedelta(days=7)

        if date_to:
            date_to = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
        else:
            date_to = datetime.now(timezone.utc)

        session = db.get_session()

        query = session.query(Detection).filter(
            Detection.timestamp >= date_from,
            Detection.timestamp <= date_to,
            Detection.speed_mph >= speed_min,
            Detection.speed_mph <= speed_max
        )

        if direction:
            query = query.filter(Detection.direction == direction)

        # Order by timestamp descending
        query = query.order_by(desc(Detection.timestamp))

        # Paginate
        total = query.count()
        detections = query.offset((page-1) * per_page).limit(per_page).all()

        session.close()

        return jsonify({
            'total': total,
            'page': page,
            'per_page': per_page,
            'detections': [d.to_dict() for d in detections]
        })
    except Exception as e:
        logging.error(f"Error in api_detections: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/gif/<int:detection_id>')
def api_gif(detection_id):
    """Serve GIF for a specific detection"""
    try:
        session = db.get_session()
        detection = session.query(Detection).filter(Detection.id == detection_id).first()
        session.close()

        if not detection or not detection.gif_data:
            return 'GIF not found', 404

        return send_file(
            BytesIO(detection.gif_data),
            mimetype='image/gif',
            as_attachment=False,
            download_name=f'detection_{detection_id}.gif'
        )
    except Exception as e:
        logging.error(f"Error serving GIF: {e}")
        return 'Error serving GIF', 500

@app.route('/api/preview')
def api_preview():
    """Serve the live preview image with cache-busting support"""
    try:
        with open('data/preview.jpg', 'rb') as f:
            image_data = f.read()
        response = send_file(
            BytesIO(image_data),
            mimetype='image/jpeg',
            as_attachment=False
        )
        # Disable caching to ensure fresh image
        response.cache_control.max_age = 0
        response.cache_control.no_cache = True
        response.cache_control.no_store = True
        return response
    except FileNotFoundError:
        return jsonify({'error': 'Preview not available'}), 404
    except Exception as e:
        logging.error(f"Error serving preview: {e}")
        return jsonify({'error': 'Error serving preview'}), 500

def run_flask():
    """Run Flask app in a separate thread"""
    port = int(os.environ.get('FLASK_PORT', 5000))
    logging.info(f"Starting Flask web server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# Start Flask in a background thread
flask_thread = Thread(target=run_flask, daemon=False)
flask_thread.start()

logging.info("Web interface started on http://0.0.0.0:5000")

# calculate the the width of the image at the distance specified
l2r_ft_per_pixel = get_pixel_width(cfg.fov, cfg.l2r_distance, cfg.image_width)
r2l_ft_per_pixel = get_pixel_width(cfg.fov, cfg.r2l_distance, cfg.image_width)
logging.info("L2R: {:.0f}ft from camera == {:.2f} per pixel".format(cfg.l2r_distance, l2r_ft_per_pixel))
logging.info("R2L: {:.0f}ft from camera == {:.2f} per pixel".format(cfg.r2l_distance, r2l_ft_per_pixel))

state = WAITING
direction = UNKNOWN
# location
initial_x = 0
initial_w = 0
last_x = 0
last_w = 0
biggest_area = 0
areas = np.array([])
# timing
initial_time = datetime.now(timezone.utc)
cap_time = datetime.now(timezone.utc)
timestamp = datetime.now(timezone.utc)
# speeds
sd = 0
speeds = np.array([])
counter = 0
# event captures
events = []
# fps
fps_time = datetime.now(timezone.utc)
fps_frames = 0
# capture
base_image = None
# stats
stats_l2r = np.array([])
stats_r2l = np.array([])
stats_time = datetime.now(timezone.utc)
# startup
has_started = False
# preview frame counter
frame_counter = 0

# capture frames from the camera (using capture_continuous.
#   This keeps the picamera in capture mode - it doesn't need
#   to prep for each frame's capture.
#
# capture frames from the camera
#
try:
    while True:
        # initialize the timestamp
        timestamp = datetime.now(timezone.utc)

        # Get the frame from camera first
        image = camera.get_frame()

        # Save a preview of the image (continuously if enabled)
        if cfg.preview_enabled and frame_counter % cfg.preview_frame_skip == 0:
            preview_image = annotate_image(image, timestamp)
            cv2.imwrite("data/preview.jpg", preview_image)

        # Mark startup for legacy compatibility
        if not has_started:
            has_started = True

        if PREVIEW:
            camera.stop()
            exit(0)

        # Increment frame counter
        frame_counter += 1

        # Log the current FPS
        fps_frames += 1
        if fps_frames > 1000:
            elapsed = secs_diff(timestamp, fps_time)
            logging.info("Current FPS @ {:.0f}".format(fps_frames/elapsed))
            fps_time = timestamp
            fps_frames = 0

        # Share stats every X hours
        if secs_diff(timestamp, stats_time) > cfg.telegram_frequency * 60 * 60:
            stats_time = timestamp
            total = len(stats_l2r) + len(stats_r2l)
            if total > 0:
                l2r_perc = len(stats_l2r) / total * 100
                r2l_perc = len(stats_r2l) / total * 100

                l2r_mean = 0
                r2l_mean = 0
                if len(stats_l2r) > 0:
                    l2r_mean = np.mean(stats_l2r)
                if len(stats_r2l) > 0:
                    r2l_mean = np.mean(stats_r2l)

                # Log periodic statistics (Telegram support removed)
                logging.info(
                    "Stats: {:.0f} cars in the past {:.0f} hours | L2R {:.0f}% at {:.0f} mph | R2L {:.0f}% at {:.0f} mph".format(
                        total, cfg.telegram_frequency, l2r_perc, l2r_mean, r2l_perc, r2l_mean
                    )
                )

            # clear stats
            stats_l2r = np.array([])
            stats_r2l = np.array([])
            stats_time = timestamp

        # crop area defined by [y1:y2,x1:x2]
        gray = image[
            cfg.upper_left_y:cfg.lower_right_y,
            cfg.upper_left_x:cfg.lower_right_x
        ]

        # convert the fram to grayscale, and blur it
        gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, BLURSIZE, 0)

        # if the base image has not been defined, initialize it
        if base_image is None:
            base_image = gray.copy().astype("float")
            lastTime = timestamp
            continue

        #  compute the absolute difference between the current image and
        # base image and then turn eveything lighter gray than THRESHOLD into
        # white
        frameDelta = cv2.absdiff(gray, cv2.convertScaleAbs(base_image))
        thresh = cv2.threshold(frameDelta, THRESHOLD, 255, cv2.THRESH_BINARY)[1]

        # look for motion in the image
        (motion_found, x, y, w, h, biggest_area) = detect_motion(thresh, cfg.image_min_area)

        if motion_found:
            if state == WAITING:
                # intialize tracking
                state = TRACKING
                initial_x = x
                initial_w = w
                last_x = x
                last_w = w
                initial_time = timestamp

                last_mph = 0

                # initialise array for storing speeds & standard deviation
                areas = np.array([])
                speeds = np.array([])

                # event capturing
                events = []

                # detect gap and data points
                car_gap = secs_diff(initial_time, cap_time)

                logging.info('Tracking')
                logging.info("Initial Data: x={:.0f} w={:.0f} area={:.0f} gap={}".format(initial_x, initial_w, biggest_area, car_gap))
                logging.info(" x-Δ     Secs      MPH  x-pos width area dir")

                # if gap between cars too low then probably seeing tail lights of current car
                # but I might need to tweek this if find I'm not catching fast cars
                if (car_gap < cfg.min_distance):
                    state = WAITING
                    direction = UNKNOWN
                    motion_found = False
                    biggest_area = 0
                    base_image = None
                    logging.info("Car too close, skipping")
                    continue
            else:
                # compute the lapsed time
                secs = secs_diff(timestamp, initial_time)

                # timeout after 5 seconds of inactivity
                if secs >= 5:
                    state = WAITING
                    direction = UNKNOWN
                    motion_found = False
                    biggest_area = 0
                    base_image = None
                    logging.info('Resetting')
                    continue

                if state == TRACKING:
                    abs_chg = 0
                    mph = 0
                    distance = 0
                    if x >= last_x:
                        direction = LEFT_TO_RIGHT
                        distance = cfg.l2r_distance
                        abs_chg = (x + w) - (initial_x + initial_w)
                        mph = get_speed(abs_chg, l2r_ft_per_pixel, secs)
                    else:
                        direction = RIGHT_TO_LEFT
                        distance = cfg.r2l_distance
                        abs_chg = initial_x - x
                        mph = get_speed(abs_chg, r2l_ft_per_pixel, secs)

                    speeds = np.append(speeds, mph)
                    areas = np.append(areas, biggest_area)

                    # Store event data
                    events.append({
                        'image': image.copy(),
                        'ts': timestamp,
                        # Location of object
                        'x': x,
                        'y': y,
                        'w': w,
                        'h': h,
                        # Speed
                        'mph': mph,
                        # MPH is calculated from secs, delta, fov, distance, image_width
                        'fov': cfg.fov,
                        'image_width': cfg.image_width,
                        'distance': distance,
                        'secs': secs,
                        'delta': abs_chg,
                        # Other useful data
                        'area': biggest_area,
                        'dir': str_direction(direction),
                    })

                    # If we've stopped or are going backward, reset.
                    if mph <= 0:
                        logging.info("negative speed - stopping tracking")
                        # Don't change direction, just mark for save
                        if direction == LEFT_TO_RIGHT:
                            x = 1 # Force save
                        else:
                            x = cfg.monitored_width + MIN_SAVE_BUFFER  # Force save

                    logging.info("{0:4d}  {1:7.2f}  {2:7.0f}   {3:4d}  {4:4d} {5:4d} {6:s}".format(
                        abs_chg, secs, mph, x, w, biggest_area, str_direction(direction)))

                    # is front of object outside the monitired boundary? Then write date, time and speed on image
                    # and save it
                    if ((x <= MIN_SAVE_BUFFER) and (direction == RIGHT_TO_LEFT)) \
                            or ((x+w >= cfg.monitored_width - MIN_SAVE_BUFFER)
                            and (direction == LEFT_TO_RIGHT)):
                        sd_speed = 0
                        sd_area = 0
                        confidence = 0
                        #you need at least 3 data points to calculate a mean and we're deleting two
                        if (len(speeds) > 3):
                            # Mean of all items except the first and last one
                            mean_speed = float(np.mean(speeds[1:-1]))
                            # Mode of area (except the first and last)
                            avg_area = float(np.average(areas[1:-1]))
                            # SD of all items except the last one
                            sd_speed = float(np.std(speeds[:-1]))
                            sd_area = float(np.std(areas[1:-1]))
                            confidence = float(((mean_speed - sd_speed) / mean_speed) * 100)
                        elif (len(speeds) > 1):
                            # use the last element in the array
                            mean_speed = float(speeds[-1])
                            avg_area = float(areas[-1])
                            # Set it to a very high value to highlight it's not to be trusted.
                            sd_speed = 99
                            sd_area = 99999
                        else:
                            mean_speed = 0  # ignore it
                            avg_area = 0
                            sd_speed = 0
                            sd_area = 0

                        logging.info("Determined area:   avg={:4.0f} deviation={:4.0f} frames={:0d}".format(avg_area, sd_area, len(areas)))
                        logging.info("Determined speed: mean={:4.0f} deviation={:4.0f} frames={:0d}".format(mean_speed, sd_speed, len(speeds)))
                        logging.info("Overall Confidence Level {:.0f}%".format(confidence))

                        # If they are speeding, record the event and image
                        recorded = recorder.record(
                            image=image,
                            timestamp=timestamp,
                            confidence=confidence,
                            mean_speed=mean_speed,
                            avg_area=avg_area,
                            sd_speed=sd_speed,
                            sd_area=sd_area,
                            speeds=speeds,
                            secs=secs,
                            direction=direction,
                            events=events
                        )
                        if recorded:
                            logging.info("Event recorded")
                            if direction == LEFT_TO_RIGHT :
                                stats_l2r = np.append(stats_l2r, mean_speed)
                            elif direction == RIGHT_TO_LEFT:
                                stats_r2l = np.append(stats_r2l, mean_speed)
                        else:
                            logging.info("Event not recorded: Speed, Area, or Confidence too low")

                        state = SAVING
                        cap_time = timestamp
                    # if the object hasn't reached the end of the monitored area, just remember the speed
                    # and its last position
                    last_mph = mph
                    last_x = x
        else:
            if state != WAITING:
                state = WAITING
                direction = UNKNOWN
                logging.info('Resetting')

        # Adjust the base_image as lighting changes through the day
        if state == WAITING:
            last_x = 0
            cv2.accumulateWeighted(gray, base_image, 0.25)

        # clear the stream in preparation for the next frame


except KeyboardInterrupt:
    logging.info("Interrupted by user")
except Exception as e:
    logging.error(f"Error in main loop: {e}")
finally:
    # cleanup the camera and close any open windows
    camera.stop()
    cv2.destroyAllWindows()
