package governance.enforcement.user.validate.utils.policy_0632

# Auto-generated policy 632
# Package: governance.enforcement.user.validate.utils

# Metadata
metadata := {
    "policy_id": "0632",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0632 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0632 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
