package compliance.enforcement.resource.allow.policy_0113

# Auto-generated policy 113
# Package: compliance.enforcement.resource.allow

# Metadata
metadata := {
    "policy_id": "0113",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0113 {
    input.user.role == "admin"
}
allowed_0113 {
    data.policies.compliance.enabled
}
allowed_0113 {
    input.user.active
    input.resource.public
}
denied_0113 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
