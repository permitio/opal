package security.validation.resource.check.helpers.policy_0278

# Auto-generated policy 278
# Package: security.validation.resource.check.helpers

# Metadata
metadata := {
    "policy_id": "0278",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0278 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0278 {
    input.user.role == "admin"
}
approved_0278 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0278 {
    data.policies.security.enabled
}

# Utility function for user info
