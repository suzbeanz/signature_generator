import os
import logging
import re
from flask import Flask, render_template, request, url_for, send_file
from werkzeug.utils import secure_filename
from PIL import Image
from google.cloud import storage
from google.auth.exceptions import RefreshError
from google.auth import default
from google.auth import exceptions as auth_exceptions  # Import exceptions

# Set the environment variable for Google Cloud credentials
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = os.path.join(
    os.path.dirname(__file__), 'credentials', 'hoppian-signature-apparatus-363df3579c99.json'
)

credentials, project = default()
print(f"Credentials: {credentials}")
print(f"Project ID: {project}")

print(os.environ.get('GOOGLE_APPLICATION_CREDENTIALS'))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Define the upload folder and ensure it exists
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

BUCKET_NAME = os.environ.get('BUCKET_NAME', 'hoppian-signature-images')
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
        {cell_number}
        <p style="margin: 4px 0;"><strong>E </strong><a href="mailto:{email}">{email}</a></p>
        {calendar_link}
      </td>
    </tr>
  </table>
</div>
</body>
</html>
"""

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def upload_to_gcs(file_path, filename):
    """
    Uploads the processed image to Google Cloud Storage and returns the public URL.
    """
    try:
        logger.info(f"Uploading {filename} to GCS bucket {BUCKET_NAME}.")
        client = storage.Client()  # Use the authenticated client
        bucket = client.bucket(BUCKET_NAME)
        blob = bucket.blob(filename)
        blob.upload_from_filename(file_path)
        gcs_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{filename}"
        logger.info(f"File uploaded to {gcs_url}")
        return gcs_url
    except auth_exceptions.GoogleAuthError as e:
        logger.error(f"Authentication error: {e}")
        raise
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

def check_credentials():
    credentials, project = default()
    print(f"Credentials: {credentials}")
    print(f"Project ID: {project}")

check_credentials()

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
            calendar_link = request.form['calendar_link'].strip()

            # Validate cell number if provided
            cell_number = None
            if cell_number_raw:
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
            try:
                processed_headshot_url = process_image(headshot_path)
            except RefreshError as e:
                logger.error(f"Error refreshing credentials: {e}")
                return "An error occurred while refreshing credentials. Please check your credentials and try again.", 500

            # Generate signature HTML
            signature_html = template.format(
                name=name,
                title=title,
                cell_number=f"<strong>C </strong>{cell_number}" if cell_number else "",
                email=email,
                headshot_url=processed_headshot_url,
                calendar_link=f'<p style="margin: 4px 0;"><a href="{calendar_link}">Book Time with Me</a></p>' if calendar_link else ""
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

if __name__ == '__main__':
    app.run(debug=True)
