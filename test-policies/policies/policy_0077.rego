package security.authentication.resource.verify.policy_0077

# Auto-generated policy 77
# Package: security.authentication.resource.verify

# Metadata
metadata := {
    "policy_id": "0077",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0077 = false
allowed_0077 {
    data.policies.security.enabled
}
denied_0077 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
