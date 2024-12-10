import os
import logging
import re
from flask import Flask, render_template, request, url_for, send_file, redirect, send_from_directory
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
        body {{ font-family: 'Avenir', sans-serif; color: #5c5a5b; background-image: url('{background_url}'); }}
        a {{ color: #DB499A; text-decoration: none; }}
        .banner-container {{
            text-align: left;
            margin-top: 20px;
        }}
        .banner-container a {{
            display: inline;
            margin-right: 10px;
            vertical-align: top;
        }}
        .banner-container img {{
            vertical-align: top;
        }}
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
  <div class="banner-container">
    <a href="https://hedyandhopp.com/" style="display: inline;">
      <img src="{logo_url}" alt="Hedy & Hopp Banner" style="vertical-align: top; width: auto; height: 85px;">
    </a>
    <a href="https://podcasters.spotify.com/pod/show/wearemarketinghappy" style="display: inline; margin-left: 1%;">
      <img src="{podcast_logo_url}" alt="We Are, Marketing Happy Podcast" style="vertical-align: top; width: 82px; height: 80px;">
    </a>
  </div>
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
    output_path = os.path.join(app.config['UPLOAD_FOLDER'], 'processed_' + os.path.basename(image_path))
    with Image.open(image_path) as img:
        img = img.convert('RGB')  # Ensure image is in RGB format
        img = img.resize((120, 120))  # Resize to desired dimensions
        img.save(output_path, 'JPEG', quality=85)
    return output_path

def check_credentials():
    credentials, project = default()
    print(f"Credentials: {credentials}")
    print(f"Project ID: {project}")

check_credentials()

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        try:
            # Get form data
            name = request.form.get('name', '')
            title = request.form.get('title', '')
            cell_number = request.form.get('cell_number', '')
            email = request.form.get('email', '')
            calendar_link = request.form.get('calendar_link', '')
            headshot = request.files.get('headshot')

            # Process the headshot image
            if headshot and allowed_file(headshot.filename):
                # Save the uploaded image temporarily
                filename = secure_filename(headshot.filename)
                temp_image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                headshot.save(temp_image_path)

                # Resize the image
                processed_image_path = process_image(temp_image_path)

                # Upload the image to GCS or use local path
                # If you're using GCS:
                # headshot_url = upload_to_gcs(processed_image_path, filename)
                # If not using GCS, use local path:
                headshot_url = url_for('static', filename=f'uploads/{os.path.basename(processed_image_path)}')

                # Remove the temporary file if needed
                # os.remove(temp_image_path)
                # os.remove(processed_image_path)

            else:
                error_message = "Invalid or missing headshot image."
                return render_template(
                    'index.html',
                    name=name,
                    title=title,
                    cell_number=cell_number,
                    email=email,
                    calendar_link=calendar_link,
                    error_message=error_message
                )

            # **Define logo_url here**
            logo_url = url_for('static', filename='company_banner.png')
            podcast_logo_url = url_for('static', filename='pod.png')
            background_url = url_for('static', filename='background.png')

            # Generate the signature HTML
            signature_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{ font-family: 'Avenir', sans-serif; color: #5c5a5b; background-image: url('{background_url}'); }}
                    a {{ color: #DB499A; text-decoration: none; }}
                    .banner-container {{
                        text-align: left;
                        margin-top: 20px;
                    }}
                    .banner-container a {{
                        display: inline;
                        margin-right: 10px;
                        vertical-align: top;
                    }}
                    .banner-container img {{
                        vertical-align: top;
                    }}
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
                    <p style="margin: 1px 0;"><strong>{name.upper()}</strong></p>
                    <p style="margin: 4px 0;"><em>{title}</em></p>
                    {f'<p style="margin: 4px 0;"><strong>C </strong>{cell_number}</p>' if cell_number else ''}
                    <p style="margin: 4px 0;"><strong>E </strong><a href="mailto:{email}">{email}</a></p>
                    {f'<p style="margin: 4px 0;"><a href="{calendar_link}">Book Time with Me</a></p>' if calendar_link else ''}
                  </td>
                </tr>
              </table>
              <div class="banner-container">
                <a href="https://hedyandhopp.com/" style="display: inline;">
                  <img src="{logo_url}" alt="Hedy & Hopp Banner" style="vertical-align: top; width: 320px; height: 82px;">
                </a>
                <a href="https://podcasters.spotify.com/pod/show/wearemarketinghappy" style="display: inline; margin-left: 1%;">
                  <img src="{podcast_logo_url}" alt="We Are, Marketing Happy Podcast" style="vertical-align: top; width: 120px; height: 80px;">
                </a>
              </div>
            </div>
            </body>
            </html>
            """

            # Save the signature HTML to a file
            signature_filename = f"signature_{secure_filename(name.lower().replace(' ', '_'))}.html"
            signature_file_path = os.path.join(app.config['UPLOAD_FOLDER'], signature_filename)
            with open(signature_file_path, 'w') as f:
                f.write(signature_html)

            # Provide the signature and download link to the template
            return render_template(
                'index.html',
                signature=signature_html,
                download_link=url_for('download_file', filename=signature_filename),
                name=name,
                title=title,
                cell_number=cell_number,
                email=email,
                calendar_link=calendar_link
            )

        except Exception as e:
            logger.exception(f"Error processing form submission: {e}")
            error_message = f"An error occurred: {e}"
            return render_template(
                'index.html',
                error_message=error_message,
                name=request.form.get('name', ''),
                title=request.form.get('title', ''),
                cell_number=request.form.get('cell_number', ''),
                email=request.form.get('email', ''),
                calendar_link=request.form.get('calendar_link', '')
            ), 500
    else:
        return render_template('index.html')

@app.route('/download/<filename>')
def download_file(filename):
    try:
        logger.info(f"Processing download for file: {filename}")
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)
    except Exception as e:
        logger.exception(f"Error sending file {filename}: {e}")
        return f"An error occurred: {e}", 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
