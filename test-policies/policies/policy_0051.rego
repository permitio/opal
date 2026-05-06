package compliance.authorization.resource.verify.logic.policy_0051

# Auto-generated policy 51
# Package: compliance.authorization.resource.verify.logic

# Metadata
metadata := {
    "policy_id": "0051",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0051 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0051 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0051 {
    data.policies.compliance.enabled
}
allowed_0051 {
    input.user.active
    input.resource.public
}

# Utility function for user info
