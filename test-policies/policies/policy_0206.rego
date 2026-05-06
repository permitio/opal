package access.authentication.user.verify.utils.policy_0206

# Auto-generated policy 206
# Package: access.authentication.user.verify.utils

# Metadata
metadata := {
    "policy_id": "0206",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0206 {
    input.user.role == "admin"
}
approved_0206 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0206 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0206 {
    data.policies.access.enabled
}

# Utility function for user info
