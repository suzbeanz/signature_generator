import os
import logging
import re
from flask import Flask, render_template, request, url_for, send_file
from werkzeug.utils import secure_filename
from PIL import Image
from google.cloud import storage

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Define the upload folder and ensure it exists
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Fetch BUCKET_NAME from environment variables
BUCKET_NAME = os.environ.get('BUCKET_NAME')
if not BUCKET_NAME:
    logger.error("BUCKET_NAME environment variable is not set.")
    raise EnvironmentError("BUCKET_NAME environment variable is not set.")

# Define allowed extensions for uploads
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# HTML template for the signature
template = """
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: 'Avenir', sans-serif; color: #5c5a5b; }}
        a {{ color: #DB499A; text-decoration: none; }}
    </style>
</head>
<body>
<div style="width: 600px;">
  <table cellpadding="0" cellspacing="0" style="width: 100%; border-spacing: 0;">
    <tr>
      <td style="width: 120px; vertical-align: top; padding: 0;">
        <img src="{headshot_url}" alt="{name} Headshot" style="width: 120px; height: 120px; display: block; border-radius: 0 0 45px 0;">
      </td>
      <td style="vertical-align: top; padding-left: 10px; text-align: left;">
        <p style="margin: 1px 0;"><strong>{name}</strong></p>
        <p style="margin: 4px 0;"><em>{title}</em></p>
        <p style="margin: 4px 0;"><strong>C </strong>{cell_number}</p>
        <p style="margin: 4px 0;"><strong>E </strong><a href="mailto:{email}">{email}</a></p>
      </td>
    </tr>
    <tr><td colspan="2" style="height: 10px;"></td></tr>
    <tr>
      <td colspan="2" style="padding: 0; text-align: left;">
        <a href="https://hedyandhopp.com/" style="display: inline;"><img src="https://i.imgur.com/iLpJv2j.png" alt="Hedy & Hopp" style="vertical-align: top; width: 320px; height: 82px;"></a>
        <a href="https://podcasters.spotify.com/pod/show/wearemarketinghappy" style="display: inline; margin-left: 1%;"><img src="https://i.imgur.com/tpTA5J3.png" alt="We Are, Marketing Happy Podcast" style="vertical-align: top; width: 120px; height: 80px;"></a>
      </td>
    </tr>
  </table>

</div>
</body>
</html>
"""

def allowed_file(filename):
    """Check if the uploaded file has an allowed extension."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def upload_to_gcs(file_path, filename):
    """
    Uploads the processed image to Google Cloud Storage and returns the public URL.
    """
    try:
        logger.info(f"Uploading {filename} to GCS bucket {BUCKET_NAME}.")
        client = storage.Client()
        bucket = client.bucket(BUCKET_NAME)
        blob = bucket.blob(filename)
        blob.upload_from_filename(file_path)
        # Make the blob publicly viewable (optional)
        # blob.make_public()
        gcs_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{filename}"
        logger.info(f"File uploaded to {gcs_url}")
        return gcs_url
    except Exception as e:
        logger.exception(f"Failed to upload to GCS: {e}")
        raise

def process_image(image_path):
    """
    Processes the uploaded image:
    - Resizes it to 120x120 pixels.
    - Adds a white background.
    - Saves the processed image.
    - Uploads it to GCS.
    Returns the GCS URL of the processed image.
    """
    try:
        logger.info(f"Processing image: {image_path}")
        with Image.open(image_path).convert("RGBA") as img:
            img = img.resize((120, 120), Image.Resampling.LANCZOS)
            background = Image.new('RGBA', (120, 120), (255, 255, 255, 255))
            background.paste(img, (0, 0), img)
            processed_image_path = os.path.join(app.config['UPLOAD_FOLDER'], 'processed_' + os.path.basename(image_path))
            background.save(processed_image_path, "PNG")
            logger.info(f"Image processed and saved to {processed_image_path}")
    except Exception as e:
        logger.exception(f"Failed to process image: {e}")
        raise

    try:
        gcs_url = upload_to_gcs(processed_image_path, 'processed_' + os.path.basename(image_path))
    except Exception as e:
        logger.exception(f"Failed to upload processed image: {e}")
        raise

    return gcs_url

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        try:
            logger.info("Received form submission.")
            # Retrieve and sanitize form data
            name = request.form['name'].strip().upper()
            title = request.form['title'].strip().title()
            cell_number_raw = request.form['cell_number'].strip()
            email = request.form['email'].strip()

            # Validate cell number
            cell_number_digits = re.sub(r'\D', '', cell_number_raw)
            if len(cell_number_digits) != 10:
                logger.error("Invalid cell number format.")
                return "Invalid cell number format. Please enter a 10-digit number.", 400
            cell_number = f"({cell_number_digits[:3]}) {cell_number_digits[3:6]}-{cell_number_digits[6:]}"

            # Validate email (basic validation)
            if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
                logger.error("Invalid email format.")
                return "Invalid email format. Please enter a valid email address.", 400

            # Handle headshot upload
            if 'headshot' not in request.files:
                logger.error("No headshot part in the request.")
                return "No headshot part in the request.", 400
            headshot = request.files['headshot']
            if headshot.filename == '':
                logger.error("No selected file for headshot.")
                return "No selected file for headshot.", 400
            if not allowed_file(headshot.filename):
                logger.error("Unsupported file extension for headshot.")
                return "Unsupported file type. Please upload a PNG, JPG, JPEG, or GIF image.", 400

            # Secure the filename and save the headshot
            headshot_filename = secure_filename(headshot.filename)
            headshot_path = os.path.join(app.config['UPLOAD_FOLDER'], headshot_filename)
            headshot.save(headshot_path)
            logger.info(f"Headshot saved to {headshot_path}")

            # Process the image and upload to GCS
            processed_headshot_url = process_image(headshot_path)

            # Generate signature HTML
            signature_html = template.format(
                name=name,
                title=title,
                cell_number=cell_number,
                email=email,
                headshot_url=processed_headshot_url
            )

            # Save the signature HTML to the uploads directory
            signature_filename = f"signature_{name.lower().replace(' ', '_')}.html"
            signature_filepath = os.path.join(app.config['UPLOAD_FOLDER'], signature_filename)
            with open(signature_filepath, 'w') as f:
                f.write(signature_html)
            logger.info(f"Signature HTML saved to {signature_filepath}")

            return render_template('index.html', signature=signature_html, download_link=url_for('download_file', filename=signature_filename))
        except Exception as e:
            logger.exception(f"Error processing form submission: {e}")
            return f"An error occurred: {e}", 500

    return render_template('index.html')

@app.route('/download/<filename>')
def download_file(filename):
    try:
        logger.info(f"Processing download for file: {filename}")
        return send_file(os.path.join(app.config['UPLOAD_FOLDER'], filename), as_attachment=True)
    except Exception as e:
        logger.exception(f"Error sending file {filename}: {e}")
        return f"An error occurred: {e}", 500
