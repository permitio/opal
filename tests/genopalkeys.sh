# This is utility script to generate OPAL keys - Use it for your needs

# This function generates a pair of RSA keys using ssh-keygen, extracts the public key into OPAL_AUTH_PUBLIC_KEY,
# formats the private key by replacing newlines with underscores and stores it in OPAL_AUTH_PRIVATE_KEY,
# and then removes the key files. It outputs messages indicating the start and completion of key generation.

function generate_opal_keys {
  echo "- Generating OPAL keys"

  ssh-keygen -q -t rsa -b 4096 -m pem -f opal_crypto_key -N ""
  OPAL_AUTH_PUBLIC_KEY="$(cat opal_crypto_key.pub)"
  OPAL_AUTH_PRIVATE_KEY="$(tr '\n' '_' <opal_crypto_key)"
  rm opal_crypto_key.pub opal_crypto_key

  echo "- OPAL keys generated\n"
}

generate_opal_keys
