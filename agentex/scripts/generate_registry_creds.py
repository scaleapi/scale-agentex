import argparse
import base64
import json


def generate_docker_auth(registry: str, robot_account: str, secret: str) -> str:
    # Create the auth string "robot_account:secret" and encode it to base64
    auth_string = f"{robot_account}:{secret}"
    auth_encoded = base64.b64encode(auth_string.encode()).decode()

    # Create the dictionary in the desired format
    auth_dict = {"auths": {registry: {"auth": auth_encoded}}}

    # Convert the dictionary to a JSON string and encode it in base64
    auth_json = json.dumps(auth_dict)
    auth_json_encoded = base64.b64encode(auth_json.encode()).decode()

    return auth_json_encoded


def main():
    # Set up argument parsing
    parser = argparse.ArgumentParser(
        description="Generate base64-encoded Docker registry credentials."
    )
    parser.add_argument("--registry", required=True, help="The Docker registry URL")
    parser.add_argument(
        "--account", required=True, help="The robot account for the registry"
    )
    parser.add_argument(
        "--secret", required=True, help="The secret or password for the robot account"
    )

    # Parse the arguments
    args = parser.parse_args()

    # Generate the base64-encoded Docker credentials
    encoded_auth = generate_docker_auth(args.registry, args.account, args.secret)

    # Print the encoded auth string
    print(encoded_auth)


if __name__ == "__main__":
    main()
