# The Grype release that .github/scripts/image_gate.py scans images with. Nothing builds this file:
# image_gate.py runs the image its FROM line names, and Dependabot's docker entry for
# /.github/grype proposes newer releases (after its cooldown), as it does for the images'
# own bases. Keep the tag and the digest of the tag's index together.
FROM anchore/grype:v0.121.1@sha256:6b06708b036f74b2cd70e94b706b4586af96d1932e6ac46255940b2e39dd44a9
