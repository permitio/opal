package risk.enforcement.policy.allow.policy_0224

# Auto-generated policy 224
# Package: risk.enforcement.policy.allow

# Metadata
metadata := {
    "policy_id": "0224",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0224 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0224 {
    input.user.active
    input.resource.public
}

# Utility function for user info
