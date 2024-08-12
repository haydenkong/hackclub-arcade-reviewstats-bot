from flask import Flask, request, render_template
import os
import tempfile
import mosspy
import argparse
import requests
import zipfile
import io
import shutil
import re
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)

MOSS_USER_ID = 000000000  # user moss id, need to implement feature for custom moss id due to rate limits

def validate_github_url(url):
    pattern = r'^https?://github\.com/[\w-]+/[\w.-]+(/[\w.-]+)*$'
    return re.match(pattern, url) is not None

def download_and_extract_repo(url, temp_dir):
    logging.info(f"Attempting to download repository: {url}")
    if not validate_github_url(url):
        raise ValueError(f"Invalid GitHub URL: {url}")

    parts = url.rstrip('/').split('/')
    owner, repo = parts[3], parts[4]
    subpath = '/'.join(parts[5:]) if len(parts) > 5 else ''
    api_url = f"https://api.github.com/repos/{owner}/{repo}/zipball"
    
    logging.info(f"Requesting ZIP from GitHub API: {api_url}")
    response = requests.get(api_url)
    
    if response.status_code == 200:
        logging.info(f"Successfully downloaded repository: {url}")
        z = zipfile.ZipFile(io.BytesIO(response.content))
        z.extractall(temp_dir)
        extracted_dir = os.path.join(temp_dir, os.listdir(temp_dir)[0])
        
        target_dir = os.path.join(extracted_dir, subpath) if subpath else extracted_dir
        if not os.path.exists(target_dir):
            raise Exception(f"Specified folder not found in the repository: {subpath}")
        
        for item in os.listdir(target_dir):
            item_path = os.path.join(target_dir, item)
            if os.path.isfile(item_path) and os.path.getsize(item_path) > 0:
                shutil.move(item_path, temp_dir)
            elif os.path.isfile(item_path):
                os.remove(item_path)
        
        shutil.rmtree(extracted_dir)
    elif response.status_code == 404:
        logging.error(f"Repository not found: {url}")
        raise Exception(f"Repository not found. It might be private or doesn't exist: {url}")
    else:
        logging.error(f"Failed to download repository: {url}, HTTP {response.status_code}")
        raise Exception(f"Failed to download repository: HTTP {response.status_code}")

def add_files_to_moss(moss, directory):
    for root, _, files in os.walk(directory):
        for file in files:
            file_path = os.path.join(root, file)
            moss.addFile(file_path)

@app.route('/', methods=['GET', 'POST'])
def compare_repos():
    if request.method == 'POST':
        repo1_url = request.form['repo1']
        repo2_url = request.form['repo2']
        
        logging.info(f"Comparing repositories: {repo1_url} and {repo2_url}")
        
        with tempfile.TemporaryDirectory() as temp_dir1, tempfile.TemporaryDirectory() as temp_dir2:
            try:
                download_and_extract_repo(repo1_url, temp_dir1)
                download_and_extract_repo(repo2_url, temp_dir2)
                
                m = mosspy.Moss(MOSS_USER_ID, "*")  # * for all file types, debug why readme aren't included
                
                add_files_to_moss(m, temp_dir1)
                add_files_to_moss(m, temp_dir2)
                
                logging.info("Sending files to MOSS for analysis")
                url = m.send()
                logging.info(f"MOSS analysis complete. Result URL: {url}")
                
                return render_template('result.html', moss_url=url)
            except Exception as e:
                logging.error(f"Error occurred: {str(e)}")
                return render_template('error.html', error=str(e), repo1_url=repo1_url, repo2_url=repo2_url)
    
    return render_template('upload.html')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run the MOSS Detector app')
    parser.add_argument('--port', type=int, default=8020, help='Port to run the app on')
    args = parser.parse_args()
    
    app.run(host='127.0.0.1', port=args.port, debug=False)