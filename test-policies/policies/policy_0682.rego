package risk.validation.action.validate.helpers.policy_0682

# Auto-generated policy 682
# Package: risk.validation.action.validate.helpers

# Metadata
metadata := {
    "policy_id": "0682",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0682 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0682 {
    data.policies.risk.enabled
}
approved_0682 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
