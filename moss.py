from flask import Flask, request, render_template
import os
import tempfile
import mosspy
import argparse
import requests
import base64
import logging
import re

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)

MOSS_USER_ID = 4897394  # MOSS ID 
GITHUB_API_TOKEN = 'ghp-nicetrythisisnotanactualapitoken:)'  # github API token

def parse_github_url(url):
    # expression to match GitHub URLs
    pattern = r'https?://github\.com/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)(/tree/(?P<branch>[\w.-]+))?(?P<path>/.*)?'
    match = re.match(pattern, url)
    if not match:
        raise ValueError("Invalid GitHub URL")
    
    owner = match.group('owner')
    repo = match.group('repo')
    branch = match.group('branch') or 'main'  # default to 'main' if no branch specified
    path = match.group('path') or ''
    path = path.lstrip('/')  # remove leading slash
    
    return owner, repo, branch, path

def download_github_folder(owner, repo, branch, path, temp_dir):
    headers = {'Authorization': f'token {GITHUB_API_TOKEN}'} if GITHUB_API_TOKEN else {}
    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={branch}"
    response = requests.get(api_url, headers=headers)
    
    if response.status_code != 200:
        raise Exception(f"Failed to fetch repository contents: HTTP {response.status_code}")

    contents = response.json()

    # handle case if contents is a single file
    if not isinstance(contents, list):
        contents = [contents]

    for item in contents:
        if item['type'] == 'file':
            file_url = item['download_url']
            file_path = os.path.join(temp_dir, item['name'])
            
            file_response = requests.get(file_url, headers=headers)
            if file_response.status_code == 200:
                with open(file_path, 'wb') as f:
                    f.write(file_response.content)
                if os.path.getsize(file_path) == 0:
                    os.remove(file_path)
                    logging.info(f"Removed empty file: {file_path}")
            else:
                logging.error(f"Failed to download file {item['name']}: HTTP {file_response.status_code}")

def add_files_to_moss(moss, directory):
    for root, _, files in os.walk(directory):
        for file in files:
            file_path = os.path.join(root, file)
            if os.path.getsize(file_path) > 0:  # only add non-empty files
                moss.addFile(file_path)

@app.route('/', methods=['GET', 'POST'])
def compare_repos():
    if request.method == 'POST':
        repo1_url = request.form['repo1']
        repo2_url = request.form['repo2']
        
        logging.info(f"Comparing repositories: {repo1_url} and {repo2_url}")
        
        with tempfile.TemporaryDirectory() as temp_dir1, tempfile.TemporaryDirectory() as temp_dir2:
            try:
                owner1, repo1, branch1, path1 = parse_github_url(repo1_url)
                owner2, repo2, branch2, path2 = parse_github_url(repo2_url)

                download_github_folder(owner1, repo1, branch1, path1, temp_dir1)
                download_github_folder(owner2, repo2, branch2, path2, temp_dir2)
                
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