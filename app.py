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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = os.path.join(os.path.dirname(__file__), 'credentials', 'credentials.json')

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
        .signature-wrapper {{
            width: 600px;
            height: 200px;
            overflow: hidden;
            margin: 0;
            padding: 0;
            font-family: Arial, sans-serif;
            color: #5c5a5b;
        }}
        .headshot {{
            width: 80px;
            height: 80px;
            border-radius: 8px;
            display: block;
        }}
        .text-area {{
            font-size: 12px;
            line-height: 1.2;
            padding: 5px;
        }}
        .name {{
            font-size: 16px;
            color: #D4458E;
            margin: 0 0 8px 0;
        }}
        .bottom-banner {{
            width: 180px;
            height: 40px;
            display: block;
        }}
        .podcast-logo {{
            width: 40px;
            height: 40px;
            display: block;
            margin-top: 4px;
        }}
    </style>
</head>
<body>
    <div class="signature-wrapper">
        <table cellspacing="0" cellpadding="0" style="border-collapse: collapse;">
            <tr>
                <td style="vertical-align: top; padding: 5px;">
                    <img 
                        src="{headshot_url}" 
                        alt="Headshot"
                        class="headshot"
                    />
                </td>

                <td class="text-area" style="vertical-align: top;">
                    <div class="name">
                        {fname}<br>{lname}
                    </div>
                    <div>
                        <strong>{title}, </strong>HEDY &amp; HOPP<br>
                        <span style="color: #D4458E; font-weight: bold;">C</span> {cell_number}<br>
                        <span style="color: #D4458E; font-weight: bold;">E</span> 
                        <a href="mailto:{email}" style="color: #5C5A5B; text-decoration: none;">
                            {email}
                        </a>
                    </div>
                    {f'<p><a href="{calendar_link}" style="color:#DB499A;">Schedule Time With Me</a></p>' if calendar_link else ''}
                </td>

                <td style="vertical-align: bottom; text-align: right; padding: 5px;">
                    <img
                        src="https://storage.googleapis.com/hoppian-signature-images/2025signatureairbanner.png"
                        alt="Bottom Banner"
                        class="bottom-banner"
                    />
                    <img
                        src="https://storage.googleapis.com/hoppian-signature-images/podlogowhite400px.png"
                        alt="Podcast Logo"
                        class="podcast-logo"
                    />
                </td>
            </tr>
        </table>
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

    encoded_blob_name = quote(destination_blob_name, safe='')

    public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{encoded_blob_name}"

    logging.info(f"Public URL: {public_url}")
    logging.info(f"Generated public URL: {public_url}")

    return public_url

def process_image(image_path):
    output_path = os.path.join(app.config['UPLOAD_FOLDER'], 'processed_' + os.path.basename(image_path))
    with Image.open(image_path) as img:
        img = img.convert('RGB')
        img.thumbnail((300, 300), Image.ANTIALIAS)
        img.save(output_path, 'JPEG', quality=95)
    return output_path

def check_credentials():
    credentials, project = default()
    print(f"Credentials: {credentials}")
    print(f"Project ID: {project}")

check_credentials()

def format_phone_number(phone):
    digits = re.sub(r'\D', '', phone)
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return phone

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        try:
            fname = request.form.get('fname', '')
            lname = request.form.get('lname', '')
            title = request.form.get('title', '')
            cell_number = format_phone_number(request.form.get('cell_number', ''))
            email = request.form.get('email', '')
            calendar_link = request.form.get('calendar_link', '') 
            headshot = request.files.get('headshot')
            
            if not headshot:
                raise ValueError("Headshot file is required.")

            if headshot and allowed_file(headshot.filename):
                filename = secure_filename(headshot.filename)
                temp_image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                headshot.save(temp_image_path)

                processed_image_path = process_image(temp_image_path)

                destination_blob_name = f"headshots/{os.path.basename(processed_image_path)}"
                try:
                    headshot_url = upload_to_gcs(processed_image_path, destination_blob_name)
                except Exception as e:
                    logging.error(f"Exception during GCS upload: {e}", exc_info=True)
                    error_message = f"An error occurred during file upload: {e}"
                    return render_template(
                        'index.html',
                        fname=fname,
                        lname=lname,
                        title=title,
                        cell_number=cell_number,
                        email=email,
                        error_message=error_message
                    )
                os.remove(temp_image_path)
                os.remove(processed_image_path)

            else:
                error_message = "Invalid or missing headshot image."
                return render_template(
                    'index.html',
                    fname=fname,
                    lname=lname,
                    title=title,
                    cell_number=cell_number,
                    email=email,
                    error_message=error_message
                )

            signature_html = f"""
            <!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Email Signature</title>
</head>
<body style="margin: 0; padding: 0;">

<table 
  width="850"
  border="0"
  cellpadding="0"
  cellspacing="0"
  style="
    border-collapse: collapse;
    width: 700px;
    margin: 0 auto;
  "
>
  <tr>
    <td
      width="225"
      valign="top"
      style="
        padding: 0;
        margin: 0;
      "
    >
      <img
        src="https://storage.googleapis.com/hoppian-signature-images/2025ampersand.png"
        alt="Ampersand"
        width="225"
        height="225"
        style="
          display: block;
          border: 0;
          outline: none;
        "
      />
    </td>
  
    <td
      width="225"
      valign="top"
      style="
        padding: 0;
        margin: 0;
      "
    >
      <img
        src="{headshot_url}"
        alt="Headshot"
        width="225"
        height="225"
        style="
          display: block;
          border: 0;
          outline: none;
        "
      />
    </td>
    
    <td
      width="400"
      valign="top"
      style="
        padding: 10px;
        margin: 0;
        font-family: Arial, sans-serif;
        font-size: 14px;
        line-height: 1.6;
        color: #5C5A5B;
        background-color: #FFFFFF;
      "
    >
      <div 
        style="
          font-family: Arial, sans-serif;
          font-size: 32px;
          line-height: 1;
          color: #D4458E;
          margin: 0 0 8px 0;
        "
      >
        {fname}</br>{lname}
      </div>
      
      <div 
        style="
          margin-bottom: 16px;
        "
      >
        <strong>{title}, </strong>HEDY &amp; HOPP<br />
        <span style="color: #D4458E; font-weight: bold;">C</span> {cell_number}<br />
        <span style="color: #D4458E; font-weight: bold;">E</span> 
        <a 
          href="mailto:{email}" 
          style="color: #5C5A5B; text-decoration: none;"
        >
          {email}
        </a>
      </div>
      {f'<p><a href="{calendar_link}" style="color:#DB499A">Schedule Time With Me</a></p>' if calendar_link else ''}
      
    </td>
  </tr>
  
  <tr>
    <td
      colspan="2"
      valign="bottom"
      style="
        padding: 0;
        margin: 0;
        vertical-align: bottom;
      "
    >
      <img
        src="https://storage.googleapis.com/hoppian-signature-images/2025signatureairbanner.png"
        alt="Bottom Banner"
        width="450"
        height="100"
        style="
          display: block;
          border: 0;
          outline: none;
          vertical-align: bottom;
        "
      />
    </td>
    
    <td
      width="400"
      valign="bottom"
      style="
        padding: 0;
        margin: 0;
        text-align: center;
        vertical-align: bottom;
      "
    >
      <a
        href="https://open.spotify.com/show/6cBADj7GMn7Rzou4dcVH3B"
        style="text-decoration: none; border: 0; outline: none;"
      >
        <img
          src="https://storage.googleapis.com/hoppian-signature-images/podlogowhite400px.png"
          alt="Podcast Logo"
          width="300"
          style="
            display: inline-block;
            border: 0;
            outline: none;
          "
        />
      </a>
    </td>
  </tr>
</table>

</body>
</html>
"""

            signature_filename = f"signature_{secure_filename(fname.lower().replace(' ', '_'))}.html"
            signature_file_path = os.path.join(app.config['UPLOAD_FOLDER'], signature_filename)
            with open(signature_file_path, 'w') as f:
                f.write(signature_html)

            return render_template(
                'index.html',
                signature=signature_html,
                download_link=url_for('download_file', filename=signature_filename),
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
                name=request.form.get('fname', 'lname'),
                title=request.form.get('title', ''),
                cell_number=request.form.get('cell_number', ''),
                email=request.form.get('email', '')
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