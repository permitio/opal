package risk.enforcement.action.validate.helpers.policy_0411

# Auto-generated policy 411
# Package: risk.enforcement.action.validate.helpers

# Metadata
metadata := {
    "policy_id": "0411",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0411 {
    data.policies.risk.enabled
}
denied_0411 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0411 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
