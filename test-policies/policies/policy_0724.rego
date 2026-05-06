package audit.enforcement.resource.allow.policy_0724

# Auto-generated policy 724
# Package: audit.enforcement.resource.allow

# Metadata
metadata := {
    "policy_id": "0724",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0724 {
    data.policies.audit.enabled
}
allowed_0724 {
    input.user.active
    input.resource.public
}
allowed_0724 {
    input.user.role == "admin"
}
default allowed_0724 = false

# Utility function for user info
