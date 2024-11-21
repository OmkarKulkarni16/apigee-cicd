import os
from string import Template
import json
import shutil
import subprocess
import requests
import argparse
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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
    proxy_dir = os.path.join(BASE_DIR, "scripts", proxy_name, "apiproxy")
    os.makedirs(os.path.join(proxy_dir, "policies"), exist_ok=True)
    os.makedirs(os.path.join(proxy_dir, "proxies"), exist_ok=True)
    os.makedirs(os.path.join(proxy_dir, "targets"), exist_ok=True)
    logger.info(f"Directories created for proxy: {proxy_dir}")
    return proxy_dir

def generate_files(config, proxy_dir, proxy_name, proxy_base_path, policies_list, target_server_name):
    for policy in policies_list:
        template_path = os.path.join(TEMPLATES_DIR, "policies", f"{policy}.xml")
        output_path = os.path.join(proxy_dir, "policies", f"{policy}.xml")
        try:
            with open(template_path, "r") as template_file:
                template_content = template_file.read()
                template = Template(template_content)
                output = template.safe_substitute(proxy_name=proxy_name, policy_name=policy)
                with open(output_path, "w") as output_file:
                    output_file.write(output)
                logger.info(f"Generated policy file: {output_path}")
        except FileNotFoundError:
            logger.error(f"Template file not found: {template_path}")
            raise
        except Exception as e:
            logger.error(f"Error processing template {template_path}: {e}")
            raise

    # Generate Proxy Endpoint
    proxy_template_path = os.path.join(TEMPLATES_DIR, "bundle", "apiproxy", "proxies", "default.xml")
    proxy_output_path = os.path.join(proxy_dir, "proxies", "default.xml")
    try:
        with open(proxy_template_path, "r") as template_file:
            template_content = template_file.read()
            template = Template(template_content)
            output = template.safe_substitute(proxy_base_path=proxy_base_path, proxy_name=proxy_name)
            with open(proxy_output_path, "w") as output_file:
                output_file.write(output)
            logger.info(f"Generated Proxy Endpoint file: {proxy_output_path}")
    except Exception as e:
        logger.error(f"Error processing proxy template: {e}")
        raise

    # Generate Target Endpoint
    target_template_path = os.path.join(TEMPLATES_DIR, "bundle", "apiproxy", "targets", "default.xml")
    target_output_path = os.path.join(proxy_dir, "targets", "default.xml")
    try:
        with open(target_template_path, "r") as template_file:
            template_content = template_file.read()
            template = Template(template_content)
            output = template.safe_substitute(target_server_name=target_server_name, proxy_name=proxy_name)
            with open(target_output_path, "w") as output_file:
                output_file.write(output)
            logger.info(f"Generated Target Endpoint file: {target_output_path}")
    except Exception as e:
        logger.error(f"Error processing target template: {e}")
        raise

def create_zip(proxy_dir):
    zip_path = shutil.make_archive(proxy_dir, 'zip', os.path.dirname(proxy_dir), os.path.basename(proxy_dir))
    logger.info(f"Created zip bundle at: {zip_path}")
    return zip_path

def validate_proxy(token, apigee_base_url, proxy_bundle_path):
    headers = {"Authorization": f"Bearer {token}"}
    with open(proxy_bundle_path, "rb") as file:
        files = {"file": file}
        url = f"{apigee_base_url}/apis?action=validate"
        logger.info(f"Validating proxy bundle: {url}")
        response = requests.post(url, headers=headers, files=files)

    if response.status_code != 200:
        logger.error(f"Validation Failed! HTTP Status Code: {response.status_code}")
        logger.error(response.text)
        exit(1)
    logger.info("Validation Successful!")
    logger.info(response.text)

def deploy_with_maven(proxy_name, env_name, gcp_project_id):
    proxy_bundle_path = os.path.join(BASE_DIR, "scripts", proxy_name, "apiproxy.zip")
    maven_command = [
        "mvn", "clean", "install", "-Pgoogleapi",
        f"-Denv={env_name}",
        f"-Dorg={gcp_project_id}",
        f"-Dapigee.proxy.bundle.path={proxy_bundle_path}",
        "-f", POM_FILE
    ]
    try:
        subprocess.run(maven_command, check=True)
        logger.info(f"Deployment of {proxy_name} was successful.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Deployment failed: {e}")
        raise

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Apigee Proxy Deployment Tool")
    parser.add_argument("stage", choices=["generate", "validate", "deploy"], help="Stage to execute")
    parser.add_argument("--proxy_name", required=True, help="Name of the proxy")
    parser.add_argument("--proxy_category", required=True, choices=["low", "medium", "high", "critical"], help="Proxy category")
    parser.add_argument("--proxy_base_path", required=True, help="Base path for the proxy")
    parser.add_argument("--target_server_name", required=True, help="Target server name")
    parser.add_argument("--env_name", default="dev-00", help="Environment name (default: dev-00)")
    parser.add_argument("--token", required=False, help="GCP Access Token")
    args = parser.parse_args()

    try:
        config = load_config()
        PROXY_NAME = args.proxy_name
        PROXY_CATEGORY = args.proxy_category
        PROXY_BASE_PATH = args.proxy_base_path
        TARGET_SERVER_NAME = args.target_server_name
        ENV_NAME = args.env_name
        GCP_ACCESS_TOKEN = args.token or os.getenv("GCP_ACCESS_TOKEN")
        APIGEE_BASE_URL = f"https://apigee.googleapis.com/v1/organizations/{config['gcp_project_id']}"

        if not GCP_ACCESS_TOKEN:
            raise ValueError("GCP_ACCESS_TOKEN is required.")

        if args.stage == "generate":
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
        elif args.stage == "validate":
            proxy_bundle_path = os.path.join(BASE_DIR, "scripts", PROXY_NAME, "apiproxy.zip")
            validate_proxy(GCP_ACCESS_TOKEN, APIGEE_BASE_URL, proxy_bundle_path)
        elif args.stage == "deploy":
            deploy_with_maven(PROXY_NAME, ENV_NAME, config["gcp_project_id"])
        else:
            logger.error("Invalid stage. Use 'generate', 'validate', or 'deploy'.")
            exit(1)
    except Exception as e:
        logger.error(f"Error: {e}")
        exit(1)
