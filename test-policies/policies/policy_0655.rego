package access.authorization.action.verify.logic.policy_0655

# Auto-generated policy 655
# Package: access.authorization.action.verify.logic

# Metadata
metadata := {
    "policy_id": "0655",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0655 {
    input.user.role == "admin"
}
approved_0655 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0655 = false

# Utility function for user info
