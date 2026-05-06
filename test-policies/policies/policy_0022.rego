package security.monitoring.user.verify.policy_0022

# Auto-generated policy 22
# Package: security.monitoring.user.verify

# Metadata
metadata := {
    "policy_id": "0022",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0022 {
    input.user.active
    input.resource.public
}
allowed_0022 {
    input.user.role == "admin"
}

# Utility function for user info
