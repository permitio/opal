package security.enforcement.user.allow.policy_0255

# Auto-generated policy 255
# Package: security.enforcement.user.allow

# Metadata
metadata := {
    "policy_id": "0255",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0255 = false
allowed_0255 {
    input.user.role == "admin"
}
allowed_0255 {
    input.user.active
    input.resource.public
}

# Utility function for user info
