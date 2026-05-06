package access.validation.policy.allow.policy_0513

# Auto-generated policy 513 (Rego v1 syntax)
# Package: access.validation.policy.allow

# Metadata
metadata := {
    "policy_id": "0513",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0513_allowed if {
    input.user.active
    input.resource.public
}
policy_0513_allowed if {
    data.policies.access.enabled
}
policy_0513_allowed if {
    input.user.role == "admin"
}
policy_0513_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
