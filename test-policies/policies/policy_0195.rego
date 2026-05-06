package risk.authentication.context.deny.utils.policy_0195

# Auto-generated policy 195
# Package: risk.authentication.context.deny.utils

# Metadata
metadata := {
    "policy_id": "0195",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0195 = false
allowed_0195 {
    input.user.role == "admin"
}
allowed_0195 {
    input.user.active
    input.resource.public
}

# Utility function for user info
