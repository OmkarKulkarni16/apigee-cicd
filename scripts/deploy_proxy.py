import os
import json
import shutil
import subprocess
from string import Template
import requests

# Configuration
CONFIG_FILE = "configs/config.json"
BASE_DIR = "C:/Users/omkar/Documents/tmp/proxy_deployment"
TEMPLATES_DIR = "templates"
POM_FILE = "pom.xml"

def load_config():
    """Load configuration from config.json."""
    with open(CONFIG_FILE, 'r') as file:
        return json.load(file)

def create_directories(proxy_name):
    """Create directory structure for the proxy bundle."""
    proxy_dir = os.path.join(BASE_DIR, proxy_name, "apiproxy")
    os.makedirs(os.path.join(proxy_dir, "policies"), exist_ok=True)
    os.makedirs(os.path.join(proxy_dir, "proxies"), exist_ok=True)
    os.makedirs(os.path.join(proxy_dir, "targets"), exist_ok=True)
    return proxy_dir

def generate_files(config, proxy_dir, proxy_name, proxy_base_path, policies_list, target_server_name):
    """Generate XML files dynamically based on templates."""
    for policy in policies_list:
        with open(f"{TEMPLATES_DIR}/policies/{policy}.xml", "r") as template_file:
            template = Template(template_file.read())
            output = template.substitute(proxy_name=proxy_name)
            with open(f"{proxy_dir}/policies/{policy}.xml", "w") as output_file:
                output_file.write(output)

    # Proxy Endpoint
    with open(f"{TEMPLATES_DIR}/bundle/apiproxy/proxies/default.xml", "r") as template_file:
        template = Template(template_file.read())
        output = template.substitute(proxy_base_path=proxy_base_path)
        with open(f"{proxy_dir}/proxies/default.xml", "w") as output_file:
            output_file.write(output)

    # Target Endpoint
    with open(f"{TEMPLATES_DIR}/bundle/apiproxy/targets/default.xml", "r") as template_file:
        template = Template(template_file.read())
        output = template.substitute(target_server_name=target_server_name)
        with open(f"{proxy_dir}/targets/default.xml", "w") as output_file:
            output_file.write(output)

def create_zip(proxy_dir):
    """Create zip bundle of the proxy."""
    zip_path = shutil.make_archive(proxy_dir, 'zip', proxy_dir)
    return zip_path

def validate_proxy(token, apigee_base_url, proxy_bundle_path):
    """Validate the proxy bundle with Apigee."""
    headers = {"Authorization": f"Bearer {token}"}
    files = {"file": open(proxy_bundle_path, "rb")}
    url = f"{apigee_base_url}/apis?action=validate&validate=true"

    response = requests.post(url, headers=headers, files=files)
    if response.status_code != 200:
        print(f"Validation Failed! HTTP Status Code: {response.status_code}")
        print(response.text)
        exit(1)
    print("Validation Successful!")
    print(response.text)

def deploy_with_maven(proxy_name, env_name, gcp_project_id):
    """Deploy the proxy bundle using Maven."""
    proxy_bundle_path = f"{BASE_DIR}/{proxy_name}/apiproxy.zip"
    maven_command = [
        "mvn", "clean", "install", "-Pgoogleapi",
        f"-Denv={env_name}",
        f"-Dorg={gcp_project_id}",
        f"-Dapigee.proxy.bundle.path={proxy_bundle_path}",
        "-f", POM_FILE
    ]
    try:
        subprocess.run(maven_command, check=True)
        print(f"Deployment of {proxy_name} was successful.")
    except subprocess.CalledProcessError as e:
        print(f"Deployment failed: {e}")

if __name__ == "__main__":
    import sys
    config = load_config()

    # Common parameters
    PROXY_NAME = os.getenv("PROXY_NAME", config["proxy_name"])
    PROXY_CATEGORY = os.getenv("PROXY_CATEGORY", config["proxy_category"])
    PROXY_BASE_PATH = os.getenv("PROXY_BASE_PATH", config["proxy_base_path"])
    TARGET_SERVER_NAME = os.getenv("TARGET_SERVER_NAME", config["target_server_name"])
    ENV_NAME = os.getenv("ENV_NAME", "dev-00")
    GCP_ACCESS_TOKEN = os.getenv("GCP_ACCESS_TOKEN")
    APIGEE_BASE_URL = f"https://apigee.googleapis.com/v1/organizations/{config['gcp_project_id']}"

    # Check the command-line argument for the stage
    if len(sys.argv) < 2:
        print("Usage: python deploy_proxy.py <generate|validate|deploy>")
        exit(1)

    stage = sys.argv[1]

    if stage == "generate":
        proxy_dir = create_directories(PROXY_NAME)
        generate_files(
            config,
            proxy_dir,
            PROXY_NAME,
            PROXY_BASE_PATH,
            config["categories"][PROXY_CATEGORY],
            TARGET_SERVER_NAME
        )
        create_zip(proxy_dir)
        print(f"Proxy bundle generated at: {proxy_dir}")
    elif stage == "validate":
        validate_proxy(GCP_ACCESS_TOKEN, APIGEE_BASE_URL, f"{BASE_DIR}/{PROXY_NAME}/apiproxy.zip")
    elif stage == "deploy":
        deploy_with_maven(PROXY_NAME, ENV_NAME, config["gcp_project_id"])
    else:
        print("Invalid stage. Use 'generate', 'validate', or 'deploy'.")
        exit(1)
