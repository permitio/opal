package risk.authorization.context.verify.policy_0997

# Auto-generated policy 997
# Package: risk.authorization.context.verify

# Metadata
metadata := {
    "policy_id": "0997",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0997 {
    data.policies.risk.enabled
}
approved_0997 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0997 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
