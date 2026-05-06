package risk.authentication.user.verify.core.policy_0147

# Auto-generated policy 147
# Package: risk.authentication.user.verify.core

# Metadata
metadata := {
    "policy_id": "0147",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0147 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0147 {
    input.user.active
    input.resource.public
}
allowed_0147 {
    data.policies.risk.enabled
}
approved_0147 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
