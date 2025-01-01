function generate_opal_keys {
  echo "- Generating OPAL keys"

  ssh-keygen -q -t rsa -b 4096 -m pem -f opal_crypto_key -N ""
  OPAL_AUTH_PUBLIC_KEY="$(cat opal_crypto_key.pub)"
  OPAL_AUTH_PRIVATE_KEY="$(tr '\n' '_' <opal_crypto_key)"
  rm opal_crypto_key.pub opal_crypto_key

  echo "- OPAL keys generated\n"
}

generate_opal_keys
