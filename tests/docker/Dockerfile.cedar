# CEDAR AGENT BUILD STAGE ---------------------------
# This stage compiles the Cedar agent
# ---------------------------------------------------
    FROM rust:1.79 AS cedar-builder

    # Copy Cedar agent source code
    COPY ./cedar-agent /tmp/cedar-agent
    WORKDIR /tmp/cedar-agent

    # Build the Cedar agent in release mode
    RUN CARGO_REGISTRIES_CRATES_IO_PROTOCOL=sparse cargo build --release

    # CEDAR AGENT IMAGE ---------------------------------
    # The final image with the Cedar agent executable
    # ---------------------------------------------------
    FROM alpine:latest AS cedar-agent

    # Create a non-root user for running the agent
    RUN adduser -D cedar && mkdir -p /cedar && chown cedar:cedar /cedar
    USER cedar

    # Copy the Cedar agent binary from the build stage
    COPY --from=cedar-builder /tmp/cedar-agent/target/*/cedar-agent /cedar/cedar-agent

    # Define environment variables for configuration
    ENV OPAL_POLICY_STORE_TYPE=CEDAR
    ENV OPAL_INLINE_CEDAR_ENABLED=true
    ENV OPAL_INLINE_CEDAR_EXEC_PATH=/cedar/cedar-agent
    ENV OPAL_INLINE_CEDAR_CONFIG='{"addr": "0.0.0.0:8180"}'
    ENV OPAL_POLICY_STORE_URL=http://localhost:8180

    # Expose Cedar agent port
    EXPOSE 8180

    # Set default working directory
    WORKDIR /cedar

    # Set the default command
    CMD ["/cedar/cedar-agent"]
