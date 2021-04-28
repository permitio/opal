# Using standalone image as base --------------------
# ---------------------------------------------------
FROM authorizon/opal-client-standalone:latest
# curl is needed for next section
RUN apk add --update --no-cache curl
# copy opa from official image (main binary and lib for web assembly)
RUN curl -L -o /opa https://openpolicyagent.org/downloads/latest/opa_linux_amd64 && chmod 755 /opa
# enable inline OPA
ENV OPAL_INLINE_OPA_ENABLED=true
# expose opa port
EXPOSE 8181
# run gunicorn
CMD ["/start.sh"]
