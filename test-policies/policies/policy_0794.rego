package audit.validation.action.allow.policy_0794

# Auto-generated policy 794
# Package: audit.validation.action.allow

# Metadata
metadata := {
    "policy_id": "0794",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0794 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0794 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
