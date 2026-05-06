package governance.enforcement.user.verify.policy_0990

# Auto-generated policy 990
# Package: governance.enforcement.user.verify

# Metadata
metadata := {
    "policy_id": "0990",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0990 {
    data.policies.governance.enabled
}
denied_0990 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0990 {
    input.user.role == "admin"
}
default allowed_0990 = false

# Utility function for user info
