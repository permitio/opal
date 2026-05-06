package security.authentication.context.allow.data.policy_0702

# Auto-generated policy 702
# Package: security.authentication.context.allow.data

# Metadata
metadata := {
    "policy_id": "0702",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0702 {
    input.user.role == "admin"
}
denied_0702 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0702 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
