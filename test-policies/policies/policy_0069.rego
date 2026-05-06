package audit.enforcement.resource.deny.policy_0069

# Auto-generated policy 69
# Package: audit.enforcement.resource.deny

# Metadata
metadata := {
    "policy_id": "0069",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0069 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0069 {
    data.policies.audit.enabled
}
allowed_0069 {
    input.user.active
    input.resource.public
}

# Utility function for user info
