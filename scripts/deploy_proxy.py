import os
from string import Template
import json
import shutil
import subprocess
import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "../configs/config.json")
TEMPLATES_DIR = os.path.join(BASE_DIR, "../templates")
POM_FILE = os.path.join(BASE_DIR, "../pom.xml")

def load_config():
    if not os.path.exists(CONFIG_FILE):
        raise FileNotFoundError(f"Configuration file not found: {CONFIG_FILE}")
    with open(CONFIG_FILE, 'r') as file:
        return json.load(file)

def create_directories(proxy_name):
    proxy_dir = os.path.join(BASE_DIR, proxy_name, "apiproxy")
    os.makedirs(os.path.join(proxy_dir, "policies"), exist_ok=True)
    os.makedirs(os.path.join(proxy_dir, "proxies"), exist_ok=True)
    os.makedirs(os.path.join(proxy_dir, "targets"), exist_ok=True)
    return proxy_dir

def generate_files(config, proxy_dir, proxy_name, proxy_base_path, policies_list, target_server_name):
    for policy in policies_list:
        template_path = f"{TEMPLATES_DIR}/policies/{policy}.xml"
        output_path = f"{proxy_dir}/policies/{policy}.xml"
        try:
            with open(template_path, "r") as template_file:
                template_content = template_file.read()
                print(f"Processing template: {template_path}")
                template = Template(template_content)
                output = template.safe_substitute(proxy_name=proxy_name, policy_name=policy)  # Add 'policy_name'
                with open(output_path, "w") as output_file:
                    output_file.write(output)
                print(f"Generated file: {output_path}")
        except Exception as e:
            print(f"Error processing template {template_path}: {e}")
            raise

    proxy_template_path = f"{TEMPLATES_DIR}/bundle/apiproxy/proxies/default.xml"
    proxy_output_path = f"{proxy_dir}/proxies/default.xml"
    try:
        with open(proxy_template_path, "r") as template_file:
            template_content = template_file.read()
            print(f"Processing Proxy Endpoint template: {proxy_template_path}")
            template = Template(template_content)
            output = template.safe_substitute(proxy_base_path=proxy_base_path, proxy_name=proxy_name)
            with open(proxy_output_path, "w") as output_file:
                output_file.write(output)
            print(f"Generated Proxy Endpoint file: {proxy_output_path}")
    except Exception as e:
        print(f"Error processing proxy template: {e}")
        raise

    target_template_path = f"{TEMPLATES_DIR}/bundle/apiproxy/targets/default.xml"
    target_output_path = f"{proxy_dir}/targets/default.xml"
    try:
        with open(target_template_path, "r") as template_file:
            template_content = template_file.read()
            print(f"Processing Target Endpoint template: {target_template_path}")
            template = Template(template_content)
            output = template.safe_substitute(target_server_name=target_server_name, proxy_name=proxy_name)
            with open(target_output_path, "w") as output_file:
                output_file.write(output)
            print(f"Generated Target Endpoint file: {target_output_path}")
    except Exception as e:
        print(f"Error processing target template: {e}")
        raise


def create_zip(proxy_dir):
    zip_path = shutil.make_archive(proxy_dir, 'zip', os.path.dirname(proxy_dir), os.path.basename(proxy_dir))
    print(f"Created zip bundle at: {zip_path}")
    return zip_path

def validate_proxy(token, apigee_base_url, proxy_bundle_path):
    headers = {"Authorization": f"Bearer {token}"}
    with open(proxy_bundle_path, "rb") as file:
        files = {"file": file}
        url = f"{apigee_base_url}/apis?action=validate"  # Generic validation URL for new proxies
        response = requests.post(url, headers=headers, files=files)

    if response.status_code != 200:
        print(f"Validation Failed! HTTP Status Code: {response.status_code}")
        print(response.text)
        exit(1)
    print("Validation Successful!")
    print(response.text)



def deploy_with_maven(proxy_name, env_name, gcp_project_id):
    proxy_bundle_path = os.path.join(BASE_DIR, proxy_name, "apiproxy.zip")
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
        raise

if __name__ == "__main__":
    import sys
    try:
        config = load_config()
        PROXY_NAME = os.getenv("PROXY_NAME", config["proxy_name"])
        PROXY_CATEGORY = os.getenv("PROXY_CATEGORY", config["proxy_category"])
        PROXY_BASE_PATH = os.getenv("PROXY_BASE_PATH", config["proxy_base_path"])
        TARGET_SERVER_NAME = os.getenv("TARGET_SERVER_NAME", config["target_server_name"])
        ENV_NAME = os.getenv("ENV_NAME", "dev-00")
        GCP_ACCESS_TOKEN = os.getenv("GCP_ACCESS_TOKEN")
        APIGEE_BASE_URL = f"https://apigee.googleapis.com/v1/organizations/{config['gcp_project_id']}"

        if len(sys.argv) < 2:
            print("Usage: python deploy_proxy.py <generate|validate|deploy>")
            exit(1)

        stage = sys.argv[1].lower()

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
        elif stage == "validate":
            validate_proxy(
                GCP_ACCESS_TOKEN,
                APIGEE_BASE_URL,
                os.path.join(BASE_DIR, PROXY_NAME, "apiproxy.zip")
            )
        elif stage == "deploy":
            deploy_with_maven(PROXY_NAME, ENV_NAME, config["gcp_project_id"])
        else:
            print("Invalid stage. Use 'generate', 'validate', or 'deploy'.")
            exit(1)
    except Exception as e:
        print(f"Error: {e}")
        exit(1)
