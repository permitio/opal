package security.enforcement.resource.allow.policy_0310

# Auto-generated policy 310
# Package: security.enforcement.resource.allow

# Metadata
metadata := {
    "policy_id": "0310",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0310 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0310 {
    input.user.active
    input.resource.public
}
allowed_0310 {
    data.policies.security.enabled
}

# Utility function for user info
