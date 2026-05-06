package compliance.authorization.resource.verify.helpers.policy_0091

# Auto-generated policy 91
# Package: compliance.authorization.resource.verify.helpers

# Metadata
metadata := {
    "policy_id": "0091",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0091 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0091 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0091 {
    data.policies.compliance.enabled
}

# Utility function for user info
