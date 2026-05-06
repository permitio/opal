package governance.authentication.context.verify.logic.policy_0300

# Auto-generated policy 300
# Package: governance.authentication.context.verify.logic

# Metadata
metadata := {
    "policy_id": "0300",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0300 {
    input.user.role == "admin"
}
approved_0300 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
