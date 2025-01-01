# OPA EXTRACTOR STAGE --------------------------------
# This stage extracts the OPA binary from the official OPA image
# -----------------------------------------------------
    FROM alpine:latest AS opa-extractor

    # Install necessary tools for extracting the OPA binary
    RUN apk update && apk add --no-cache skopeo tar

    # Define working directory
    WORKDIR /opa

    # Copy OPA binary from the official OPA image
    ARG OPA_IMAGE=openpolicyagent/opa
    ARG OPA_TAG=latest-static
    RUN skopeo copy "docker://${OPA_IMAGE}:${OPA_TAG}" docker-archive:./image.tar && \
        mkdir image && tar xf image.tar -C ./image && cat image/*.tar | tar xf - -C ./image -i && \
        find image/ -name "opa*" -type f -executable -print0 | xargs -0 -I "{}" cp {} ./opa && chmod 755 ./opa && \
        rm -r image image.tar

    # STANDALONE OPA CONTAINER ----------------------------
    # This is the final image with the extracted OPA binary
    # -----------------------------------------------------
    FROM alpine:latest

    # Create a non-root user for running OPA
    RUN adduser -D opa && mkdir -p /opa && chown opa:opa /opa
    USER opa

    # Copy the OPA binary from the extractor stage
    COPY --from=opa-extractor /opa/opa /opa/opa

    # Set the working directory
    WORKDIR /opa

    # Expose the default OPA port
    EXPOSE 8181

    # Set the default command to run the OPA server
    CMD ["/opa/opa", "run", "--server", "--log-level", "info"]
