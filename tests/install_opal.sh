# This is a helper script to install opal-server and opal-client

# Installs opal-server and opal-client using pip.
# If the installation fails or the commands are not available,
# it exits with an error message.

function install_opal_server_and_client {
  echo "- Installing opal-server and opal-client from pip..."

  pip install opal-server opal-client > /dev/null 2>&1

  if ! command -v opal-server &> /dev/null || ! command -v opal-client &> /dev/null; then
    echo "Installation failed: opal-server or opal-client is not available."
    exit 1
  fi

  echo "- opal-server and opal-client successfully installed."
}

install_opal_server_and_client
