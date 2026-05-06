package risk.enforcement.policy.check.policy_0317

# Auto-generated policy 317
# Package: risk.enforcement.policy.check

# Metadata
metadata := {
    "policy_id": "0317",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0317 {
    input.user.active
    input.resource.public
}
default allowed_0317 = false
denied_0317 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
