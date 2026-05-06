package governance.authentication.user.check.policy_0240

# Auto-generated policy 240
# Package: governance.authentication.user.check

# Metadata
metadata := {
    "policy_id": "0240",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0240 {
    input.user.active
    input.resource.public
}
denied_0240 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0240 {
    data.policies.governance.enabled
}
allowed_0240 {
    input.user.role == "admin"
}

# Utility function for user info
