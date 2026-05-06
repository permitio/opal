package governance.authorization.resource.validate.policy_0843

# Auto-generated policy 843
# Package: governance.authorization.resource.validate

# Metadata
metadata := {
    "policy_id": "0843",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0843 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0843 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0843 {
    data.policies.governance.enabled
}
allowed_0843 {
    input.user.active
    input.resource.public
}

# Utility function for user info
