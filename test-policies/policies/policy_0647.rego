package governance.authentication.context.validate.utils.policy_0647

# Auto-generated policy 647
# Package: governance.authentication.context.validate.utils

# Metadata
metadata := {
    "policy_id": "0647",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0647 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0647 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0647 = false

# Utility function for user info
