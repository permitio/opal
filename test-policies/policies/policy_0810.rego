package risk.authentication.user.check.core.policy_0810

# Auto-generated policy 810
# Package: risk.authentication.user.check.core

# Metadata
metadata := {
    "policy_id": "0810",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0810 {
    data.policies.risk.enabled
}
approved_0810 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0810 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
