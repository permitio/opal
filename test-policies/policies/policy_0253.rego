package audit.validation.resource.check.policy_0253

# Auto-generated policy 253
# Package: audit.validation.resource.check

# Metadata
metadata := {
    "policy_id": "0253",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0253 {
    input.user.active
    input.resource.public
}
denied_0253 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
