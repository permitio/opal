package risk.authentication.user.allow.data.policy_0934

# Auto-generated policy 934
# Package: risk.authentication.user.allow.data

# Metadata
metadata := {
    "policy_id": "0934",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0934 = false
denied_0934 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0934 {
    data.policies.risk.enabled
}

# Utility function for user info
