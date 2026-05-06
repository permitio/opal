package risk.authentication.context.allow.policy_0151

# Auto-generated policy 151
# Package: risk.authentication.context.allow

# Metadata
metadata := {
    "policy_id": "0151",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0151 {
    data.policies.risk.enabled
}
default allowed_0151 = false
denied_0151 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0151 {
    input.user.role == "admin"
}

# Utility function for user info
