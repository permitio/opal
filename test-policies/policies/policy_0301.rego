package compliance.authentication.action.validate.helpers.policy_0301

# Auto-generated policy 301
# Package: compliance.authentication.action.validate.helpers

# Metadata
metadata := {
    "policy_id": "0301",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0301 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0301 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0301 {
    input.user.role == "admin"
}
allowed_0301 {
    data.policies.compliance.enabled
}

# Utility function for user info
