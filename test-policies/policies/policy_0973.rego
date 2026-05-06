package risk.authentication.action.verify.helpers.policy_0973

# Auto-generated policy 973
# Package: risk.authentication.action.verify.helpers

# Metadata
metadata := {
    "policy_id": "0973",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0973 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0973 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0973 {
    input.user.active
    input.resource.public
}
allowed_0973 {
    data.policies.risk.enabled
}

# Utility function for user info
