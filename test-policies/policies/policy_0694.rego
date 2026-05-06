package security.enforcement.resource.verify.policy_0694

# Auto-generated policy 694
# Package: security.enforcement.resource.verify

# Metadata
metadata := {
    "policy_id": "0694",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0694 {
    input.user.active
    input.resource.public
}
default allowed_0694 = false

# Utility function for user info
