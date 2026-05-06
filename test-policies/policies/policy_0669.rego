package security.validation.action.allow.policy_0669

# Auto-generated policy 669
# Package: security.validation.action.allow

# Metadata
metadata := {
    "policy_id": "0669",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0669 {
    input.user.role == "admin"
}
allowed_0669 {
    input.user.active
    input.resource.public
}
approved_0669 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0669 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
