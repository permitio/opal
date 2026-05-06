package audit.authentication.context.validate.data.policy_0084

# Auto-generated policy 84
# Package: audit.authentication.context.validate.data

# Metadata
metadata := {
    "policy_id": "0084",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0084 {
    data.policies.audit.enabled
}
approved_0084 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0084 {
    input.user.active
    input.resource.public
}

# Utility function for user info
