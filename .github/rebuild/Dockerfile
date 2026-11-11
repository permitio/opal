# syntax=docker/dockerfile:1.19@sha256:b6afd42430b15f2d2a4c5a02b919e98a525b785b1aaff16747d2f623364e39b6
# check=skip=InvalidDefaultArgInFrom
# The weekly rebuild (.github/workflows/rebuild_images.yml): a published release image with its
# Wolfi packages upgraded. Only apk packages move; the Python packages, OPAL's code, known_hosts
# and everything else stay as released. RELEASE_IMAGE is the release's own image, by digest,
# never an earlier rebuild, so layers never stack. It has no default on purpose, hence the
# check skipped above: a build without it must fail rather than rebuild another image.
ARG RELEASE_IMAGE
FROM ${RELEASE_IMAGE} AS rebuild
ARG RELEASE_IMAGE
USER root
# /etc/apk/world pins each of wolfi-base's own packages (glibc, openssl, busybox, ...) to the
# version the release shipped, so apk upgrade alone leaves them as they are. Dropping every
# version constraint from it first lets apk upgrade move every apk package to the newest.
RUN sed -i -E 's/[<>~=].*//' /etc/apk/world && apk upgrade --no-cache && \
  python /opal/check_trust_store.py
LABEL ac.opal.rebuilt-from="${RELEASE_IMAGE}"
USER opal
