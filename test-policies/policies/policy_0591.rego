package access.authentication.policy.verify.policy_0591

# Auto-generated policy 591 (Rego v1 syntax)
# Package: access.authentication.policy.verify

# Metadata
metadata := {
    "policy_id": "0591",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0591_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0591_allowed if {
    input.user.active
    input.resource.public
}
policy_0591_allowed if {
    data.policies.access.enabled
}
