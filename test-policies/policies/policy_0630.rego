package compliance.validation.action.verify.policy_0630

# Auto-generated policy 630
# Package: compliance.validation.action.verify

# Metadata
metadata := {
    "policy_id": "0630",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0630 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0630 {
    input.user.active
    input.resource.public
}
default allowed_0630 = false

# Utility function for user info
