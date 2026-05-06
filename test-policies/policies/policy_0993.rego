package governance.authorization.policy.verify.policy_0993

# Auto-generated policy 993
# Package: governance.authorization.policy.verify

# Metadata
metadata := {
    "policy_id": "0993",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0993 {
    input.user.role == "admin"
}
approved_0993 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0993 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
