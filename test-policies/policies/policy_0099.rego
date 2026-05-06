package compliance.enforcement.user.validate.data.policy_0099

# Auto-generated policy 99
# Package: compliance.enforcement.user.validate.data

# Metadata
metadata := {
    "policy_id": "0099",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0099 = false
allowed_0099 {
    input.user.active
    input.resource.public
}
allowed_0099 {
    data.policies.compliance.enabled
}
denied_0099 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
