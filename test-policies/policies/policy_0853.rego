package security.enforcement.action.verify.policy_0853

# Auto-generated policy 853
# Package: security.enforcement.action.verify

# Metadata
metadata := {
    "policy_id": "0853",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0853 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0853 {
    input.user.role == "admin"
}
allowed_0853 {
    data.policies.security.enabled
}
default allowed_0853 = false

# Utility function for user info
