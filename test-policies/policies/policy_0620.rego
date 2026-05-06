package risk.authentication.action.allow.utils.policy_0620

# Auto-generated policy 620
# Package: risk.authentication.action.allow.utils

# Metadata
metadata := {
    "policy_id": "0620",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0620 {
    input.user.active
    input.resource.public
}
default allowed_0620 = false

# Utility function for user info
