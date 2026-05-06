package compliance.authentication.resource.allow.policy_0452

# Auto-generated policy 452
# Package: compliance.authentication.resource.allow

# Metadata
metadata := {
    "policy_id": "0452",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0452 = false
allowed_0452 {
    data.policies.compliance.enabled
}
allowed_0452 {
    input.user.active
    input.resource.public
}
allowed_0452 {
    input.user.role == "admin"
}

# Utility function for user info
