import os
import logging
import re
from flask import Flask, render_template, request, url_for, send_file, redirect, send_from_directory
from werkzeug.utils import secure_filename
from PIL import Image
from google.cloud import storage
import google.auth
from google.auth.exceptions import RefreshError
from google.auth import default
from google.auth import exceptions as auth_exceptions 
from urllib.parse import quote

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = os.path.join(
    os.path.dirname(__file__), 'credentials', 'hoppian-signature-apparatus-363df3579c99.json'
)

BUCKET_NAME = 'hoppian-signature-images'

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

BUCKET_NAME = os.environ.get('BUCKET_NAME', 'hoppian-signature-images')
if not BUCKET_NAME:
    logger.error("BUCKET_NAME environment variable is not set.")
    raise EnvironmentError("BUCKET_NAME environment variable is not set.")

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

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

def upload_to_gcs(source_file_name, destination_blob_name):
    """Uploads a file to GCS bucket and returns the public URL."""
    storage_client = storage.Client()
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(destination_blob_name)

    logging.info(f"Uploading {source_file_name} to GCS bucket {BUCKET_NAME} as {destination_blob_name}")
    logging.info(f"Uploading file to GCS: {source_file_name} as {destination_blob_name}")

    blob.upload_from_filename(source_file_name)

    # Do not attempt to make the blob public or access its ACL.

    # URL-encode the blob name in the public URL
    encoded_blob_name = quote(destination_blob_name, safe='')

    public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{encoded_blob_name}"

    logging.info(f"Public URL: {public_url}")
    logging.info(f"Generated public URL: {public_url}")

    return public_url

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

            if headshot and allowed_file(headshot.filename):
                filename = secure_filename(headshot.filename)
                temp_image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                headshot.save(temp_image_path)

                processed_image_path = process_image(temp_image_path)

                destination_blob_name = f"headshots/{os.path.basename(processed_image_path)}"
                try:
                    # Attempt to upload and get the public URL
                    headshot_url = upload_to_gcs(processed_image_path, destination_blob_name)
                except Exception as e:
                    logging.error(f"Exception during GCS upload: {e}", exc_info=True)
                    error_message = f"An error occurred during file upload: {e}"
                    # Handle the error as before
                    return render_template(
                        'index.html',
                        name=name,
                        title=title,
                        cell_number=cell_number,
                        email=email,
                        calendar_link=calendar_link,
                        error_message=error_message
                    )

                # Clean up local files
                os.remove(temp_image_path)
                os.remove(processed_image_path)

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

            logo_url = url_for('static', filename='company_banner.png')
            podcast_logo_url = url_for('static', filename='pod.png')
            background_url = url_for('static', filename='background.png')

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
                  <img src="https://storage.googleapis.com/hoppian-signature-images/company_banner.png" alt="Hedy & Hopp Banner" style="vertical-align: top; width: 320px; height: 82px;">
                </a>
                <a href="https://open.spotify.com/show/6cBADj7GMn7Rzou4dcVH3B" style="display: inline; margin-left: 1%;">
                  <img src="https://storage.googleapis.com/hoppian-signature-images/podcast_banner.png" alt="We Are, Marketing Happy Podcast" style="vertical-align: top; width: 120px; height: 80px;">
                </a>
              </div>
            </div>
            </body>
            </html>
            """

            signature_filename = f"signature_{secure_filename(name.lower().replace(' ', '_'))}.html"
            signature_file_path = os.path.join(app.config['UPLOAD_FOLDER'], signature_filename)
            with open(signature_file_path, 'w') as f:
                f.write(signature_html)

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
