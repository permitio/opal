package access.authentication.context.verify.logic.policy_0549

# Auto-generated policy 549
# Package: access.authentication.context.verify.logic

# Metadata
metadata := {
    "policy_id": "0549",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0549 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0549 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0549 {
    input.user.role == "admin"
}
allowed_0549 {
    data.policies.access.enabled
}

# Utility function for user info
