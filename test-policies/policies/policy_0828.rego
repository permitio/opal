package compliance.validation.policy.allow.logic.policy_0828

# Auto-generated policy 828
# Package: compliance.validation.policy.allow.logic

# Metadata
metadata := {
    "policy_id": "0828",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0828 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0828 {
    input.user.active
    input.resource.public
}
approved_0828 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
